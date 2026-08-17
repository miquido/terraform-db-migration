locals {
  dump_s3_prefix       = "db-dumps/"
  anonymized_s3_prefix = "anonymized/"
}

# S3 Bucket for dumps
module "dump-s3" {
  source              = "cloudposse/s3-bucket/aws"
  version             = "4.15.0"
  acl                 = "private"
  enabled             = true
  user_enabled        = false
  versioning_enabled  = true
  s3_object_ownership = "BucketOwnerEnforced"
  name                = "pg-dumps"
  stage               = var.environment
  namespace           = var.project
}

# PG Dump ECS Task
module "pg_dump_task" {
  source                = "git::https://github.com/miquido/terraform-ecs-task.git?ref=tags/1.0.11"
  name                  = "pg-dump"
  cluster_arn           = var.ecs_cluster_arn
  task_cpu              = 1024
  container_image       = "miquido/pg_dump"
  task_memory           = 2048
  container_tag         = "151259-2501fdc9"
  environment           = var.environment
  project               = var.project
  security_groups       = var.security_group_ids
  subnets               = var.subnet_ids
  region                = var.region
  environment_variables = [
    {
      name  = "PG_HOST"
      value = var.db_host
    },
    {
      name  = "PG_DATABASE"
      value = var.db_name
    },
    {
      name  = "PG_USER"
      value = var.db_user
    },
    {
      name  = "PG_PORT"
      value = var.db_port
    },
    {
      name  = "S3_BUCKET"
      value = module.dump-s3.bucket_id
    },
    {
      name  = "AWS_REGION"
      value = var.region
    },
    {
      name  = "S3_PREFIX"
      value = local.dump_s3_prefix
    },
  ]
  secrets = [
    {
      name      = "PG_PASSWORD"
      ssmName   = var.db_password_ssm_name
      valueFrom = var.db_password_ssm_arn
    }]
  assign_public_ip = false
  log_retention    = var.log_retention
}

# PG Dump Cron Job
module "pg_dump" {
  source                  = "git::https://github.com/miquido/terraform-cron-job-ecs.git?ref=tags/1.1.0"
  name                    = "pg-dump"
  aws_sns_error_topic_arn = var.sns_error_topic_arn
  environment             = var.environment
  project                 = var.project
  subnet_ids              = var.subnet_ids
  security_group_ids      = var.security_group_ids
  ecs_cluster_arn         = var.ecs_cluster_arn
  task_definition         = module.pg_dump_task.task_definition_arn
  task_role_arn           = module.pg_dump_task.service_role_arn
  task_exec_role_arn      = module.pg_dump_task.execution_role_arn
  schedule_expression     = var.schedule_expression
}

# IAM Policy for PG Dump Task
data "aws_iam_policy_document" "pg-dump-policy" {
  statement {
    actions = [
      "s3:*"
    ]
    resources = [
      "${module.dump-s3.bucket_arn}*"
    ]
  }
}

resource "aws_iam_role_policy" "pg-dump-policy" {
  policy = data.aws_iam_policy_document.pg-dump-policy.json
  role   = module.pg_dump_task.service_role_name
}

# ===== Anonymize Lambda =====

resource "aws_iam_role" "anonymize_lambda_role" {
  name = "${var.project}-${var.environment}-anonymize-lambda"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}

data "aws_iam_policy_document" "anonymize_lambda_policy" {
  statement {
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:ListBucket"
    ]
    resources = [
      module.dump-s3.bucket_arn,
      "${module.dump-s3.bucket_arn}/*"
    ]
  }

  statement {
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents"
    ]
    resources = ["arn:aws:logs:*:*:*"]
  }
}

resource "aws_iam_role_policy" "anonymize_lambda_policy" {
  name   = "anonymize-lambda-policy"
  role   = aws_iam_role.anonymize_lambda_role.id
  policy = data.aws_iam_policy_document.anonymize_lambda_policy.json
}

# Package Lambda with anonymization rules
data "archive_file" "anonymize_lambda_zip" {
  type        = "zip"
  output_path = "${path.module}/anonymize.zip"

  source {
    content  = file("${path.module}/anonimize.py")
    filename = "anonimize.py"
  }

  source {
    content  = var.anonymization_rules_file != "" ? file(var.anonymization_rules_file) : "# No rules provided\nANONYMIZATION_RULES = {}"
    filename = "anonymization_rules.py"
  }
}

