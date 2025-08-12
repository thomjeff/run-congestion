# run_congestion/hashing.py
import base64
import hashlib
import json
import urllib.request
import urllib.error
from typing import Tuple, Optional

def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

def sha256_json(data: dict) -> str:
    # Stable canonical JSON string for keying
    s = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def _is_probably_base64(s: str) -> bool:
    # heuristics: long-ish, only base64 alphabet, no spaces
    if not isinstance(s, str):
        return False
    if "://" in s:
        return False
    if len(s) < 32:
        return False
    try:
        base64.b64decode(s, validate=True)
        return True
    except Exception:
        return False

def fetch_bytes(source: str, timeout: int = 20) -> Tuple[bytes, Optional[str]]:
    """Return (data, mime) for http(s) URL or base64 string or local file path."""
    if _is_probably_base64(source):
        try:
            return base64.b64decode(source, validate=True), None
        except Exception as e:
            raise ValueError(f"Invalid base64 payload: {e}")
    if source.startswith("http://") or source.startswith("https://"):
        try:
            with urllib.request.urlopen(source, timeout=timeout) as r:
                return r.read(), r.headers.get("Content-Type")
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"HTTP error fetching {source}: {e}")
        except urllib.error.URLError as e:
            raise RuntimeError(f"URL error fetching {source}: {e}")
    # Fallback: local path
    with open(source, "rb") as f:
        return f.read(), None
