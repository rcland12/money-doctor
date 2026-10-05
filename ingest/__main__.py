"""Money Doctor document ingest.

  python -m ingest run          # parse + summarize: the usual monthly command
  python -m ingest parse        # BoA CSVs and pay statements, exact and local (no model)
  python -m ingest redact       # other PDFs -> redacted text, local, for review
  python -m ingest extract      # redacted text -> JSON via a model (--backend)
  python -m ingest categorize   # list merchants that still need a category
  python -m ingest summarize    # -> data/ingest/summary.md + intake-draft.yaml

Drop files anywhere under inbox/. Re-running is safe: results are cached and
transactions from overlapping files are de-duplicated.
"""

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import yaml

from . import boa_csv, boa_statement, household, llm, paystub, rules, validate
from .paths import DATA_DIR, INBOX_DIR, OUT_DIR, ROOT
from .pdftext import pdf_to_text
from .redact import PII_CONFIG, load_terms, redact
from .schemas import DocumentExtraction
from .store import load_docs as _load_docs
from .summarize import all_transactions, build

INBOX = INBOX_DIR
OUT = OUT_DIR
REDACTED = OUT / "redacted"
EXTRACTED = OUT / "extracted"


def _show(p: Path) -> str:
    """A short path for messages; absolute when outside the project (e.g. in Docker)."""
    return str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p)


def _slug(path: Path) -> str:
    return str(path.relative_to(INBOX).with_suffix("")).replace("/", "__")


def _files(*suffixes: str) -> list[Path]:
    return sorted(p for p in INBOX.rglob("*") if p.is_file() and p.suffix.lower() in suffixes)


def _save(name: str, doc: DocumentExtraction, backend: str, digest: str, problems: list[str]) -> None:
    EXTRACTED.mkdir(parents=True, exist_ok=True)
    (EXTRACTED / f"{name}.json").write_text(json.dumps(
        {"hash": digest, "backend": backend, "problems": problems, "doc": doc.model_dump()}, indent=1))


def _cached(name: str, digest: str) -> bool:
    out = EXTRACTED / f"{name}.json"
    return out.exists() and json.loads(out.read_text()).get("hash") == digest


def _digest(path: Path, salt: str = "") -> str:
    return hashlib.sha256(salt.encode() + path.read_bytes()).hexdigest()[:16]


def cmd_parse(args) -> int:
    counts: Counter = Counter()
    for f in _files(".csv"):
        if not boa_csv.is_boa_csv(f):
            print(f"skip (unknown CSV format): {f.relative_to(INBOX)}")
            continue
        digest = _digest(f, "boa_csv-v4")
        if _cached(_slug(f), digest) and not args.force:
            counts["cached"] += 1
            continue
        statement, problems = boa_csv.parse(f)
        doc = DocumentExtraction(doc_type="account_statement", statement=statement, notes="")
        problems += validate.check(doc)
        _save(_slug(f), doc, "boa_csv", digest, problems)
        counts["csv"] += 1
        for p in problems:
            print(f"  {f.relative_to(INBOX)}: {p}")
    for f in _files(".pdf"):
        digest = _digest(f, "pdf-v2")
        if _cached(_slug(f), digest) and not args.force:
            counts["cached"] += 1
            continue
        if paystub.matches(f):
            doc = DocumentExtraction(doc_type="pay_statement", pay=paystub.parse(f), notes="")
            backend, kind = "paystub", "pay"
        elif boa_statement.is_statement(f):
            doc = DocumentExtraction(doc_type="account_statement", statement=boa_statement.parse(f), notes="")
            backend, kind = "boa_statement", "statement"
        else:
            continue
        problems = validate.check(doc)
        _save(_slug(f), doc, backend, digest, problems)
        counts[kind] += 1
        for p in problems:
            print(f"  {f.relative_to(INBOX)}: {p}")
    sheets = sorted(INBOX.glob("household/*.xlsx"), key=lambda p: p.stat().st_mtime)
    if sheets:  # the newest export is the whole truth; older ones are ignored
        (OUT / "household.json").write_text(json.dumps(household.parse(sheets[-1]), indent=1))
        counts["household"] += 1
    print(f"parsed {counts['csv']} CSVs, {counts['pay']} pay statements, {counts['statement']} card statements, {counts['household']} household sheet "
          f"({counts['cached']} unchanged)")
    return 0


def _needs_model(f: Path) -> bool:
    return (f.suffix.lower() == ".pdf" and not (EXTRACTED / f"{_slug(f)}.json").exists()
            and not paystub.matches(f) and not boa_statement.is_statement(f))


