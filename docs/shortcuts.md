# iPhone Shortcuts

The website has this guide too, filled in with your own URLs: **Settings → iPhone setup** (`/setup`).

Every Shortcut is a few actions around **Get Contents of URL**. Make a token
first: website → **Settings → Shortcut tokens → Create token**, and copy it.

On every *Get Contents of URL* action, tap **Show More** and add the header:

| Header | Value |
|---|---|
| `Authorization` | `Bearer md_…your token…` |

If the API sits behind Cloudflare Access, also add `CF-Access-Client-Id` and
`CF-Access-Client-Secret` (the service token's values).

Base URL below: `https://money.example.com`; use your own.

---

## 1. Log Expense (home screen or "Hey Siri, log expense")

1. **Get Contents of URL**: `https://money.example.com/api/v1/categories` (GET, with the header)
2. **Get Dictionary Value**: `categories` from *Contents of URL*
3. **Choose from List**: *Dictionary Value*, prompt "What was it?"
4. **Ask for Input**: Number, prompt "How much?"
5. **Ask for Input**: Text, prompt "Note (optional)", allow empty
6. **Get Contents of URL**: `https://money.example.com/api/v1/tx`
   - Method **POST**, Request Body **JSON**:
     - `amount` (Number) → *Provided Input* from step 4
     - `category` (Text) → *Chosen Item*
     - `note` (Text) → *Provided Input* from step 5
7. **Get Dictionary Value**: `message` from *Contents of URL*
8. **Show Notification**: *Dictionary Value*

You'll see something like **"Logged $12.50 to Groceries. $187.50 left for October ($8.10 a day)."**
The category menu comes from your budget, so new lines show up automatically.

## 2. Log Apple Pay purchases automatically

Automation tab → **+** → **Apple Pay** (called *Transaction* or *Wallet* on older iOS).
Select your debit and credit cards, Apple Card, and Apple Cash; unselect IDs such as a
driver's license. Leave all categories selected → **Run Immediately**, **Notify When Run** off.

It fires only for Apple Pay. Card swipes and peer-to-peer apps (Cash App, Zelle, Venmo,
PayPal, Apple Cash in Messages) don't trigger it; log those with Log Expense.

1. **Get Contents of URL**: `https://money.example.com/api/v1/tx`, POST, JSON:
   - `amount` (Text) → *Shortcut Input → Amount* (a string like "$12.50" is fine)
   - `merchant` (Text) → *Shortcut Input → Merchant*
   - `category` (Text) → `auto`
2. **Get Dictionary Value** `message` → **Show Notification**

The merchant name picks the budget line using the same rules as bank imports.
Anything it can't place lands as "Other" for you to assign on the website. When
the bank statement arrives later, the import matches it to this entry, so
nothing is counted twice.

## 3. Undo Last

**Get Contents of URL**: `…/api/v1/undo`, Method **POST** → **Get Dictionary Value** `message` → **Show Notification**.

## 4. Money Today ("Hey Siri, money today")

**Get Contents of URL**: `…/api/v1/summary` → **Get Dictionary Value** `message` → **Show Content** (older iOS: *Show Result*).
Siri reads out today's safe-to-spend amount, the next bills, and whether you're on track.

## 5. Send to Money Doctor (share sheet)

For pay statements, card statements, bank CSVs, and the household spreadsheet.

1. Shortcut settings (ⓘ): **Show in Share Sheet** on; accepts **Files** and **PDFs**
2. **Get Contents of URL**: `…/api/v1/documents`
   - Method **POST**, Request Body **Form**
   - Add field: key `files`, type **File**, value *Shortcut Input*
3. **Get Dictionary Value** `message` → **Show Notification**

Open a PDF in Files or Safari → Share → **Send to Money Doctor**. The reply looks
like **"Uploaded 1 file: 0 new transactions. Card balances: Card 1 $5,830."**

Bank CSVs need the account in the file name (`checking_1234_…`,
`credit_card_1234_…`). For a file that doesn't have it, add `?account=credit_card_1234` to the URL.

## API reference

| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/api/v1/categories` | | `{categories: [...]}` |
| POST | `/api/v1/tx` | `{amount, category, note?, merchant?, date?, refund?}` | `{message, remaining}` |
| POST | `/api/v1/undo` (or DELETE `/api/v1/tx/last`) | | `{message}` |
| GET | `/api/v1/summary` | | `{message, safe_today}` |
| POST | `/api/v1/documents` | multipart `files` (+ `?account=`) | `{message, saved, import}` |
