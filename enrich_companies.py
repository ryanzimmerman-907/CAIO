#!/usr/bin/env python3
"""
enrich_companies.py — an autonomous AI agent that augments a bare list of
company names with rich, *verified* data: official website, headquarters
location, a public phone number, founding year, current CEO/founder, annual
revenue, and a short industry description.

Why this is an "agentic AI" workflow
-------------------------------------
This is not a static script that hits one fixed API. For each company it hands
control to an LLM agent (Claude) that operates in a perceive → reason → act
loop with real tools:

  1. GOAL      — it is given an objective (verify N fields for a company).
  2. TOOL USE  — it autonomously issues live `WebSearch` queries, decides which
                 results are trustworthy, and follows up as needed.
  3. REASONING — it cross-checks sources, corrects bad inputs, and refuses to
                 fabricate (returns "N/A" when a fact can't be verified).
  4. STRUCTURED OUTPUT — it returns a schema-validated JSON object.
  5. SELF-CORRECTION — on malformed/failed output the harness retries with
                 backoff, and a deterministic normalization pass enforces the
                 house style (phone formatting, "N/A" for empty fields).

The orchestration layer below (this file) is the agent *harness*: it fans the
agent out across many companies in parallel, validates and normalizes each
result, and writes the final sheet. Swapping the input CSV is all it takes to
re-run the agent on a new list — no code changes required.

This uses your existing Claude subscription via the `claude` CLI — no separate
API key needed. You must be logged in first:

    claude auth login

Usage
-----
    python3 enrich_companies.py
    python3 enrich_companies.py --input starter_companies.csv --output enriched_companies.csv
    python3 enrich_companies.py --limit 5          # quick test on first 5 rows
    python3 enrich_companies.py --workers 8         # more parallelism

Only depends on the Python standard library — no pip install required.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

FIELDS = [
    "website",
    "headquarters_city",
    "headquarters_state",
    "headquarters_country",
    "phone_number",
    "founded_year",
    "ceo_or_founder",
    "annual_revenue",
    "industry_segment",
]

OUTPUT_COLUMNS = ["company_name", *FIELDS, "enrichment_status"]

# Value written into any field the agent could not verify.
NA = "N/A"

# Country dialing codes, keyed by the country string the agent returns, used to
# prepend a "+<cc>" when a phone number was found without one.
COUNTRY_DIAL_CODES = {
    "United States": "1", "USA": "1", "Canada": "1",
    "United Kingdom": "44", "UK": "44",
    "France": "33", "Germany": "49", "Italy": "39", "Switzerland": "41",
    "Sweden": "46", "Norway": "47", "Finland": "358", "Denmark": "45",
    "Netherlands": "31", "Austria": "43", "Spain": "34", "New Zealand": "64",
    "Australia": "61", "Japan": "81", "China": "86",
}

JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "website": {
            "type": "string",
            "description": "The company's official homepage URL, including https://",
        },
        "headquarters_city": {"type": "string"},
        "headquarters_state": {
            "type": "string",
            "description": "State/province/region. Use 'N/A' if the country does not use one (e.g. Finland, Norway).",
        },
        "headquarters_country": {"type": "string"},
        "phone_number": {
            "type": "string",
            "description": "A real, public HQ or customer-service phone number, in international format with a leading country code, e.g. '+1 800-638-6464' or '+44 161-366-9732'. 'N/A' if none can be verified.",
        },
        "founded_year": {
            "type": "string",
            "description": "Four-digit year the company was founded, e.g. '1973'. Verify against a reliable source; 'N/A' if unknown.",
        },
        "ceo_or_founder": {
            "type": "string",
            "description": "Current CEO as 'Name (CEO)'. If there is no standalone CEO (e.g. a brand owned by a parent), give the founder as 'Name (founder)'. 'N/A' if unknown.",
        },
        "annual_revenue": {
            "type": "string",
            "description": "Most recent annual revenue with year, e.g. '$1.5B (2024)'. Append ' est.' if it is an estimate (common for private companies). 'N/A' if undisclosed.",
        },
        "industry_segment": {
            "type": "string",
            "description": "One short sentence describing what the company makes/sells.",
        },
    },
    "required": FIELDS,
}

PROMPT_TEMPLATE = """You are a data-verification agent. Research the apparel / outdoor-gear
company "{company}" using web search and VERIFY every field against reliable
sources (prefer the company's own official site, then Wikipedia, press releases,
annual reports). Do NOT guess.

