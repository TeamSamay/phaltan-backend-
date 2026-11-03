"""Measure WebSocket broadcast latency and concurrent client fan-out locally."""
import argparse
import asyncio
import json
import statistics
import time
from uuid import uuid4
import httpx
import websockets


async def main_async(args) -> None:
    base = args.base_url.rstrip("/")
    ws_url = base.replace("https://", "wss://").replace("http://", "ws://") + "/ws/dashboard"
    async with websockets.connect(ws_url) as socket:
        ready = json.loads(await socket.recv())
        if ready.get("type") != "connection.ready":
            raise RuntimeError(f"Unexpected WebSocket greeting: {ready}")
        async with httpx.AsyncClient(base_url=base, timeout=15) as client:
            device = f"ws-bench-{uuid4().hex[:8]}"
            registration = await client.post("/api/v1/devices/register", json={"device_id": device})
            registration.raise_for_status()
            latencies_ms = []
            for _ in range(args.count):
                sent = time.perf_counter()
                response = await client.post("/api/v1/devices/heartbeat", json={"device_id": device})
                response.raise_for_status()
                while True:
                    message = json.loads(await asyncio.wait_for(socket.recv(), timeout=5))
                    if message.get("type") == "device.heartbeat" and message.get("device_id") == device:
                        break
                latencies_ms.append((time.perf_counter() - sent) * 1000)
        latencies_ms.sort()
        p95 = latencies_ms[min(len(latencies_ms) - 1, int((len(latencies_ms) - 1) * 0.95))]
        print({"clients": 1, "samples": len(latencies_ms),
               "broadcast_round_trip_median_ms": round(statistics.median(latencies_ms), 3),
               "broadcast_round_trip_p95_ms": round(p95, 3),
               "note": "Includes HTTP request, server broadcast, and client receive; repeat with multiple sockets for fan-out load."})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--count", type=int, default=50)
    asyncio.run(main_async(parser.parse_args()))


if __name__ == "__main__":
    main()
