from pathlib import Path

from fastapi import HTTPException


def normalize_relative_path(relative: str) -> str:
    cleaned = relative.strip().replace("\\", "/").strip("/")
    if not cleaned:
        return ""
    for part in cleaned.split("/"):
        if part in (".", "..", ""):
            raise HTTPException(status_code=400, detail="Invalid path")
    return cleaned


def resolve_under_root(root: Path, relative: str) -> Path:
    normalized = normalize_relative_path(relative)
    target = (root / normalized).resolve() if normalized else root.resolve()
    root_resolved = root.resolve()
    if not str(target).startswith(str(root_resolved)):
        raise HTTPException(status_code=400, detail="Invalid path")
    return target
