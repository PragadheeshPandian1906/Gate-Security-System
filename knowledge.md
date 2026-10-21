# SmartGuard AI — Project Knowledge

> **Updated:** 2026-10-21  
> **Purpose:** Current, source-grounded reference for the SmartGuard AI Gate Security System.  
> **Authority:** Runtime source, schemas, and migrations take precedence over older narrative documents and historical test logs. Configuration values and live infrastructure status are not reproduced here.

## 1. Project Summary

SmartGuard AI is a campus gate security application composed of:

- A React/TypeScript web dashboard for security operators and administrators.
- A main FastAPI backend for authentication, AI verification, access decisions, visitor workflows, alerts, and reports.
- PostgreSQL with pgvector for application records and face embeddings.
- A separate FastAPI IoT microservice that owns the ESP32 device WebSocket.
- ESP32 firmware that commands a servo and LCD and reports controller state, heartbeats, and acknowledgements.
- A Python mock-device simulator for testing the IoT protocol without hardware.

The main backend is authoritative for operator authentication, policy evaluation, and persisted application records. The IoT service is authoritative for the live device connection and its latest reported telemetry. Firmware controls the servo target and LCD. The system has no gate-position sensor or person-crossing sensor: software state, device acknowledgements, visitor check-in/out, and access decisions are not proof of physical movement.

## 2. Implementation Status

| Area | Current implementation |
|---|---|
| Browser application | React 19, TypeScript, Vite, Tailwind CSS v4, React Router, Axios, Lucide React |
| Main API | FastAPI, Pydantic 2, SQLAlchemy 2, Alembic, Uvicorn |
| Database | PostgreSQL; Supabase PostgreSQL is the documented deployment option |
| Face recognition | InsightFace `buffalo_l` / ArcFace, ONNX Runtime, 512-dimensional embeddings, pgvector cosine search |
| License-plate recognition | FastALPR detection/OCR and normalized exact vehicle-plate lookup |
| Access policy | Server-side revalidation, freshness checks, identity/vehicle/status/ownership/watchlist/schedule checks, ALLOW/DENY/MANUAL_REVIEW |
| Visitor management | Visitor passes, hashed QR tokens, entry approval, exit lifecycle, alert and email integration |
| Security operations | Alerts, audit notes, access reports, CSV export, contacts, notification history and retry endpoints |
| Gate control | In-process software simulation plus HTTP bridge to the independent IoT service; manual-open latch and separate automated closing behavior |
| IoT controller | FastAPI microservice with authenticated device WebSocket, command acknowledgements, heartbeat watchdog, telemetry and event broadcast |
| Firmware | Canonical ESP32 sketch, SG90-compatible servo target, 16×2 I2C LCD, Wi-Fi and WebSocket reconnect logic |
| Physical gate feedback | No position, obstacle, or person-crossing sensor found |
| Background jobs | No message broker, independent task worker, or scheduled daily-summary/retry worker found |

“Implemented” describes repository code. It does not establish that the database, AI model weights, optional cloud/email providers, LAN, or physical hardware are configured or available at runtime.

## 3. Architecture at a Glance

```text
Security operator / administrator
              │
              ▼
React dashboard ── REST + dashboard WebSocket ──► Main FastAPI backend
                                                        │
                       ┌────────────────────────────────┼─────────────────────────┐
                       ▼                                ▼                         ▼
                PostgreSQL + pgvector         AI and policy services     Storage/email providers
                                                        │
                                             authenticated HTTP bridge
                                                        ▼
                                                IoT FastAPI service
                                                        │
                                                  device WebSocket
                                                        ▼
                                              ESP32 ──► servo + LCD

Mock ESP32 simulator ─────────────── alternate software client of IoT WebSocket
```

The ESP32 connects to the IoT microservice, not directly to the main backend. The main backend calls the IoT microservice over HTTP. It polls service status/events approximately every four seconds and broadcasts updates to connected main-dashboard clients.

### Service ownership

- **Main backend:** application auth/RBAC, AI orchestration, access decisions, visitor and alert records, schedules, watchlists, reports, and software gate simulation.
- **IoT service:** one active physical-device WebSocket, device authentication, command dispatch, ACK tracking, heartbeat timeout, latest controller-reported state, and IoT event broadcast.
- **Firmware:** local controller mode/state, servo target, LCD display, heartbeat/state/ACK generation, and automated close timer.
- **Frontend:** operator interaction and rendering. It is not an authorization authority.
- **Database:** durable application records. Gate simulation, IoT telemetry/event buffers, and the firmware manual latch are process/device memory, not durable DB state.

