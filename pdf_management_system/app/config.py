import os
from dotenv import load_dotenv

load_dotenv()

# Storage configuration: 's3' or 'minio'
STORAGE_PROVIDER = os.getenv("STORAGE_PROVIDER", "s3").lower()

# AWS S3 Settings
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME", os.getenv("MINIO_BUCKET", "company-documents"))
S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL")  # Optional: for MinIO or custom S3-compatible endpoints

# MinIO backwards-compatibility fallbacks
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "minio:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", AWS_ACCESS_KEY_ID or "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", AWS_SECRET_ACCESS_KEY or "minioadmin")
MINIO_BUCKET = S3_BUCKET_NAME
MINIO_SECURE = os.getenv("MINIO_SECURE", "false").lower() == "true"

# Local upload directory
UPLOAD_DIRECTORY = os.getenv("UPLOAD_DIRECTORY", "upload_pdf")

# PostgreSQL / RDS Database Settings
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/pdf_management"
)