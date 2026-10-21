# SmartGuard AI — System Architecture Report

**Repository:** `D:\Gate-Security-System`  
**Investigation date:** 2026-10-21  
**Scope:** Source-based architecture discovery. This report describes the current repository; it is not a deployment verification or hardware test. No architecture diagram is included.

## 1. Executive Summary

SmartGuard AI is a browser-based campus gate security and visitor-management application. It combines a React/TypeScript security dashboard, a main FastAPI API, PostgreSQL with pgvector, image-based face and vehicle-plate recognition, access-policy services, visitor passes and approvals, security alerts and email delivery, and a separately runnable IoT FastAPI service that manages an ESP32 WebSocket connection.

The main backend owns application login, role authorization, AI request orchestration, access decisions, schedules, watchlists, visitor state, and the software gate state machine. It does not maintain the ESP32's device WebSocket. A separate IoT microservice owns that single physical-device connection and forwards commands. The main backend communicates with that microservice over authenticated HTTP and receives its status/events through polling; authenticated dashboard clients receive gate and IoT updates through a WebSocket served by the main backend.

The repository contains canonical ESP32 firmware for an SG90-compatible servo and 16×2 I2C LCD. The firmware reports its commanded gate state, heartbeat, and command acknowledgements, but no gate-position or person-crossing sensor is configured. Therefore neither an ESP32 acknowledgement nor an `OPEN`/`CLOSED` report independently proves physical movement or a person entering/exiting.

The source shows real implementations for most named application subsystems. However, live database credentials and availability, model downloads/runtime availability, cloud storage configuration, email provider configuration, LAN connectivity, and physical hardware behavior are environment-dependent and were not verified as part of this source investigation.

## 2. Verified Technology Stack

| Component | Technology | Actual purpose | Evidence | Status |
|---|---|---|---|---|
| Frontend | React 19, TypeScript, Vite, Tailwind CSS v4, Lucide React, React Router, Axios | Security/admin SPA, camera workflow, management views, and API calls | [frontend/package.json](frontend/package.json), [frontend/src/main.tsx](frontend/src/main.tsx), [frontend/vite.config.ts](frontend/vite.config.ts) | IMPLEMENTED |
| Main API | Python 3.12+, FastAPI, Pydantic 2, Uvicorn | Authentication, application APIs, decisions, persistence integration, backend dashboard WebSocket | [backend/requirements.txt](backend/requirements.txt), [backend/app/main.py](backend/app/main.py) | IMPLEMENTED |
| ORM/migrations | SQLAlchemy 2.x, Alembic | PostgreSQL models, per-request DB sessions, versioned schema | [backend/app/db/session.py](backend/app/db/session.py), [backend/alembic/env.py](backend/alembic/env.py), [backend/alembic/versions/](backend/alembic/versions/) | IMPLEMENTED |
| Database | PostgreSQL, configured for SSL when using a PostgreSQL URL; Supabase is the documented provider | Operational records and accounts; relational links and constraints | [backend/app/db/session.py](backend/app/db/session.py), [backend/alembic/versions/001_initial_schema.py](backend/alembic/versions/001_initial_schema.py) | IMPLEMENTED; live service UNVERIFIED |
| Vector search | pgvector, `vector(512)` face embedding and cosine search | Stores and searches ArcFace face embeddings | [backend/alembic/versions/002_phase2_schema.py](backend/alembic/versions/002_phase2_schema.py), [backend/app/services/face_service.py](backend/app/services/face_service.py) | IMPLEMENTED; extension availability UNVERIFIED |
| Face recognition | InsightFace `buffalo_l` / ArcFace, ONNX Runtime | Face detection, embedding extraction, nearest profile matching | [backend/app/services/face_service.py](backend/app/services/face_service.py), [backend/app/services/ai_diagnostics.py](backend/app/services/ai_diagnostics.py) | IMPLEMENTED; model/runtime availability UNVERIFIED |
| ALPR | FastALPR and ONNX Runtime | License-plate detection/OCR and exact normalized plate lookup | [backend/app/services/alpr_service.py](backend/app/services/alpr_service.py) | IMPLEMENTED; model/runtime availability UNVERIFIED |
| File/object storage | Local filesystem plus optional Supabase Storage | Face images, verification evidence, live event frames, and visitor QR images | [backend/app/services/storage_service.py](backend/app/services/storage_service.py) | IMPLEMENTED; cloud configuration UNVERIFIED |
| Email | Brevo transactional API or SMTP | Visitor pass email, alert messages, daily summaries, test email | [backend/app/services/email_service.py](backend/app/services/email_service.py), [backend/app/services/notification_service.py](backend/app/services/notification_service.py) | IMPLEMENTED; delivery configuration UNVERIFIED |
| IoT service | Separate FastAPI/Uvicorn service, HTTP/JSON, WebSockets | Sole live ESP32 connection manager, command dispatch, state/heartbeat tracking, telemetry | [iot-service/app/main.py](iot-service/app/main.py), [iot-service/app/services/device_manager.py](iot-service/app/services/device_manager.py) | IMPLEMENTED; live device UNVERIFIED |
| Firmware | Arduino C++ for ESP32, Wi-Fi, WebSockets, ArduinoJson, ESP32Servo, LiquidCrystal_I2C | Commands servo and LCD; sends state, heartbeat, acknowledgements | [iot-service/firmware/esp32_gate_controller/esp32_gate_controller.ino](iot-service/firmware/esp32_gate_controller/esp32_gate_controller.ino) | IMPLEMENTED in source; hardware operation UNVERIFIED |
| Gate position sensing | None found | No independent physical-position or person-crossing verification | Firmware pin/setup source and gate response contracts | NOT IMPLEMENTED |

**Important stack corrections from source:** passwords use Argon2id (`argon2-cffi`), not bcrypt/Passlib. JWTs are signed using the configured algorithm whose default is HS256. The `knowledge.md` narrative includes several stale stack and IoT claims; source files and migrations are authoritative for this report.

## 3. System Context

### Human actors

- **Administrator (`ADMIN`):** manages security accounts, campus people, vehicles, schedules, reports, notification contacts, and notification logs. Administrators can also use security-operational screens.
- **Security officer (`SECURITY`):** performs gate operations, runs verification, reviews alerts, manages visitor scan/approval workflows, and monitors the IoT device.
- **Campus people:** students, staff, visitors, and contractors are records in `campus_people`; they are not application login accounts.
- **Visitors/hosts:** visitors may be registered as campus people, associated with host people, and issued time-limited QR passes.

### External systems and boundary

- The browser uses local camera access and makes HTTP requests to the main backend.
- The main backend connects to PostgreSQL (Supabase is the configured/documented deployment target).
- Optional Supabase Storage and optional Brevo/SMTP are external provider boundaries.
- The main backend calls the independent IoT service over HTTP. The ESP32 connects to the IoT service over a device-authenticated WebSocket.
- The physical hardware boundary consists of an ESP32, a servo, and an I2C LCD. No position sensor, obstacle sensor, or crossing sensor appears in the firmware configuration.