## 4. Repository Map

| Path | Role |
|---|---|
| `frontend/` | React application, API clients, UI components, and Vitest tests |
| `backend/` | Main FastAPI application, services, SQLAlchemy models, migrations, and pytest suite |
| `iot-service/` | Independent IoT FastAPI app, device manager, schemas, simulator, firmware, and tests |
| `iot-service/firmware/esp32_gate_controller/` | Canonical ESP32 sketch identified by current project documentation |
| `iot-service/scripts/mock_esp32.py` | Python mock device implementing the IoT WebSocket protocol |
| `firmware-legacy/` | Legacy firmware copy; do not assume it is the active/flash target |
| `database/` | Database-related scripts/resources |
| `docs/` | Architecture and integration documents; some older IoT narrative is stale |
| `README.md` | Current local setup, service startup, and hardware connection guidance |
| `SMARTGUARD_AI_SYSTEM_ARCHITECTURE_REPORT.md` | Detailed architecture investigation and diagram blueprint; no diagram generated |

### Main source entry points

- Frontend bootstrap and routes: `frontend/src/main.tsx`, `frontend/src/App.tsx`.
- Main API: `backend/app/main.py`.
- Main application settings and DB engine: `backend/app/core/config.py`, `backend/app/db/session.py`.
- IoT service: `iot-service/app/main.py`.
- IoT device manager/protocol: `iot-service/app/services/device_manager.py`, `iot-service/app/api/routes.py`, `iot-service/app/schemas/gate_status.py`.
- Canonical firmware: `iot-service/firmware/esp32_gate_controller/esp32_gate_controller.ino`.

## 5. Frontend

### Startup, routing, and session

- Vite serves the SPA from `frontend/index.html`; `frontend/src/main.tsx` mounts the React application.
- `frontend/src/App.tsx` provides the auth context, router, and nested protected routes.
- `frontend/src/context/AuthContext.tsx` stores the operator JWT/profile in browser localStorage and restores them on mount.
- `frontend/src/routes/ProtectedRoutes.tsx` applies UI role restrictions for `ADMIN` and `SECURITY`; backend dependencies enforce actual authorization.
- `frontend/src/api/client.ts` builds the API base from `VITE_API_BASE_URL`, adds the Bearer token, and clears local auth/redirects on HTTP 401.
- Tokens in localStorage are readable by same-origin JavaScript; they are not HttpOnly cookies.

### Main screens and API clients

- Security gate workflow: `frontend/src/pages/security/SecurityDashboard.tsx`.
- Visitor passes and QR workflow: `frontend/src/pages/security/VisitorManagement.tsx`.
- Alerts: `frontend/src/pages/security/AlertCenter.tsx`.
- IoT device monitor: `frontend/src/pages/security/IotGateMonitor.tsx`.
- Campus access analytics: `frontend/src/components/security/CampusEntryOverview.tsx`.
- Admin registry, schedules, watchlists, reports, contacts, notifications, health, and accounts are under `frontend/src/pages/admin/`.
- API clients are under `frontend/src/api/`, including `client.ts`, `phase2.ts`, `phase3.ts`, `visitors.ts`, `gate.ts`, and feature-specific modules.

### Camera and automation workflow

1. The operator starts camera access through `getUserMedia`; the login page does not request camera access.
2. The dashboard captures JPEG frames using a video element and canvas, then posts them to `POST /api/ai/live-frame`.
3. The frame-processing loop has an in-flight guard so a slow inference request does not accumulate an unbounded queue. Camera tracks/timers are cleaned up when the camera/workflow stops or the component unmounts.
4. The dashboard renders face and plate bounding boxes and retains server-issued verification IDs for the later access request.
5. The operator can run face and plate stages manually or use the guarded automation state machine in `frontend/src/utils/automationController.ts`, which supports start, pause, resume, stop, workflow correlation, and idempotent evaluation safeguards.
6. `POST /api/access/attempts` receives direction and verification record IDs. The server reloads and revalidates the records; client-supplied identity/vehicle assertions are not trusted.

