terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# NoSQL data layer: a single DynamoDB table keyed by company_name.
# PAY_PER_REQUEST (on-demand) means no idle/provisioned cost — free-tier friendly.
resource "aws_dynamodb_table" "companies" {
  name         = var.table_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "company_name"

  attribute {
    name = "company_name"
    type = "S"
  }

  tags = {
    Project = "CAIO"
  }
}
