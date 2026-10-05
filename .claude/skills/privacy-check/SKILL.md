---
name: privacy-check
description: Before a commit, push or pull request on a Money Doctor checkout or fork, check that no personal financial data (names, account digits, balances, emails, domains, employer details, statements) is in tracked or about-to-be-tracked files. Use whenever someone is about to share their copy of the code.
---

# Privacy check

The repo is public, and a working copy sits next to real financial data. This
checks what git would publish. Report what you find; don't change git state.

## 1. What would be published

```bash
git status --short
git diff HEAD --stat
git ls-files --others --exclude-standard     # new files git would pick up
```

Anything under `data/`, `inbox/`, `intake/*.yaml`, `.env`, `deploy/*.env`,
`compose.yml`, `CLAUDE.local.md`, `PLAN.md` or `ingest/paystub_local.py`
showing up here means `.gitignore` was changed or bypassed: stop and say so.
Same for any `.pdf .csv .xlsx .ofx .qfx .db` file.

## 2. Their values in the changes

Collect values from their own files and search the tracked and new files for
them. Print only where a match is (file:line) and what kind of value it is,
never the value itself.

```bash
python - <<'EOF'
import re, subprocess, yaml
from pathlib import Path
terms = {}
def walk(x, k=""):
    if isinstance(x, dict):
        for kk, v in x.items(): walk(v, kk)
    elif isinstance(x, list):
        for v in x: walk(v, k)
    elif x is not None:
        s = str(x)
        if k in ("last4", "to", "owner", "email", "account") or "@" in s or re.fullmatch(r"\d{4}", s):
            terms[s] = k
        elif k in ("balance", "apr", "paycheck_net", "limit", "minimum", "amount") and len(s) >= 4:
            terms[s] = k
for f in ("data/budget.yaml", "data/pii.yaml", "data/merchant-patterns.yaml", "data/settings.yaml"):
    p = Path(f)
    if p.exists():
        walk(yaml.safe_load(p.read_text()) or {}, "pii" if "pii" in f else "")
env = Path(".env")
if env.exists():
    for line in env.read_text().splitlines():
        m = re.match(r"(MD_PUBLIC_URL|SMTP_FROM|MAIL_USER|SMTP_USER)=(.+)", line)
        if m:
            for v in re.findall(r"[\w.+-]+@[\w.-]+|https?://([\w.-]+)", m.group(2)):
                if v: terms[v] = m.group(1)
files = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"],
                       capture_output=True, text=True).stdout.split()
hits = 0
for t, kind in terms.items():
    if len(t) < 4:
        continue
    out = subprocess.run(["git", "grep", "--no-index", "-n", "-F", "-w", t, "--", *files],
                         capture_output=True, text=True).stdout.splitlines()
    for line in out:
        hits += 1
        print(f"[{kind or 'value'}] {':'.join(line.split(':')[:2])}")
print(f"{len(terms)} personal values checked, {hits} matches")
EOF
```

Many matches are harmless (a budget line called "Groceries", `1000` as a
uid). Look at each in context and sort them into real leaks and false alarms.

## 3. Things a search can't see

Read the diff (`git diff HEAD`) for: real merchant names that point to a
place (a local utility, a small business), an employer or employer type, a
real-looking date from their plan, screenshots or images, and logs. The
built-in rules and examples stay generic: national chains, `Alex`, card
`1111`, `example.com`, round numbers.

## Report

List the real problems with file:line and a suggested fix (move it to a
`data/` file, replace with a fake value). If there are none, say so plainly.