Face and plate inference run in sequence in the backend live-frame route, even though older UI/documentation prose described them as simultaneous.

### Gate state refresh

- Security Dashboard and IoT Gate Monitor use the main backend's pushed gate/IoT WebSocket updates.
- The Security Dashboard uses `/ws/gate/monitor` and REST status polling as a disconnected-socket fallback (2.5 seconds).
- The IoT Gate Monitor uses the same main dashboard WebSocket and a slower REST fallback (10 seconds).
- A second WebSocket handler is also registered at `/api/gate/ws/monitor` by the gate router; the current frontend points to `/ws/gate/monitor`.
- Campus analytics refreshes every 15 seconds and uses an in-flight guard and abort cleanup.

## 6. Main Backend and Authorization

### Application and API layout

`backend/app/main.py` initializes FastAPI, CORS, logging, application lifecycle, routers, exception handling, and the root dashboard WebSocket. The default REST prefix is `/api`.

Major route groups:

| Prefix | Main responsibility |
|---|---|
| `/api/auth` | Operator login and current account profile |
| `/api/admin/accounts` | Administrator-managed security accounts |
| `/api/health` | Liveness and DB/pgvector readiness |
| `/api/people`, `/api/vehicles` | Campus person and vehicle registries |
| `/api/ai` | Face/plate verification, live frames, snapshots, diagnostics |
| `/api/access` | Access attempts, review queue/resolution, campus analytics |
| `/api/gate` | Simulated gate status, manual commands, IoT status/events, reset |
| `/api/access/schedule` | Campus weekly operating schedule |
| `/api/watchlist` | Vehicle/plate watchlist |
| `/api/visitors` | Visitor passes, QR scan, approval, history and lifecycle |
| `/api/alerts` | Security incident list, detail, metrics and lifecycle |
| `/api/reports` | Access reports, CSV export, daily summary |
| `/api/admin/security-contacts` | Email contacts and non-secret gateway configuration status |
| `/api/admin/notifications` | Delivery logs and bounded retry actions |

Route files live in `backend/app/api/routes/`; request/response schemas in `backend/app/schemas/`; business logic in `backend/app/services/`.

### Authentication

1. `POST /api/auth/login` authenticates an account from `security_accounts`.
2. Passwords use Argon2id via `argon2-cffi`; they do not use bcrypt/Passlib.
3. A signed JWT contains subject, timestamps, role, and username. The signing algorithm is configurable and defaults to HS256; the token expiry defaults to 30 minutes.
4. REST dependencies load/check the active security account and apply ADMIN or SECURITY authorization.
5. `ADMIN` and `SECURITY` application accounts are separate from campus people in `campus_people`.
6. Some browser WebSocket authentication handlers verify JWT signature/subject at handshake rather than applying the complete REST account/role lookup. See “Known limitations”.

### Persistence

- SQLAlchemy 2 and Alembic manage data access/schema migrations.
- The DB session dependency provides a request-scoped SQLAlchemy session.
- PostgreSQL URLs are configured with SSL behavior in the DB engine.
- Alembic migrations are under `backend/alembic/versions/`; the current schema includes migrations for accounts/registry/AI, access policy, security operations, and visitors.
- The `/api/health/ready` route performs DB and pgvector checks; it is not a cached liveness-only response.

## 7. AI Verification and Access Decisions

### Face recognition

- `face_service.py` lazily initializes InsightFace `buffalo_l` / ArcFace.
- It extracts 512-dimensional embeddings and searches active face profiles using pgvector cosine distance.
- The configured decision thresholds in source are similarity `>= 0.45` for a match and `>= 0.30` for a low-confidence candidate; lower values are treated as no match.
- ONNX Runtime provider selection prefers CUDA when available and falls back to CPU. Hardware availability was not established by source inspection.
- Face verification rows and image references are persisted through the AI routes/services.

### Vehicle number plate recognition

- `alpr_service.py` uses FastALPR detection/OCR, normalizes plate strings (uppercase and punctuation/whitespace removal), then performs exact normalized lookup.
- A registered plate alone does not authorize access; vehicle and person status, ownership, watchlist, schedule, and face checks also apply.
- Model package/weight availability and inference performance depend on the running environment.

### Access decision

The access attempt endpoint requires persisted face/ALPR verification IDs. The service validates record existence and freshness (120 seconds), reloads linked person/vehicle data, and evaluates:

