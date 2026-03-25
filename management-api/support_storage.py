from __future__ import annotations

from base64 import b64decode, b64encode
from pathlib import Path
from typing import Any, Optional
import os
from uuid import uuid4

SUPPORT_ATTACHMENT_STORAGE_ROOT = Path(
    os.getenv(
        "SUPPORT_ATTACHMENT_STORAGE_ROOT",
        str(Path(__file__).resolve().parent / "storage" / "support-attachments"),
    )
)


def support_attachment_safe_filename(filename: str) -> str:
    base = Path(filename or "").name.strip()
    return base[:120] if base else "attachment"


def _resolved_storage_root() -> Path:
    root = SUPPORT_ATTACHMENT_STORAGE_ROOT.resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _resolve_storage_ref_path(storage_ref: str) -> Optional[Path]:
    if not storage_ref:
        return None

    raw_ref = str(storage_ref).strip().replace("\\", "/")
    rel = Path(raw_ref)
    if rel.is_absolute() or ".." in rel.parts:
        return None

    root = _resolved_storage_root()
    abs_path = (root / rel).resolve()
    try:
        abs_path.relative_to(root)
    except ValueError:
        return None
    return abs_path


def support_attachment_write_bytes(ticket_id: int, filename: str, content: bytes) -> str:
    rel_path = Path(f"ticket-{ticket_id}") / f"{uuid4().hex}_{support_attachment_safe_filename(filename)}"
    abs_path = _resolved_storage_root() / rel_path
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_bytes(content)
    return rel_path.as_posix()


def support_attachment_read_bytes(attachment: Any) -> bytes:
    storage_ref = getattr(attachment, "storage_ref", None) or ""
    if storage_ref:
        abs_path = _resolve_storage_ref_path(storage_ref)
        if abs_path and abs_path.exists():
            try:
                return abs_path.read_bytes()
            except OSError:
                return b""

    file_data = getattr(attachment, "file_data", None) or ""
    if not file_data:
        return b""
    try:
        return b64decode(file_data)
    except Exception:
        return b""


def support_attachment_download_url(attachment: Any) -> str:
    content_type = (getattr(attachment, "content_type", None) or "application/octet-stream").strip()
    content = support_attachment_read_bytes(attachment)
    encoded = b64encode(content).decode("ascii") if content else ""
    return f"data:{content_type};base64,{encoded}"
