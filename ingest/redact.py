"""Strip PII from statement text before it leaves this machine.

Kept: dates, amounts, merchant names, pay line items, the last 4 digits of
account numbers (needed to tell accounts apart).
Removed: names, addresses, SSNs, full account/card/routing numbers, emails,
phone numbers, and anything listed in data/pii.yaml.
"""

import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .paths import PII_FILE as PII_CONFIG

SSN = re.compile(r"\b\d{3}[- ]\d{2}[- ]\d{4}\b")
EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
PHONE = re.compile(r"(?<!\d)(?:\+?1[ .-]?)?\(?\d{3}\)?[ .-]\d{3}[ .-]\d{4}(?!\d)")
# 8+ digits, optionally grouped by single spaces or dashes: card, account,
# routing, loan and reference numbers. Amounts ("1,234.56") and dates never
# match because they contain commas, periods, or slashes.
LONG_NUMBER = re.compile(r"(?<![\d.,/])\d(?:[ -]?\d){7,}(?![\d.,/])")
# Horizontal whitespace only ([ \t]), so a match never spans two lines.
STREET = re.compile(
    r"(?<![\d/])\b\d{1,6}[ \t]+(?:[NSEW]\.?[ \t]+)?[A-Za-z0-9.' \t]{2,40}?[ \t]"
    r"(?:ST|STREET|AVE|AVENUE|RD|ROAD|DR|DRIVE|LN|LANE|CT|COURT|BLVD|WAY|CIR|CIRCLE|CV|COVE|PL|PLACE|PKWY|TER|TRL|HWY)\b"
    r"\.?(?:[ \t,]+(?:APT|UNIT|STE|#)[ \t]*[\w-]+)?",
    re.IGNORECASE,
)
CITY_STATE_ZIP = re.compile(r"\b[A-Z][A-Za-z .'-]{1,30},?[ \t]+[A-Z]{2}[ \t]+\d{5}(?:-\d{4})?\b")
PO_BOX = re.compile(r"\bP\.?\s*O\.?\s*BOX\s*\d+\b", re.IGNORECASE)


@dataclass
class RedactionReport:
    counts: Counter = field(default_factory=Counter)

    def summary(self) -> str:
        return ", ".join(f"{k}={v}" for k, v in sorted(self.counts.items())) or "nothing found"


def _mask_number(m: re.Match) -> str:
    digits = re.sub(r"\D", "", m.group())
    return f"[NUM ••{digits[-4:]}]"


def load_terms() -> list[str]:
    if not PII_CONFIG.exists():
        return []
    cfg = yaml.safe_load(PII_CONFIG.read_text()) or {}
    terms = []
    for key in ("names", "address_lines", "employer_ids", "extra_terms"):
        terms += [str(t).strip() for t in cfg.get(key) or [] if str(t).strip()]
    # Longest first so "Jane Q Doe" is removed before "Doe".
    return sorted(set(terms), key=len, reverse=True)


def redact(text: str, terms: list[str]) -> tuple[str, RedactionReport]:
    report = RedactionReport()

    def sub(pattern: re.Pattern, label: str, repl, s: str) -> str:
        s, n = pattern.subn(repl, s)
        report.counts[label] += n
        return s

    for term in terms:
        # Tolerate the variable spacing that layout-mode extraction produces.
        words = [re.escape(w) for w in term.split()]
        pattern = re.compile(r"\b" + r"\s+".join(words) + r"\b", re.IGNORECASE)
        text = sub(pattern, "custom_term", "[REDACTED]", text)

    text = sub(SSN, "ssn", "[SSN]", text)
    text = sub(EMAIL, "email", "[EMAIL]", text)
    text = sub(PHONE, "phone", "[PHONE]", text)
    text = sub(LONG_NUMBER, "account_number", _mask_number, text)
    text = sub(PO_BOX, "address", "[ADDRESS]", text)
    text = sub(STREET, "address", "[ADDRESS]", text)
    text = sub(CITY_STATE_ZIP, "address", "[ADDRESS]", text)
    report.counts = Counter({k: v for k, v in report.counts.items() if v})
    return text, report