1. Verification presence, validity, freshness, and inference outcome.
2. Face ambiguity and match.
3. Plate detection/OCR and vehicle registration.
4. Person and vehicle active/flagged/suspended status.
5. Vehicle/person ownership mapping.
6. Active watchlist hits and severity.
7. Operating schedule in the configured campus timezone.

Results are `ALLOW`, `DENY`, or `MANUAL_REVIEW`. Untrusted, missing, stale, or policy-failing conditions do not silently become ALLOW. The attempt is persisted in `access_attempts`, and applicable alerts/notification workflows are invoked.

An `ALLOW` is an authorization decision, not proof that a person or vehicle physically crossed the gate.

## 8. Gate and IoT Behavior

### Gate state layers

1. **Backend simulation:** `gate_service.py` keeps software gate state in process memory and has its own automated close timer.
2. **IoT report:** `iot_manager` in the main backend polls the IoT service and broadcasts the reported controller state/telemetry.
3. **IoT microservice:** `device_manager.py` owns the ESP32 WebSocket, ACK futures, connection health, and latest received snapshot.
4. **Firmware:** commands servo target and LCD, maintains volatile mode/state, and reports it over the WebSocket.

No layer receives independent servo-angle or gate-position sensor feedback. APIs/UI expose physical position as unconfirmed.

### Automated versus manual operation

- Automated ALLOW commands retain the existing automatic-close policy. Backend simulation and the ESP32 have separate timers; default firmware automated duration is 15 seconds.
- Manual dashboard commands are distinct from automated commands.
- Manual Open sends a MANUAL open command. After a successful controller execution acknowledgement, the backend latches its software state; firmware moves to its OPEN servo target, enters `MANUAL_LATCHED_OPEN`, disarms the automatic-close timer, and displays `MANUAL GATE OPEN` / `WAITING TO CLOSE`.
- Heartbeats, telemetry, status reports, reconnects, and display updates are not physical close commands.
- Only an authorized Manual Close processed by the firmware clears the latch and commands the servo to its CLOSED target.
- Duplicate open commands are idempotent. A normal status report updates reported state; it does not move the servo.
- The backend manual latch and firmware latch are volatile. A restart does not guarantee restoration of a previously manually opened state; firmware initializes to the safe CLOSED target.
- A reset endpoint dispatches a physical close as an automated/reset action and does not override a firmware manual-open latch. Use Manual Close to explicitly clear manual mode.
- The normal automated DENY path updates the software state/display; it is not a general physical close command. A physical close is issued by an explicit close/reset operation or firmware's automated timer.

The dashboard's “open” state should be interpreted as controller-reported/commanded state. It is not a measured gate position.

### HTTP and WebSocket addresses

| Component | Default local port | Path / role |
|---|---:|---|
| Frontend Vite | 5173 | Browser SPA |
| Main FastAPI | 8000 | `/api/*` REST; `/ws/gate/monitor` dashboard WebSocket |
| Main FastAPI gate router | 8000 | Also registers `/api/gate/ws/monitor`; frontend currently uses the root path above |
| IoT FastAPI | 8001 | `/api/v1/*` REST |
| IoT device socket | 8001 | `/api/v1/ws/iot/gate` |
| IoT standalone monitor socket | 8001 | `/api/v1/ws/monitor` |

The physical ESP32 and Python simulator use the IoT device socket, not the main backend socket.

### Device authentication and messages

- Device identity is `device_id`; the query credential is named `token`. Firmware uses `device_id` and `token` query parameters. Service-side settings are `IOT_DEVICE_ID` and `IOT_DEVICE_KEY`.
- A device may also send an `AUTH` JSON frame within the service's five-second handshake window when query/header authentication is not used.
- Main backend service-to-service REST calls use `X-Service-Secret`; manual command routes also receive the already-authorized operator role/ID.
- The microservice supports a single active device connection; a newer authenticated connection can supersede the old one.
- Firmware/simulator send `HEARTBEAT` every 10 seconds and `GATE_STATE` on state changes.
- Heartbeat watchdog checks approximately every 5 seconds and marks the device offline after the configured 30-second timeout.
- Commands include `GATE_OPEN`, `GATE_CLOSE`, and `DISPLAY_STATUS`. Gate command metadata includes sequence/command IDs and distinguishes `MANUAL` from `AUTOMATED`.
- ACK/event message names include `COMMAND_ACK` and `GATE_ACTION_ACK`; ACK statuses distinguish receipt/execution/failure. Command ACK timeout defaults to 5 seconds.
- JSON is transported on the ESP32 WebSocket. The Python simulator follows the same message protocol and manual/automated behavior, but cannot validate Wi-Fi, wiring, PWM, power, servo travel, or physical gate movement.

