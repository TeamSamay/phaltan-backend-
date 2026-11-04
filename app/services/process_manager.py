"""
SUTRA AI Engine Process Supervisor.
Manages spawning, live telemetry streaming, log buffering, health monitoring,
and graceful shutdown of the sutra-ai-engine process.
"""

from __future__ import annotations

import collections
import logging
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

import psutil

from app.config import settings
from app.services.mongo_service import record_ai_engine_run

logger = logging.getLogger("sutra.process_manager")


class EngineProcessManager:
    """Manages the lifecycle of the Sutra AI Engine child process."""

    def __init__(self) -> None:
        self.process: Optional[subprocess.Popen] = None
        self.run_id: Optional[str] = None
        self.mode: Optional[str] = None
        self.source: Optional[str] = None
        self.started_at: Optional[datetime] = None
        self.stopped_at: Optional[datetime] = None
        self._log_buffer: collections.deque[str] = collections.deque(maxlen=300)
        self._log_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    @property
    def is_running(self) -> bool:
        with self._lock:
            if self.process is None:
                return False
            return self.process.poll() is None

    def get_engine_script_path(self) -> Path:
        """Find the main entrypoint of sutra-ai-engine."""
        engine_dir = Path(settings.ai_engine_dir)
        candidate = engine_dir / "app" / "main.py"
        if candidate.exists():
            return candidate
        # Fallback search
        candidate2 = settings.BASE_DIR.parent / "sutra-ai-engine" / "app" / "main.py"
        if candidate2.exists():
            return candidate2
        raise FileNotFoundError(f"Sutra AI Engine entrypoint not found at {candidate} or {candidate2}")

    def start(
        self,
        mode: str = "synthetic",
        source: Optional[str] = None,
        publish: bool = True,
        headless: bool = True,
        frames: int = 0,
        port: int = 8000
    ) -> dict[str, Any]:
        """Start the sutra-ai-engine subprocess."""
        with self._lock:
            if self.process is not None and self.process.poll() is None:
                return {
                    "success": False,
                    "message": "AI Engine is already running",
                    "pid": self.process.pid,
                    "status": "running"
                }

            script_path = self.get_engine_script_path()
            engine_root = script_path.parent.parent

            cmd = [sys.executable, str(script_path), "--mode", mode]
            if headless:
                cmd.append("--headless")
            if frames > 0:
                cmd.extend(["--frames", str(frames)])
            if source:
                cmd.extend(["--source", str(source)])
            if publish:
                cmd.append("--publish")

            env = os.environ.copy()
            # Direct AI Engine's publisher to our FastAPI backend
            backend_url = f"http://127.0.0.1:{settings.port}/api/v1/events"
            env["SUTRA_PUBLISHER_URL"] = backend_url
            env["SUTRA_ENABLE_HTTP_PUBLISHER"] = "true" if publish else "false"
            env["PYTHONUNBUFFERED"] = "1"
            env["PYTHONPATH"] = str(engine_root)

            self.run_id = f"run-{uuid4().hex[:10]}"
            self.mode = mode
            self.source = source
            self.started_at = datetime.now(timezone.utc)
            self.stopped_at = None
            self._log_buffer.clear()

            logger.info("Spawning Sutra AI Engine: %s (cwd=%s)", " ".join(cmd), engine_root)

            try:
                self.process = subprocess.Popen(
                    cmd,
                    cwd=str(engine_root),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    env=env
                )
            except Exception as e:
                logger.error("Failed to spawn Sutra AI Engine process: %s", e)
                return {
                    "success": False,
                    "message": f"Failed to spawn process: {e}",
                    "status": "error"
                }

            # Start background thread to capture stdout/stderr
            self._log_thread = threading.Thread(
                target=self._capture_logs,
                args=(self.process, self.run_id),
                name=f"EngineLogger-{self.run_id}",
                daemon=True
            )
            self._log_thread.start()

            # Record initial run in MongoDB async via non-blocking call
            run_doc = {
                "run_id": self.run_id,
                "pid": self.process.pid,
                "mode": mode,
                "source": source or "synthetic_default",
                "headless": headless,
                "publish": publish,
                "frames": frames,
                "status": "running",
                "started_at": self.started_at.isoformat()
            }
            threading.Thread(target=self._record_run_sync, args=(run_doc,), daemon=True).start()

            return {
                "success": True,
                "message": "Sutra AI Engine started successfully",
                "run_id": self.run_id,
                "pid": self.process.pid,
                "mode": mode,
                "status": "running"
            }

    def _record_run_sync(self, doc: dict[str, Any]) -> None:
        """Helper to run async mongo save from sync background thread."""
        try:
            import asyncio
            asyncio.run(record_ai_engine_run(doc))
        except Exception as e:
            logger.debug("Failed saving run doc to Mongo: %s", e)

    def _capture_logs(self, proc: subprocess.Popen, run_id: str) -> None:
        """Stream process output lines into circular ring buffer."""
        try:
            if proc.stdout:
                for line in iter(proc.stdout.readline, ""):
                    clean = line.rstrip()
                    if clean:
                        self._log_buffer.append(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] {clean}")
                proc.stdout.close()
        except Exception as e:
            logger.debug("Engine log reader stopped: %s", e)
        finally:
            self.stopped_at = datetime.now(timezone.utc)
            exit_code = proc.poll()
            logger.info("Sutra AI Engine process terminated (run_id=%s, exit_code=%s)", run_id, exit_code)

    def stop(self, force: bool = False) -> dict[str, Any]:
        """Terminate or kill the AI Engine process."""
        with self._lock:
            if self.process is None:
                return {"success": True, "message": "No AI Engine process is active", "status": "stopped"}

            if self.process.poll() is not None:
                return {"success": True, "message": "AI Engine is already stopped", "status": "stopped"}

            pid = self.process.pid
            logger.info("Stopping Sutra AI Engine process PID %d (force=%s)...", pid, force)

            try:
                parent = psutil.Process(pid)
                children = parent.children(recursive=True)
                for child in children:
                    try:
                        child.terminate() if not force else child.kill()
                    except (psutil.NoSuchProcess, Exception):
                        pass

                if force:
                    self.process.kill()
                else:
                    self.process.terminate()

                self.process.wait(timeout=3.0)
            except (subprocess.TimeoutExpired, Exception):
                try:
                    self.process.kill()
                    self.process.wait(timeout=2.0)
                except Exception:
                    pass

            self.stopped_at = datetime.now(timezone.utc)
            status_desc = "stopped"

            return {
                "success": True,
                "message": f"Sutra AI Engine process (PID {pid}) stopped",
                "pid": pid,
                "status": status_desc
            }

    def get_status(self) -> dict[str, Any]:
        """Query live execution status and resource metrics."""
        with self._lock:
            if self.process is None:
                return {
                    "is_running": False,
                    "status": "stopped",
                    "pid": None,
                    "mode": None,
                    "source": None,
                    "cpu_percent": 0.0,
                    "memory_mb": 0.0,
                    "uptime_seconds": 0.0,
                    "started_at": None,
                    "recent_logs": list(self._log_buffer)[-20:]
                }

            poll_result = self.process.poll()
            is_alive = poll_result is None

            cpu = 0.0
            mem_mb = 0.0
            if is_alive:
                try:
                    p = psutil.Process(self.process.pid)
                    cpu = p.cpu_percent(interval=None)
                    mem_mb = round(p.memory_info().rss / (1024 * 1024), 2)
                except Exception:
                    pass

            uptime = 0.0
            if self.started_at:
                end_time = self.stopped_at or datetime.now(timezone.utc)
                uptime = round((end_time - self.started_at).total_seconds(), 1)

            return {
                "is_running": is_alive,
                "status": "running" if is_alive else f"exited({poll_result})",
                "pid": self.process.pid if is_alive else None,
                "run_id": self.run_id,
                "mode": self.mode,
                "source": self.source,
                "cpu_percent": cpu,
                "memory_mb": mem_mb,
                "uptime_seconds": uptime,
                "started_at": self.started_at.isoformat() if self.started_at else None,
                "recent_logs": list(self._log_buffer)[-25:]
            }

    def get_logs(self, max_lines: int = 100) -> list[str]:
        """Fetch latest console log lines."""
        with self._lock:
            return list(self._log_buffer)[-max_lines:]


# Global singleton instance
process_manager = EngineProcessManager()
