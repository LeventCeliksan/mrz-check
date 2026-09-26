"""Offline ICAO 9303 MRZ parser and check-digit validator (TD1, TD2, TD3)."""
from .core import Check, MRZResult, check_digit, parse

__all__ = ["parse", "check_digit", "MRZResult", "Check"]
