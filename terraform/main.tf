terraform {
  required_version = ">= 1.5.0"
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

# -------------------------------------------------
# 1. S3 bucket (single bucket, you can enable versioning/replication later)
# -------------------------------------------------
resource "aws_s3_bucket" "media" {
  bucket = var.s3_bucket_name
  acl    = "private"
}

# -------------------------------------------------
# 2. PostgreSQL – using Amazon RDS (single‑AZ for quick test)
# -------------------------------------------------
resource "aws_db_instance" "postgres" {
  identifier          = var.db_identifier
  engine              = "postgres"
  engine_version      = "15"
  instance_class      = "db.t4g.micro"
  allocated_storage   = 20
  username            = var.db_username
  password            = var.db_password
  skip_final_snapshot = true
  publicly_accessible = true   # for local testing; tighten later
  availability_zone   = data.aws_availability_zones.available.names[0]
}

# -------------------------------------------------
# 3. IAM role for the backend container (optional – you can also rely on env vars)
# -------------------------------------------------
resource "aws_iam_role" "backend_role" {
  name = "backend-s3-access"
  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Effect    = "Allow",
      Principal = { Service = "ecs-tasks.amazonaws.com" },
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_policy" "s3_put" {
  name   = "backend-s3-put"
  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Effect   = "Allow",
      Action   = ["s3:PutObject"],
      Resource = "${aws_s3_bucket.media.arn}/*"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "attach" {
  role       = aws_iam_role.backend_role.name
  policy_arn = aws_iam_policy.s3_put.arn
}
