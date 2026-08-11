# Serve-only API: a Lambda function (read-only over DynamoDB) exposed via a
# Lambda Function URL. No API Gateway needed.

# Zip the single-file handler at apply time.
data "archive_file" "lambda_zip" {
  type        = "zip"
  source_file = "${path.module}/../python/lambda/handler.py"
  output_path = "${path.module}/lambda.zip"
}

# Execution role the Lambda assumes at runtime.
resource "aws_iam_role" "lambda_exec" {
  name = "caio-lambda-exec"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

# CloudWatch Logs for the function.
resource "aws_iam_role_policy_attachment" "lambda_logs" {
  role       = aws_iam_role.lambda_exec.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Least-privilege read access to just this table.
resource "aws_iam_role_policy" "lambda_dynamo_read" {
  name = "caio-lambda-dynamo-read"
  role = aws_iam_role.lambda_exec.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["dynamodb:Scan", "dynamodb:Query", "dynamodb:GetItem"]
      Resource = aws_dynamodb_table.companies.arn
    }]
  })
}

resource "aws_lambda_function" "api" {
  function_name    = "caio-companies-api"
  role             = aws_iam_role.lambda_exec.arn
  runtime          = "python3.12"
  handler          = "handler.handler"
  filename         = data.archive_file.lambda_zip.output_path
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256
  timeout          = 10

  environment {
    variables = {
      TABLE_NAME = aws_dynamodb_table.companies.name
    }
  }
}

# Public HTTPS endpoint for the function (read-only company data).
resource "aws_lambda_function_url" "api" {
  function_name      = aws_lambda_function.api.function_name
  authorization_type = "NONE"

  cors {
    allow_origins = ["*"]
    allow_methods = ["GET"]
  }
}

# A public (authorization_type = NONE) Function URL still needs an explicit
# resource-based permission allowing anonymous invoke.
resource "aws_lambda_permission" "public_url" {
  statement_id           = "AllowPublicFunctionUrl"
  action                 = "lambda:InvokeFunctionUrl"
  function_name          = aws_lambda_function.api.function_name
  principal              = "*"
  function_url_auth_type = "NONE"
}

output "api_url" {
  description = "Public URL of the serve-only companies API"
  value       = aws_lambda_function_url.api.function_url
}