The system is developed as separate frontend, main-backend, and IoT-service processes. The repository does not show a Docker Compose deployment, Kubernetes configuration, Redis, Celery, a message broker, or a production reverse-proxy definition.

## 4. High-Level Architecture

1. **Browser application:** React Router mounts role-protected dashboards. Axios calls the main API using `VITE_API_BASE_URL` and attaches the stored bearer token.
2. **Main FastAPI backend:** `/api/*` routers authenticate operators, validate requests, run service logic, access PostgreSQL, and return Pydantic responses.
3. **AI processing:** uploaded camera JPEGs are decoded in the backend. The face and ALPR functions process the same live frame in sequence, then persist selected recognition records and evidence.
4. **Decision/persistence:** the access decision service re-loads recent face/ALPR records from the database, checks identity/vehicle policy, schedule, and watchlist, then records an `access_attempts` row.
5. **Software gate and IoT bridge:** `gate_service` holds a process-local simulation state. On an allowed automated decision it starts the software auto-close timer and schedules an open command through `iot_manager`. `iot_manager` calls the IoT service using HTTP.
6. **IoT service and ESP32:** the microservice authenticates and maintains one device WebSocket; it serializes outgoing commands, waits for ACKs, and broadcasts status/events. The ESP32 drives the servo target and LCD and reports its state.
7. **Dashboard updates:** the main backend WebSocket broadcasts gate status and IoT telemetry to authenticated dashboards. REST polling is used as a fallback on the gate view and by the backend bridge to collect IoT service status/event data.

The three gate-related sources of state have different roles: `gate_service` is an in-memory software simulation; the IoT service stores the latest device-reported snapshot; firmware stores volatile controller state and controls the servo target. None is an independent physical position sensor or persisted, sensor-confirmed campus-presence ledger.

## 5. Detailed Component Inventory

| Component | Responsibility / location | Inputs | Outputs and dependencies |
|---|---|---|---|
| Browser bootstrap and routes | [frontend/src/main.tsx](frontend/src/main.tsx), [frontend/src/App.tsx](frontend/src/App.tsx) | Browser location, restored session | React application, `AuthProvider`, nested role-protected routes |
| Authentication context | [frontend/src/context/AuthContext.tsx](frontend/src/context/AuthContext.tsx) | Login/logout actions and local storage | In-memory user/token state; localStorage persistence |
| Main API client | [frontend/src/api/client.ts](frontend/src/api/client.ts) | `VITE_API_BASE_URL`, token from local storage | Bearer-authenticated Axios requests; global 401 cleanup/redirect |
| Security dashboard | [frontend/src/pages/security/SecurityDashboard.tsx](frontend/src/pages/security/SecurityDashboard.tsx) | Browser camera, operator actions, live API results | AI detections, access decisions, gate controls, review queue, gate WebSocket |
| Visitor console | [frontend/src/pages/security/VisitorManagement.tsx](frontend/src/pages/security/VisitorManagement.tsx) | Visitor/host data and browser QR camera | Pass registration, QR scanning, approval actions, visitor lifecycle display |
| Admin/security pages | `frontend/src/pages/admin/` and `frontend/src/pages/security/` | Backend REST responses | Admin account/registry/report/contact UIs; alerts, health, IoT monitoring |
| Main FastAPI app | [backend/app/main.py](backend/app/main.py) | HTTP, WebSocket, environment settings | CORS, application lifecycle, router registration, exception handlers |
| Main API routers | [backend/app/api/routes/](backend/app/api/routes/) | Validated HTTP inputs, dependencies | Login, registries, AI, decisions, gates, schedules, watchlists, visitors, alerts, reports, contacts, notifications |
| Application services | [backend/app/services/](backend/app/services/) | Typed inputs, DB sessions, external APIs | Business logic for auth, AI, policy, visitors, alerting, notifications, storage, and IoT bridge |
| SQLAlchemy DB session | [backend/app/db/session.py](backend/app/db/session.py) | `DATABASE_URL` | SSL-enabled PostgreSQL engine, pooled connections, request-scoped sessions |
| Main IoT bridge | [backend/app/services/iot_service.py](backend/app/services/iot_service.py) | Gate/manual operations and HTTP responses from IoT service | Authenticated HTTP command/status calls, 4-second status/event polling, main-backend WS broadcasts |
| IoT device manager | [iot-service/app/services/device_manager.py](iot-service/app/services/device_manager.py) | ESP32 messages and main-backend commands | Device connection, health/state snapshots, ACK Futures, watchdog, event broadcast |
| ESP32 firmware | [iot-service/firmware/esp32_gate_controller/esp32_gate_controller.ino](iot-service/firmware/esp32_gate_controller/esp32_gate_controller.ino) | Wi-Fi, WebSocket commands, board startup | Servo target, LCD, heartbeat, state reports, ACK messages |
| Simulator | [iot-service/scripts/mock_esp32.py](iot-service/scripts/mock_esp32.py) | Same microservice WebSocket protocol and environment | Simulated state/LCD/ACK/auto-close behavior; no physical hardware |

The root-level `firmware-legacy/esp32_gate_controller/` is documented as a legacy copy. The canonical sketch named by current project documentation is under `iot-service/firmware/esp32_gate_controller/`. Source inspection cannot establish which sketch, if any, is currently flashed on a board.

## 6. Frontend Architecture

### Startup and routing

- Vite's entry is [frontend/index.html](frontend/index.html) and [frontend/src/main.tsx](frontend/src/main.tsx); the latter mounts React `StrictMode`.
- [frontend/src/App.tsx](frontend/src/App.tsx) wraps the app in `AuthProvider` and `BrowserRouter`, then uses nested `RequireAuth`, `RequireRole`, and `PublicOnly` route elements.
- The UI roles are `ADMIN` and `SECURITY`. Admin pages are restricted to `ADMIN`; security operational routes allow `SECURITY` and `ADMIN`.
- [frontend/src/layouts/AppShell.tsx](frontend/src/layouts/AppShell.tsx) provides the main navigation/layout.

### Authentication and API calls

- [frontend/src/pages/auth/LoginPage.tsx](frontend/src/pages/auth/LoginPage.tsx) submits username/password through `/auth/login`, then calls the auth context login action.
- [frontend/src/context/AuthContext.tsx](frontend/src/context/AuthContext.tsx) stores the JWT and safe account profile in `localStorage` under `sg_token` and `sg_user`. It restores them on mount; it does not validate them with `/auth/me` during restoration.
- [frontend/src/api/client.ts](frontend/src/api/client.ts) reads `VITE_API_BASE_URL`, adds `Authorization: Bearer …`, and on HTTP 401 clears local storage and navigates to `/login`.
- Client-side route guards improve navigation UX but are not the authorization boundary; the backend dependencies enforce roles.

