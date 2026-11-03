# SUTRA Backend — Code ko samajhne aur fix karne ki guide

Yeh guide codebase ko chhote, manageable hisson mein todkar samajhne aur bugs ko safe tareeke se fix karne ke liye hai. Pehle local tests chalao, ek waqt mein ek behavior badlo, phir tests dobara chalao. AI/Vision engine ya React dashboard is repository ka hissa nahi hai.

## 1. Project ka flow

```text
AI/mock client
   -> FastAPI route (app/main.py)
   -> Pydantic request validation (app/schemas/)
   -> device token check (app/core/auth.py)
   -> event ingestion (app/services/ingestion.py)
   -> experiment transition rules (modules/experiment_engine/)
   -> SQLAlchemy models / SQLite (app/models/, app/database.py)
   -> WebSocket updates (app/websocket/manager.py)
```

Agar event ka JSON hi galat hai to API 422 deta hai. Agar JSON sahi hai lekin protocol order galat hai, event `rejected` status ke saath store hota hai aur deviation ban sakta hai. Repeated `event_id` par duplicate record nahi banta.

## 2. File map — bug kahan dhoondhein?

| Agar issue yahan dikhe | Pehle yeh files dekhein |
|---|---|
| App start, endpoints, HTTP errors, request limit | `app/main.py` |
| Environment settings | `app/config.py`, `.env.example` |
| DB URL, session, schema init | `app/database.py` |
| Tables, columns, indexes, constraints | `app/models/models.py` |
| Request payload validation | `app/schemas/schemas.py` |
| Duplicate, timestamp, event persistence/processing | `app/services/ingestion.py` |
| Protocol transitions/order/confidence | `modules/experiment_engine/engine.py` |
| Demo steps/version | `protocols/demo_wetlab.yaml` |
| Device token validation | `app/core/auth.py` |
| WebSocket connect/broadcast/disconnect | `app/websocket/manager.py`, `app/main.py` |
| Alert fields | `app/services/alerts.py` |
| API usage/event fields | `docs/EVENT_CONTRACT.md` |
| Reproducible tests | `tests/` |
| Mock input | `tools/mock_ai_client.py`, `tools/event_simulator.py` |

## 3. Local setup aur basic checks (Windows PowerShell)

Project root mein terminal kholkar:

1. Environment activate karo: `.venv\\Scripts\\Activate.ps1`
2. Dependencies install/update karo: `pip install -r requirements.txt`
3. Test suite: `python -m pytest -q`
4. Server: `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`
5. Browser mein `http://127.0.0.1:8000/docs` kholkar endpoints dekho.
6. Doosre terminal mein mock client: `python tools/mock_ai_client.py`

LAN par doosre laptop se connect karne ke liye server host `0.0.0.0` set karo; doosre laptop par `localhost` nahi, server laptop ka network IP use karo.

## 4. Safe bug-fix workflow

1. **Bug ko reproduce karo:** exact endpoint, request JSON, response/status, expected behavior note karo.
2. **Existing test dhoondo:** `tests/` mein related test dekho. Nahi ho to pehle chhota failing regression test add karo.
3. **Sahi layer chuno:** schema, route, service, engine, database, ya WebSocket — bug ko us layer par fix karo jo galat behavior produce kar rahi hai.
4. **Chhota change karo:** unrelated refactor aur multiple behavior changes ek saath na karo.
5. **Focused test chalao**, phir full suite `python -m pytest -q`.
6. **Live check zaroori ho to:** server aur mock tool se integration verify karo.
7. **Git inspect karo:** `git diff` aur `git status --short`; `.env`, `sutra.db`, tokens ya `.venv` commit na hon.
8. **Commit tabhi karo** jab tests pass hon aur diff samajh aa raha ho.

## 5. Behavior ke hisaab se debugging

### Event 422 de raha hai
- `EventContract` ko `app/schemas/schemas.py` mein dekho.
- `schema_version` abhi `1.0` hai; timestamp timezone ke saath hona chahiye.
- `event_type` supported list mein ho aur extra top-level fields allowed nahi hain.
- `/docs` se valid request model dekho. Error envelope ke `details` mein invalid field diya hota hai.

### Event accepted hai, par step update nahi hua
- `/api/v1/events/{event_id}` dekho: `processing_status` aur `processing_error` batayega.
- Experiment pehle `running` hona chahiye.
- Step ko start karke hi complete karo; protocol order aur minimum confidence `protocols/demo_wetlab.yaml` se check hote hain.
- Rules `modules/experiment_engine/engine.py` mein; actual DB update `app/services/ingestion.py` mein.

### Duplicate event / missing event
- Same `event_id` idempotency key hai. Duplicate response `duplicate: true` dega.
- Event filters, pagination, `device_id`, `experiment_id`, aur event timestamp verify karo.
- SQLite data `sutra.db` mein hota hai; `.gitignore` is file ko commit se exclude karta hai.

### Device auth fail
- Local default development mode mein token optional hai.
- Token mode ke liye `SUTRA_DEV_AUTH=false` aur registration response ka `X-Device-Token` bhejo.
- Token ko logs, source control ya chat mein mat daalo.

### WebSocket event nahi mil raha
- `/ws/dashboard` connect karke pehla `connection.ready` message lo.
- Connection ke baad `ping` bhejne par `pong` expected hai.
- Broadcast service `app/websocket/manager.py` mein; event-specific broadcast `app/services/ingestion.py` ya endpoint mein dekho.
- Reconnect ke baad missing events REST se recover karo: events list ya experiment timeline.

## 6. Database change karte waqt

Models `app/models/models.py` mein hain. Nayi column ya constraint ke liye:

1. Model update karo.
2. Test database par schema aur behavior test add/update karo.
3. `python -m pytest -q` chalao.

Is MVP mein startup par `Base.metadata.create_all()` hai, Alembic migrations nahi. `create_all()` pehle se maujood tables mein columns alter nahi karta. Existing local DB schema change ke baad mismatch kare to **sirf local test data ki zaroorat na ho tabhi** `sutra.db` backup/delete karke dobara initialize karo. Shared/important data ko bina backup delete mat karo. Team/production use se pehle Alembic migrations add karna uchit hai.

## 7. Test ko sahi jagah add karna

- API behavior / request-response: `tests/test_api.py`
- Protocol edge conditions: `tests/test_engine.py`
- Timestamp ya unusual input: `tests/test_edge_cases.py`
- Persistence across sessions: `tests/test_persistence.py`
- Shared fixtures aur test helpers: `tests/conftest.py`

Har bug fix ke liye test mein **input + expected result** assert karo. WebSocket disconnect/broadcast changes mein ek se zyada connected clients ke behavior ko bhi test karo.

## 8. Dhyan dene layak MVP limitations

- Protocol demo hai; official BAS procedure nahi.
- Backend reported evidence ko validate karta hai, video ko nahi dekhta.
- SQLite aur in-memory rate limiter single-machine MVP ke liye hain.
- SQL schema initialization `create_all()` hai, migration history nahi.
- Dashboard alerts WebSocket messages hain; alag persistent alert table/API nahi.
- Performance scripts local observation deti hain, production load guarantee nahi.
- Development auth default hai; ise production security na samjhein.

## 9. GitHub par changes bhejne se pehle

- `python -m pytest -q` ka result check karo.
- `git status --short --branch` aur `git diff` dekho.
- `.env`, `sutra.db`, `.venv`, tokens/API keys staged na hon.
- Chhota aur saaf commit message likho.
- Push se pehle branch/remote confirm karo: `git remote -v`, `git branch --show-current`.
