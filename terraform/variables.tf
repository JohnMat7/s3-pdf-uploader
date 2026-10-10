variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "s3_bucket_name" {
  description = "Name of the S3 bucket for uploads"
  type        = string
  default     = "simple-uploader-demo"
}

variable "db_identifier" {
  description = "RDS instance identifier"
  type        = string
  default     = "simple-uploader-db"
}

variable "db_username" {
  description = "Postgres admin username"
  type        = string
  default     = "admin"
}

variable "db_password" {
  description = "Postgres admin password"
  type        = string
  sensitive   = true
  default     = "changeme123"
}
