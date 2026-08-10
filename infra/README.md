# CAIO infrastructure (Terraform → AWS)

Provisions the NoSQL data layer for the project: one **DynamoDB** table
(`caio-companies`). Serverless compute (Lambda/API Gateway) is a later phase.

## Prerequisites
- An AWS account with CLI credentials configured: `aws configure` (or env vars).
- Terraform >= 1.5 and the AWS CLI installed.

## Deploy the table
```
cd infra
terraform init
terraform apply        # creates the DynamoDB table (on-demand billing, ~$0 at this scale)
```

## Load the enriched data into it
```
cd ..
.venv/bin/pip install boto3          # once
.venv/bin/python python/load_to_dynamo.py --table caio-companies --region us-east-1
```

## Tear it all down (do this before deleting the project on 2026-08-23)
```
cd infra
terraform destroy
```

Terraform state (`*.tfstate`) and the `.terraform/` cache are git-ignored — they
can contain resource details and should not be committed.
