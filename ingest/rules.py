"""Transaction categorization: your rules first, then built-in rules, then
whatever a model guessed, then "other".

Your rules live in data/merchant-rules.yaml (git-ignored) as
`MERCHANT KEY: category`. Run `python -m ingest categorize` to see the keys
that still need one. For local businesses and your employer's payroll, use
regexes in data/merchant-patterns.yaml (also git-ignored), a list of
`{match: REGEX, category: ...}`; add `salary: true` to mark your paycheck."""

import re
from functools import lru_cache
from pathlib import Path
from typing import get_args

import yaml

from .schemas import Category

from .paths import DATA_DIR

PERSONAL_RULES = DATA_DIR / "merchant-rules.yaml"
OVERRIDES = DATA_DIR / "transaction-overrides.yaml"
PERSONAL_PATTERNS = DATA_DIR / "merchant-patterns.yaml"
CATEGORIES = set(get_args(Category))

# First match wins, so money-movement rules come before merchant rules.
BUILTIN: list[tuple[str, str]] = [
    (r"INTEREST CHARGED|LATE FEE|ANNUAL FEE|OVERDRAFT|FOREIGN TRANSACTION FEE|MONTHLY MAINTENANCE FEE", "fees_interest"),
    (r"TRANSFER (TO|FROM) (SAV|CHK)|ONLINE BANKING TRANSFER|ONLINE SCHEDULED TRANSFER|KEEP THE CHANGE", "transfer_internal"),
    (r"PAYMENT (TO|FROM) (CRD|CHK)|ONLINE PAYMENT FROM CHK|PAYMENT - THANK YOU|APPLECARD GSBANK|DES:AUTO ?LOAN|LOAN PMT|DES:(CRCARDPMT|EPAY|PAYMENT)\b", "debt_payment"),
    (r"DES:PAYROLL|DIRECT DEP|DES:CASHREWARD|CASH REWARDS STATEMENT CREDIT|IRS TREAS|TAX ?REF|TAXRFD|INTEREST EARNED", "income"),
    (r"PAYPAL.*(PAY ?MONTHLY|INST|LOAN|PAY IN 4)|AFFIRM|KLARNA|AFTERPAY", "installment_plan"),
    (r"DES:RENT\b", "rent_housing"),
    (r"IRS DES:USATAXPYMT|TURBOTAX|H&R BLOCK", "taxes"),
    (r"ALPACA SECURITIE|ROBINHOOD|FIDELITY|VANGUARD|SCHWAB|E\*TRADE|MERRILL|COINBASE", "investing"),
    (r"\bATM\b|WITHDRWL|CASH WITHDRAWAL", "cash_atm"),
    (r"NETFLIX|SPOTIFY|HULU|DISNEY ?PLUS|DISNEYPLUS|APPLE\.COM/BILL|YOUTUBE|MAX\.COM|HBO ?MAX|PARAMOUNT|PEACOCK|CHATGPT|OPENAI|ANTHROPIC|CLAUDE\.AI|PATREON|XBOX|PLAYSTATION|NINTENDO|AUDIBLE|ICLOUD|DROPBOX|ADOBE|PRIME VIDEO|AMAZON PRIME|SIRIUSXM", "subscriptions"),
    (r"VERIZON|AT&T|ATT\*|T-MOBILE|TMOBILE|XFINITY|COMCAST|SPECTRUM|COX COMM|GOOGLE ?FI|MINT MOBILE|VISIBLE", "phone_internet"),
    (r"ELECTRIC|WATER ?(DEPT|AUTH|WORKS)|ENERGY|POWER CO|NATURAL GAS|UTILIT", "utilities"),
    (r"GEICO|PROGRESSIVE|STATE FARM|ALLSTATE|LIBERTY MUTUAL|INSURANCE|LEMONADE", "insurance"),
    (r"MARATHON|RACEWAY|SUNOCO|BUC-EE|MURPHY ?\d*(USA|EXP|ATWAL)|SHELL OIL|\bSHELL\b|CHEVRON|EXXON|MOBIL\b|\bBP\b|CIRCLE ?K|TEXACO|VALERO|AMOCO|QUIKTRIP|\bQT\b|RACETRAC|RACE TRAC|SPEEDWAY|WAWA|PILOT|LOVE'?S TRAVEL|\bUBER\b(?! ?EATS)|LYFT|PARKING|TOLL", "gas_transport"),
    (r"DOORDASH|UBER ?EATS|GRUBHUB|MCDONALD|SONIC DRIVE|CHICK-FIL|CHICKFIL|WENDY|TACO BELL|BURGER KING|STARBUCKS|DUNKIN|CHIPOTLE|SUBWAY|DOMINO|PIZZA|POPEYES|ARBY|CRACKER BARREL|WHATABURGER|DAIRY QUEEN|FIVE GUYS|5 ?GUYS|LITTLE CAESARS|KRISPY KREME|DUTCH BROS|HARDEE|STEAK N SHAKE|TAQUERIA|CRUMBL|PANERA|JERSEY MIKE|WINGSTOP|RAISING CANE|CULVER|KFC|JACK IN THE BOX|IHOP|APPLEBEE|CHILI'?S|OLIVE GARDEN|TEXAS ROADHOUSE|BUFFALO WILD|WINGS|RESTAURANT|GRILL|CAFE|COFFEE|BAR ?& ?GRILL|TST\*|SQ \*.*(CAFE|COFFEE|GRILL|KITCHEN)", "dining"),
    (r"KROGER|PUBLIX|ALDI|WALMART SUPERCENTER|WAL-MART|WM SUPERCENTER|FOOD LION|HARRIS TEETER|SAFEWAY|WHOLE FOODS|TRADER JOE|COSTCO|SAM'?S ?CLUB|LIDL|GROCERY|MARKET ?BASKET", "groceries"),
    (r"INTEREST REF", "fees_interest"),
    (r"CVS|WALGREENS|PHARMACY|MEDICAL|DENTAL|HOSPITAL|CLINIC|URGENT ?CARE|DOCTOR|OPTOMETR|LABCORP|QUEST DIAG", "health_medical"),
    (r"GREAT CLIPS|SPORT ?CLIPS|SALON|BARBER", "personal_care"),
    (r"PETSMART|PETCO|CHEWY|VETERINAR|ANIMAL HOSP", "pets"),
    (r"AUTOZONE|O'?REILLY|ADVANCE AUTO|JIFFY LUBE|VALVOLINE|TIRE|CAR ?WASH|TAKE 5 OIL|DMV", "auto"),
    (r"\bAMC\b|REGAL|CINEMA|THEATRE|THEATER|STEAM ?GAMES|STEAMPOWERED|TICKETMASTER|BOWL|TOP GOLF|TOPGOLF|DAVE ?& ?BUSTER", "entertainment_leisure"),
    (r"AIRLINE|DELTA AIR|SOUTHWEST|AMERICAN AIR|UNITED AIR|HOTEL|MARRIOTT|HILTON|AIRBNB|EXPEDIA", "travel"),
    (r"AMAZON|AMZN|TARGET|BEST BUY|HOME DEPOT|LOWE'?S|EBAY|ETSY|TEMU|SHEIN|DOLLAR GENERAL|DOLLAR TREE|FAMILY DOLLAR|FIVE BELOW|ROSS|TJ ?MAXX|MARSHALLS|WALMART|WAL-MART|WM\.COM", "shopping"),
]
BUILTIN_RE = [(re.compile(p, re.IGNORECASE), c) for p, c in BUILTIN]

