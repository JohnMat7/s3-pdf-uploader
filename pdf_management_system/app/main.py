import shutil
from datetime import datetime, timezone
from pathlib import Path

import uvicorn
from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import STORAGE_PROVIDER, UPLOAD_DIRECTORY
from app.database import (
    UserActivity,
    get_db,
    init_db,
    log_activity,
)
from app.minio_routes import minio_router, router as s3_router
from app.paths import normalize_relative_path, resolve_under_root
from app.storage import (
    bucket_storage_stats,
    create_bucket_if_not_exists,
    delete_object,
    upload_file,
)

app = FastAPI(
    title="PDF S3/MinIO Management System",
    description="Manage PDF folders locally and sync with AWS S3 / MinIO, with PostgreSQL activity auditing",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include both S3 and MinIO backward compatibility routers
app.include_router(s3_router)
app.include_router(minio_router)

upload_directory = Path(UPLOAD_DIRECTORY if UPLOAD_DIRECTORY.startswith("/") else f"/app/{UPLOAD_DIRECTORY}")


class CreateFolderRequest(BaseModel):
    parent: str = ""
    name: str = Field(..., min_length=1, max_length=128)


def local_storage_stats() -> dict:
    total_bytes = 0
    file_count = 0
    folder_count = 0

    if upload_directory.exists():
        for path in upload_directory.rglob("*"):
            if path.is_file() and path.suffix.lower() == ".pdf":
                file_count += 1
                total_bytes += path.stat().st_size
            elif path.is_dir():
                folder_count += 1

    return {
        "directory": str(upload_directory),
        "bytes": total_bytes,
        "pdf_count": file_count,
        "folder_count": max(folder_count - 1, 0),
    }


def file_entry(path: Path) -> dict:
    stat = path.stat()
    relative = path.relative_to(upload_directory).as_posix()
    return {
        "name": path.name,
        "path": relative,
        "size": stat.st_size,
        "modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
    }


def ensure_pdf_filename(name: str) -> str:
    if not name.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")
    return name


@app.on_event("startup")
def startup_event():
    upload_directory.mkdir(parents=True, exist_ok=True)
    create_bucket_if_not_exists()
    init_db()


@app.get("/health")
def health():
    return {
        "status": "UP",
        "service": "pdf-s3-uploader",
        "storage_provider": STORAGE_PROVIDER,
    }


@app.get("/storage/usage")
def storage_usage():
    try:
        remote_stats = bucket_storage_stats()
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to read storage usage: {error!s}",
        )

    return {
        "local": local_storage_stats(),
        "s3": remote_stats,
        "minio": remote_stats,  # backward compatibility with frontend
    }


@app.get("/browse")
def browse(path: str = Query(default="", description="Folder path relative to upload root")):
    folder = resolve_under_root(upload_directory, path)
    if not folder.is_dir():
        raise HTTPException(status_code=404, detail="Folder not found")

    folders = sorted(
        entry.name
        for entry in folder.iterdir()
        if entry.is_dir() and not entry.name.startswith(".")
    )
    files = sorted(
        (file_entry(entry) for entry in folder.iterdir() if entry.is_file() and entry.suffix.lower() == ".pdf"),
        key=lambda item: item["name"].lower(),
    )

    relative = (
        folder.relative_to(upload_directory).as_posix()
        if folder != upload_directory.resolve()
        else ""
    )

    return {
        "path": relative,
        "folders": folders,
        "files": files,
        "file_count": len(files),
    }


@app.get("/files")
def list_files():
    files = []
    if upload_directory.exists():
        for file in upload_directory.rglob("*.pdf"):
            if file.is_file():
                files.append(file.relative_to(upload_directory).as_posix())

    files.sort()
    return {
        "directory": str(upload_directory),
        "files": files,
        "count": len(files),
    }


