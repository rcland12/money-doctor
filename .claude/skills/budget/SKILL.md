---
name: budget
description: Build or change someone's Money Doctor budget (data/budget.yaml) - interview them or read their documents, write the file, validate it with app.check, and explain what it adds up to. Use for a first budget, a raise, a new bill or debt, a paid-off card, a changed payoff target, or "can I afford X".
---

# Write or change the budget

`data/budget.yaml` drives everything. Every key is documented in
`docs/budget-reference.md`; read it before writing. The method (README, "How
the budget works"): budget on the regular paychecks only, give every dollar a
line, and whatever is left goes to the highest-APR debt every month.

Run CLIs inside the container if the app runs in Docker
(`docker compose exec money-doctor python -m app.check`), otherwise from the
repo root (`python -m app.check`).

## Changing an existing budget

1. Read `data/budget.yaml`, `data/budget-plan.md` if it exists, and run
   `app.check` to see where things stand.
2. Make the change. Keep their keys, order and comments.
3. Run `app.check` again and show the difference: extra to debt per month
   before and after, payoff month before and after.
4. Ask before reloading. Settings -> Reload budget & re-import, or
   `docker compose restart money-doctor` (seeding happens on start).

## A first budget

### Gather the facts

Best first: if they have statements, upload them (Upload page or `inbox/`),
then read `data/ingest/summary.md` and `data/ingest/intake-draft.yaml`. They
have income, balances, APRs and subscriptions already worked out.

Then interview for the rest, a few questions at a time, following the
sections of `intake/budget-intake.example.yaml`: goals, income, fixed bills,
debts, everyday spending, irregular costs, savings. If they'd rather fill it
in alone, copy it to `intake/budget-intake.yaml` (git-ignored) and read it
when they're done. Estimates are fine.

What you need:
- **Income**: take-home per regular paycheck (no overtime or bonuses), how
  often, one recent payday.
- **Bills**: amount and due day for each.
- **Debts**: balance, APR, minimum, due day, last 4 for cards, statement date.
- **Everyday spending**: groceries, gas, dining, fun, shopping. Use their bank
  history if you have it, and check the number with them.
- **Irregular costs**: insurance paid twice a year, gifts, car repairs,
  annual renewals. Each becomes a `fund` line at its yearly cost / 12.
- **Goals**: payoff target date, emergency fund size, what extra paychecks do.

### Shape it

- Lines should add up to `paycheck_net x budget_paychecks` or a bit less. The
  rest is the extra payment to debt; `app.check` shows it.
- Each debt's minimum is a `bill` line with `debt:` set to that debt.
- Loans they won't pay early (car, student, mortgage): `payoff_order: last`.
- Map spending with `tracks` categories (list: `Category` in
  `ingest/schemas.py`); use `match` for a specific payee.
- `shortcut:` on the everyday lines they'll log from the phone.
- An emergency fund first is often worth it: `plan.third_paycheck` can fill it
  from the first extra paycheck.
- `plan.target_payoff`: run `app.check` without a target first, show them
  the projected month, then set what they choose.

### Write and check

1. Show a short summary first: income, the lines by group, extra to debt,
   projected payoff. Adjust until they're happy.
2. Write `data/budget.yaml`, run `app.check`, fix every error. Explain any
   warnings.
3. Write the reasoning to `data/budget-plan.md` (git-ignored): target, order,
   what extra money does, what they decided and why. Later check-ins compare
   against it.
4. Ask, then reload.

## Things the model can't do yet (say so plainly)

- Pay twice a month or monthly: paydays step by a fixed number of days, so
  only weekly (7) and every two weeks (14) line up.
- Two incomes on different schedules: budget on the steadier one, and treat
  the other as extra money for debt; or add them if the schedules match.
- Snowball: only avalanche (highest APR first) is computed.
- `recurring` frequencies: monthly, semiannual, yearly, every_3_years.

## Tone

It's their money and their plan. Show trade-offs in months and dollars
("moving $50 from dining to the card saves 2 months and $180 interest"),
recommend, and let them choose. Don't judge spending. Not financial advice.
