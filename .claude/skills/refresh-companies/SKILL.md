---
name: refresh-companies
description: Refresh the CAIO company dataset — re-run the enrichment agent, then show a field-level changelog of what changed since the previous version. Use when the user wants to update/refresh enriched_companies.csv, do the weekly refresh, or see what changed.
---

# Refresh companies

Runs the enrichment agent again and reports a field-level diff of what changed.
Execute from the CAIO project root (`/Users/ryanzimmerman/CAIO`).

## Steps

1. **Snapshot** the current data so we can diff against it:
   ```
   cp enriched_companies.csv enriched_companies.prev.csv
   ```

2. **Re-enrich** — regenerate the dataset with the agent (re-verifies every
   company via web search; takes a few minutes and spends tokens):
   ```
   python3 enrich_companies.py --input starter_companies.csv --output enriched_companies.csv
   ```
   If it reports the Claude CLI is not logged in, tell the user to run
   `claude auth login`, then retry.

3. **Diff** — produce the field-level changelog:
   ```
   python3 python/diff_companies_skill.py enriched_companies.prev.csv enriched_companies.csv
   ```

4. **Summarize** the changelog for the user. Lead with the counts
   (added / removed / field changes), then call out notable edits — CEO
   changes, revenue updates, corrected founding years, HQ/phone fixes.

5. **Offer to commit + push** the refreshed data. If the user agrees:
   ```
   git add -A && git commit -m "Weekly refresh: update enriched company data" && git push
   ```

6. **Clean up** the snapshot after the diff has been shown:
   ```
   rm -f enriched_companies.prev.csv
   ```

## Notes
- The snapshot file `enriched_companies.prev.csv` is git-ignored scratch; never commit it.
- Keep the summary concise: counts first, then grouped per-company changes.
- To view the refreshed data in the browser afterward, run `./python/run_ui.sh`.
