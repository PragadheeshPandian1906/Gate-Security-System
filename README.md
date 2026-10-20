# SmartGuard AI — Phase 1: Authentication, Authorization & Infrastructure Foundation

SmartGuard AI is an enterprise-grade AI-powered gate security and access management system.

**Phase 1** delivers the foundational infrastructure:
- **FastAPI** backend with asynchronous SQLAlchemy and connection pooling.
- **Supabase PostgreSQL** integration with native **pgvector** extension support for high-dimensional face embedding similarity search.
- **Alembic** migration pipeline with automated revision tracking and UUID primary keys.
- **Stateless JWT Authentication** with password hashing using bcrypt.
- **Role-Based Access Control (RBAC)** strictly partitioning `ADMIN` and `SECURITY` capabilities.
- **React 19 + TypeScript + Vite + Tailwind CSS v4 + Lucide React** modern Security Operations Center (SOC) dashboard with responsive App Shell, role-based routing guards, deep charcoal aesthetic, real-time health diagnostics, and user account management.

---

## Architecture Overview

```
Gate-Security-System/
├── backend/
│   ├── alembic/              # Alembic migrations & environment
│   ├── alembic.ini           # Alembic configuration
│   ├── app/
│   │   ├── api/              # API routes (/auth, /admin, /health)
│   │   ├── core/             # Security (JWT, bcrypt), config, database session
│   │   ├── models/           # SQLAlchemy models (User with pgvector)
│   │   ├── schemas/          # Pydantic validation schemas
│   │   ├── services/         # Business logic layer
│   │   └── main.py           # FastAPI entrypoint & middleware
│   ├── tests/                # Pytest unit & integration test suite
│   ├── bootstrap_admin.py    # Admin initialization script
│   └── requirements.txt      # Python dependencies
├── frontend/
│   ├── src/
│   │   ├── api/              # Centralized Axios client & API modules
│   │   ├── components/ui/    # Reusable SOC design system components (Button, Modal, Table, etc.)
│   │   ├── context/          # AuthContext for session management
│   │   ├── layouts/          # AppShell responsive layout with navigation
│   │   ├── pages/
│   │   │   ├── auth/         # LoginPage (two-column SOC layout)
│   │   │   ├── admin/        # AdminDashboard, AccountManagement, SystemHealth
│   │   │   └── security/     # SecurityDashboard, SecurityHealth
│   │   ├── routes/           # ProtectedRoutes (RequireAuth, RequireRole, PublicOnly)
│   │   ├── theme/            # Design system tokens and constants
│   │   ├── types/            # TypeScript type definitions
│   │   └── App.tsx           # Route definitions & providers
│   ├── .env.example          # Frontend environment variables template
│   └── package.json          # Frontend dependencies & build scripts
└── README.md
```

### IoT Gate Controller

The physical ESP32 connects only to the IoT microservice on port `8001` at
`/api/v1/ws/iot/gate`. The canonical firmware sketch and simulator instructions are
documented in [iot-service/README.md](./iot-service/README.md). Configure the
backend-to-service secret independently in `backend/.env` and `iot-service/.env`;
the backend validates operator roles before forwarding manual commands. Keep
firmware Wi-Fi credentials, device token, and the current laptop LAN IPv4 in the
ignored local `secrets.h` beside the canonical sketch. Never flash with
`localhost` or `127.0.0.1` as the ESP32 server host.

Dashboard Manual Open is a separate, indefinitely latched controller mode; it
does not use the automated 15-second close timer. Only an acknowledged Manual
Close clears the latch. The controller reports the mode in heartbeat and gate
state telemetry. A firmware restart initializes the servo CLOSED; manual-latch
persistence through a power loss is not implemented.

---

## Quickstart Guide

### 1. Backend Setup

1. **Activate Virtual Environment**:
   ```powershell
   cd backend
   .\venv\Scripts\Activate.ps1
   ```

2. **Configure Environment Variables**:
   Copy `.env.example` to `.env`:
   ```powershell
   cp .env.example .env
   ```
   Set your Supabase PostgreSQL connection string and generate a JWT secret key:
   ```env
   DATABASE_URL=postgresql://postgres.YOURREF:YOURPASS@aws-0-ap-south-1.pooler.supabase.com:5432/postgres
   JWT_SECRET_KEY=your_32_character_secret_key_here
   FRONTEND_ORIGINS=http://localhost:5173
   ```

3. **Run Database Migrations**:
   ```powershell
   alembic upgrade head
   ```

4. **Bootstrap Initial Administrator**:
   ```powershell
   python bootstrap_admin.py --username admin --password "SecureAdmin123!" --name "System Administrator"
   ```

5. **Run Backend Test Suite**:
   ```powershell
   pytest
   ```

6. **Start the FastAPI Development Server**:
   ```powershell
   uvicorn app.main:app --reload --port 8000
   ```
   FastAPI Interactive Docs will be accessible at [http://localhost:8000/docs](http://localhost:8000/docs).

---

### 2. Frontend Setup

1. **Navigate to Frontend**:
   ```powershell
   cd ../frontend
   ```

2. **Verify Environment Variables**:
   Ensure `frontend/.env` contains:
   ```env
   VITE_API_BASE_URL=http://localhost:8000/api
   ```

3. **Install Dependencies** (if needed) & **Build**:
   ```powershell
   npm install
   npm run build
   ```

4. **Start the Frontend Development Server**:
   ```powershell
   npm run dev
   ```
   Open [http://localhost:5173](http://localhost:5173) in your browser.

---

## Role Access Matrix

| Feature | Endpoint / Route | `ADMIN` | `SECURITY` | Unauthenticated |
|---|---|:---:|:---:|:---:|
| User Login | `POST /api/auth/login` | :white_check_mark: | :white_check_mark: | :white_check_mark: |
| Current Session | `GET /api/auth/me` | :white_check_mark: | :white_check_mark: | :x: |
| System Liveness | `GET /api/health/live` | :white_check_mark: | :white_check_mark: | :white_check_mark: |
| Database & pgvector Diagnostics | `GET /api/health/ready` | :white_check_mark: | :white_check_mark: | :white_check_mark: |
| List Personnel Accounts | `GET /api/admin/accounts` | :white_check_mark: | :x: | :x: |
| Create Personnel Account | `POST /api/admin/accounts` | :white_check_mark: | :x: | :x: |
| Toggle Account Status | `PATCH /api/admin/accounts/{id}/status` | :white_check_mark: | :x: | :x: |
| Admin Password Reset | `POST /api/admin/accounts/{id}/reset-password` | :white_check_mark: | :x: | :x: |
| Admin Dashboard | `/admin/dashboard` | :white_check_mark: | :x: | :x: |
| Security Station Console | `/security/dashboard` | :white_check_mark: | :white_check_mark: | :x: |

---

## Next Steps (Phase 2 Preview)

Phase 2 builds directly upon this Phase 1 foundation:
- Camera capture pipelines (WebRTC / RTSP stream ingestion).
- InsightFace / FaceNet 512-dimensional vector embedding generation.
- Cosine distance similarity search querying pgvector.
- ANPR plate recognition using YOLOv8 + PaddleOCR.
- Gate barrier hardware relay automation.
