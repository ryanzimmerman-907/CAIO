"""
AWS Lambda handler — serve-only API over the caio-companies DynamoDB table.

Exposed via a Lambda Function URL (GET). Supported query params:
    ?search=  substring match across all fields (case-insensitive)
    ?country= filter by headquarters_country (substring)
    ?state=   filter by headquarters_state (substring)
    ?sort=    field to sort by (default: company_name)
    ?order=   asc | desc (default: asc)
    ?limit=   max rows to return

Returns JSON: { "count": N, "total": M, "companies": [ ... ] }

boto3 is preinstalled in the Lambda runtime, so this needs no bundled deps.
"""
import json
import os

import boto3

TABLE_NAME = os.environ.get("TABLE_NAME", "caio-companies")
_table = boto3.resource("dynamodb").Table(TABLE_NAME)

SEARCHABLE = [
    "company_name", "website", "headquarters_city", "headquarters_state",
    "headquarters_country", "phone_number", "founded_year",
    "ceo_or_founder", "annual_revenue", "industry_segment",
]


def _scan_all():
    """Read every item from the (small) table, following pagination."""
    items, kwargs = [], {}
    while True:
        resp = _table.scan(**kwargs)
        items.extend(resp.get("Items", []))
        last_key = resp.get("LastEvaluatedKey")
        if not last_key:
            return items
        kwargs["ExclusiveStartKey"] = last_key


def handler(event, context):
    params = event.get("queryStringParameters") or {}
    q = (params.get("search") or "").strip().lower()
    country = (params.get("country") or "").strip().lower()
    state = (params.get("state") or "").strip().lower()
    sort_by = params.get("sort") or "company_name"
    order = (params.get("order") or "asc").lower()
    try:
        limit = int(params["limit"]) if params.get("limit") else None
    except (ValueError, TypeError):
        limit = None

    items = _scan_all()

    def keep(it):
        if q and not any(q in str(it.get(f, "")).lower() for f in SEARCHABLE):
            return False
        if country and country not in str(it.get("headquarters_country", "")).lower():
            return False
        if state and state not in str(it.get("headquarters_state", "")).lower():
            return False
        return True

    rows = [it for it in items if keep(it)]
    rows.sort(key=lambda it: str(it.get(sort_by, "")).lower(), reverse=(order == "desc"))
    if limit is not None:
        rows = rows[:limit]

    return {
        "statusCode": 200,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps({"count": len(rows), "total": len(items), "companies": rows}, default=str),
    }
