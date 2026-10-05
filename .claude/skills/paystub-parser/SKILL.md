---
name: paystub-parser
description: Write an exact parser for someone's pay statement PDFs (ingest/paystub_local.py, git-ignored) so pay, deductions and leave are read without a model. Use when they upload pay statements, the Income page is empty or wrong, or they change employers.
---

# Pay statement parser

Every employer's pay statement looks different, so the parser is personal:
`ingest/paystub_local.py`, git-ignored. `ingest/paystub.py` loads it if it
exists. Without it, pay PDFs go to the model extractor (if
`MD_EXTRACT_BACKEND` is set) or are skipped.

## Steps

1. **Samples.** Ask for two or three recent statements (ideally one with
   overtime or a bonus). They're usually in `inbox/pay/` once uploaded. Read
   the text the way the parser will:
   `python -c "from pathlib import Path; from ingest.pdftext import pdf_to_text; print(pdf_to_text(Path('inbox/pay/<file>.pdf'))[0])"`
2. **Target.** Read `PayStatement` and its parts (`EarningLine`,
   `DeductionLine`, `LeaveBalance`, `EmployerContribution`) in
   `ingest/schemas.py`. Required: `gross_pay`, `net_pay`, `earnings`,
   `deductions`, `leave` (empty list if none). Current-period amounts only, not
   year-to-date.
3. **Write** `ingest/paystub_local.py`:

   ```python
   """Pay statement parser for <employer> (personal, git-ignored)."""
   from pathlib import Path
   from .pdftext import pdf_to_text   # (text, warnings); OCRs pages with no text
   from .schemas import PayStatement

   def matches(pdf: Path) -> bool:
       ...  # cheap and specific: a phrase only this layout has

   def parse(pdf: Path) -> PayStatement:
       ...
   ```

   Anchor regexes on labels, not positions. Amounts: strip `$` and commas;
   watch for negatives in parentheses.
4. **Test** on every sample: gross minus deductions must equal net (within a
   cent), dates must be YYYY-MM-DD, and `matches()` must be False for a bank
   statement. Print each result and compare with the PDF together.
5. **Use it.** `python -m ingest run` from the checkout, or rebuild the image
   (`docker compose up -d --build`; the file is copied in at build) and
   re-upload or reload. Check the Income page.

Also add their paycheck deposit to `data/merchant-patterns.yaml` with
`salary: true`, so deposits are counted as pay.

## Privacy

The file names their employer and its layout. It stays git-ignored: never
move it into a tracked file, and keep `matches()` phrases out of anything public.
