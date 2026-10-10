from typing import Any, BinaryIO, Optional
import io
import boto3
from botocore.exceptions import ClientError
from minio import Minio
from minio.error import S3Error

from app.config import (
    AWS_ACCESS_KEY_ID,
    AWS_REGION,
    AWS_SECRET_ACCESS_KEY,
    MINIO_ACCESS_KEY,
    MINIO_BUCKET,
    MINIO_ENDPOINT,
    MINIO_SECRET_KEY,
    MINIO_SECURE,
    S3_BUCKET_NAME,
    S3_ENDPOINT_URL,
    STORAGE_PROVIDER,
)

# Initialize AWS S3 client via boto3
boto3_kwargs: dict[str, Any] = {"region_name": AWS_REGION}
if AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY:
    boto3_kwargs["aws_access_key_id"] = AWS_ACCESS_KEY_ID
    boto3_kwargs["aws_secret_access_key"] = AWS_SECRET_ACCESS_KEY
if S3_ENDPOINT_URL:
    boto3_kwargs["endpoint_url"] = S3_ENDPOINT_URL

s3_client = boto3.client("s3", **boto3_kwargs)

# Initialize MinIO client for fallback compatibility
minio_client = Minio(
    MINIO_ENDPOINT,
    access_key=MINIO_ACCESS_KEY,
    secret_key=MINIO_SECRET_KEY,
    secure=MINIO_SECURE,
)


def create_bucket_if_not_exists() -> None:
    """Ensure the target bucket exists either on AWS S3 or MinIO."""
    if STORAGE_PROVIDER == "s3":
        try:
            s3_client.head_bucket(Bucket=S3_BUCKET_NAME)
            print(f"S3 Bucket '{S3_BUCKET_NAME}' exists and is accessible.")
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code")
            if error_code in ("404", "NoSuchBucket"):
                print(f"Creating S3 Bucket: {S3_BUCKET_NAME} in region {AWS_REGION}...")
                create_params: dict[str, Any] = {"Bucket": S3_BUCKET_NAME}
                if AWS_REGION != "us-east-1":
                    create_params["CreateBucketConfiguration"] = {
                        "LocationConstraint": AWS_REGION
                    }
                s3_client.create_bucket(**create_params)
                print(f"Created S3 bucket: {S3_BUCKET_NAME}")
            else:
                print(f"Warning checking S3 bucket: {e}")
    else:
        try:
            if not minio_client.bucket_exists(MINIO_BUCKET):
                minio_client.make_bucket(MINIO_BUCKET)
                print(f"Created MinIO bucket: {MINIO_BUCKET}")
            else:
                print(f"MinIO bucket already exists: {MINIO_BUCKET}")
        except S3Error as e:
            print(f"MinIO bucket error: {e}")


def upload_file(file_path: str, object_name: str) -> dict[str, Any]:
    """Upload a file on disk to object storage."""
    if STORAGE_PROVIDER == "s3":
        try:
            s3_client.upload_file(
                Filename=file_path,
                Bucket=S3_BUCKET_NAME,
                Key=object_name,
                ExtraArgs={"ContentType": "application/pdf"},
            )
            head = s3_client.head_object(Bucket=S3_BUCKET_NAME, Key=object_name)
            return {
                "bucket": S3_BUCKET_NAME,
                "object": object_name,
                "etag": head.get("ETag", "").strip('"'),
            }
        except ClientError as e:
            print(f"S3 upload error: {e}")
            raise
    else:
        try:
            result = minio_client.fput_object(
                bucket_name=MINIO_BUCKET,
                object_name=object_name,
                file_path=file_path,
                content_type="application/pdf",
            )
            return {
                "bucket": result.bucket_name,
                "object": result.object_name,
                "etag": result.etag,
            }
        except S3Error as e:
            print(f"MinIO upload error: {e}")
            raise


def put_object_data(
    object_name: str,
    data: BinaryIO,
    content_type: str = "application/pdf",
    length: Optional[int] = None,
) -> dict[str, Any]:
    """Upload bytes/stream to object storage."""
    if STORAGE_PROVIDER == "s3":
        try:
            extra_args = {"ContentType": content_type}
            s3_client.upload_fileobj(
                Fileobj=data,
                Bucket=S3_BUCKET_NAME,
                Key=object_name,
                ExtraArgs=extra_args,
            )
            head = s3_client.head_object(Bucket=S3_BUCKET_NAME, Key=object_name)
            return {
                "bucket": S3_BUCKET_NAME,
                "object": object_name,
                "etag": head.get("ETag", "").strip('"'),
            }
        except ClientError as e:
            print(f"S3 put_object error: {e}")
            raise
    else:
        try:
            if length is None:
                current_pos = data.tell()
                data.seek(0, io.SEEK_END)
                length = data.tell() - current_pos
                data.seek(current_pos)
            result = minio_client.put_object(
                bucket_name=MINIO_BUCKET,
                object_name=object_name,
                data=data,
                length=length,
                content_type=content_type,
            )
            return {
                "bucket": result.bucket_name,
                "object": result.object_name,
                "etag": result.etag,
            }
        except S3Error as e:
            print(f"MinIO put_object error: {e}")
            raise