Find and verify:
- Official website URL
- Headquarters city, state/region, and country. If the country does not use a
  state/province (e.g. Finland, Norway, Sweden, New Zealand), set the state to "N/A".
- A real public phone number (HQ or customer service). Return it in international
  format with a leading country code, e.g. "+1 800-638-6464" or "+44 161-366-9732".
- The year the company was founded (double-check — historical dates are often wrong).
- The current CEO as "Name (CEO)". If the brand has no standalone CEO (e.g. it is
  owned by a parent company), give the founder as "Name (founder)".
- Most recent annual revenue with the year, e.g. "$1.5B (2024)". Append " est." if
  it is an estimate. Use "N/A" if it is genuinely not disclosed.
- A one-sentence description of what they make/sell.

If you cannot confidently verify a field after searching, return "N/A" for that
field rather than fabricating a value.

Return ONLY the JSON object described by the schema — no extra commentary."""

MAX_RETRIES = 2
RETRY_BACKOFF_SECONDS = 3
MAX_BUDGET_USD_PER_CALL = 0.35


# ---------------------------------------------------------------------------
# Claude CLI plumbing
# ---------------------------------------------------------------------------

def find_claude_binary() -> str:
    """Locate the `claude` executable, falling back to the known install path."""
    found = shutil.which("claude")
    if found:
        return found
    fallback = Path.home() / ".local" / "bin" / "claude"
    if fallback.exists():
        return str(fallback)
    sys.exit(
        "Could not find the `claude` CLI on PATH or at ~/.local/bin/claude.\n"
        "Install Claude Code first: https://docs.claude.com/en/docs/claude-code"
    )


def check_auth(claude_bin: str) -> None:
    """Fail fast with a clear message if the CLI isn't logged in."""
    result = subprocess.run(
        [claude_bin, "auth", "status"],
        capture_output=True,
        text=True,
    )
    try:
        status = json.loads(result.stdout or result.stderr or "{}")
    except json.JSONDecodeError:
        status = {}
    if not status.get("loggedIn"):
        sys.exit(
            "Claude CLI is not logged in. Run this first, then re-run this script:\n\n"
            "    claude auth login\n"
        )


# ---------------------------------------------------------------------------
# Deterministic normalization (the "house style" pass)
# ---------------------------------------------------------------------------

def normalize_phone(raw: str, country: str) -> str:
    """Enforce a consistent '+<cc> <digits-grouped-by-hyphens>' phone format.

    - Blank / unusable -> 'N/A'.
    - If no country code is present, prepend one inferred from the HQ country.
    - Groups the national number with hyphens; keeps a single space after '+cc'.
    """
    if not raw or raw.strip().upper() in {"", "N/A", "NA", "NONE"}:
        return NA

    s = raw.strip()
    # Pull out the country code if the number already carries a leading '+'.
    cc = None
    m = re.match(r"\+\s*(\d{1,3})", s)
    if m:
        cc = m.group(1)
        national = s[m.end():]
    else:
        cc = COUNTRY_DIAL_CODES.get(country, None)
        national = s

    digits = re.sub(r"\D", "", national)
    if not digits:
        return NA
    if cc is None:
        # Couldn't infer a country code; return the digits as-is (last resort).
        return digits

    # Group the national digits into readable hyphen-separated chunks.
    if cc == "1" and len(digits) == 10:  # North American Numbering Plan
        grouped = f"{digits[0:3]}-{digits[3:6]}-{digits[6:10]}"
    else:
        grouped = "-".join(re.findall(r"\d{2,4}", digits)) or digits
    return f"+{cc} {grouped}"


