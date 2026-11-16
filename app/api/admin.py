"""Staff-only endpoints. Every route here needs the X-Admin-Key header."""
import secrets
from pathlib import Path

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, UploadFile

from app.audit import recent
from app.config import get_settings
from app.rag.ingest import SUPPORTED, ingest_file

MAX_UPLOAD_BYTES = 10 * 1024 * 1024


def require_admin(x_admin_key: str = Header(default="")) -> None:
    key = get_settings().admin_api_key
    if not key or not secrets.compare_digest(x_admin_key.encode(), key.encode()):
        raise HTTPException(status_code=401, detail="Invalid admin key")


router = APIRouter(dependencies=[Depends(require_admin)])


@router.post("/ingest")
def ingest(file: UploadFile = File(...)):
    name = Path(file.filename or "").name  # drop any folder parts from the upload name
    if Path(name).suffix.lower() not in SUPPORTED:
        raise HTTPException(status_code=400, detail=f"Supported types: {', '.join(sorted(SUPPORTED))}")
    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 10 MB)")
    dest = get_settings().upload_dir / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    try:
        chunks = ingest_file(dest)
    except ValueError as exc:  # an empty or unreadable document
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"file": name, "chunks": chunks}


@router.get("/audit")
def audit(limit: int = Query(50, ge=1, le=500)):
    return recent(limit)
