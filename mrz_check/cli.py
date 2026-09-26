"""mrz-check CLI: validate an MRZ passed as arguments (one per line) or on stdin."""
import argparse
import json
import sys
from dataclasses import asdict

from .core import parse


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="mrz-check", description="Validate ICAO 9303 MRZ check digits (TD1, TD2, TD3). Runs fully offline.")
    p.add_argument("lines", nargs="*", help="MRZ lines; read from stdin if omitted")
    p.add_argument("--json", action="store_true", help="print the parsed result as JSON")
    a = p.parse_args(argv)

    text = "\n".join(a.lines) if a.lines else sys.stdin.read()
    try:
        r = parse(text)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2

    if a.json:
        d = asdict(r)
        d["valid"], d["expired"] = r.valid, r.is_expired()
        for c, raw in zip(d["checks"], r.checks):
            c["ok"] = raw.ok
        print(json.dumps(d, default=str, indent=2))
    else:
        print(f"{r.format} {r.document_type} {r.issuing_country}  {r.surname}, {r.given_names}")
        print(f"document {r.document_number}  nationality {r.nationality}  born {r.birth_date}  sex {r.sex}  expires {r.expiry_date}"
              + ("  (EXPIRED)" if r.is_expired() else ""))
        for c in r.checks:
            print(f"  {'OK ' if c.ok else 'BAD'} {c.field:<16} expected {c.expected} found {c.found}")
        for e in r.errors:
            print(f"  BAD {e}")
        print("VALID" if r.valid else "INVALID")
    return 0 if r.valid else 1


if __name__ == "__main__":
    sys.exit(main())
