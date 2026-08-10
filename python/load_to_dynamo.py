#!/usr/bin/env python3
"""
load_to_dynamo.py — load enriched_companies.csv into the DynamoDB table
provisioned by ../infra (Terraform).

Idempotent: re-running overwrites items by company_name, so it doubles as the
"sync after a refresh" step.

    .venv/bin/pip install boto3         # once
    python3 python/load_to_dynamo.py --table caio-companies --region us-east-1

Uses your AWS credentials from the environment or `aws configure`.
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import boto3

DEFAULT_CSV = Path(__file__).resolve().parent.parent / "enriched_companies.csv"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--table", default="caio-companies", help="DynamoDB table name")
    ap.add_argument("--region", default="us-east-1", help="AWS region")
    ap.add_argument("--csv", default=str(DEFAULT_CSV), help="Path to the enriched CSV")
    args = ap.parse_args()

    table = boto3.resource("dynamodb", region_name=args.region).Table(args.table)

    with open(args.csv, newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r.get("company_name", "").strip()]

    with table.batch_writer(overwrite_by_pkeys=["company_name"]) as batch:
        for r in rows:
            # DynamoDB rejects empty strings; fall back to "N/A".
            item = {k: (v if v not in ("", None) else "N/A") for k, v in r.items()}
            batch.put_item(Item=item)

    print(f"Loaded {len(rows)} companies into '{args.table}' ({args.region}).")


if __name__ == "__main__":
    main()
