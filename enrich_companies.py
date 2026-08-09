#!/usr/bin/env python3
"""
enrich_companies.py — AI agent that augments a bare list of company names with
rich data: official website, headquarters location, a public phone number,
founding year, and a short industry description.

How it works
------------
For each company in the input CSV, this script shells out to the Claude Code
CLI in non-interactive ("headless") mode with the WebSearch tool enabled, and
asks it to look up and verify the company's details, returning a strict JSON
object (validated against a JSON Schema) that we parse straight into a new
CSV row. Running many companies in parallel (a small thread pool of
subprocesses) keeps a 50-row sheet fast without hammering any single request.

This uses your existing Claude subscription via the `claude` CLI — no
separate API key needed. You must be logged in first:

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
    "industry_segment",
]

OUTPUT_COLUMNS = ["company_name", *FIELDS, "enrichment_status"]

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
            "description": "State/province/region, if applicable. Empty string if not applicable.",
        },
        "headquarters_country": {"type": "string"},
        "phone_number": {
            "type": "string",
            "description": "A public HQ or customer-service phone number, in the format found on the company's site.",
        },
        "founded_year": {"type": "string", "description": "Four-digit year as a string, e.g. '1973'."},
        "industry_segment": {
            "type": "string",
            "description": "One short sentence describing what the company makes/sells.",
        },
    },
    "required": FIELDS,
}

PROMPT_TEMPLATE = """Research the apparel / outdoor-gear company "{company}" using web search.

Find and verify (do not guess):
- Official website URL
- Headquarters city, state/region, and country
- A public phone number (HQ or customer service) listed on their official site or a reliable directory
- The year the company was founded
- A one-sentence description of what they make/sell

If you cannot verify a field confidently after searching, return an empty
string "" for that field rather than fabricating a value. Prefer information
from the company's own official website.

Return ONLY the JSON object described by the schema — no extra commentary."""

MAX_RETRIES = 2
RETRY_BACKOFF_SECONDS = 3
MAX_BUDGET_USD_PER_CALL = 0.25


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


def call_claude(claude_bin: str, company: str) -> dict:
    """Ask Claude (headless, with web search) to enrich one company."""
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
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
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
                        row["enrichment_status"] = "ok"
                        return row
                    last_error = f"no structured_output/result JSON: {str(envelope.get('result', ''))[:200]!r}"
                else:
                    last_error = str(envelope.get("result", "unknown error"))

        if attempt <= MAX_RETRIES:
            time.sleep(RETRY_BACKOFF_SECONDS * attempt)

    row = {field: "" for field in FIELDS}
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
    print(f"Enriching {total} companies using Claude (web search)... this can take a few minutes.\n")

    results: dict[str, dict] = {}
    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(call_claude, claude_bin, name): name for name in companies}
        for future in as_completed(futures):
            name = futures[future]
            row = future.result()
            results[name] = row
            done += 1
            status = "OK" if row["enrichment_status"] == "ok" else "FAILED"
            print(f"[{done}/{total}] {name}: {status}")

    output_path = Path(args.output)
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        for name in companies:  # preserve original row order
            writer.writerow(results[name])

    failures = [n for n, r in results.items() if r["enrichment_status"] != "ok"]
    print(f"\nDone. Wrote {output_path}")
    if failures:
        print(f"{len(failures)} companies failed and can be re-run: {', '.join(failures)}")


if __name__ == "__main__":
    main()
