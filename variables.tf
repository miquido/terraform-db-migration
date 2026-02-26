variable "project" {
  description = "Project name"
  type        = string
}

variable "environment" {
  description = "Environment name"
  type        = string
}

variable "region" {
  description = "AWS region"
  type        = string
}

variable "ecs_cluster_arn" {
  description = "ECS cluster ARN for running pg_dump task"
  type        = string
}

variable "subnet_ids" {
  description = "Subnet IDs for ECS tasks"
  type        = list(string)
}

variable "security_group_ids" {
  description = "Security group IDs for ECS tasks"
  type        = list(string)
}

variable "db_host" {
  description = "Database host"
  type        = string
}

variable "db_name" {
  description = "Database name"
  type        = string
}

variable "db_user" {
  description = "Database user"
  type        = string
}

variable "db_port" {
  description = "Database port"
  type        = string
}

variable "db_password_ssm_name" {
  description = "SSM parameter name for database password"
  type        = string
}

variable "db_password_ssm_arn" {
  description = "SSM parameter ARN for database password"
  type        = string
}

variable "sns_error_topic_arn" {
  description = "SNS topic ARN for error notifications"
  type        = string
}

variable "log_retention" {
  description = "CloudWatch log retention in days"
  type        = number
  default     = 7
}

variable "schedule_expression" {
  description = "Cron expression for pg_dump schedule"
  type        = string
  default     = null
}

variable "destination_dump_bucket" {
  description = "Destination S3 bucket for copying anonymized dumps"
  type        = string
}

variable "destination_dump_prefix" {
  description = "Prefix for dumps in destination bucket"
  type        = string
  default     = "dumps/"
}

variable "anonymization_rules_file" {
  description = "Path to Python file containing anonymization rules (ANONYMIZATION_RULES variable)"
  type        = string
  default     = ""
}