def get_object_stream(object_name: str) -> Any:
    """Return a stream/body of the object."""
    if STORAGE_PROVIDER == "s3":
        try:
            response = s3_client.get_object(Bucket=S3_BUCKET_NAME, Key=object_name)
            return response["Body"]
        except ClientError as e:
            print(f"S3 get_object error: {e}")
            raise
    else:
        try:
            return minio_client.get_object(MINIO_BUCKET, object_name)
        except S3Error as e:
            print(f"MinIO get_object error: {e}")
            raise


def delete_object(object_name: str) -> None:
    """Delete an object from object storage."""
    if STORAGE_PROVIDER == "s3":
        try:
            s3_client.delete_object(Bucket=S3_BUCKET_NAME, Key=object_name)
        except ClientError as e:
            print(f"S3 delete error: {e}")
            raise
    else:
        try:
            minio_client.remove_object(MINIO_BUCKET, object_name)
        except S3Error as e:
            print(f"MinIO delete error: {e}")
            raise


def list_objects(prefix: str = "") -> list[dict[str, Any]]:
    """List objects/folders with a given prefix."""
    obj_list: list[dict[str, Any]] = []
    if STORAGE_PROVIDER == "s3":
        try:
            paginator = s3_client.get_paginator("list_objects_v2")
            pages = paginator.paginate(
                Bucket=S3_BUCKET_NAME,
                Prefix=prefix,
                Delimiter="/"
            )
            for page in pages:
                # Subdirectories/CommonPrefixes
                for common_prefix in page.get("CommonPrefixes", []):
                    prefix_name = common_prefix.get("Prefix")
                    if prefix_name:
                        obj_list.append({
                            "name": prefix_name,
                            "size": 0,
                            "last_modified": None,
                            "is_dir": True,
                        })
                # Files/Contents
                for item in page.get("Contents", []):
                    key = item.get("Key")
                    if not key or key == prefix:
                        continue
                    last_mod = item.get("LastModified")
                    obj_list.append({
                        "name": key,
                        "size": item.get("Size", 0),
                        "last_modified": last_mod.isoformat() if last_mod else None,
                        "is_dir": key.endswith("/"),
                    })
            return obj_list
        except ClientError as e:
            print(f"S3 list_objects error: {e}")
            raise
    else:
        try:
            objects = minio_client.list_objects(MINIO_BUCKET, prefix=prefix, recursive=False)
            for obj in objects:
                obj_list.append({
                    "name": obj.object_name,
                    "size": obj.size,
                    "last_modified": obj.last_modified.isoformat() if obj.last_modified else None,
                    "is_dir": obj.is_dir,
                })
            return obj_list
        except S3Error as e:
            print(f"MinIO list_objects error: {e}")
            raise


def bucket_storage_stats() -> dict[str, Any]:
    """Calculate bucket stats (total bytes, object count, prefix breakdown)."""
    total_bytes = 0
    object_count = 0
    prefix_counts: dict[str, int] = {}

    if STORAGE_PROVIDER == "s3":
        try:
            paginator = s3_client.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=S3_BUCKET_NAME):
                for item in page.get("Contents", []):
                    key = item.get("Key", "")
                    if key.endswith("/"):
                        continue
                    object_count += 1
                    total_bytes += item.get("Size", 0)
                    prefix = object_name_folder(key)
                    prefix_counts[prefix] = prefix_counts.get(prefix, 0) + 1
            return {
                "bucket": S3_BUCKET_NAME,
                "bytes": total_bytes,
                "object_count": object_count,
                "prefix_counts": prefix_counts,
            }
        except ClientError as e:
            print(f"S3 bucket_storage_stats error: {e}")
            raise
    else:
        try:
            for obj in minio_client.list_objects(MINIO_BUCKET, recursive=True):
                if obj.is_dir:
                    continue
                object_count += 1
                total_bytes += obj.size or 0
                prefix = object_name_folder(obj.object_name or "")
                prefix_counts[prefix] = prefix_counts.get(prefix, 0) + 1
            return {
                "bucket": MINIO_BUCKET,
                "bytes": total_bytes,
                "object_count": object_count,
                "prefix_counts": prefix_counts,
            }
        except S3Error as e:
            print(f"MinIO bucket_storage_stats error: {e}")
            raise


def object_name_folder(object_name: str) -> str:
    if "/" not in object_name:
        return ""
    return object_name.rsplit("/", 1)[0]