@app.post("/folders")
def create_folder(request: Request, body: CreateFolderRequest):
    parent = normalize_relative_path(body.parent)
    name = body.name.strip().strip("/")
    if not name or "/" in name or name in (".", ".."):
        raise HTTPException(status_code=400, detail="Invalid folder name")

    target = resolve_under_root(upload_directory, f"{parent}/{name}" if parent else name)
    if target.exists():
        raise HTTPException(status_code=409, detail="Folder already exists")

    target.mkdir(parents=True, exist_ok=False)

    log_activity(
        action="CREATE_LOCAL_FOLDER",
        filename=target.relative_to(upload_directory).as_posix(),
        storage_type="local",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return {
        "message": "Folder created",
        "path": target.relative_to(upload_directory).as_posix(),
    }


@app.post("/files")
async def upload_pdf_file(
    request: Request,
    file: UploadFile = File(...),
    folder: str = Query(default="", description="Destination folder relative to upload root"),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename")

    filename = ensure_pdf_filename(Path(file.filename).name)
    dest_dir = resolve_under_root(upload_directory, folder)
    if not dest_dir.is_dir():
        raise HTTPException(status_code=404, detail="Destination folder not found")

    dest_path = dest_dir / filename
    if dest_path.exists():
        raise HTTPException(status_code=409, detail="File already exists")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")

    try:
        dest_path.write_bytes(content)
    except OSError as error:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {error!s}")

    log_activity(
        action="UPLOAD_LOCAL_FILE",
        filename=dest_path.relative_to(upload_directory).as_posix(),
        storage_type="local",
        file_size_bytes=len(content),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return {
        "message": "File uploaded successfully",
        "file": file_entry(dest_path),
    }


@app.get("/files/download")
def download_file(request: Request, path: str = Query(..., description="Relative path to PDF")):
    file_path = resolve_under_root(upload_directory, path)
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    if file_path.suffix.lower() != ".pdf":
        raise HTTPException(status_code=400, detail="Only PDF files can be downloaded")

    log_activity(
        action="DOWNLOAD_LOCAL_FILE",
        filename=file_path.relative_to(upload_directory).as_posix(),
        storage_type="local",
        file_size_bytes=file_path.stat().st_size,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return FileResponse(
        path=file_path,
        media_type="application/pdf",
        filename=file_path.name,
    )


@app.delete("/files")
def delete_file(request: Request, path: str = Query(..., description="Relative path to PDF")):
    file_path = resolve_under_root(upload_directory, path)
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    if file_path.suffix.lower() != ".pdf":
        raise HTTPException(status_code=400, detail="Only PDF files can be deleted")

    relative = file_path.relative_to(upload_directory).as_posix()
    remote_removed = False
    remote_error = None

    try:
        delete_object(relative)
        remote_removed = True
    except Exception as error:
        remote_error = str(error)

    try:
        file_path.unlink()
    except OSError as error:
        raise HTTPException(status_code=500, detail=f"Failed to delete file: {error!s}")

    log_activity(
        action="DELETE_LOCAL_FILE",
        filename=relative,
        storage_type="local",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return {
        "message": "File deleted",
        "path": relative,
        "remote_removed": remote_removed,
        "remote_error": remote_error,
        "minio_removed": remote_removed,
        "minio_error": remote_error,
    }


@app.post("/upload/{filename:path}")
def upload_pdf_to_remote(request: Request, filename: str):
    file_path = resolve_under_root(upload_directory, filename)

    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"File not found: {filename}",
        )

    if not file_path.is_file():
        raise HTTPException(
            status_code=400,
            detail=f"{filename} is not a file",
        )

    if file_path.suffix.lower() != ".pdf":
        raise HTTPException(
            status_code=400,
            detail="Only PDF files are allowed",
        )

    object_name = file_path.relative_to(upload_directory).as_posix()

    try:
        result = upload_file(
            file_path=str(file_path),
            object_name=object_name,
        )

        log_activity(
            action=f"SYNC_{STORAGE_PROVIDER.upper()}",
            filename=object_name,
            storage_type=STORAGE_PROVIDER,
            file_size_bytes=file_path.stat().st_size,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            details=f"Synced local file to {STORAGE_PROVIDER.upper()}",
        )

        return {
            "message": "File uploaded successfully",
            "filename": object_name,
            "provider": STORAGE_PROVIDER,
            "storage": result,
            "minio": result,
        }

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Upload failed: {error!s}",
        )


@app.post("/upload-all")
def upload_all_pdfs(request: Request, folder: str = Query(default="", description="Limit to folder subtree")):
    root = resolve_under_root(upload_directory, folder)
    if not root.is_dir():
        raise HTTPException(status_code=404, detail="Folder not found")

    pdf_files = [file for file in root.rglob("*.pdf") if file.is_file()]
    uploaded = []
    failed = []

    for file_path in pdf_files:
        object_name = file_path.relative_to(upload_directory).as_posix()
        try:
            result = upload_file(
                file_path=str(file_path),
                object_name=object_name,
            )

            uploaded.append({
                "filename": object_name,
                "storage": result,
                "minio": result,
            })

            log_activity(
                action=f"SYNC_{STORAGE_PROVIDER.upper()}",
                filename=object_name,
                storage_type=STORAGE_PROVIDER,
                file_size_bytes=file_path.stat().st_size,
                ip_address=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent"),
            )

        except Exception as error:
            failed.append({
                "filename": object_name,
                "error": f"{error!s}",
            })

    return {
        "message": "Upload process completed",
        "provider": STORAGE_PROVIDER,
        "uploaded": uploaded,
        "failed": failed,
        "uploaded_count": len(uploaded),
        "failed_count": len(failed),
    }


@app.delete("/folders")
def delete_folder(request: Request, path: str = Query(..., description="Relative folder path")):
    folder = resolve_under_root(upload_directory, path)
    if folder == upload_directory.resolve():
        raise HTTPException(status_code=400, detail="Cannot delete root upload directory")
    if not folder.is_dir():
        raise HTTPException(status_code=404, detail="Folder not found")

    try:
        shutil.rmtree(folder)
    except OSError as error:
        raise HTTPException(status_code=500, detail=f"Failed to delete folder: {error!s}")

    log_activity(
        action="DELETE_LOCAL_FOLDER",
        filename=path,
        storage_type="local",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return {"message": "Folder deleted", "path": path}


# New endpoint to query user activity metadata from PostgreSQL
@app.get("/activities")
def get_user_activities(
    limit: int = Query(50, ge=1, le=200),
    action: str = Query(None),
    db: Session = Depends(get_db),
):
    try:
        query = db.query(UserActivity).order_by(UserActivity.created_at.desc())
        if action:
            query = query.filter(UserActivity.action == action)
        activities = query.limit(limit).all()
        return [
            {
                "id": a.id,
                "user_id": a.user_id,
                "action": a.action,
                "filename": a.filename,
                "storage_type": a.storage_type,
                "file_size_bytes": a.file_size_bytes,
                "ip_address": a.ip_address,
                "details": a.details,
                "created_at": a.created_at.isoformat() if getattr(a, "created_at", None) is not None else None,
            }
            for a in activities
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch activities: {e}")


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",  # nosec B104
        port=8080,
        reload=True,
    )
