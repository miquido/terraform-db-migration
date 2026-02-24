output "bucket_id" {
  description = "S3 bucket ID for database dumps"
  value       = module.dump-s3.bucket_id
}

output "bucket_arn" {
  description = "S3 bucket ARN for database dumps"
  value       = module.dump-s3.bucket_arn
}

output "anonymize_lambda_arn" {
  description = "ARN of the anonymize Lambda function"
  value       = aws_lambda_function.anonymize_dumps.arn
}

output "copy_lambda_arn" {
  description = "ARN of the copy dumps Lambda function"
  value       = aws_lambda_function.copy_dumps.arn
}

output "pg_dump_task_arn" {
  description = "ARN of the pg_dump ECS task definition"
  value       = module.pg_dump_task.task_definition_arn
}