### Hardware and canonical firmware

- **Upload target:** `iot-service/firmware/esp32_gate_controller/esp32_gate_controller.ino`.
- **Legacy copy:** `firmware-legacy/`; do not use it as the canonical upload target without an explicit project decision.
- ESP32 DevKit V1 / ESP32 WROOM family; servo signal GPIO 18; target 0° CLOSED / 90° OPEN.
- LCD: 16×2 I2C, SDA GPIO 21, SCL GPIO 22, address `0x27`.
- Firmware uses Wi-Fi, WebSockets, ArduinoJson, ESP32Servo, and LiquidCrystal_I2C.
- Automated auto-close defaults to 15 seconds and uses non-blocking timing.
- Manual open remains latched until authorized Manual Close; this is RAM state and is not power-loss persistent.
- Wi-Fi retry is non-blocking; WebSocket reconnect interval is approximately 3 seconds.
- Servo target command/ACK is not position feedback. Hardware power, common ground, and physical movement must be checked on the actual assembly.

## 9. Visitor Management

- Visitors are records in `campus_people` with `person_type='visitor'`; they do not receive operator login accounts.
- Visitor passes are stored in `visitor_passes`; the QR credential is high entropy, the database stores a SHA-256 hash, and the raw credential is returned only during pass issuance.
- ENTRY scan validates the pass and creates a pending officer approval; scanning alone does not open the gate.
- Approval changes the pass lifecycle to `ACTIVE_INSIDE`, writes a check-in time and access attempt, then requests gate opening.
- EXIT requires the pass to be active inside, marks it completed and records check-out before requesting gate opening.
- Pass expiration affects admission; an already-active visitor is not supposed to be denied an exit solely because the entry validity window elapsed.
- These timestamps reflect workflow processing, not confirmed crossing. `ACTIVE_INSIDE` is not sensor-verified occupancy.
- Visitor pass email and QR object storage depend on configured providers; delivery/storage failure and pass creation are distinct concerns.

## 10. Alerts, Email, Reports, and Analytics

### Alerts

- `alert_service.py` creates/deduplicates alerts based on access attempts, watchlist hits, denials, manual review, repeated-denial patterns, and visitor conditions.
- Alerts and notes persist in `security_alerts` and `alert_notes`.
- Alert state actions include acknowledge, investigate, note, resolve, and ADMIN-only dismiss.
- Alert failures are logged/caught so alert side effects do not change an already-made access decision.

### Email and notifications

- Email transport supports Brevo HTTPS API or SMTP based on configuration.
- `security_contacts` controls recipients, active state, severity threshold, categories, and daily-summary preference.
- `notification_log` persists delivery attempts, outcomes, errors, provider metadata, and idempotency details.
- Email attempts are performed synchronously from application request paths; there is no independent queue worker. Retry actions are bounded and exposed through admin APIs; no autonomous retry scheduler was found.
- Daily summaries are generated/sent on demand; no scheduled daily-summary job was found.
- Secret values and real personal sender/recipient addresses are intentionally excluded from this reference.

### Reports

- Access reports query access-decision audit records; CSV export includes formula-injection protection.
- Daily summary is an API-triggered report, not a scheduled job.
- The report route uses a fixed `Asia/Kolkata` timezone constant. Schedule evaluation and campus analytics use configured campus timezone with a fallback; these should not be assumed to be one shared setting.

### Campus access analytics

- Endpoint: authenticated `GET /api/access/analytics/campus`.
- It aggregates today's `DENY` access decisions and hourly `ALLOW` authorizations grouped by direction using campus-local day boundaries and an efficient SQL aggregate.
- It returns recent access decision activity and supported categories from the person model.
- The dashboard refreshes every 15 seconds and labels hourly values as **authorizations**, not confirmed crossings.
- Total confirmed entries, total confirmed exits, current occupancy, and occupancy-by-category are explicitly reported as unavailable. The schema has no sensor-confirmed person-crossing event. Access ALLOW, gate open, visitor approval, and `ACTIVE_INSIDE` do not establish physical presence.

