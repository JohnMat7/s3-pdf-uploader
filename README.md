# FastAPI S3 Upload Service

This repository contains a minimal FastAPI application that lets users upload files to Amazon S3 and records each upload activity in a PostgreSQL database.

## Directory layout
```
fastapi_s3_upload/
├─ app/
│  ├─ __init__.py        # package marker
│  ├─ main.py            # FastAPI entrypoint
│  ├─ models.py          # SQLAlchemy models
│  └─ database.py        # DB engine & session helper
├─ static/
│  └─ index.html         # Simple HTML upload page
├─ Dockerfile            # Build FastAPI image
├─ docker-compose.yml    # Compose services (app, db, localstack)
└─ requirements.txt      # Python dependencies
```

## Prerequisites
- Docker & Docker Compose installed.
- AWS credentials (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`) that have permission to put objects into the target S3 bucket.
- An existing S3 bucket name set via the `S3_BUCKET` environment variable.

## Running locally
```bash
# Copy this repository or navigate to the project directory
cd /home/johnmat/Documents/Projects/fastapi_s3_upload

# (Optional) Create a .env file with required env vars for convenience:
cat > .env <<EOF
AWS_ACCESS_KEY_ID=your_key_id
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_REGION=us-east-1
S3_BUCKET=your-bucket-name
EOF

# Start services (PostgreSQL, FastAPI app, and a localstack S3 emulator)
docker compose up --build
```
The FastAPI server will be reachable at `http://localhost:8000`. Open that URL in a browser to see the upload page.

## Using the service
1. Fill in a **User** name and select a file.
2. Click **Upload**.
3. The response displays the uploaded file information, including a public S3 URL and the database record ID.

## Notes
- The `docker-compose.yml` includes a `localstack` service for local S3 testing. If you prefer to use real AWS S3, keep the container running but ignore the `localstack` service or remove it.
- The FastAPI app uses SQLAlchemy's declarative base to create the `activities` table automatically on startup.
- Adjust the bucket policy or generate presigned URLs if you need restricted access.

