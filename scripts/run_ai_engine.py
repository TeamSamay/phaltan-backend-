"""
Launcher script to run Sutra AI Engine and stream real-time telemetry to SUTRA Backend.
Automatically configures event publisher, environment, and execution arguments.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app.config import settings


def main():
    parser = argparse.ArgumentParser(description="Run Sutra AI Engine with SUTRA Backend Telemetry Integration")
    parser.add_argument("--mode", choices=["synthetic", "live", "video", "test-deviation", "benchmark"], default="synthetic",
                        help="Execution mode (default: synthetic)")
    parser.add_argument("--source", type=str, default=None,
                        help="Video source: camera index (0) or path to video file")
    parser.add_argument("--frames", type=int, default=180,
                        help="Frame count before stopping (0 = continuous)")
    parser.add_argument("--backend-url", type=str, default=f"http://127.0.0.1:{settings.port}/api/v1/events",
                        help="Backend ingestion endpoint")
    parser.add_argument("--headless", action="store_true", default=True,
                        help="Run without GUI OpenCV window")
    parser.add_argument("--no-headless", dest="headless", action="store_false",
                        help="Enable GUI OpenCV display window")
    parser.add_argument("--no-publish", dest="publish", action="store_false", default=True,
                        help="Disable publishing events to backend")
    args = parser.parse_args()

    engine_dir = Path(settings.ai_engine_dir)
    engine_main = engine_dir / "app" / "main.py"
    if not engine_main.exists():
        engine_main = backend_dir.parent / "sutra-ai-engine" / "app" / "main.py"
        engine_dir = engine_main.parent.parent

    if not engine_main.exists():
        print(f"[ERROR] Sutra AI Engine entrypoint not found at: {engine_main}")
        sys.exit(1)

    print("=" * 65)
    print("  SUTRA AI VISION ENGINE LAUNCHER")
    print("=" * 65)
    print(f"  * Engine Root        : {engine_dir}")
    print(f"  * Mode               : {args.mode}")
    print(f"  * Frames             : {args.frames if args.frames > 0 else 'Continuous'}")
    print(f"  * Target Backend     : {args.backend_url if args.publish else 'Local / No publish'}")
    print(f"  * Headless           : {args.headless}")
    print("=" * 65)

    cmd = [sys.executable, str(engine_main), "--mode", args.mode]
    if args.headless:
        cmd.append("--headless")
    if args.frames > 0:
        cmd.extend(["--frames", str(args.frames)])
    if args.source:
        cmd.extend(["--source", str(args.source)])
    if args.publish:
        cmd.append("--publish")

    env = os.environ.copy()
    env["SUTRA_PUBLISHER_URL"] = args.backend_url
    env["SUTRA_ENABLE_HTTP_PUBLISHER"] = "true" if args.publish else "false"
    env["PYTHONPATH"] = str(engine_dir)

    try:
        proc = subprocess.run(cmd, cwd=str(engine_dir), env=env)
        sys.exit(proc.returncode)
    except KeyboardInterrupt:
        print("\nShutdown signaled by user.")


if __name__ == "__main__":
    main()
