import os
import uuid
from datetime import datetime

import boto3
from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel

from .database import SessionLocal, engine
from . import models
from .models import Base
# Create tables
Base.metadata.create_all(bind=engine)

# Ensure DB tables exist (models will be imported elsewhere for metadata creation)

app = FastAPI()

# Mount static files (frontend) directory
# Static files are served by the separate Nginx container (frontend service)

# Initialize S3 client using environment variables
s3_client = boto3.client(
    "s3",
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    region_name=os.getenv("AWS_REGION", "us-east-1"),
    endpoint_url=os.getenv("S3_ENDPOINT_URL"),  # optional, used for local testing with LocalStack
)

S3_BUCKET = os.getenv("S3_BUCKET")
if not S3_BUCKET:
    raise RuntimeError("S3_BUCKET environment variable not set")

@app.get("/", response_class=RedirectResponse)
async def read_root():
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:8080")
    return RedirectResponse(url=frontend_url)

class UploadResponse(BaseModel):
    filename: str
    s3_key: str
    url: str
    record_id: int

@app.post("/upload", response_model=UploadResponse)
async def upload_file(user: str = Form(...), file: UploadFile = File(...)):
    # Generate a unique S3 key for the object
    ext = os.path.splitext(file.filename)[1]
    s3_key = f"uploads/{uuid.uuid4().hex}{ext}"

    # Read the file content
    try:
        contents = await file.read()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read file: {e}")

    # Upload to S3
    try:
        s3_client.put_object(Bucket=S3_BUCKET, Key=s3_key, Body=contents)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"S3 upload error: {e}")

    # Record activity in PostgreSQL
    db = SessionLocal()
    try:
        activity = models.Activity(
            user=user,
            filename=file.filename,
            s3_key=s3_key,
            uploaded_at=datetime.utcnow(),
        )
        db.add(activity)
        db.commit()
        db.refresh(activity)
    finally:
        db.close()

    # Build public S3 URL (assumes bucket policy allows access)
    s3_url = f"https://{S3_BUCKET}.s3.amazonaws.com/{s3_key}"

    return UploadResponse(
        filename=file.filename,
        s3_key=s3_key,
        url=s3_url,
        record_id=activity.id,
    )
