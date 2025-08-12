# run_congestion/cache.py
import time
from collections import OrderedDict
from typing import Any, Optional

class LRUCacheTTL:
    def __init__(self, capacity: int = 64, ttl_seconds: int = 600):
        self.capacity = max(1, capacity)
        self.ttl = max(1, ttl_seconds)
        self._store = OrderedDict()  # key -> (expires_at, value)

    def get(self, key: str) -> Optional[Any]:
        now = time.time()
        if key in self._store:
            expires_at, value = self._store[key]
            if expires_at >= now:
                # refresh LRU
                self._store.move_to_end(key)
                return value
            # expired
            del self._store[key]
        return None

    def set(self, key: str, value: Any) -> None:
        now = time.time()
        expires_at = now + self.ttl
        self._store[key] = (expires_at, value)
        self._store.move_to_end(key)
        # evict if needed
        while len(self._store) > self.capacity:
            self._store.popitem(last=False)