resource "aws_lambda_function" "anonymize_dumps" {
  filename         = data.archive_file.anonymize_lambda_zip.output_path
  function_name    = "${var.project}-${var.environment}-anonymize-dumps"
  role             = aws_iam_role.anonymize_lambda_role.arn
  handler          = "anonimize.lambda_handler"
  source_code_hash = data.archive_file.anonymize_lambda_zip.output_base64sha256
  runtime          = "python3.13"
  timeout          = 900
  memory_size      = 1024

  environment {
    variables = {
      OUTPUT_PREFIX = local.anonymized_s3_prefix
    }
  }
}

resource "aws_cloudwatch_log_group" "anonymize_lambda_logs" {
  name              = "/aws/lambda/${aws_lambda_function.anonymize_dumps.function_name}"
  retention_in_days = var.log_retention
}

resource "aws_lambda_permission" "allow_s3_invoke" {
  statement_id  = "AllowExecutionFromS3Bucket"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.anonymize_dumps.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = module.dump-s3.bucket_arn
}

# ===== Copy Dumps Lambda =====

resource "aws_iam_role" "copy_dumps_lambda_role" {
  name = "${var.project}-${var.environment}-copy-dumps-lambda"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}

data "aws_iam_policy_document" "copy_dumps_lambda_policy" {
  statement {
    actions = [
      "s3:GetObject",
      "s3:GetObjectVersion",
      "s3:ListBucket"
    ]
    resources = [
      module.dump-s3.bucket_arn,
      "${module.dump-s3.bucket_arn}/*"
    ]
  }

  statement {
    actions = [
      "s3:PutObject",
      "s3:PutObjectAcl"
    ]
    resources = [
      "arn:aws:s3:::${var.destination_dump_bucket}/*"
    ]
  }

  statement {
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents"
    ]
    resources = ["arn:aws:logs:*:*:*"]
  }
}

resource "aws_iam_role_policy" "copy_dumps_lambda_policy" {
  name   = "copy-dumps-lambda-policy"
  role   = aws_iam_role.copy_dumps_lambda_role.id
  policy = data.aws_iam_policy_document.copy_dumps_lambda_policy.json
}

data "archive_file" "copy_dumps_lambda_zip" {
  type        = "zip"
  source_file = "${path.module}/copy_dumps.py"
  output_path = "${path.module}/copy_dumps.zip"
}

resource "aws_lambda_function" "copy_dumps" {
  filename         = data.archive_file.copy_dumps_lambda_zip.output_path
  function_name    = "${var.project}-${var.environment}-copy-dumps"
  role             = aws_iam_role.copy_dumps_lambda_role.arn
  handler          = "copy_dumps.lambda_handler"
  source_code_hash = data.archive_file.copy_dumps_lambda_zip.output_base64sha256
  runtime          = "python3.13"
  timeout          = 900
  memory_size      = 512

  environment {
    variables = {
      DESTINATION_BUCKET = var.destination_dump_bucket
      DESTINATION_PREFIX = var.destination_dump_prefix
    }
  }
}

resource "aws_cloudwatch_log_group" "copy_dumps_lambda_logs" {
  name              = "/aws/lambda/${aws_lambda_function.copy_dumps.function_name}"
  retention_in_days = var.log_retention
}

resource "aws_lambda_permission" "allow_s3_invoke_copy" {
  statement_id  = "AllowExecutionFromS3BucketCopy"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.copy_dumps.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = module.dump-s3.bucket_arn
}

# S3 Bucket Notifications
resource "aws_s3_bucket_notification" "dump_bucket_notification" {
  bucket = module.dump-s3.bucket_id

  lambda_function {
    id                  = "anonymize-dumps"
    lambda_function_arn = aws_lambda_function.anonymize_dumps.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = local.dump_s3_prefix
    filter_suffix       = ".sql"
  }

  lambda_function {
    id                  = "copy-anonymized-dumps"
    lambda_function_arn = aws_lambda_function.copy_dumps.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = local.anonymized_s3_prefix
    filter_suffix       = ".sql"
  }

  depends_on = [
    aws_lambda_permission.allow_s3_invoke,
    aws_lambda_permission.allow_s3_invoke_copy,
  ]
}