## 11. Storage and Database Model

### Main entities

- **Security accounts:** `security_accounts` for ADMIN/SECURITY application operators.
- **Campus identities:** `campus_people` for students, staff, visitors, contractors, and other supported modeled categories.
- **Vehicles:** `vehicles`, including normalized plate and optional `owner_person_id`.
- **Biometrics:** `face_profiles`, `face_verifications`, and `alpr_verifications`.
- **Policy/audit:** `access_schedules`, `watchlist_entries`, and `access_attempts`.
- **Security operations:** `security_alerts`, `alert_notes`, `security_contacts`, and `notification_log`.
- **Visitors:** `visitor_passes` and `visitor_approvals`.

The model does not contain a canonical, sensor-confirmed movement table.

### File/object storage

`storage_service.py` writes application images/QR artifacts to local storage and can also upload to private Supabase Storage when configured. Supabase upload is optional and best-effort; local files and database references are separate from PostgreSQL row data. Exact path and cloud outcomes depend on runtime configuration.

## 12. Configuration Map

Only variable names and purposes are listed. Do not commit or share actual values.

### Main backend (`backend/.env`)

- Application/API: `APP_NAME`, `APP_ENV`, `API_PREFIX`, `FRONTEND_ORIGINS`, `APP_BASE_URL`, `LOG_LEVEL`.
- Database: `DATABASE_URL`.
- Supabase Storage: `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_KEY`.
- Authentication: `JWT_SECRET_KEY`, `JWT_ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`.
- IoT bridge: `IOT_MICROSERVICE_URL`, `IOT_SERVICE_SECRET`, `IOT_AUTO_CLOSE_DURATION_MS`.
- Email: `EMAIL_ENABLED`, `EMAIL_PROVIDER`, `EMAIL_API_KEY`, `EMAIL_FROM_ADDRESS`, `EMAIL_FROM_NAME`, and SMTP host/port/username/password/TLS settings.

### IoT service (`iot-service/.env`)

- Service: `IOT_SERVICE_HOST`, `IOT_SERVICE_PORT`, `IOT_LOG_LEVEL`, `IOT_ALLOWED_ORIGINS`.
- Device/service auth: `IOT_DEVICE_ID`, `IOT_DEVICE_KEY`, `IOT_SERVICE_SECRET`.
- Timing: `IOT_HEARTBEAT_TIMEOUT_SECONDS`, `IOT_ACK_TIMEOUT_SECONDS`, `IOT_AUTO_CLOSE_DURATION_MS`.
- Servo-angle settings sometimes shown in example configuration are informational; actual firmware angles are constants.

### Frontend (`frontend/.env`)

- `VITE_API_BASE_URL`, normally `http://localhost:8000/api` for local development.

### Firmware local secrets

Firmware credentials/network settings are supplied through a local, untracked `secrets.h`, including macros such as `SG_WIFI_SSID`, `SG_WIFI_PASSWORD`, `SG_IOT_SERVER_HOST`, `SG_IOT_DEVICE_ID`, and `SG_IOT_DEVICE_TOKEN`. Never paste actual values into project documentation.

## 13. Local Development and Validation

The three services run independently. See `README.md` for full Windows setup, dependency installation, database migration, and administrator bootstrap instructions.

Typical development ports:

- Frontend: `http://localhost:5173`
- Main backend: `http://localhost:8000`; API prefix `/api`
- IoT microservice: `http://localhost:8001`; API prefix `/api/v1`

Start the IoT service and main backend in separate terminals; start Vite in a third terminal. Main backend calls IoT over HTTP on port 8001. For physical hardware, the ESP32 must use a reachable laptop LAN IPv4 address and connect to `ws://<LAN-IP>:8001/api/v1/ws/iot/gate`; `localhost`/`127.0.0.1` on the ESP32 points to the ESP32 itself, not the laptop.

Available validation suites include:

- Backend: pytest under `backend/tests/` (run from `backend/` with the backend environment installed).
- IoT service: pytest under `iot-service/tests/` (run from `iot-service/` with its environment installed).
- Frontend: `npm test` and `npm run build` from `frontend/`.

