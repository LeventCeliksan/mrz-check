"""Parse ICAO 9303 machine-readable zones (TD1 ID cards, TD2, TD3 passports) and validate every check digit."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

_VALID = re.compile(r"^[A-Z0-9<]+$")
_WEIGHTS = (7, 3, 1)


def char_value(c: str) -> int:
    if c.isdigit():
        return int(c)
    if c == "<":
        return 0
    if "A" <= c <= "Z":
        return ord(c) - 55
    raise ValueError(f"invalid MRZ character {c!r}")


def check_digit(data: str) -> str:
    """ICAO 9303 check digit: weights 7-3-1 repeating, sum mod 10."""
    return str(sum(char_value(c) * _WEIGHTS[i % 3] for i, c in enumerate(data)) % 10)


@dataclass
class Check:
    field: str
    data: str
    expected: str
    found: str

    @property
    def ok(self) -> bool:
        return self.expected == self.found


@dataclass
class MRZResult:
    format: str
    document_type: str
    issuing_country: str
    surname: str
    given_names: str
    document_number: str
    nationality: str
    birth_date: date | None
    sex: str
    expiry_date: date | None
    optional_data: str
    checks: list[Check] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.errors and all(c.ok for c in self.checks)

    def is_expired(self, today: date | None = None) -> bool | None:
        if self.expiry_date is None:
            return None
        return self.expiry_date < (today or date.today())


def normalize(lines) -> list[str]:
    if isinstance(lines, str):
        lines = lines.splitlines()
    return [re.sub(r"\s+", "", ln).upper() for ln in lines if ln.strip()]


def detect_format(lines: list[str]) -> str:
    lengths = [len(ln) for ln in lines]
    if lengths == [30, 30, 30]:
        return "TD1"
    if lengths == [36, 36]:
        return "TD2"
    if lengths == [44, 44]:
        return "TD3"
    raise ValueError(f"unrecognized MRZ layout: {len(lines)} lines of lengths {lengths} "
                     "(expected TD1 3x30, TD2 2x36 or TD3 2x44)")


def _date(yymmdd: str, *, is_expiry: bool, today: date) -> date | None:
    if not yymmdd.isdigit():
        return None
    yy, mm, dd = int(yymmdd[:2]), int(yymmdd[2:4]), int(yymmdd[4:])
    if is_expiry:
        year = 2000 + yy  # documents valid today expire this century
    else:
        year = 2000 + yy if 2000 + yy <= today.year else 1900 + yy
    try:
        return date(year, mm, dd)
    except ValueError:
        return None


def _names(field_: str) -> tuple[str, str]:
    surname, _, given = field_.partition("<<")
    clean = lambda s: " ".join(p for p in s.split("<") if p)
    return clean(surname), clean(given)


def _doc_number(number: str, check: str, optional: str) -> tuple[str, str, str, str]:
    """Handle long document numbers: '<' in the check position means the number continues in optional data."""
    if check == "<" and optional:
        rest = optional.split("<", 1)[0]
        if len(rest) >= 2:
            return number + rest[:-1], number + rest[:-1], rest[-1], optional[len(rest):]
    return number.rstrip("<"), number, check, optional


def parse(mrz, today: date | None = None) -> MRZResult:
    today = today or date.today()
    lines = normalize(mrz)
    fmt = detect_format(lines)
    errors = [f"line {i + 1} has invalid characters" for i, ln in enumerate(lines) if not _VALID.match(ln)]
    checks: list[Check] = []

    if fmt == "TD1":
        l1, l2, l3 = lines
        doc_type, country = l1[0:2], l1[2:5]
        number, number_data, number_cd, opt1 = _doc_number(l1[5:14], l1[14], l1[15:30])
        dob, dob_cd, sex, exp, exp_cd, nat, opt2 = l2[0:6], l2[6], l2[7], l2[8:14], l2[14], l2[15:18], l2[18:29]
        surname, given = _names(l3)
        composite_data, composite_cd = l1[5:30] + l2[0:7] + l2[8:15] + l2[18:29], l2[29]
        optional = (opt1 + opt2).strip("<")
    else:
        l1, l2 = lines
        name_end = 36 if fmt == "TD2" else 44
        doc_type, country = l1[0:2], l1[2:5]
        surname, given = _names(l1[5:name_end])
        number, number_data, number_cd = l2[0:9].rstrip("<"), l2[0:9], l2[9]
        nat, dob, dob_cd, sex, exp, exp_cd = l2[10:13], l2[13:19], l2[19], l2[20], l2[21:27], l2[27]
        if fmt == "TD3":
            opt, opt_cd = l2[28:42], l2[42]
            optional = opt.strip("<")
            # Personal number check digit may be '<' when the field is empty.
            if not (opt_cd == "<" and not optional):
                checks.append(Check("personal_number", opt, check_digit(opt), opt_cd))
            composite_data, composite_cd = l2[0:10] + l2[13:20] + l2[21:43], l2[43]
        else:
            opt = l2[28:35]
            if l2[9] == "<" and opt.strip("<"):
                number, number_data, number_cd, _ = _doc_number(l2[0:9], "<", opt)
            optional = opt.strip("<")
            composite_data, composite_cd = l2[0:10] + l2[13:20] + l2[21:35], l2[35]

    checks[0:0] = [
        Check("document_number", number_data, check_digit(number_data), number_cd),
        Check("birth_date", dob, check_digit(dob), dob_cd),
        Check("expiry_date", exp, check_digit(exp), exp_cd),
    ]
    checks.append(Check("composite", composite_data, check_digit(composite_data), composite_cd))

    birth, expiry = _date(dob, is_expiry=False, today=today), _date(exp, is_expiry=True, today=today)
    if birth is None:
        errors.append("birth date is not a valid date")
    if expiry is None:
        errors.append("expiry date is not a valid date")
    if sex not in "MFX<":
        errors.append(f"invalid sex field {sex!r}")

    return MRZResult(fmt, doc_type.rstrip("<"), country.rstrip("<"), surname, given, number, nat.rstrip("<"),
                     birth, "X" if sex == "<" else sex, expiry, optional, checks, errors)