FILLER = {"PURCHASE", "DEBIT", "CARD", "CHECKCARD", "POS", "RECURRING", "ONLINE", "PMT", "WEB", "PPD", "CCD", "MOBILE", "THE"}


SALARY = re.compile(r"DES:PAYROLL|DIRECT DEP|PAYROLL", re.IGNORECASE)


def personal_patterns() -> list[tuple[re.Pattern, str, bool]]:
    """(regex, category, is salary) from data/merchant-patterns.yaml, reloaded when the file changes."""
    return _patterns(PERSONAL_PATTERNS.stat().st_mtime if PERSONAL_PATTERNS.exists() else 0)


@lru_cache(maxsize=1)
def _patterns(_mtime: float) -> list[tuple[re.Pattern, str, bool]]:
    if not PERSONAL_PATTERNS.exists():
        return []
    out = []
    for r in yaml.safe_load(PERSONAL_PATTERNS.read_text()) or []:
        if r["category"] not in CATEGORIES:
            raise ValueError(f"{PERSONAL_PATTERNS.name}: unknown category {r['category']!r}")
        out.append((re.compile(r["match"], re.IGNORECASE), r["category"], bool(r.get("salary"))))
    return out


def is_salary(description: str) -> bool:
    return bool(SALARY.search(description)) or any(s and rx.search(description) for rx, _, s in personal_patterns())


