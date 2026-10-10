import io
from typing import Any
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse

from app.config import S3_BUCKET_NAME, STORAGE_PROVIDER
from app.database import log_activity
from app.storage import (
    bucket_storage_stats,
    delete_object,
    get_object_stream,
    list_objects,
    put_object_data,
)

router = APIRouter(prefix="/s3", tags=["s3"])
# Also support /minio endpoint for backwards compatibility
minio_router = APIRouter(prefix="/minio", tags=["minio_compat"])


@router.get("/files")
@minio_router.get("/files")
def get_files(prefix: str = "") -> dict[str, Any]:
    try:
        if prefix and not prefix.endswith("/"):
            prefix += "/"
        obj_list = list_objects(prefix=prefix)
        return {
            "provider": STORAGE_PROVIDER,
            "bucket": S3_BUCKET_NAME,
            "prefix": prefix,
            "objects": obj_list,
            "count": len(obj_list),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/upload")
@minio_router.post("/upload")
async def upload_custom_pdf(
    request: Request,
    file: UploadFile = File(...),
    folder: str = Form(""),
) -> dict[str, Any]:
    filename = file.filename or ""
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")

    object_name = filename
    if folder:
        folder_clean = folder.strip("/")
        object_name = f"{folder_clean}/{filename}"

    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    try:
        result = put_object_data(
            object_name=object_name,
            data=io.BytesIO(content),
            content_type="application/pdf",
            length=len(content),
        )

        # Log User Activity to PostgreSQL
        log_activity(
            action="UPLOAD_OBJECT_STORAGE",
            filename=object_name,
            storage_type=STORAGE_PROVIDER,
            file_size_bytes=len(content),
            ip_address=client_ip,
            user_agent=user_agent,
            details=f"Uploaded directly to {STORAGE_PROVIDER.upper()} bucket {S3_BUCKET_NAME}",
        )

        return {
            "message": "File uploaded successfully",
            "provider": STORAGE_PROVIDER,
            "filename": filename,
            "object_name": object_name,
            "storage": result,
            "minio": result,  # backwards compatibility with existing UI
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/download/{object_name:path}")
@minio_router.get("/download/{object_name:path}")
def download_storage_file(request: Request, object_name: str) -> StreamingResponse:
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    filename = object_name.split("/")[-1]

    try:
        stream = get_object_stream(object_name)

        # Log User Activity to PostgreSQL
        log_activity(
            action="DOWNLOAD_OBJECT_STORAGE",
            filename=object_name,
            storage_type=STORAGE_PROVIDER,
            ip_address=client_ip,
            user_agent=user_agent,
            details=f"Downloaded from {STORAGE_PROVIDER.upper()}",
        )

        # Support streaming for botocore StreamingBody or MinIO response
        def iterfile():
            if hasattr(stream, "iter_chunks") and callable(getattr(stream, "iter_chunks")):
                for chunk in stream.iter_chunks(32 * 1024):
                    yield chunk
            elif hasattr(stream, "stream") and callable(getattr(stream, "stream")):
                for chunk in stream.stream(32 * 1024):
                    yield chunk
            elif hasattr(stream, "read") and callable(getattr(stream, "read")):
                while True:
                    chunk = stream.read(32 * 1024)
                    if not chunk:
                        break
                    yield chunk

        return StreamingResponse(
            iterfile(),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"File not found: {e}")


@router.delete("/delete/{object_name:path}")
@minio_router.delete("/delete/{object_name:path}")
def delete_storage_file(request: Request, object_name: str) -> dict[str, Any]:
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    try:
        delete_object(object_name)

        # Log User Activity to PostgreSQL
        log_activity(
            action="DELETE_OBJECT_STORAGE",
            filename=object_name,
            storage_type=STORAGE_PROVIDER,
            ip_address=client_ip,
            user_agent=user_agent,
            details=f"Deleted from {STORAGE_PROVIDER.upper()}",
        )

        return {
            "message": "File deleted",
            "provider": STORAGE_PROVIDER,
            "object_name": object_name,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/folder")
@minio_router.post("/folder")
def create_storage_folder(request: Request, folder_name: str = Form(...)) -> dict[str, Any]:
    folder_clean = folder_name.strip("/")
    if not folder_clean:
        raise HTTPException(status_code=400, detail="Invalid folder name")

    object_name = f"{folder_clean}/.keep"
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    try:
        put_object_data(
            object_name=object_name,
            data=io.BytesIO(b""),
            content_type="application/x-empty",
            length=0,
        )

        log_activity(
            action="CREATE_FOLDER",
            filename=folder_clean,
            storage_type=STORAGE_PROVIDER,
            ip_address=client_ip,
            user_agent=user_agent,
            details=f"Created folder in {STORAGE_PROVIDER.upper()}",
        )

        return {
            "message": "Folder created",
            "provider": STORAGE_PROVIDER,
            "bucket": S3_BUCKET_NAME,
            "folder": folder_clean,
            "marker": object_name,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
@minio_router.get("/stats")
def get_storage_stats() -> dict[str, Any]:
    try:
        stats = bucket_storage_stats()
        return {
            "provider": STORAGE_PROVIDER,
            "total_bytes": stats["bytes"],
            "total_files": stats["object_count"],
            "total_folders": len(stats["prefix_counts"]),
            "bucket": stats["bucket"],
            "bytes": stats["bytes"],
            "object_count": stats["object_count"],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