### Camera, inference, and display

- The security dashboard requests a browser `MediaStream` with `getUserMedia`, draws video frames to an offscreen canvas, encodes JPEG blobs, and posts them to `/api/ai/live-frame`.
- The frame interval is configurable in the component (default 750 ms); an in-flight ref prevents a second frame from being processed while one is outstanding. The backend also rate-limits evidence writes per detection key.
- Bounding boxes, labels, similarity/confidence, and latency fields are rendered over the previews. The dashboard retains the latest face/ALPR verification IDs and submits them with the selected direction to `/api/access/attempts`.
- Explicit upload-based face/plate verification endpoints and diagnostics are also available through [frontend/src/api/phase2.ts](frontend/src/api/phase2.ts).
- Face and plate processing for a live frame are independent in their results but are invoked sequentially in the backend endpoint; the route's prose description saying “simultaneous” does not match its call ordering.

### Gate and dashboard monitoring

- The Security Dashboard uses the authenticated main-backend WebSocket at `/ws/gate/monitor` for gate and IoT status. When disconnected, it polls `/api/gate/status` every 2.5 seconds with a single in-flight fallback request and reconnects the socket after 4 seconds.
- Manual Open/Close call `/api/gate/open` and `/api/gate/close`. The UI distinguishes command delivery/acknowledgement from physical position confirmation.
- [frontend/src/pages/security/IotGateMonitor.tsx](frontend/src/pages/security/IotGateMonitor.tsx) consumes the same backend WebSocket and polls the REST status/events every 10 seconds while disconnected.
- [frontend/src/components/security/CampusEntryOverview.tsx](frontend/src/components/security/CampusEntryOverview.tsx) polls `/api/access/analytics/campus` every 15 seconds. Its access authorizations/denials are explicitly not represented as confirmed movements; unsupported entry, exit, and occupancy metrics are unavailable.
- Other pages include alert lifecycle, visitor approval, health, report, notification history, account, people, vehicle, and contact screens. Their API clients are under `frontend/src/api/`.

### Error behavior

The Axios layer globally handles 401 by clearing the local session and redirecting. Other views commonly show local error messages or console warnings. The frontend stores bearer tokens in script-accessible localStorage rather than an HttpOnly cookie.

## 7. Backend Architecture

### Initialization and routing

[backend/app/main.py](backend/app/main.py) creates the FastAPI app, configures logging and CORS from settings, registers routers under `API_PREFIX` (default `/api`), and registers `/ws/gate/monitor` as a root WebSocket. Development OpenAPI pages are conditional on development mode. The app lifespan validates critical settings but logs configuration errors and continues startup, enabling liveness reporting.

Major REST groups include:

| Prefix | Responsibility | Examples |
|---|---|---|
| `/api/auth` | Login/profile | `/login`, `/me` |
| `/api/admin` | Security account administration | Accounts CRUD/status/password reset |
| `/api/health` | Process and DB readiness | `/live`, `/ready` |
| `/api/people`, `/api/vehicles` | Campus registry | Registration, search/update, photo and face enrollment |
| `/api/ai` | Face, ALPR, diagnostics, evidence | `/live-frame`, `/verify-face`, `/verify-plate`, histories |
| `/api/access` | Access decisions and audit | `/attempts`, `/pending-reviews`, `/attempts/{id}/resolve`, `/analytics/campus` |
| `/api/gate` | Software state, manual gate commands, IoT monitoring | `/status`, `/open`, `/close`, `/reset`, `/iot/status`, `/iot/events` |
| `/api/access/schedule` | Operating schedule configuration | GET/PUT schedule |
| `/api/watchlist` | Plate/vehicle watchlist | CRUD/filter |
| `/api/visitors` | Visitor registry, QR passes, scan/approval, active visitor view | `/passes`, `/scan`, `/approvals/*`, `/active-inside` |
| `/api/alerts` | Alert metrics and lifecycle | List/detail/acknowledge/investigate/note/resolve/dismiss |
| `/api/reports` | Access exports and daily summaries | `/access`, `/access/export`, `/daily-summary` |
| `/api/admin/security-contacts` | Recipient configuration and test email | contacts/config-status |
| `/api/admin/notifications` | Delivery logs and retries | list, retry, retry-all |

Pydantic request/response models are in `backend/app/schemas/`. SQLAlchemy sessions are injected per request and closed in `get_db()`. Explicit commits/rollbacks are performed by service and route paths; there is no global unit-of-work middleware.

### Service-layer ownership

- `account_service.py` and `account_repository.py`: account authentication and admin account workflows.
- `face_service.py`, `alpr_service.py`, and `ai_diagnostics.py`: inference, vector matching, ALPR matching, runtime diagnostics/provider choice.
- `access_decision_service.py`, `schedule_service.py`, and `watchlist_service.py`: policy evaluation and access-attempt recording.
- `gate_service.py`: in-memory simulated state, auto-close timer, and command delegation.
- `iot_service.py`: main-backend-to-IoT HTTP bridge, polling, event buffer, main-backend WebSocket broadcast.
- `visitor_service.py`: pass issuance, QR credentials, scan, approval/denial, check-in/check-out lifecycle.
- `alert_service.py`, `notification_service.py`, `email_service.py`: incident rules, delivery tracking, and external email transport.
- `storage_service.py`: local and Supabase object storage.

### Error handling and health

The app has explicit Pydantic validation and generic exception handlers. Services also have local logging/error paths; behavior varies by subsystem. `/api/health/live` indicates process liveness. `/api/health/ready` performs a combined database/pgvector check with a PostgreSQL query and returns 503 if either check fails. The readiness check is real work on every request, not a cached answer.

## 8. AI Processing Architecture

### Face recognition path

1. The browser captures a video frame or an operator uploads an image.
2. The frontend sends a JPEG blob or multipart image to `/api/ai/live-frame` or `/api/ai/verify-face`.
3. The route enforces supported image content types and a 10 MB limit, then reads bytes.
4. `face_service.detect_and_embed()` lazily initializes InsightFace `FaceAnalysis(name="buffalo_l")`, decodes using OpenCV, and obtains face bounding boxes/landmarks and embeddings.
5. `ai_diagnostics.get_execution_providers()` prefers CUDA when available and otherwise CPU. This is runtime-dependent; actual GPU availability was not probed.
6. Embeddings are 512-dimensional ArcFace vectors. Enrollment stores them in `face_profiles.embedding` (`vector(512)`).
7. `search_face()` performs PostgreSQL pgvector cosine-distance nearest-neighbor search over active people. Similarity ≥ 0.45 is `matched`; ≥ 0.30 but below 0.45 is `low_confidence`; otherwise `no_match`.
8. Explicit verification persists `face_verifications`; live-frame processing persists selected detections and evidence on its cooldown, not every frame.
9. Response includes recognition status, confidence/distance, candidate/person data, and bounding boxes for display.

