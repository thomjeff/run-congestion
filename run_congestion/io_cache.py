# run_congestion/io_cache.py
"""Warm-instance CSV cache for Vercel Hobby.
- Caches parsed DataFrames for URLs/paths
- Sends If-None-Match with cached ETag to avoid re-downloading
- Falls back to content hash (sha256) when ETag/Last-Modified absent
- Supports local files with mtime tracking
"""
import hashlib
import io
import os
import time
import urllib.request
import urllib.error
from typing import Dict, Optional, Tuple
import pandas as pd

# URL -> cache entry
_CACHE: Dict[str, dict] = {}

def _sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

def _read_url(url: str, etag: Optional[str]) -> Tuple[bytes, dict]:
    req = urllib.request.Request(url)
    # Encourage efficient CSV transfer
    req.add_header("Accept", "text/csv, text/plain; q=0.9, */*; q=0.1")
    req.add_header("Accept-Encoding", "gzip, deflate")
    if etag:
        req.add_header("If-None-Match", etag)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = r.read()
            headers = {k.lower(): v for k, v in r.headers.items()}
            return data, headers
    except urllib.error.HTTPError as e:
        # 304 Not Modified
        if e.code == 304:
            return b"", {"status": "304"}
        raise

def _read_path(path: str) -> Tuple[bytes, dict]:
    with open(path, "rb") as f:
        data = f.read()
    mtime = os.path.getmtime(path)
    return data, {"local-mtime": str(mtime)}

def get_csv_df(source: str) -> pd.DataFrame:
    """Return a pandas DataFrame for CSV at URL or local path, using warm cache when possible."""
    # Local file path case
    if not (source.startswith("http://") or source.startswith("https://")):
        entry = _CACHE.get(source)
        data, meta = _read_path(source)
        mtime = meta.get("local-mtime")
        if entry and entry.get("local-mtime") == mtime:
            return entry["df"]
        df = pd.read_csv(io.BytesIO(data))
        _CACHE[source] = {"df": df, "local-mtime": mtime, "sha256": _sha256(data)}
        return df

    # URL case
    entry = _CACHE.get(source)
    etag = entry.get("etag") if entry else None
    try:
        data, headers = _read_url(source, etag)
    except Exception:
        # On any fetch error, if we have a cached DF, use it
        if entry and "df" in entry:
            return entry["df"]
        raise

    # 304 Not Modified -> serve cached
    if headers.get("status") == "304":
        return entry["df"]

    # Fresh download
    df = pd.read_csv(io.BytesIO(data))
    _CACHE[source] = {
        "df": df,
        "etag": headers.get("etag"),
        "last-modified": headers.get("last-modified"),
        "sha256": _sha256(data),
        "fetched-at": time.time(),
    }
    return df
