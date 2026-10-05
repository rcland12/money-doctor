"""Turn redacted statement text into a DocumentExtraction.

Three backends, same prompt and schema:
  claude-code  headless Claude Code (`claude -p`), billed to your Claude subscription
  claude       Anthropic API (reads ANTHROPIC_API_KEY or an `ant auth login` profile)
  local        an Ollama server, e.g. on a GPU machine on your LAN (OLLAMA_URL, OLLAMA_MODEL)
Only the redacted text is ever sent; the PDF itself never leaves this machine.
"""

import json
import os
import subprocess
import urllib.request

from pydantic import BaseModel

from .schemas import DocumentExtraction

CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-5-5")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3:14b")

SYSTEM = """You extract structured data from one financial document at a time: a \
pay stub, or a bank, credit card, or loan \
statement. The text came from a PDF with its layout preserved, so tables may be \
spread across aligned columns. Personal details were replaced with tokens such as \
[REDACTED], [ADDRESS], or [NUM ••1234]; take account_last4 from those tokens.

Rules:
- Copy numbers exactly as printed. Never estimate or invent a value; use null when absent.
- Pay statements: current-period amounts only, never year-to-date columns. Classify \
every earning line (overtime, holiday, premium pay...) and every deduction line.
- Account statements: list every transaction in the period, including interest \
charged and fees. Sign: negative = money out or debt growing (purchases, bills, \
interest, fees, withdrawals); positive = money in or debt shrinking (deposits, \
refunds, payments made to the card or loan).
- For cards and loans, opening/closing balance is the amount owed as a positive number.
- Categories: transfers between the person's own accounts are transfer_internal; \
payments to a credit card or loan are debt_payment; PayPal Pay Monthly/Pay in 4, \
Affirm, Klarna, Afterpay, and device installment charges are installment_plan.
- Put anything unreadable or ambiguous in notes."""


def _user_prompt(text: str) -> str:
    return f"Extract this document.\n\n<document>\n{text}\n</document>"


def extract_claude(text: str) -> DocumentExtraction:
    import anthropic

    client = anthropic.Anthropic()
    response = client.beta.messages.parse(
        model=CLAUDE_MODEL,
        max_tokens=16000,
        system=SYSTEM,
        messages=[{"role": "user", "content": _user_prompt(text)}],
        output_format=DocumentExtraction,
        output_config={"effort": "medium"},
        # On a safety-classifier decline, retry server-side on Anthropic's
        # recommended fallback model instead of failing the document.
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    )
    if response.stop_reason == "refusal":
        raise RuntimeError(f"model declined: {response.stop_details}")
    if response.stop_reason == "max_tokens":
        raise RuntimeError("output hit max_tokens; split the PDF and retry")
    return response.parsed_output


def run_claude_code(system: str, prompt: str, schema: type[BaseModel]) -> BaseModel:
    """One tool-less `claude -p` call with a JSON schema; uses the logged-in subscription."""
    out = subprocess.run(
        ["claude", "-p", "--output-format", "json", "--json-schema", json.dumps(schema.model_json_schema()),
         "--tools", "", "--no-session-persistence", "--system-prompt", system],
        input=prompt, capture_output=True, text=True, timeout=900,
    )
    result = json.loads(out.stdout or "{}")
    if out.returncode or result.get("is_error") or "structured_output" not in result:
        raise RuntimeError(f"claude -p failed: {result.get('result') or out.stderr.strip()[:300]}")
    return schema.model_validate(result["structured_output"])


def extract_claude_code(text: str) -> DocumentExtraction:
    return run_claude_code(SYSTEM, _user_prompt(text), DocumentExtraction)


def extract_local(text: str) -> DocumentExtraction:
    body = {
        "model": OLLAMA_MODEL,
        "stream": False,
        "format": DocumentExtraction.model_json_schema(),
        "options": {"temperature": 0, "num_ctx": 32768},
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": _user_prompt(text)},
        ],
    }
    req = urllib.request.Request(
        f"{OLLAMA_URL.rstrip('/')}/api/chat",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=900) as resp:
        content = json.load(resp)["message"]["content"]
    return DocumentExtraction.model_validate_json(content)


BACKENDS = {"claude-code": extract_claude_code, "claude": extract_claude, "local": extract_local}


def backend_model(backend: str) -> str:
    return {"claude-code": "subscription", "claude": CLAUDE_MODEL, "local": OLLAMA_MODEL}[backend]
