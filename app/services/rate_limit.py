from collections import defaultdict, deque
from time import monotonic
from fastapi import HTTPException


class RateLimiter:
    def __init__(self, limit: int, window_seconds: int = 60):
        self.limit, self.window = limit, window_seconds
        self.hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> None:
        now = monotonic()
        bucket = self.hits[key]
        while bucket and now - bucket[0] > self.window:
            bucket.popleft()
        if len(bucket) >= self.limit:
            raise HTTPException(429, detail={"code": "rate_limited", "message": "Request rate limit exceeded"})
        bucket.append(now)
