# run_congestion/l2_blob.py
import os
import urllib.request
from typing import Optional

# If unset, L2 is disabled.
BLOB_READ_WRITE_URL = os.getenv("BLOB_READ_WRITE_URL", "").strip()

def is_enabled() -> bool:
    return bool(BLOB_READ_WRITE_URL)

def _blob_url(key: str) -> str:
    base = BLOB_READ_WRITE_URL.rstrip("/")
    return f"{base}/{key.lstrip('/')}"

def put_text(key: str, text: str) -> str:
    if not is_enabled():
        return ""
    data = text.encode("utf-8")
    req = urllib.request.Request(_blob_url(key), data=data, method="PUT")
    req.add_header("Content-Type", "text/plain; charset=utf-8")
    with urllib.request.urlopen(req) as r:
        return r.read().decode("utf-8", errors="ignore") or "ok"

def get_text(key: str) -> Optional[str]:
    if not is_enabled():
        return None
    try:
        with urllib.request.urlopen(_blob_url(key)) as r:
            return r.read().decode("utf-8")
    except Exception:
        return None