### Number-plate path

1. The browser frame/upload is sent to `/api/ai/live-frame` or `/api/ai/verify-plate`.
2. `alpr_service.detect_plates()` decodes the image and calls FastALPR (the source comments identify YOLO-v9 detection and cct-xs OCR).
3. Plate text is uppercased and whitespace, hyphens, and dots are removed.
4. `match_plate()` performs an exact lookup against the normalized vehicle plate in PostgreSQL.
5. The full verification route records an `alpr_verifications` result; live-frame processing records eligible detections and evidence on the cooldown.
6. The response includes plate text, normalized plate, detection/OCR confidence, matched vehicle, and bounding boxes.

The two live pipelines are called in sequence by `process_live_frame`, not concurrently, despite the endpoint's “simultaneous” description. A full access evaluation later correlates them by the verification record IDs submitted by the frontend; it does not create a trusted identity simply from frontend-supplied person/vehicle claims.

### Combined access evaluation

The frontend submits `direction` plus persisted face/ALPR verification IDs. The decision service re-fetches those records, rejects invalid/missing/stale data (maximum age 120 seconds), re-fetches person and vehicle records, then checks recognition status, person/vehicle status, ownership, watchlist, and schedule. Any unresolved/security-sensitive condition fails closed to `DENY` or `MANUAL_REVIEW`; only all required checks passing yields `ALLOW`. It persists the attempt and triggers gate/alert/notification flows.

## 9. Authentication and Authorization Flow

1. Operator submits username/password to `POST /api/auth/login`.
2. `AccountService.authenticate()` loads the account, verifies the Argon2id hash, rejects inactive accounts, and opportunistically rehashes when parameters change. Invalid credentials use a generic response to avoid identifying which field failed.
3. `AccountService.build_token()` creates a signed JWT with `sub`, `iat`, `exp`, role, and username. The algorithm defaults to HS256 and expiry defaults to 30 minutes; both settings are environment-configured.
4. The frontend stores the token/profile in localStorage.
5. Axios adds a Bearer authorization header to REST requests. FastAPI decodes/verifies the signature and account ID, looks up the account (with an in-memory 10-second account cache), and checks active status and role.
6. `require_admin` permits only active ADMIN. `require_security` permits active SECURITY or ADMIN. Some registry operations are admin-only; security operations accept both allowed roles.
7. A 401 from REST clears client state and redirects to login.

`campus_people` and security login accounts (`security_accounts`) are separate identity domains. Face matching links to a campus person; operator authentication uses a security account. Frontend route restrictions are not sufficient alone; protected backend routes use authentication/authorization dependencies.

The dashboard WebSocket validates a signed JWT at handshake, but its code checks for a valid subject and signature rather than loading the active account and applying the normal REST role dependency. Device authentication is separate and uses a configured device ID/key.

## 10. Intelligent Access Control Flow

### Policy checks and precedence

The main path is `POST /api/access/attempts` → `evaluate_access_attempt()`:

1. Load recent face and ALPR verification rows from PostgreSQL and enforce the 120-second freshness window.
2. Re-fetch matched campus person and vehicle server-side.
3. Evaluate face result and face-count ambiguity.
4. Evaluate plate/OCR result and vehicle registration.
5. Query active watchlist entries by vehicle and normalized plate. High-severity blocking hits deny; review-class hits require human review.
6. Check vehicle status, person status, and vehicle/person ownership.
7. Check the per-weekday campus schedule using the configured campus timezone.
8. Apply fail-closed precedence: hard failures deny; selected uncertain/policy cases require manual review; all required checks passing allows.
9. Persist the `AccessAttempt` with decision, direction, reason codes, identities, vehicle, and policy context.
10. Apply the in-memory gate state and invoke the associated gate-control side effects.

`ENTRY` and `EXIT` are validated directions, but the normal face/plate decision service evaluates the same kinds of checks for both. Neither an `ALLOW` nor an `OPEN` gate command is a verified person crossing.

### Gate actuation semantics

- `gate_service.py` starts in `CLOSED` in process memory. Automated ALLOW transitions to `OPEN`, starts a default 15-second software timer, and asynchronously dispatches an IoT open command. The ESP32 separately runs its automated close timer.
- `DENY` sets the software state to `CLOSED` and updates the ESP32 LCD; in the current `gate_service.apply_decision()` deny branch, it does **not** dispatch a physical `GATE_CLOSE` command.
- `MANUAL_REVIEW` changes software state and updates the LCD without opening the barrier.
- Manual Open/Close endpoints require `require_security`. Manual Open sends a MANUAL command and latches backend state only after a controller execution acknowledgement. Manual Close clears the latch and updates software state only after acknowledgement. A reset sends an automated close command and does not override an active manual latch at the controller.
- Automated decisions during a backend manual latch do not actuate the gate. Controller state reports and acknowledgements are reported state, not measured physical position.

The software simulation timer and firmware auto-close timer are separate. No architecture drawing should collapse those into one mechanism.

## 11. Visitor Management Flow

1. A security operator registers or reuses a `CampusPerson` with `person_type='visitor'`; visitor reuse searches by email or phone. A host and optional vehicle/plate may be linked.
2. Pass creation validates `valid_until > valid_from`, generates a random URL-safe token, stores only its SHA-256 hash in `visitor_passes`, generates a QR image, and writes the QR through local/Supabase dual storage. The API returns QR content for display/printing; email delivery is optional.
3. The browser scans QR data using `jsQR` or accepts manual entry and posts the credential/direction to `/api/visitors/scan`.
4. The service hashes the submitted credential and looks up the pass. Revoked, completed/reused, invalid-window, and other invalid states are rejected. Invalid scans can create/deduplicate security alerts.
5. An ENTRY scan creates/reuses a pending `VisitorApproval`; the gate remains closed pending security decision.
6. An officer approves or denies through the approval endpoints. Approval transactionally changes the pass to `ACTIVE_INSIDE`, sets `check_in_at`, creates an ALLOW ENTRY access attempt, resolves its associated alert, commits, then commands gate open. The check-in timestamp is written at approval, not from a crossing sensor.
7. EXIT requires `ACTIVE_INSIDE`; the service marks the pass `COMPLETED`, writes `check_out_at`, creates an ALLOW EXIT access attempt, commits, then opens the gate. This records an exit workflow, not an independently sensed crossing.
8. Passes can be revoked; validity expiration is checked during scan/list response. The active visitor page is based on pass `ACTIVE_INSIDE` state.

