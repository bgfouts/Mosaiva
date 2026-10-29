import uuid
from pathlib import Path

from app.settings import PAPERS_DIR, get_settings

SEED_PAPERS_DIR = Path(__file__).resolve().parent.parent / "data" / "seed_papers"
BLOB_PREFIX = "blob:"
SEED_PREFIX = "seed:"


def seed_location(relative: str) -> str:
    return f"{SEED_PREFIX}{relative}"


def save_pdf(body: bytes) -> str:
    """Store a downloaded PDF and return the location to keep on the research row."""
    name = f"{uuid.uuid4().hex}.pdf"
    settings = get_settings()
    if settings.blob_enabled:
        from vercel.blob import sync as blob

        uploaded = blob.put_blob(
            f"papers/{name}",
            body,
            access=settings.mosaiva_blob_access,
            content_type="application/pdf",
        )
        return f"{BLOB_PREFIX}{uploaded.url}"
    PAPERS_DIR.mkdir(parents=True, exist_ok=True)
    path = PAPERS_DIR / name
    path.write_bytes(body)
    return str(path)


def read_pdf(location: str) -> bytes | None:
    if not location:
        return None
    if location.startswith(BLOB_PREFIX):
        from vercel.blob import sync as blob

        result = blob.get_blob(location[len(BLOB_PREFIX):], access=get_settings().mosaiva_blob_access)
        return result.body
    if location.startswith(SEED_PREFIX):
        path = (SEED_PAPERS_DIR / location[len(SEED_PREFIX):]).resolve()
        if SEED_PAPERS_DIR.resolve() not in path.parents:
            return None
    else:
        path = Path(location)
    return path.read_bytes() if path.is_file() else None