def merchant_key(description: str) -> str:
    """A short, stable name for grouping: 'NETFLIX.COM 866-579 CA 08/14' -> 'NETFLIX COM'."""
    s = description.upper()
    m = re.match(r"(ZELLE|VENMO|CASH APP|PAYPAL) (?:PAYMENT|TRANSFER) (TO|FROM) (.+?)(?: FOR |;| CONF#|$)", s)
    if m:  # person-to-person: one key per person and direction
        return f"{m.group(1)} {m.group(2)} {m.group(3).strip()}"
    s = s.split(" DES:")[0]                      # ACH: company name comes before DES:
    s = re.sub(r"\[[^\]]*\]", " ", s)             # redaction tokens
    s = re.sub(r"\d\d/\d\d", " ", s)              # embedded dates
    s = re.sub(r"[^A-Z&' ]+", " ", s)             # digits, #, *, punctuation
    words = [w for w in s.split() if len(w) > 1 and w not in FILLER]
    return " ".join(words[:3]) or description.upper()[:24]


@lru_cache(maxsize=1)
def personal_rules() -> dict[str, str]:
    if not PERSONAL_RULES.exists():
        return {}
    rules = yaml.safe_load(PERSONAL_RULES.read_text()) or {}
    bad = {k: v for k, v in rules.items() if v not in CATEGORIES}
    if bad:
        raise ValueError(f"{PERSONAL_RULES.name}: unknown categories {bad}; allowed: {sorted(CATEGORIES)}")
    return {k.upper(): v for k, v in rules.items()}


@lru_cache(maxsize=1)
def overrides() -> dict[tuple[str, float], list[tuple[str, str]]]:
    """(date, amount) -> [(text that must appear in the description, category)]."""
    if not OVERRIDES.exists():
        return {}
    out: dict[tuple[str, float], list[tuple[str, str]]] = {}
    for o in yaml.safe_load(OVERRIDES.read_text()) or []:
        if o["category"] not in CATEGORIES:
            raise ValueError(f"{OVERRIDES.name}: unknown category {o['category']!r}")
        out.setdefault((str(o["date"]), round(float(o["amount"]), 2)), []).append((str(o.get("match", "")).upper(), o["category"]))
    return out


def categorize(description: str, model_guess: str | None = None, when: str | None = None,
               amount: float | None = None) -> tuple[str, str]:
    """Return (category, source): override | personal | builtin | model | none."""
    if when is not None and amount is not None:
        for match, category in overrides().get((when, round(amount, 2)), []):
            if match in description.upper():
                return category, "override"
    key = merchant_key(description)
    if key in personal_rules():
        return personal_rules()[key], "personal"
    for pattern, category, _ in personal_patterns():
        if pattern.search(description):
            return category, "personal"
    for pattern, category in BUILTIN_RE:
        if pattern.search(description):
            return category, "builtin"
    if model_guess and model_guess != "other":
        return model_guess, "model"
    return "other", "none"
