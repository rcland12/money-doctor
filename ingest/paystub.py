"""Pay statements. Every employer's layout is different, so the exact parser
is yours: put it in ingest/paystub_local.py (git-ignored) with

    def matches(pdf: Path) -> bool         # is this one of my pay statements?
    def parse(pdf: Path) -> PayStatement   # see schemas.PayStatement

Without one, pay statement PDFs go through redact + extract like any other PDF."""

from pathlib import Path

from .schemas import PayStatement

try:
    from . import paystub_local as _local
except ImportError:
    _local = None


def matches(pdf: Path) -> bool:
    return _local is not None and _local.matches(pdf)


def parse(pdf: Path) -> PayStatement:
    return _local.parse(pdf)