The UI and data model therefore implement a visitor lifecycle but do not provide physical entry/exit proof. “Active inside” represents approved pass lifecycle state.

## 12. Security Alerts and Notification Flow

### Alerts

`access_decision_service` calls `alert_service` after an access attempt is persisted. Rules include watchlist hits, DENY decisions, MANUAL_REVIEW, and repeated denials grouped by normalized plate/window. Alert deduplication keys merge repeated logical alerts; manual-review alerts are per-attempt. Alert failures are caught/logged so they do not change the access decision. Visitor flows can also create approval and invalid-QR alerts.

Alerts persist category, severity, status, related attempt/person/vehicle/pass, occurrence count, dedup key, assignment/acknowledgement/resolution, and timestamps in `security_alerts`. `alert_notes` stores investigation notes/history. API actions support acknowledge, investigate, add note, resolve, and ADMIN-only dismiss.

### Email and reports

- `security_contacts` holds recipients, active state, category/severity preferences, and daily-summary preference.
- `notification_log` stores ALERT, DAILY_SUMMARY, and TEST delivery status, attempts, timestamps, provider identifiers, errors, idempotency key, and summary date.
- `email_service` sends through Brevo HTTPS API or SMTP depending on settings.
- Alert notification code creates notification rows and immediately invokes pending processing. This processing uses synchronous email transport in the request call stack; it is not an external worker/background queue. Although it is described as non-blocking in some comments, network send latency can therefore add to the triggering request.
- Retry is bounded (up to three attempts with 60/300/900-second delays) and the repository exposes admin retry endpoints. No scheduler/worker that automatically wakes at retry time was found; retry processing is triggered by subsequent queue/retry calls.
- Daily summaries are computed on demand and can be manually emailed by an ADMIN. No scheduled daily-summary job was found.
- Access reports support server-side filtering, CSV export, and daily summary. The report module uses a fixed `Asia/Kolkata` timezone constant; schedule evaluation and the campus analytics endpoint use the configured schedule timezone. These are separate timezone sources.

Notification delivery configuration is optional. Failed sends are logged and retried within implemented limits; visitor pass issuance and test-email paths call email delivery synchronously as well.

## 13. Database and Storage Architecture

### Database

SQLAlchemy models and five ordered Alembic migrations define the schema. The database engine uses SSL for PostgreSQL URLs, a bounded connection pool, pre-ping, and per-request sessions. The readiness check queries database connectivity and pgvector availability.

Main table groups:

- **Identity/governance:** `security_accounts`, `audit_logs`.
- **Campus registry:** `campus_people`, `vehicles`.
- **Biometrics/verification:** `face_profiles`, `face_verifications`, `alpr_verifications`.
- **Access policy/audit:** `access_schedules`, `watchlist_entries`, `access_attempts`.
- **Alerts/communications:** `security_alerts`, `alert_notes`, `security_contacts`, `notification_log`.
- **Visitors:** `visitor_passes`, `visitor_approvals`.

Important links include vehicle owner → campus person; face profile/verification → campus person; access attempt → person, vehicle, face/ALPR verification, and optional visitor pass; alert → attempt/person/vehicle/watchlist/pass; visitor pass → visitor/host/vehicle; approval → pass/visitor/security account/access attempt/alert; notification → alert/contact.

`access_attempts` stores authorization decisions, intended gate result, and context. It has no sensor-confirmed movement column/event table. No unique physical crossing ledger exists.

### Files and objects

`storage_service.py` always attempts local filesystem storage under `backend/storage/` for `face-images`, `access-evidence`, and `visitor-qr`, and separately attempts optional private Supabase Storage upload. Database rows store paths, not image bytes. Cloud-storage failure is treated as non-fatal by the dual-write service; both success flags are returned. AI/visitor processing state, gate timers, IoT state, and event buffers also exist in process memory and are not durable database state.

## 14. IoT and Gate Controller Architecture

### Ports and paths

| Component | Port/path | Purpose |
|---|---|---|
| Main FastAPI | Development README command uses port 8000 | REST `/api/*`; authenticated dashboard WebSocket `/ws/gate/monitor` |
| IoT FastAPI | Default port 8001 | REST `/api/v1/*`; standalone monitor served at `/` and `/monitor` |
| Device WebSocket | `/api/v1/ws/iot/gate` on port 8001 | ESP32 or simulator persistent connection |
| IoT monitor WebSocket | `/api/v1/ws/monitor` on port 8001 | Standalone IoT dashboard telemetry |
| Main backend bridge | HTTP to `http://localhost:8001` by default | Status/events and automated/manual commands |

### Main-backend-to-IoT flow

- The main backend includes one in-process `IoTManager` for proxying; it is **not** a second ESP32 WebSocket manager.
- Startup schedules an async loop that polls the IoT service status and event endpoints every four seconds. Status snapshots and deduplicated recent events are broadcast to main-backend dashboards.
- Service requests include `X-Service-Secret`. Manual requests additionally include forwarded `X-Operator-Role` and `X-Operator-Id` after the main API has verified the operator JWT.
- Automated statuses go to `POST /api/v1/gate/status`; MANUAL OPEN and CLOSE use distinct `/api/v1/gate/manual-open` and `/api/v1/gate/manual-close` routes. The HTTP service has bounded connect/response timeout behavior; device command ACK waiting defaults to five seconds.
- The backend REST gate state is an in-memory simulation. IoT status is another snapshot and may be UNKNOWN/offline.

### ESP32 connection authentication and protocol

- The firmware connects to the microservice on port 8001 at `/api/v1/ws/iot/gate?device_id=…&token=…`.
- The microservice checks those values against `IOT_DEVICE_ID` and `IOT_DEVICE_KEY`. If query/header authentication is absent, it accepts the socket and waits up to five seconds for an `AUTH` JSON frame; invalid credentials close with WebSocket policy code 1008.
- Only one device connection is retained. A newer connection supersedes/closes the prior connection.
- ESP32 sends `HEARTBEAT` every 10 seconds and `GATE_STATE` after state transitions. Heartbeat includes state/mode, uptime, RSSI, and heap. The service watchdog checks every five seconds and closes the connection after the configured 30-second heartbeat timeout.
- The service sends `GATE_OPEN`, `GATE_CLOSE`, and `DISPLAY_STATUS` JSON commands. Gate commands carry sequence, command ID, command type (`AUTOMATED` or `MANUAL`), duration/reason, and LCD lines. ACKs can be `ACCEPTED`, `EXECUTED`, `COMPLETED`, `REJECTED`, or `FAILED`; final ACKs resolve pending command futures.
- Device event/state/ACK reports are broadcast to dashboards. State reports do not themselves command a servo.

The IoT standalone monitor WebSocket currently has comments/code permitting connections without validating its query token. It should not be confused with the authenticated main-backend monitor socket.

