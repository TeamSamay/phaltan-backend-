"""
FastAPI Server Launcher for SUTRA Backend.
Starts uvicorn with configured host, port, and auto-reload options.
"""

import argparse
import sys
from pathlib import Path

# Ensure backend root is in sys.path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

import uvicorn
from app.config import settings


def main():
    parser = argparse.ArgumentParser(description="Run SUTRA Backend API Server")
    parser.add_argument("--host", default=settings.host, help="Bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=settings.port, help="Bind port (default: 8000)")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload for development")
    parser.add_argument("--workers", type=int, default=1, help="Number of worker processes")
    args = parser.parse_args()

    print("=" * 65)
    print("  SUTRA EXPERIMENT GUARDIAN & AI ENGINE BACKEND")
    print("=" * 65)
    print(f"  * API Address        : http://{args.host}:{args.port}")
    print(f"  * Swagger Docs       : http://{args.host}:{args.port}/docs")
    print(f"  * WebSocket Feed     : ws://{args.host}:{args.port}/ws/dashboard")
    print(f"  * MongoDB URI        : {settings.mongodb_url} (DB: {settings.mongodb_db})")
    print(f"  * AI Engine Path     : {settings.ai_engine_dir}")
    print("=" * 65)

    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        workers=args.workers if not args.reload else 1,
        log_level="info"
    )


if __name__ == "__main__":
    main()
