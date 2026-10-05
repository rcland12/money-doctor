"""Reads what parse/extract saved under data/ingest/extracted/."""

import json
from pathlib import Path

from .paths import OUT_DIR
from .schemas import DocumentExtraction

EXTRACTED = OUT_DIR / "extracted"


def load_docs(extracted: Path = EXTRACTED) -> list[tuple[str, DocumentExtraction, list[str]]]:
    loaded = []
    for f in sorted(extracted.glob("*.json")) if extracted.exists() else []:
        data = json.loads(f.read_text())
        loaded.append((f.stem, DocumentExtraction.model_validate(data["doc"]), data["problems"], data["backend"]))
    # Where an account has CSV exports, those are the transaction record; its
    # statement PDFs only contribute balances and terms (APR, minimum, limit).
    csv_accounts = {d.statement.account_last4 for _, d, _, b in loaded if d.statement and b == "boa_csv"}
    for _, d, _, backend in loaded:
        if d.statement and backend != "boa_csv" and d.statement.account_last4 in csv_accounts:
            d.statement.transactions = []
    return [(name, d, problems) for name, d, problems, _ in loaded]