### Simulator and physical firmware

The Python simulator uses the same `/api/v1/ws/iot/gate` path, `device_id`/`token` query parameters, `HEARTBEAT`, `GATE_STATE`, `GATE_OPEN`, `GATE_CLOSE`, ACK, sequence, and manual-latch semantics. It simulates gate/LCD state and an automated timer; it cannot test Wi-Fi, PWM, wiring, physical servo travel, or gate position.

Canonical firmware hardware/timing constants:

- Servo signal GPIO 18; closed/open target 0°/90°.
- LCD I2C SDA 21, SCL 22, address `0x27`, 16×2.
- Firmware heartbeat every 10 seconds; default automated open timer 15 seconds.
- Wi-Fi reconnect attempts are non-blocking and spaced 10 seconds apart; WebSocket reconnect interval is 3 seconds.
- Manual open sets `MANUAL_LATCHED_OPEN`, disarms the close timer, and displays `MANUAL GATE OPEN` / `WAITING TO CLOSE`. Automated open retains a close timer. Manual Close clears the latch. Firmware starts safely at CLOSED; this volatile latch does not persist over restart.
- Firmware logs incoming close-command type/reason and physical servo close calls. Servo write is a commanded angle, not position feedback.

## 15. Deployment and Runtime Architecture

Documented local development uses three independent processes:

1. Frontend Vite development server, normally port 5173.
2. Main FastAPI/Uvicorn backend, port 8000.
3. IoT FastAPI/Uvicorn service, port 8001.

`frontend/.env.example` defines `VITE_API_BASE_URL`. Backend configuration includes application/API/CORS settings, database URL, Supabase settings, JWT settings, IoT bridge settings, and email/SMTP settings. The IoT service settings include host/port, log level, device ID/key, service secret, CORS origins, heartbeat timeout, ACK timeout, and automated-close duration. The firmware reads Wi-Fi/server/device credentials through local `secrets.h` macros (`SG_WIFI_SSID`, `SG_WIFI_PASSWORD`, `SG_IOT_SERVER_HOST`, `SG_IOT_DEVICE_ID`, `SG_IOT_DEVICE_TOKEN`). No credential values are reproduced here.

AI models are lazy-loaded on the first inference call rather than loaded during app startup. Runtime checks report whether ONNX Runtime, InsightFace, FastALPR, and possible CUDA providers are available. Production hosting, TLS termination, reverse proxy behavior, cloud deployment topology, database backup settings, and live LAN/firewall configuration are not defined or verified by repository inspection.

Configuration discrepancies to resolve operationally:

- Backend `.env.example` does not enumerate all fields available in `Settings` (including email fields and some optional Supabase/base-URL values).
- The IoT `.env.example` includes servo-angle values labeled informational; the current service `Settings` does not consume them. The actual firmware angles are constants.
- Main `IOT_MICROSERVICE_URL` must reach the IoT REST service; physical-device `SG_IOT_SERVER_HOST` must be a reachable LAN address, not loopback.
- Device and service credentials are distinct and must be configured on their respective sides. Their actual values are intentionally omitted.

## 16. End-to-End Data Flows

### Normal student/staff entry or exit

1. A security operator selects direction and starts the dashboard's camera workflow.
2. Browser frame capture posts JPEG to `/api/ai/live-frame`; backend returns face/plate detections and may persist verification records.
3. Operator workflow submits the latest verification record IDs plus `ENTRY` or `EXIT` to `/api/access/attempts`.
4. Backend reloads those records and campus identity/vehicle, applies the policy precedence, then writes the access attempt.
5. ALLOW updates software gate state and dispatches an automated open through backend HTTP → IoT HTTP → ESP32 WebSocket. Firmware sets servo target OPEN, reports ACK/state, and its automated timer closes later.
6. DENY or MANUAL_REVIEW is persisted and reflected in the UI; main service may create alerts/notifications. A deny updates the LCD/software state but the normal deny branch does not send a physical close command.
7. Main-backend WebSocket streams gate/IoT status; REST polling is fallback. Events are decisions and controller reports, not confirmed person movements.

### Manual review

1. An uncertain policy result is stored as `MANUAL_REVIEW`, with gate kept closed and review required.
2. An authorized officer resolves the queued attempt with a mandatory reason.
3. On approval, the service re-checks watchlist/person/vehicle conditions, commits review data, and applies an ALLOW gate decision; denial records resolution without opening.

### Visitor entry/exit

1. Registration/pass issuance creates or reuses visitor identity, issues QR token/pass, and optionally emails it.
2. ENTRY scan validates credential/window and creates a pending approval; it does not open gate.
3. Officer approval marks the pass `ACTIVE_INSIDE` and writes a check-in timestamp before gate actuation; that timestamp is approval workflow metadata, not crossing confirmation.
4. EXIT scan requires `ACTIVE_INSIDE`, marks pass `COMPLETED`, records check-out and an allowed EXIT attempt, then actuates gate open.
5. No hardware sensor confirms either crossing.

### Alert and notification

1. A persisted access attempt is evaluated for deny/watchlist/review/repeated-denial alert conditions.
2. Alert is inserted/merged using deduplication rules and shown in the alert UI.
3. Eligible contacts are selected using active status, severity, and category preferences. Notification rows are committed.
4. Email transport is attempted synchronously by the notification service on the triggering path; results/errors are logged, and bounded retries can be rescheduled through the API.
5. Admin can inspect delivery logs/retry; daily summary calculation/send is an explicit API action, not a discovered scheduled job.

## 17. Architecture Diagram Blueprint

This is a textual blueprint for a later diagram, not a generated diagram.

### A. Diagram layers

1. **Actors and browser client**
2. **Main application API and service layer**
3. **AI inference and policy evaluation**
4. **Persistent database and file/object storage**
5. **External email/storage providers**
6. **IoT microservice and device WebSocket boundary**
7. **ESP32 and physical actuator/display**

### B. Component boxes

Required boxes:

- **Security Officer / Administrator** — browser operators.
- **React Security Dashboard** — login, camera workflow, visitor approvals, manual gate control, alert and IoT views.
- **Main FastAPI Backend** — REST APIs, JWT/RBAC, orchestration.
- **Face Recognition (InsightFace / ONNX Runtime)** — detection, embedding, identity search.
- **ALPR (FastALPR / ONNX Runtime)** — plate OCR and vehicle lookup.
- **Access Decision + Schedule + Watchlist Services** — policy checks and persisted allow/deny/review decision.
- **Visitor Management Service** — QR pass lifecycle and officer approval.
- **Gate State Simulation + IoT HTTP Bridge** — process-local simulated state and commands/status proxy.
- **Alert + Notification Services** — incident handling, email delivery bookkeeping.
- **PostgreSQL + pgvector** — application records and face embeddings.
- **Local File Storage / Optional Supabase Storage** — image/evidence/QR objects.
- **Optional Brevo or SMTP Provider** — email transport.
- **IoT FastAPI Microservice / Device Manager** — physical WebSocket owner, ACK/heartbeat/state/event manager.
- **ESP32 Controller Firmware** — command parser, timer, heartbeat, state and ACK publisher.
- **Servo (GPIO 18)** and **16×2 I2C LCD** — controlled hardware.
- **Mock ESP32 Simulator** — optional replacement device endpoint for protocol testing, clearly marked simulation.

