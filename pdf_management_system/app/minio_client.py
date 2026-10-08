"""
Backward compatibility layer for minio_client.
Redirects calls to the unified storage module (AWS S3 / MinIO).
"""
from app.storage import (
    bucket_storage_stats,
    create_bucket_if_not_exists,
    delete_object,
    get_object_stream,
    list_objects,
    minio_client as client,
    object_name_folder,
    put_object_data,
    s3_client,
    upload_file,
)

__all__ = [
    "client",
    "s3_client",
    "create_bucket_if_not_exists",
    "upload_file",
    "delete_object",
    "bucket_storage_stats",
    "object_name_folder",
    "put_object_data",
    "get_object_stream",
    "list_objects",
]
