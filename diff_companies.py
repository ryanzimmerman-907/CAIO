#!/usr/bin/env python3
"""
diff_companies.py — field-level changelog between two enriched_companies CSVs.

Used by the /refresh-companies skill to summarize exactly what changed between
the previous dataset and a freshly enriched one.

    python3 diff_companies.py enriched_companies.prev.csv enriched_companies.csv
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path


def load(path: str) -> dict[str, dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return {row["company_name"]: row for row in csv.DictReader(f)}


def main() -> None:
    old_path = sys.argv[1] if len(sys.argv) > 1 else "enriched_companies.prev.csv"
    new_path = sys.argv[2] if len(sys.argv) > 2 else "enriched_companies.csv"

    new = load(new_path)
    if not Path(old_path).exists():
        print(f"# Company data refresh — changelog\n\nNo previous snapshot "
              f"({old_path}); treating all {len(new)} companies as new.")
        return
    old = load(old_path)

    added = [c for c in new if c not in old]
    removed = [c for c in old if c not in new]
    changed: list[tuple[str, str, str, str]] = []
    for company, new_row in new.items():
        old_row = old.get(company)
        if not old_row:
            continue
        for field, new_val in new_row.items():
            if field == "company_name":
                continue
            old_val = old_row.get(field, "")
            if (old_val or "") != (new_val or ""):
                changed.append((company, field, old_val, new_val))

    print("# Company data refresh — changelog\n")
    print(f"- Companies: {len(new)} (added {len(added)}, removed {len(removed)})")
    print(f"- Field changes: {len(changed)}\n")

    if added:
        print("## Added\n" + "\n".join(f"- {c}" for c in added) + "\n")
    if removed:
        print("## Removed\n" + "\n".join(f"- {c}" for c in removed) + "\n")
    if changed:
        print("## Field changes")
        current = None
        for company, field, old_val, new_val in sorted(changed):
            if company != current:
                print(f"\n### {company}")
                current = company
            print(f"- **{field}**: `{old_val or '∅'}` → `{new_val or '∅'}`")
    if not (added or removed or changed):
        print("No changes since last refresh. ✅")


if __name__ == "__main__":
    main()
