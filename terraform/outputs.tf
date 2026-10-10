output "s3_bucket_name" {
  description = "Name of the S3 bucket"
  value       = aws_s3_bucket.media.id
}

output "postgres_endpoint" {
  description = "RDS endpoint for Postgres"
  value       = aws_db_instance.postgres.endpoint
}