### C. Connections

| Source | Destination | Protocol / data | Direction and timing |
|---|---|---|---|
| Operator | React dashboard | Browser UI, camera permission and QR scan | User-driven |
| React dashboard | Main FastAPI | HTTPS/HTTP REST JSON/multipart; bearer JWT | Request/response synchronous |
| React dashboard | Main FastAPI monitor socket | WebSocket `/ws/gate/monitor`, JWT query token; INIT/STATUS_UPDATE/EVENT | Bidirectional persistent; pushed updates |
| Main FastAPI | PostgreSQL | SQLAlchemy/PostgreSQL queries and transactions | Synchronous request service operations |
| Face/ALPR services | PostgreSQL | pgvector search, registry lookup, verification records | Synchronous |
| Backend storage service | Local filesystem | Image/QR bytes | Synchronous write |
| Backend storage service | Supabase Storage (optional) | Supabase SDK object upload | Synchronous best-effort write |
| Access/visitor services | Gate simulation | In-process function calls and timer scheduling | In-process |
| Main backend IoT bridge | IoT FastAPI | HTTP JSON with service-secret and forwarded operator headers | Request/response; status/events polled every 4s |
| IoT FastAPI device manager | ESP32/simulator | WebSocket JSON: GATE_OPEN, GATE_CLOSE, DISPLAY_STATUS, HEARTBEAT, GATE_STATE, ACK | Persistent bidirectional |
| IoT device manager | Main-backend dashboard subscribers | Internal callback/broadcast via main backend WebSocket registry | Pushed event/status |
| ESP32 firmware | Servo | PWM target angle 0°/90° | Local physical command |
| ESP32 firmware | LCD | I2C text update | Local physical command |
| Alert/notification service | Brevo or SMTP | HTTPS API or SMTP | Synchronous transport in current call flow |
| Mock simulator | IoT service | Same device WebSocket protocol | Persistent; software-only |

### D. Boundaries

- Browser/frontend ↔ main API: authentication and input trust boundary.
- Main API ↔ PostgreSQL: database credentials and transaction boundary.
- Main backend ↔ IoT REST API: service-secret trust boundary; operator identity forwarded after main-backend JWT authorization.
- IoT service ↔ device: device ID/key authentication boundary; firmware credentials are separate from operator JWT.
- Backend ↔ Supabase Storage/email provider: third-party credential/network boundary.
- ESP32 ↔ servo/LCD: physical boundary with no feedback sensor in this implementation.

### E. Grouping and layout

Use a landscape layout with operator/browser at left, main API and service groups in the center, PostgreSQL/storage/email beneath or to the right of the main API, and the IoT service → ESP32 → servo/LCD chain at the far right. Draw the main-backend-to-IoT HTTP bridge separately from the ESP32 WebSocket to avoid implying the ESP32 connects to the main API directly. Place the simulator as an optional alternate client to the device WebSocket, not alongside physical hardware as an additional deployed controller.

### F. Required versus optional

Required: browser, main backend, decision/AI, database, IoT service, ESP32, actuator/display, and external provider boundaries that are actually configured. Optional: simulator, local-vs-cloud storage alternatives, detailed individual REST routes, model subcomponents, database tables, and email providers should be shown only if diagram scale allows. Do not show a person-crossing sensor or confirmed occupancy service.

## 18. Implementation Gaps and Unverified Assumptions

### Confirmed source limitations and discrepancies

- There is no sensor-confirmed gate-position or person-crossing event model. Access decisions, visitor check-in/out timestamps, and servo-target reports are not physical movement proof.
- `VisitorPass.status == ACTIVE_INSIDE` is set by officer approval, before crossing; it is a workflow state rather than measured campus occupancy.
- The main IoT bridge and the IoT device manager are separate components, but only the IoT device manager owns the device WebSocket. The backend bridge uses HTTP/polling, not a direct ESP32 socket.
- `docs/IOT_GATE_INTEGRATION_ARCHITECTURE.md` describes an older/different design, including ESP32 ↔ main-backend WebSocket on port 8000, `device_key` query authentication, and older message names. Current code/docs use IoT service port 8001, `/api/v1/ws/iot/gate`, `device_id` + `token`, and current `HEARTBEAT`/`GATE_STATE`/`GATE_ACTION_ACK` protocol. Do not use that stale document as protocol authority.
- `knowledge.md` names bcrypt/Passlib and describes “async” backend/service behavior that does not match source. Current password hashing is Argon2id; notification email dispatch is synchronously attempted in the request path.
- The face and plate inference calls in the live-frame route are sequential, despite route wording that says simultaneous.
- The normal decision deny branch updates simulated state and display but does not issue a physical GATE_CLOSE command. A prior automated open relies on the physical firmware's timer to close; reset/manual-close uses a physical close command.
- Alert retry times are recorded, but no independent retry scheduler/worker was found. Daily summary email is endpoint-triggered; no scheduled job was found.
- Main gate simulation, IoT state/event buffers, command sequence tracking, and firmware manual latch are in memory. Process/device restart does not restore a persisted manual latch.
- Main-backend WebSocket authentication verifies token signature/subject but does not apply the full active-account/role DB check used by REST dependencies. The standalone IoT monitor WebSocket code accepts the socket without validating the query token.
- Reports use a fixed `Asia/Kolkata` timezone constant, while schedule evaluation and campus overview consult the configured schedule timezone.
- Optional Supabase object upload failure does not necessarily fail local file write/API operation. Actual cloud persistence must be verified operationally.

### Not verified in this investigation

- Whether the configured Supabase project is reachable, migrations have been applied, or pgvector extension is enabled.
- Whether model packages and model weights are present, or whether CUDA is usable on the deployment machine.
- Whether email credentials/providers are configured or external messages are accepted.
- Whether a physical ESP32 is online, which firmware is flashed, whether Wi-Fi/network/firewall settings permit port 8001, and whether servo/LCD wiring and power are correct.
- Production HTTPS/WSS termination, reverse proxy, secrets rotation, backups, and deployment infrastructure.

## 19. Source Evidence

### Root documentation and manifests

