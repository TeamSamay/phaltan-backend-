"""Local, non-production microbenchmark; reports observed values, never estimates."""
import argparse
import statistics
import time
from datetime import datetime, timezone
from uuid import uuid4
import httpx
import psutil


def percentile(values: list[float], pct: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int((len(ordered) - 1) * pct))]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--count", type=int, default=100)
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    process = psutil.Process()
    client = httpx.Client(base_url=base, timeout=20)
    device = f"bench-{uuid4().hex[:8]}"
    client.post("/api/v1/devices/register", json={"device_id": device}).raise_for_status()
    exp = client.post("/api/v1/experiments", json={"name": "Benchmark run"}).json()
    experiment_id = exp["experiment_id"]
    client.post(f"/api/v1/experiments/{experiment_id}/start").raise_for_status()
    latency_ms = []
    db_write_ms = []
    started = time.perf_counter()
    for i in range(args.count):
        payload = {"schema_version": "1.0", "event_id": str(uuid4()), "source": "benchmark",
                   "device_id": device, "experiment_id": experiment_id,
                   "timestamp": datetime.now(timezone.utc).isoformat(), "event_type": "HEARTBEAT",
                   "evidence": {"sequence": i}}
        tick = time.perf_counter()
        response = client.post("/api/v1/events", json=payload)
        elapsed = (time.perf_counter() - tick) * 1000
        response.raise_for_status()
        latency_ms.append(elapsed)
        db_write_ms.append(elapsed)  # ingestion includes persistence; isolated SQL timing is not exposed.
    duration = time.perf_counter() - started
    print({"count": args.count, "elapsed_seconds": round(duration, 4),
           "event_throughput_per_second": round(args.count / duration, 2),
           "api_latency_ms_median": round(statistics.median(latency_ms), 3),
           "api_latency_ms_p95": round(percentile(latency_ms, .95), 3),
           "ingestion_plus_db_write_ms_median": round(statistics.median(db_write_ms), 3),
           "process_memory_bytes": process.memory_info().rss,
           "websocket_latency": "not measured by this HTTP-only script; use docs/benchmarking.md"})
    client.close()


if __name__ == "__main__":
    main()
