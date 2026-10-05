---
name: categorize
description: Teach Money Doctor merchants it doesn't recognize - find transactions stuck in "other", propose categories, and write them to data/merchant-rules.yaml or merchant-patterns.yaml. Use when spending lands in the wrong budget line or "other" keeps growing.
---

# Categorize merchants

Order of rules (first match wins): `data/transaction-overrides.yaml` (one
transaction) -> `data/merchant-rules.yaml` (exact merchant key) ->
`data/merchant-patterns.yaml` (regex) -> built-in rules in `ingest/rules.py`
-> `other`. Categories are the `Category` list in `ingest/schemas.py`.

Run commands inside the container if the app runs in Docker
(`docker compose exec money-doctor ...`).

## Find them

From uploaded statements and CSVs:

```bash
python -m ingest categorize
```

From bank sync, emails and Shortcuts (these live only in the database):

```bash
python -c "
from collections import Counter
from sqlalchemy import select
from app.models import Session, Txn
from ingest.rules import merchant_key
with Session() as s:
    rows = s.scalars(select(Txn).where(Txn.category == 'other', Txn.superseded_by.is_(None))).all()
c = Counter(merchant_key(t.description) for t in rows)
for k, n in c.most_common(60): print(n, k)
"
```

## Propose, then write

Group them into a table: merchant key, an example description, total,
proposed category. Ask about anything ambiguous (a person's name on a Zelle or
Venmo payment could be rent, a payback or a gift). After they confirm:

- Same text every time: `data/merchant-rules.yaml`, `MERCHANT KEY: category`.
- Text that varies (store numbers, dates): `data/merchant-patterns.yaml`,
  `- {match: "REGEX", category: dining}`. Their paycheck deposit gets
  `salary: true`.
- One odd transaction: `data/transaction-overrides.yaml`,
  `{date, amount, match, category}`.

Keep local businesses and employers in these personal files, never in
`ingest/rules.py` (the repo is public).

## Apply

Reload (Settings -> Reload budget & re-import, after asking). That
re-categorizes transactions from uploaded files. Bank sync and email
transactions keep the category they arrived with; only new ones follow the
new rules. For old ones that matter this month, they can change the category
on the Transactions page.

If a merchant is right but lands on the wrong budget line, the fix is in
`data/budget.yaml` instead: `match` on the line, or adjust `tracks`.
