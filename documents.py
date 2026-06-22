"""Просмотр загруженных документов на странице /view."""
import os

PDF_EXTENSIONS = {".pdf"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".bmp"}
TEXT_EXTENSIONS = {
    ".txt", ".md", ".markdown", ".csv", ".json", ".log", ".xml",
    ".yaml", ".yml", ".ini", ".py", ".js", ".css", ".htm", ".html",
}

MAX_TEXT_BYTES = 512_000


def _safe_upload_path(file_path: str, base_dir: str) -> str | None:
    rel = (file_path or "").replace("\\", "/").lstrip("/")
    if not rel or ".." in rel.split("/"):
        return None
    uploads_root = os.path.normpath(os.path.join(base_dir, "uploads"))
    abs_path = os.path.normpath(os.path.join(base_dir, rel))
    if not abs_path.startswith(uploads_root + os.sep) and abs_path != uploads_root:
        return None
    return abs_path if os.path.isfile(abs_path) else None


def get_document_view(file_path: str, base_dir: str) -> dict:
    """Метаданные для рендера документа в view.html."""
    abs_path = _safe_upload_path(file_path, base_dir)
    if not abs_path:
        return {"kind": "missing"}

    ext = os.path.splitext(abs_path)[1].lower()
    filename = os.path.basename(abs_path)

    if ext in PDF_EXTENSIONS:
        return {"kind": "pdf", "filename": filename, "ext": ext}

    if ext in IMAGE_EXTENSIONS:
        return {"kind": "image", "filename": filename, "ext": ext}

    if ext in TEXT_EXTENSIONS:
        try:
            with open(abs_path, "rb") as f:
                raw = f.read(MAX_TEXT_BYTES + 1)
        except OSError:
            return {"kind": "missing"}
        truncated = len(raw) > MAX_TEXT_BYTES
        if truncated:
            raw = raw[:MAX_TEXT_BYTES]
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("utf-8", errors="replace")
        return {
            "kind": "text",
            "filename": filename,
            "ext": ext,
            "text": text,
            "truncated": truncated,
        }

    return {"kind": "download", "filename": filename, "ext": ext}
