# Budget file reference

Every key `data/budget.yaml` understands. Start from
[`config/budget.example.yaml`](../config/budget.example.yaml) and only add
what you need. After editing, run `python -m app.check` (or
`docker compose exec money-doctor python -m app.check`), then
**Settings -> Reload budget & re-import**.

Amounts are monthly unless noted. Months are `YYYY-MM`, dates `YYYY-MM-DD`.
Accounts are written the way transactions name them: `checking_1234`,
`savings_1234`, `credit_card_1234` (last 4 digits), or `paypal`, `apple_card`, `apple_cash`.

## Basics

```yaml
owner: Alex                       # shown in the morning email
timezone: America/Chicago         # when the morning email goes out

income:
  paycheck_net: 2000.00           # one regular paycheck after taxes, without overtime
  pay_anchor: 2026-03-06          # any past or future payday
  pay_every_days: 14              # 14 = every two weeks, 7 = weekly
  budget_paychecks: 2             # paychecks the budget spends each month

digest:
  send_at: "06:30"
  to: you@example.com
```

**Pay schedules.** Paydays step from `pay_anchor` by `pay_every_days`, so
weekly (`7`, `budget_paychecks: 4`) and every two weeks (`14`,
`budget_paychecks: 2`) work. Months with more paydays than
`budget_paychecks` have an extra paycheck, handled by `plan.third_paycheck`.
Twice-a-month and monthly pay aren't supported yet.

**Two incomes or two jobs.** There's one `paycheck_net` today. If both are
paid on the same schedule, add them together. If not, budget on the steadier
one, and treat the other as extra money that speeds up the payoff.

## plan

```yaml
plan:
  start: 2026-03                  # funds start saving this month
  target_payoff: 2028-09-30       # compared with the projection
  strategy: avalanche             # only avalanche is implemented
  third_paycheck:                 # months with an extra paycheck
    - {month: 2027-04, emergency_fund: 1000, rest: cards}       # fill a fund first, rest to debt
    - {month: 2027-10, split: {cards: 0.7, life_happens: 0.3}}  # or a split
```

A month that isn't listed splits the extra paycheck 50/50 between debt and a buffer.

## lines

One per budget line. Everything the income doesn't assign goes to the
highest-APR debt each month.

| Key | Meaning |
|---|---|
| `key`, `name` | An id (lowercase, no spaces) and a display name |
| `group` | Heading it's shown under (`Home`, `Everyday`, ...) |
| `kind` | `variable` (everyday spending, feeds "safe to spend"), `bill` (has a due day), `fund` (saves monthly for something lumpy), `savings` (money you keep) |
| `amount` | Monthly amount |
| `due_day`, `due_amount` | Bills: day of the month, and the bill's own amount if it differs from what you budget monthly. Counts as paid at 90% of it. |
| `pay_from` | `1` or `2`: which paycheck of the month covers it |
| `tracks` | Transaction categories that count against it ([list](../ingest/schemas.py)) |
| `offsets` | Categories that reduce its spending, e.g. `[reimbursement]` on rent when roommates pay you back |
| `match` | Description text that pins a transaction here, checked before `tracks` (e.g. `[GEICO]`) |
| `debt` | A debt `key`: this line is that debt's minimum payment |
| `from`, `until` | Months the line is active, e.g. a loan that ends |
| `start_balance` | Funds: balance on `plan.start` |
| `shortcut` | Label in the iPhone "Log Expense" menu |
| `private` | Counts in totals but shows as "Personal" |
| `note` | Shown next to it |

## debts

```yaml
debts:
  - {key: card_a, name: Card A, kind: credit_card, last4: "1111", balance: 6000,
     as_of: 2026-02-18, apr: 24.99, minimum: 150, due_day: 20, limit: 8000}
  - {key: car, name: Car loan, kind: auto, balance: 12000, as_of: 2026-02-11,
     apr: 6.9, minimum: 350, due_day: 15, payoff_order: last}
```

`kind`: `credit_card`, `auto`, `installment`, or anything else. `last4` links
a card to its transactions and statements. `payoff_order: last` keeps a debt
out of the extra payments (it just gets its minimum). Statements, bank sync
and manual entries add newer balances; the `balance` here is only the starting point.

## savings_goals and events

```yaml
savings_goals:
  - {key: emergency, name: Emergency fund, target: 1000, balance: 0, account: savings_2222}

events:                           # one-off dates on the calendar and in the email
  - {date: 2026-12-20, name: Holiday gifts, amount: 200, line: gifts, kind: event}
```

## Optional extras

```yaml
# Subscriptions and renewals that charge on their own; shown on the calendar
# and the Recurring page. frequency: monthly | semiannual | yearly | every_3_years.
# Monthly ones need day; the others need next (the next charge date).
recurring:
  - {key: streaming, name: Streaming, amount: 15.49, frequency: monthly, day: 12,
     method: credit_card_1111, line: subscriptions, autopay: true}
  - {key: domain, name: Domain renewal, amount: 12, frequency: yearly, next: 2027-03-01,
     method: credit_card_1111, status: active}          # active | ending | cancelled

# Line keys (and cash_bills keys) that are paid automatically.
autopay: [car_payment, card_a_min]

# Which account each bill or fund is paid from. Without this, it's worked out
# from where its payments came from lately.
paid_with:
  rent: checking_1234

# Checking: the account the cash forecast follows, and a floor to keep in it.
cash:
  account: checking_1234
  cushion: 200

# Bills you pay in full and split with others (amount = the whole bill).
cash_bills:
  - {key: power, name: Electric, amount: 150, day: 5, match: [POWER CO], paid_with: checking_1234}

# Small charges that really belong to another line, e.g. snacks at a gas station.
small_purchases:
  - {line: gas, under: 15, becomes: dining}

# Apple Wallet card names -> accounts, for the Apple Pay Shortcut.
wallet_cards:
  "Travel Card": credit_card_1111

# Debit card last 4 -> account, for bank alert emails.
card_numbers:
  "3333": checking_1234

# Investments for net worth. simplefin: part of the bank sync account name.
assets:
  - {key: roth, name: Roth IRA, simplefin: "Roth", balance: 0, as_of: 2026-03-01}
```
