# SUTRA Backend Deployment & AI Engine Integration Guide

This guide details how to deploy, configure, and orchestrate the **SUTRA Backend** alongside the **Sutra AI Engine** and **MongoDB**.

---

## 🏗️ Architecture Overview

```
                                      +------------------------------------+
                                      |          Frontend / HUD            |
                                      |  (Browser / WebSockets / React)    |
                                      +-----------------+------------------+
                                                        |
                                                        | REST / WS
                                                        v
+------------------------+  HTTP / WS   +------------------------------------+
|    Sutra AI Engine     | -----------> |            FastAPI Backend         |
| (YOLO + Pose + FSM)    |   Telemtry   | (Supervisor, Ingestion, Engine API)|
+------------------------+              +-----------------+------------------+
                                                          |
                                           +--------------+--------------+
                                           |                             |
                                           v                             v
                                +--------------------+         +--------------------+
                                |      MongoDB       |         |   SQLite / Relational|
                                |  (Document Store)  |         |   (Relational Cache) |
                                +--------------------+         +--------------------+
```

- **FastAPI Backend (`phaltan-backend-`)**: Serves REST APIs, manages WebSocket broadcasts, acts as the process supervisor for the Sutra AI Engine, and ingests telemetry events.
- **MongoDB**: Primary document database storing `telemetry_events`, `deviations`, `protocols`, `experiments`, `devices`, `system_logs`, and `ai_engine_runs`.
- **Process Supervisor (`app/services/process_manager.py`)**: Can spawn, monitor, retrieve logs, and stop the `sutra-ai-engine` process on demand via REST APIs.
- **Sutra AI Engine (`sutra-ai-engine`)**: Computer vision and pose tracking pipeline publishing structured events (`STEP_STARTED`, `STEP_COMPLETED`, `DEVIATION_DETECTED`, `HEARTBEAT`) to the backend.

---

## ⚡ Quick Start (Local Development)

### 1. Prerequisites
- Python 3.10+ (tested on Python 3.11 - 3.14)
- MongoDB running locally on `localhost:27017` (or MongoDB Atlas URI)

### 2. Install Dependencies
```bash
cd phaltan-backend-
pip install -r requirements.txt
```

### 3. Seed MongoDB
Pre-populate MongoDB with the default wetlab protocol, pre-registered AI device (`ai-device-01`), and demo experiment:
```bash
python scripts/seed_mongodb.py
```

### 4. Run the Full Stack with a Single Command
Run backend and automatically start Sutra AI Engine streaming synthetic telemetry:
```bash
# Windows
scripts\start_all.bat
# or
python scripts/run_all.py --mode synthetic --frames 180

# Linux / Mac
chmod +x scripts/start_all.sh
./scripts/start_all.sh
```

### 5. Run Backend Only
```bash
# Windows
scripts\start_backend.bat
# or
python scripts/run_backend.py --port 8000 --reload

# Linux / Mac
chmod +x scripts/start_backend.sh
./scripts/start_backend.sh
```

---

## 🐳 Docker & Docker Compose Deployment

The repository includes a production multi-stage `Dockerfile` and `docker-compose.yml`.

### Launch Everything with Docker Compose:
```bash
docker compose up -d --build
```

Services started:
1. **`sutra-backend`**: FastAPI application exposed on `http://localhost:8000`
2. **`sutra-mongodb`**: MongoDB 7.0 database on `mongodb://localhost:27017` with persistent volume `sutra-mongo-data`
3. **`sutra-mongo-express`**: Web GUI for MongoDB on `http://localhost:8081`

### Check Status & Logs:
```bash
docker compose ps
docker compose logs -f backend
```

### Health Check:
```bash
curl http://localhost:8000/health
```

---

## 📡 API Reference for AI Engine & MongoDB

### 1. AI Engine Process Supervisor

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/engine/start` | Launch Sutra AI Engine child process (`mode`, `source`, `publish`, `headless`) |
| `POST` | `/api/v1/engine/stop` | Terminate running AI Engine process |
| `GET` | `/api/v1/engine/status` | Live CPU, RAM, PID, uptime, and last log lines |
| `GET` | `/api/v1/engine/logs` | Fetch circular console buffer from AI Engine |
| `GET` | `/api/v1/engine/runs` | Historical execution runs stored in MongoDB |

#### Example: Start Sutra AI Engine via API
```bash
curl -X POST http://localhost:8000/api/v1/engine/start \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "synthetic",
    "frames": 180,
    "publish": true,
    "headless": true
  }'
```

### 2. Telemetry Ingestion (Bridge for Sutra AI Engine)

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/telemetry/events` | Ingests outbound telemetry from Sutra AI Engine's `EventPublisher` |
| `GET` | `/api/v1/telemetry/events` | Retrieve recently stored telemetry events |
| `POST` | `/api/v1/events` | Standard event contract ingestion endpoint |
| `POST` | `/api/v1/events/batch` | Bulk event ingestion |

### 3. MongoDB Document Ledger

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v1/mongo/stats` | Document counts for all collections in MongoDB |
| `GET` | `/api/v1/mongo/events` | Filter and query raw events directly from MongoDB |
| `GET` | `/api/v1/mongo/deviations` | Query deviation records from MongoDB |

---

## 🧪 Testing & Verification

Run the test suite (37 unit & integration tests):
```bash
pytest
```

Run the end-to-end integration test verifying FastAPI + MongoDB + Sutra AI Engine event contract:
```bash
python scripts/test_pipeline_e2e.py
```
