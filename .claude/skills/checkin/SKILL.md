---
name: checkin
description: Check in on someone's Money Doctor budget - how this month is going line by line, whether the debt payoff is on track, what changed, and what to adjust. Use for "how am I doing", a monthly review, after a big expense, or when they're over budget.
---

# Budget check-in

Read-only until they agree to a change. Run the commands inside the container
if the app runs in Docker (`docker compose exec money-doctor ...`).

## Gather

```bash
python -m app.digest          # today's morning email: spending room, bills due, debt progress
python -m app.check           # the plan's math: extra to debt, projected payoff vs target
```

For line-by-line numbers this month:

```bash
python -c "
from app import engine
d = engine.dashboard()
for l in d['lines']: print(f\"{l['name']:<24} {l['target']:>9.2f} {l['spent']:>9.2f} {l['remaining']:>9.2f}\")
p = d['projection']; print('payoff', p['done'], 'target', p['target'], 'on track', p['on_track'])
print('data current to', d['freshness'])
"
```

Also read `data/budget-plan.md` if it exists: it records what they decided
and why.

## Report

Short and plain, in this order:

1. **On track or not**: projected payoff month vs the target, and how that
   moved since the plan (or last check-in).
2. **This month**: lines over budget and by how much; lines with room left.
   Note if bank data lags (freshness): recent spending may be missing.
3. **What changed**: new recurring charges, balances that went up, income
   differences. Ask about anything unexplained instead of guessing.

## Adjust

Offer two or three concrete options with their effect, e.g. "cover the $120
over on dining from shopping this month" or "lower fun money by $50: payoff 1
month sooner". Let them pick. Then use the `budget` skill steps to edit,
check and (after asking) reload, and add a dated line to
`data/budget-plan.md` with what changed and why.

Don't judge spending, and don't push cuts to things they've said they keep.
