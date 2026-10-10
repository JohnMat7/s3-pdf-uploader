# Simple Uploader Project

This repository contains a minimal example of a Python backend service that uploads files to an Amazon S3 bucket and records user activity in a PostgreSQL database, along with a tiny static frontend served by Nginx. The whole stack is containerised and can be provisioned using Terraform.

## Project Structure
```
simple_uploader_project/
├─ backend/
│  ├─ app.py                # Flask API – upload to S3 & log to Postgres
│  ├─ requirements.txt      # Python dependencies
│  └─ Dockerfile            # Build Flask container (exposes 5000)
├─ frontend/
│  ├─ index.html            # Simple upload form (talks to backend)
│  └─ Dockerfile            # Nginx container serving the HTML (exposes 80)
├─ terraform/
│  ├─ main.tf               # Terraform resources (S3 bucket, RDS, IAM)
│  ├─ variables.tf          # Input variables
│  └─ outputs.tf            # Useful outputs
└─ docker-compose.yml       # Spin up both containers together
```

## Prerequisites
- Docker & Docker Compose
- Terraform (>= 1.5)
- AWS credentials configured (e.g. via `aws configure` or environment variables)

## Setup Steps
1. **Provision infrastructure**
   ```bash
   cd terraform
   terraform init
   terraform apply -auto-approve
   ```
   The apply will create an S3 bucket and an RDS PostgreSQL instance. It will also output the bucket name and the DB endpoint.

2. **Export environment variables for the backend**
   ```bash
   export S3_BUCKET=$(terraform output -raw s3_bucket_name)
   export POSTGRES_DSN="host=$(terraform output -raw postgres_endpoint) dbname=postgres user=admin password=changeme123"
   export AWS_REGION=$(terraform output -raw aws_region || echo us-east-1)
   ```
   Adjust the username/password if you changed the defaults in `variables.tf`.

3. **Build and run the containers**
   ```bash
   cd ..   # back to project root
   docker-compose up --build -d
   ```
   - Backend will be reachable at `http://localhost:5000`
   - Frontend will be reachable at `http://localhost:8080`

4. **Test the upload**
   Open your browser at `http://localhost:8080`, select a file, and click **Upload**. The file will be stored in the S3 bucket under the `uploads/` prefix and a row will be inserted into the `user_activity` table.

## Cleaning Up
```bash
# Stop containers
docker-compose down

# Destroy infrastructure
cd terraform
terraform destroy -auto-approve
```

---

Feel free to ask for any further customisations – e.g. adding a `.docker-compose.override.yml`, enabling multi‑AZ RDS, adding CORS, or wiring the backend to use the IAM role instead of static credentials.
