# CAIO — Apparel Company Enrichment Agent

Class project: an AI agent that takes a bare spreadsheet of apparel/outdoor
company names ([`starter_companies.csv`](starter_companies.csv)) and
augments it with rich, verified data — official website, headquarters
location, phone number, founding year, and industry description — writing
the result to `enriched_companies.csv`.

## How the agent works

`enrich_companies.py` reads each company name and, for every row, launches
the [Claude Code CLI](https://docs.claude.com/en/docs/claude-code) in
non-interactive ("headless") mode with the **WebSearch** tool enabled. Claude
searches the web, verifies the company's details, and returns a strict JSON
object (validated against a JSON Schema) which the script parses into a new
CSV row. Several companies are looked up in parallel to keep the whole sheet
fast.

This uses your existing Claude subscription through the CLI — there's no
separate API key, and the script only depends on the Python standard
library (no `pip install` required).

## One-time setup

1. **Log in to Claude Code** (opens a browser to authenticate):
   ```
   claude auth login
   ```
2. Confirm you're logged in:
   ```
   claude auth status
   ```

## Running it

```
cd ~/CAIO
python3 enrich_companies.py
```

Useful flags:

| Flag | Purpose |
|---|---|
| `--limit 5` | Only process the first 5 rows (quick test) |
| `--workers 8` | Look up more companies in parallel (default: 5) |
| `--input other.csv` | Use a different input file |
| `--output other_out.csv` | Write to a different output file |

Progress prints live to the terminal as each company finishes. Any company
that fails after retries is marked `FAILED: <reason>` in the
`enrichment_status` column of the output — safe to re-run just those rows
later.

## Easy run alias

Add this to your shell profile for a one-word run command:

```bash
alias CAIORun='cd ~/CAIO && python3 enrich_companies.py'
```

Then just type `CAIORun` in any new terminal.

## Publishing updates to GitHub

```
cd ~/CAIO
git add enriched_companies.csv
git commit -m "Enrich companies with location, phone, and website data"
git push
```

(Requires `gh auth login` to have been run once so `git push` is
authenticated.)

## Files

- `starter_companies.csv` — original bare list (company_name only)
- `enrich_companies.py` — the enrichment agent
- `enriched_companies.csv` — generated output (created after you run the agent)
