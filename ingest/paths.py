"""Where the ingest reads and writes. The app sets the same env vars, so both
agree when running in Docker with a mounted data volume."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("MD_DATA_DIR", ROOT / "data")).resolve()
INBOX_DIR = Path(os.environ.get("MD_INBOX_DIR", ROOT / "inbox")).resolve()
OUT_DIR = DATA_DIR / "ingest"
# Personal redaction terms: data/pii.yaml, or the older ingest/pii.yaml.
PII_FILE = next((p for p in (DATA_DIR / "pii.yaml", ROOT / "ingest" / "pii.yaml") if p.exists()), DATA_DIR / "pii.yaml")
