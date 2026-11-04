"""
Complete System Orchestrator for SUTRA:
1. Verifies / Seeds MongoDB database
2. Launches FastAPI Backend Server on port 8000
3. Automatically launches Sutra AI Engine connected via live telemetry publisher
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path
import urllib.request
import json

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app.config import settings


def wait_for_backend(url: str, timeout_s: float = 15.0) -> bool:
    start_time = time.time()
    while time.time() - start_time < timeout_s:
        try:
            with urllib.request.urlopen(f"{url}/health", timeout=1.0) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            time.sleep(0.5)
    return False


def main():
    parser = argparse.ArgumentParser(description="Orchestrate SUTRA Backend + AI Engine")
    parser.add_argument("--mode", choices=["synthetic", "live", "video", "test-deviation", "benchmark", "backend-only"],
                        default="synthetic", help="AI Engine execution mode (or 'backend-only')")
    parser.add_argument("--source", type=str, default=None, help="Video source (camera 0 or file path)")
    parser.add_argument("--port", type=int, default=settings.port, help="Backend port")
    parser.add_argument("--frames", type=int, default=180, help="AI Engine frames (0 = infinite)")
    parser.add_argument("--headless", action="store_true", default=True, help="Run AI Engine headless")
    args = parser.parse_args()

    print("=" * 68)
    print("  SUTRA FULL-STACK LAUNCHER (BACKEND + AI ENGINE + MONGODB)")
    print("=" * 68)

    # Step 1: Seed MongoDB
    print("\n[Step 1/3] Checking & Seeding MongoDB...")
    seed_script = backend_dir / "scripts" / "seed_mongodb.py"
    try:
        subprocess.run([sys.executable, str(seed_script)], check=True)
    except Exception as e:
        print(f"Warning: MongoDB seeding returned: {e}")

    # Step 2: Start Backend Server
    print(f"\n[Step 2/3] Launching FastAPI Backend on http://127.0.0.1:{args.port}...")
    backend_script = backend_dir / "scripts" / "run_backend.py"
    backend_proc = subprocess.Popen(
        [sys.executable, str(backend_script), "--port", str(args.port)],
        cwd=str(backend_dir)
    )

    backend_url = f"http://127.0.0.1:{args.port}"
    print("Waiting for FastAPI backend to respond at /health...")
    if not wait_for_backend(backend_url):
        print("[ERROR] Backend failed to start in time. Terminating...")
        backend_proc.terminate()
        sys.exit(1)
    print("[OK] SUTRA Backend is LIVE and healthy!")

    # Step 3: Run AI Engine if not backend-only
    if args.mode == "backend-only":
        print("\nBackend-only mode selected. Press Ctrl+C to terminate.")
        try:
            backend_proc.wait()
        except KeyboardInterrupt:
            print("\nTerminating backend...")
            backend_proc.terminate()
        return

    print(f"\n[Step 3/3] Launching Sutra AI Engine (mode={args.mode}, target={backend_url})...")
    engine_script = backend_dir / "scripts" / "run_ai_engine.py"
    cmd = [
        sys.executable, str(engine_script),
        "--mode", args.mode,
        "--backend-url", f"{backend_url}/api/v1/events",
        "--frames", str(args.frames)
    ]
    if args.headless:
        cmd.append("--headless")
    if args.source:
        cmd.extend(["--source", str(args.source)])

    try:
        engine_proc = subprocess.run(cmd)
        print("\nAI Engine run completed.")
    except KeyboardInterrupt:
        print("\nReceived user interrupt.")
    finally:
        print("Shutting down backend server...")
        backend_proc.terminate()
        try:
            backend_proc.wait(timeout=3.0)
        except subprocess.TimeoutExpired:
            backend_proc.kill()
        print("All processes stopped.")


if __name__ == "__main__":
    main()