- [README.md](README.md) — current runtime ports, service start-up, canonical sketch, and manual/automated mode summary.
- [knowledge.md](knowledge.md) — broad project narrative; contains stale implementation claims noted above.
- [docs/IOT_GATE_INTEGRATION_ARCHITECTURE.md](docs/IOT_GATE_INTEGRATION_ARCHITECTURE.md) — legacy IoT architecture narrative; protocol details conflict with current code.
- [frontend/package.json](frontend/package.json), [frontend/vite.config.ts](frontend/vite.config.ts), [frontend/.env.example](frontend/.env.example) — frontend dependencies, Vite plugins, API base URL variable.
- [backend/requirements.txt](backend/requirements.txt), [backend/.env.example](backend/.env.example) — Python dependencies and backend environment variable names.
- [iot-service/requirements.txt](iot-service/requirements.txt), [iot-service/.env.example](iot-service/.env.example) — IoT service dependencies and environment variable names.

### Frontend

- [frontend/src/main.tsx](frontend/src/main.tsx), [frontend/src/App.tsx](frontend/src/App.tsx) — application boot and route tree.
- [frontend/src/context/AuthContext.tsx](frontend/src/context/AuthContext.tsx), [frontend/src/routes/ProtectedRoutes.tsx](frontend/src/routes/ProtectedRoutes.tsx) — session state and UI route guards.
- [frontend/src/api/client.ts](frontend/src/api/client.ts), [frontend/src/api/phase2.ts](frontend/src/api/phase2.ts), [frontend/src/api/phase3.ts](frontend/src/api/phase3.ts), [frontend/src/api/visitors.ts](frontend/src/api/visitors.ts) — API base/auth behavior and feature clients.
- [frontend/src/pages/security/SecurityDashboard.tsx](frontend/src/pages/security/SecurityDashboard.tsx) — camera loop, access attempt workflow, gate WebSocket, manual controls.
- [frontend/src/pages/security/VisitorManagement.tsx](frontend/src/pages/security/VisitorManagement.tsx), [frontend/src/pages/security/AlertCenter.tsx](frontend/src/pages/security/AlertCenter.tsx), [frontend/src/pages/security/IotGateMonitor.tsx](frontend/src/pages/security/IotGateMonitor.tsx) — visitor, alert, and device monitoring screens.
- [frontend/src/components/security/CampusEntryOverview.tsx](frontend/src/components/security/CampusEntryOverview.tsx) — campus analytics UI and refresh.

### Backend

- [backend/app/main.py](backend/app/main.py), [backend/app/core/config.py](backend/app/core/config.py) — app, router registration, settings.
- [backend/app/core/security.py](backend/app/core/security.py), [backend/app/services/account_service.py](backend/app/services/account_service.py), [backend/app/api/dependencies.py](backend/app/api/dependencies.py), [backend/app/api/routes/auth.py](backend/app/api/routes/auth.py) — password/JWT/authentication and authorization.
- [backend/app/db/session.py](backend/app/db/session.py), [backend/alembic/env.py](backend/alembic/env.py) — database engine, session lifecycle, and migrations.
- [backend/app/api/routes/ai_verify.py](backend/app/api/routes/ai_verify.py), [backend/app/services/face_service.py](backend/app/services/face_service.py), [backend/app/services/alpr_service.py](backend/app/services/alpr_service.py), [backend/app/services/ai_diagnostics.py](backend/app/services/ai_diagnostics.py) — image routes and AI execution.
- [backend/app/services/access_decision_service.py](backend/app/services/access_decision_service.py), [backend/app/services/schedule_service.py](backend/app/services/schedule_service.py), [backend/app/services/watchlist_service.py](backend/app/services/watchlist_service.py), [backend/app/services/gate_service.py](backend/app/services/gate_service.py) — decision and gate simulation.
- [backend/app/services/iot_service.py](backend/app/services/iot_service.py), [backend/app/api/routes/gate.py](backend/app/api/routes/gate.py) — IoT HTTP bridge, manual gate operations, dashboard WebSocket.
- [backend/app/services/visitor_service.py](backend/app/services/visitor_service.py), [backend/app/api/routes/visitors.py](backend/app/api/routes/visitors.py) — visitor and QR lifecycle.
- [backend/app/services/alert_service.py](backend/app/services/alert_service.py), [backend/app/services/notification_service.py](backend/app/services/notification_service.py), [backend/app/services/email_service.py](backend/app/services/email_service.py) — alert rules, notification persistence/retry, email transport.
- [backend/app/services/storage_service.py](backend/app/services/storage_service.py), [backend/app/api/routes/reports.py](backend/app/api/routes/reports.py), [backend/app/api/routes/health.py](backend/app/api/routes/health.py) — file storage, reports/timezone, health checks.
- Models: [backend/app/models/account.py](backend/app/models/account.py), [backend/app/models/people.py](backend/app/models/people.py), [backend/app/models/access.py](backend/app/models/access.py), [backend/app/models/visitors.py](backend/app/models/visitors.py), [backend/app/models/alerts.py](backend/app/models/alerts.py).
- Migrations: [backend/alembic/versions/001_initial_schema.py](backend/alembic/versions/001_initial_schema.py), [backend/alembic/versions/002_phase2_schema.py](backend/alembic/versions/002_phase2_schema.py), [backend/alembic/versions/003_phase3_schema.py](backend/alembic/versions/003_phase3_schema.py), [backend/alembic/versions/004_phase4_schema.py](backend/alembic/versions/004_phase4_schema.py), [backend/alembic/versions/005_phase5_visitor_management.py](backend/alembic/versions/005_phase5_visitor_management.py).

### IoT, firmware, and tests

- [iot-service/app/main.py](iot-service/app/main.py), [iot-service/app/config.py](iot-service/app/config.py), [iot-service/app/api/routes.py](iot-service/app/api/routes.py), [iot-service/app/schemas/gate_status.py](iot-service/app/schemas/gate_status.py), [iot-service/app/services/device_manager.py](iot-service/app/services/device_manager.py) — service lifecycle, REST/WebSocket routes, protocol, authentication, watchdog, and ACKs.
- [iot-service/firmware/esp32_gate_controller/esp32_gate_controller.ino](iot-service/firmware/esp32_gate_controller/esp32_gate_controller.ino) — canonical firmware behavior and hardware constants.
- [iot-service/scripts/mock_esp32.py](iot-service/scripts/mock_esp32.py) — simulated device protocol.
- Tests: [backend/tests/](backend/tests/), [iot-service/tests/test_iot_service.py](iot-service/tests/test_iot_service.py), [frontend/src/api/__tests__/](frontend/src/api/__tests/), [frontend/src/utils/__tests__/](frontend/src/utils/__tests/). The tests cover unit/API behavior and simulator protocol; no source-level test can prove physical gate movement without external sensors/hardware.

---

This document is an architecture reference for a future diagram. It intentionally does not claim physical crossing detection, sensor-confirmed occupancy, or live infrastructure availability.