def normalize_row(row: dict) -> dict:
    """Apply house-style rules: blank -> 'N/A', tidy the phone number."""
    for field in FIELDS:
        val = (row.get(field) or "").strip()
        row[field] = val if val else NA
    row["phone_number"] = normalize_phone(
        row.get("phone_number", ""), row.get("headquarters_country", "")
    )
    return row


def call_claude(claude_bin: str, company: str) -> dict:
    """Ask the Claude agent (headless, with web search) to enrich one company."""
    prompt = PROMPT_TEMPLATE.format(company=company)
    cmd = [
        claude_bin,
        "-p",
        prompt,
        "--output-format",
        "json",
        "--json-schema",
        json.dumps(JSON_SCHEMA),
        "--allowedTools",
        "WebSearch",
        "--permission-mode",
        "bypassPermissions",
        "--max-budget-usd",
        str(MAX_BUDGET_USD_PER_CALL),
    ]

    last_error = "unknown error"
    for attempt in range(1, MAX_RETRIES + 2):
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=240)
        except subprocess.TimeoutExpired:
            last_error = "timed out"
        else:
            try:
                envelope = json.loads(proc.stdout)
            except json.JSONDecodeError:
                last_error = f"non-JSON CLI output: {proc.stdout[:200]!r}"
            else:
                if not envelope.get("is_error"):
                    data = envelope.get("structured_output")
                    if not isinstance(data, dict):
                        # Fall back to parsing `result` as JSON text, in case
                        # structured_output isn't present.
                        try:
                            data = json.loads(envelope.get("result") or "")
                        except json.JSONDecodeError:
                            data = None
                    if isinstance(data, dict):
                        row = {field: data.get(field, "") for field in FIELDS}
                        row["company_name"] = company
                        row = normalize_row(row)
                        row["enrichment_status"] = "verified"
                        return row
                    last_error = f"no structured_output/result JSON: {str(envelope.get('result', ''))[:200]!r}"
                else:
                    last_error = str(envelope.get("result", "unknown error"))

        if attempt <= MAX_RETRIES:
            time.sleep(RETRY_BACKOFF_SECONDS * attempt)

    row = {field: NA for field in FIELDS}
    row["company_name"] = company
    row["enrichment_status"] = f"FAILED: {last_error}"
    return row


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="starter_companies.csv", help="Input CSV with a company_name column")
    parser.add_argument("--output", default="enriched_companies.csv", help="Output CSV path")
    parser.add_argument("--limit", type=int, default=None, help="Only process the first N rows (for testing)")
    parser.add_argument("--workers", type=int, default=5, help="Number of companies to look up in parallel")
    args = parser.parse_args()

    claude_bin = find_claude_binary()
    check_auth(claude_bin)

    input_path = Path(args.input)
    if not input_path.exists():
        sys.exit(f"Input file not found: {input_path}")

    with input_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        companies = [row["company_name"].strip() for row in reader if row.get("company_name", "").strip()]

    if args.limit:
        companies = companies[: args.limit]

    total = len(companies)
    print(f"Enriching {total} companies using the Claude agent (web search)... this can take a few minutes.\n")

    results: dict[str, dict] = {}
    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(call_claude, claude_bin, name): name for name in companies}
        for future in as_completed(futures):
            name = futures[future]
            row = future.result()
            results[name] = row
            done += 1
            status = "OK" if row["enrichment_status"] == "verified" else "FAILED"
            print(f"[{done}/{total}] {name}: {status}")

    output_path = Path(args.output)
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        for name in companies:  # preserve original row order
            writer.writerow(results[name])

    failures = [n for n, r in results.items() if r["enrichment_status"] != "verified"]
    print(f"\nDone. Wrote {output_path}")
    if failures:
        print(f"{len(failures)} companies failed and can be re-run: {', '.join(failures)}")


if __name__ == "__main__":
    main()