def cmd_redact(args) -> int:
    pdfs = [f for f in _files(".pdf") if _needs_model(f)]
    if not pdfs:
        print("No PDFs need a model; everything was handled by `parse`.")
        return 0
    terms = load_terms()
    if not terms:
        print(f"warning: {PII_CONFIG.name} missing or empty; your name and address won't be removed "
              f"unless they match the generic patterns. Copy ingest/pii.example.yaml to data/pii.yaml.\n")
    REDACTED.mkdir(parents=True, exist_ok=True)
    for pdf in pdfs:
        text, warnings = pdf_to_text(pdf)
        clean, report = redact(text, terms)
        if not clean.replace("=", "").replace("PAGE", "").strip(" 0123456789\n"):
            print(f"{pdf.relative_to(INBOX)}: no text layer (a screenshot or scan). Install tesseract-ocr, "
                  "or enter its numbers in the intake form.")
            continue
        (REDACTED / f"{_slug(pdf)}.txt").write_text(clean)
        print(f"{pdf.relative_to(INBOX)}: {report.summary()}")
        for w in warnings:
            print(f"    {w}")
    print(f"\nReview {_show(REDACTED)}/ before running extract. Nothing has left this machine.")
    return 0


def cmd_extract(args) -> int:
    files = sorted(REDACTED.glob("*.txt")) if REDACTED.exists() else []
    if not files:
        print("Nothing to extract; run `python -m ingest redact` first.")
        return 0
    extract = llm.BACKENDS[args.backend]
    failures = 0
    for f in files:
        text = f.read_text()
        digest = hashlib.sha256(f"{args.backend}:{llm.backend_model(args.backend)}:{text}".encode()).hexdigest()[:16]
        if _cached(f.stem, digest) and not args.force:
            print(f"{f.stem}: cached")
            continue
        print(f"{f.stem}: extracting with {args.backend}...", flush=True)
        try:
            doc = extract(text)
        except Exception as e:  # keep going; one bad PDF shouldn't stop the batch
            failures += 1
            print(f"    FAILED: {e}")
            continue
        problems = validate.check(doc)
        _save(f.stem, doc, args.backend, digest, problems)
        print(f"    {doc.doc_type}; " + ("; ".join(problems) if problems else "checks pass"))
    return 1 if failures else 0


def cmd_categorize(args) -> int:
    stmts = [d.statement for _, d, _ in _load_docs() if d.statement]
    totals: dict[str, float] = defaultdict(float)
    examples: dict[str, str] = {}
    for _, t, c in all_transactions(stmts):
        if c == "other" and rules.categorize(t.description)[1] == "none":
            k = rules.merchant_key(t.description)
            totals[k] += t.amount
            examples.setdefault(k, t.description[:60])
    if not totals:
        print("Every merchant has a category.")
        return 0
    print(f"{len(totals)} merchants without a category. Add lines like `KEY: category` to "
          f"{_show(rules.PERSONAL_RULES)}:\n")
    for k, v in sorted(totals.items(), key=lambda kv: kv[1]):
        print(f"  {v:10.2f}  {k:<32} {examples[k]}")
    return 0


def cmd_summarize(args) -> int:
    docs = _load_docs()
    if not docs:
        print("Nothing parsed yet; run `python -m ingest parse`.")
        return 1
    house = OUT / "household.json"
    settings = DATA_DIR / "settings.yaml"
    me = (yaml.safe_load(settings.read_text()) or {}).get("household_me") if settings.exists() else None
    lines = household.summary(json.loads(house.read_text()), me) if house.exists() else None
    md, draft = build(docs, lines)
    (OUT / "summary.md").write_text(md)
    (OUT / "intake-draft.yaml").write_text(yaml.safe_dump(draft, sort_keys=False, allow_unicode=True))
    if not args.quiet:
        print(md)
    print(f"Wrote {_show(OUT / 'summary.md')} and {_show(OUT / 'intake-draft.yaml')}")
    return 0


def cmd_run(args) -> int:
    cmd_parse(args)
    if any(_needs_model(f) for f in _files(".pdf")):
        print("Some PDFs aren't BoA CSVs or pay statements; run `redact` then `extract` for those.")
    return cmd_summarize(args)


def main() -> int:
    ap = argparse.ArgumentParser(prog="python -m ingest", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn, help_ in (("run", cmd_run, "parse + summarize"), ("parse", cmd_parse, "CSVs and pay statements, no model")):
        p = sub.add_parser(name, help=help_)
        p.add_argument("--force", action="store_true", help="re-parse unchanged files")
        p.add_argument("--quiet", action="store_true", help="don't print the summary")
        p.set_defaults(fn=fn)
    sub.add_parser("redact", help="other PDFs -> redacted text (local)").set_defaults(fn=cmd_redact)
    ex = sub.add_parser("extract", help="redacted text -> JSON via a model")
    ex.add_argument("--backend", choices=list(llm.BACKENDS), default="claude-code")
    ex.add_argument("--force", action="store_true", help="ignore cached results")
    ex.set_defaults(fn=cmd_extract)
    sub.add_parser("categorize", help="list merchants without a category").set_defaults(fn=cmd_categorize)
    sm = sub.add_parser("summarize", help="combine everything")
    sm.add_argument("--quiet", action="store_true")
    sm.set_defaults(fn=cmd_summarize)
    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
