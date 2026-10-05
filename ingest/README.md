# Document ingest

Turns your pay statements and bank exports into `data/ingest/summary.md`
(income, overtime, leave, spending by month, interest, recurring charges) and
`data/ingest/intake-draft.yaml`.

```
inbox/
  bank/
    checking_1234_<start>_<end>.csv        BoA custom-range export
    savings_5678_<start>_<end>.csv
    credit_card_4321/<Month><Year>_4321.csv one statement month per file
    credit_card_4321_current.pdf            latest statement: balance, APR, minimum
  pay/*.pdf                                 pay statements
  anything-else.pdf                         goes through redact + extract
```

The account type and last 4 digits must appear in each CSV's file or folder
name (`checking_1234`, `savings_1234`, `credit_card_1234`). Overlapping date
ranges are fine: transactions are de-duplicated by BoA's reference number
(cards), or by date, amount, and running balance (checking/savings).

## Commands

```bash
# from the repo root, with requirements.txt installed
python -m ingest run          # parse everything new + write the summary
python -m ingest categorize   # merchants still in "other"
```

| Input | How it's read | Model? |
|-------|---------------|--------|
| BoA checking/savings/card CSV | `boa_csv.py`; checking must reconcile to BoA's running balance | No |
| Pay statement PDF | your own parser in `paystub_local.py` (git-ignored; see `paystub.py`); without one, redact + extract | Only without a parser |
| Any other PDF | `redact` (local), then `extract --backend …` | Yes |

Categories come from `data/merchant-rules.yaml` (yours, git-ignored), then
regexes in `data/merchant-patterns.yaml` (local businesses, your employer's
payroll; `salary: true` marks the paycheck), then the built-in rules in `rules.py`. Edit the YAML and re-run `summarize`; there's
no need to re-parse.

Inside Docker you don't run these by hand: uploads from the website or the
share-sheet Shortcut run `parse` (+ `redact`/`extract` if `MD_EXTRACT_BACKEND`
is set) and `summarize`, then import the results.

## Monthly routine (without bank sync)

1. **Every payday:** upload the pay statement (or save it into `inbox/pay/`).
2. **Once a month**, after both card statements close:
   - each card: that month's CSV into its `credit_card_XXXX/` folder
   - checking and savings: one CSV covering from the last download to today (overlap is fine)
3. `python -m ingest run`, then `categorize`. Add any new merchants to the rules file.

With SimpleFIN bank sync connected (Settings), step 2 goes away. Pay
statements stay manual; the share-sheet Shortcut makes that one tap.

## Model backends (only for PDFs no parser recognizes)

| Backend | Cost | Notes |
|---------|------|-------|
| `claude-code` | your Claude subscription | runs `claude -p` with a JSON schema and no tools; needs the Claude Code CLI, so not inside Docker |
| `claude` | API credits | needs `ANTHROPIC_API_KEY` |
| `local` | free | an Ollama server on your network |

Only redacted text is sent to a model. Copy `ingest/pii.example.yaml` to `data/pii.yaml`
first. Screenshot-style PDFs have no text layer; enter
their numbers in the intake form, or `sudo apt install tesseract-ocr` to OCR them.

### Ollama on another machine

```bash
ollama pull qwen3:14b                  # ~9 GB; leaves room for a 32k context
# make Ollama listen on the network: OLLAMA_HOST=0.0.0.0, then restart it
# (Windows: setx OLLAMA_HOST 0.0.0.0; Linux: systemctl edit ollama)
# firewall: allow TCP 11434 from your LAN only
```

```bash
OLLAMA_URL=http://<ollama-host>:11434 python -m ingest extract --backend local
```

If it misreads long tables, try `qwen3:32b` (Q4, ~20 GB, keep context ≤16k),
or whatever newer Qwen/Gemma instruct model on ollama.com fits your GPU.