Test counts recorded in older sections of this document were snapshots from past runs and are intentionally not represented as current passing results. Run the suites against the present checkout for current results. Simulator success is protocol evidence only, not physical hardware evidence.

## 14. Known Limitations and Documentation Drift

1. **No physical crossing/position sensing:** gate state and movement/occupancy metrics are command-, authorization-, or workflow-derived only. Do not call them sensor-confirmed facts.
2. **No manual latch persistence:** manual-open mode is volatile on the backend and ESP32. Firmware startup initializes CLOSED; persistence through power loss is not guaranteed.
3. **In-memory state:** software gate state, IoT recent event buffers, and some command/telemetry state are not durable application records.
4. **Multiple WebSocket routes:** the main backend registers `/ws/gate/monitor` and the gate router also registers `/api/gate/ws/monitor`; the current frontend clients use `/ws/gate/monitor`. The IoT microservice has its own device and monitor WebSockets.
5. **Authentication differences:** REST protected routes load the active account and check role. Some WebSocket handshakes perform token signature/subject checks without the same full account/role lookup. IoT standalone monitor authentication should be evaluated separately from device authentication.
6. **Email delivery is synchronous:** notifications may add provider/network latency to request processing. There is no independent email worker or scheduled retry processor in the source reviewed.
7. **Timezone sources differ:** schedule/campus analytics use configured campus timezone behavior; reports use a fixed `Asia/Kolkata` constant.
8. **Live inference is sequential:** the live frame endpoint runs face and ALPR work sequentially, not concurrently.
9. **Legacy documentation is stale:** `docs/IOT_GATE_INTEGRATION_ARCHITECTURE.md` describes an older direct ESP32-to-main-backend socket, old port/path/auth names, and old message formats. Current device protocol is ESP32-to-IoT-service on port 8001, `/api/v1/ws/iot/gate`, using `device_id` and `token`.
10. **Old `knowledge.md` claims superseded:** historical text incorrectly stated bcrypt/Passlib, obsolete AI/schedule/watchlist endpoint prefixes, stale gate close timings, automatic close/manual latch conflation, insecure real email examples, overly strong production-readiness/testing claims, and visitor pass approval as verified physical occupancy. The current sections above replace those assertions.
11. **Environment-dependent systems not verified here:** live PostgreSQL/Supabase status, migrations on any deployed DB, pgvector availability, downloaded AI weights, actual ONNX provider/GPU availability, email delivery, network/firewall, flashed firmware version, and physical servo/LCD behavior.

## 15. Source of Truth and Related Documentation

For detailed architecture and a textual diagram blueprint, see [`SMARTGUARD_AI_SYSTEM_ARCHITECTURE_REPORT.md`](./SMARTGUARD_AI_SYSTEM_ARCHITECTURE_REPORT.md). Relevant implementation sources include:

- `backend/app/main.py`, `backend/app/core/config.py`, `backend/app/core/security.py`, `backend/app/api/dependencies.py`
- `backend/app/api/routes/ai_verify.py`, `backend/app/api/routes/access.py`, `backend/app/api/routes/gate.py`
- `backend/app/services/face_service.py`, `backend/app/services/alpr_service.py`, `backend/app/services/access_decision_service.py`
- `backend/app/services/gate_service.py`, `backend/app/services/iot_service.py`, `backend/app/services/campus_analytics_service.py`
- `backend/app/services/visitor_service.py`, `backend/app/services/alert_service.py`, `backend/app/services/notification_service.py`
- `backend/app/models/`, `backend/alembic/versions/`
- `iot-service/app/api/routes.py`, `iot-service/app/config.py`, `iot-service/app/services/device_manager.py`
- `iot-service/firmware/esp32_gate_controller/esp32_gate_controller.ino`
- `iot-service/scripts/mock_esp32.py`
- `frontend/src/App.tsx`, `frontend/src/context/AuthContext.tsx`, `frontend/src/api/client.ts`
- `frontend/src/pages/security/SecurityDashboard.tsx`, `frontend/src/pages/security/IotGateMonitor.tsx`
- `frontend/src/components/security/CampusEntryOverview.tsx`

Keep this document aligned with source changes. When behavior changes, update this reference and the directly related API/architecture documentation; record measured test results with the date and exact command instead of carrying forward historical claims as current status.
