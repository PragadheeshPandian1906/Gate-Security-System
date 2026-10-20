# SmartGuard AI Gate Security System

SmartGuard AI is a gate access-control system with a React security dashboard, a
FastAPI application for identity and access decisions, and an independent IoT
microservice that manages the ESP32 controller.

## System overview

```text
Browser dashboard
    │ HTTP + authenticated dashboard WebSocket
    ▼
Main FastAPI backend ── authenticated HTTP commands/status ──► IoT microservice
    │                                                        │
    └── Supabase PostgreSQL + pgvector                       │ WebSocket
                                                             ▼
                                                   ESP32 + servo + LCD
```

The main backend owns authentication, authorization, face/vehicle verification,
and access decisions. The IoT service owns the physical ESP32 connection and
command delivery. The ESP32 reports controller state and acknowledgements; this
project does not have a gate-position sensor, so those reports do not
independently verify physical gate position.

### Project directories

| Directory | Purpose |
|---|---|
| `backend/` | FastAPI API, access decisions, database models, migrations, and tests |
| `frontend/` | React, TypeScript, Vite security and administration dashboards |
| `iot-service/` | Physical-device connection manager, simulator, API, and tests |
| `database/` | Database-related scripts and resources |
| `docs/` | Architecture and integration documentation |
| `firmware-legacy/` | Legacy firmware copy; not the canonical sketch |

## Prerequisites

For local development on Windows, install:

- Python **3.12** (the backend requirements specify Python 3.12+).
- Node.js **22 LTS** and npm.
- Git, if you are cloning the repository.
- A Supabase PostgreSQL project with the `vector` extension enabled.

For physical gate operation, also install Arduino IDE and the ESP32 board support
package, and have an ESP32 DevKit V1, an SG90 servo, and a 16×2 I2C LCD.

## 1. Get the source

Clone the repository or open your existing project directory:

```powershell
git clone https://github.com/PragadheeshPandian1906/Gate-Security-System.git
Set-Location .\Gate-Security-System
```

If the project is already on your computer, run `Set-Location` to its root
instead.

## 2. Configure the main backend

Open a PowerShell terminal at the project root:

```powershell
Set-Location D:\Gate-Security-System\backend
Copy-Item .env.example .env
```

If `.env` already exists, do **not** overwrite it. Edit it and preserve valid
local settings. Configure at least:

- `DATABASE_URL`: Supabase PostgreSQL connection string. Use the format and
  connection mode recommended for your Supabase project.
- `JWT_SECRET_KEY`: a unique random secret of at least 32 characters.
- `FRONTEND_ORIGINS=http://localhost:5173`
- `IOT_MICROSERVICE_URL=http://localhost:8001`
- `IOT_SERVICE_SECRET`: a random service-to-service secret; configure the same
  value independently in `iot-service/.env`.

Generate random values locally without putting them in command history:

```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```

Run this separately for the JWT secret, service secret, and device key. Do not
reuse one value for another purpose. Keep `.env` files private and never commit
them.

Create and activate the backend virtual environment, then install dependencies
and apply database migrations:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
alembic upgrade head
```

If PowerShell prevents virtual-environment activation, use the interpreter
directly as shown in the server commands below; changing the system execution
policy is not required.

Create the first administrator interactively. The password is entered using a
hidden prompt rather than a command-line argument:

```powershell
python bootstrap_admin.py
```

Follow the prompts. If the database is unavailable, verify `DATABASE_URL`, the
Supabase network access settings, and that pgvector is enabled.

## 3. Configure and install the IoT microservice

In a second PowerShell terminal:

```powershell
Set-Location D:\Gate-Security-System\iot-service
Copy-Item .env.example .env
```

If the file already exists, edit it without overwriting existing configuration.
Set these values:

- `IOT_DEVICE_ID`: device identity used by the firmware.
- `IOT_DEVICE_KEY`: a new random device credential. It must match the firmware's
  `SG_IOT_DEVICE_TOKEN`.
- `IOT_SERVICE_SECRET`: the service-to-service secret also set as
  `IOT_SERVICE_SECRET` in `backend/.env`.
- `IOT_ALLOWED_ORIGINS=http://localhost:5173,http://localhost:8000`
- Keep `IOT_SERVICE_PORT=8001` for the commands below.

The backend and IoT service read their own environment files. Set the service
secret in both files; matching sample/default strings are not proof that the
runtime configuration is correct. Never print or commit real secret values.

Create a separate virtual environment and install the microservice dependencies:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

The backend and microservice intentionally use separate dependency manifests
and environments.

## 4. Configure and install the frontend

In a third PowerShell terminal:

```powershell
Set-Location D:\Gate-Security-System\frontend
Copy-Item .env.example .env
npm ci
```

Set the API base URL in `frontend/.env`:

```dotenv
VITE_API_BASE_URL=http://localhost:8000/api
```

The configured frontend origin is `http://localhost:5173`; use that hostname
consistently rather than switching between `localhost` and `127.0.0.1` during
local development.

## 5. Start the three applications

Keep three PowerShell terminals open. Start the IoT microservice first.

**Terminal 1 — IoT microservice**

```powershell
Set-Location D:\Gate-Security-System\iot-service
.\venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

**Terminal 2 — Main backend**

```powershell
Set-Location D:\Gate-Security-System\backend
.\venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

**Terminal 3 — Frontend**

```powershell
Set-Location D:\Gate-Security-System\frontend
npm run dev
```

Open the URL printed by Vite, normally
[http://localhost:5173](http://localhost:5173), then sign in with the
administrator account created earlier.

### Local service URLs

| Service | URL |
|---|---|
| Frontend dashboard | `http://localhost:5173` |
| Main backend API docs | `http://localhost:8000/docs` |
| Main backend liveness | `http://localhost:8000/api/health/live` |
| Main backend readiness | `http://localhost:8000/api/health/ready` |
| IoT microservice docs | `http://localhost:8001/docs` |
| IoT service monitor | `http://localhost:8001/` |
| ESP32 WebSocket | `ws://<LAPTOP_LAN_IPV4>:8001/api/v1/ws/iot/gate` |

The backend-to-IoT service bridge uses HTTP on port 8001. The ESP32 connects to
the IoT microservice WebSocket, not directly to the main backend.

## 6. Run the ESP32 simulator (optional)

The simulator exercises the software protocol without physical hardware. With
the microservice running, open another terminal:

```powershell
Set-Location D:\Gate-Security-System\iot-service
.\venv\Scripts\python.exe scripts\mock_esp32.py
```

Use the dashboard to test manual commands and automated access. The simulator
does not test ESP32 Wi-Fi, servo movement, LCD wiring, or actual gate position.

## 7. Set up and flash the physical ESP32 (optional)

The canonical microservice-connected sketch is:

```text
iot-service\firmware\esp32_gate_controller\esp32_gate_controller.ino
```

Do not assume this is the sketch currently flashed on any existing board. The
`firmware-legacy\esp32_gate_controller` copy is legacy; do not use it for a new
upload.

1. Install ESP32 board support in Arduino IDE and select **ESP32 Dev Module**.
2. Install these Arduino libraries: **ArduinoJson** (v6/v7), **WebSockets** by
   Markus Sattler, **LiquidCrystal_I2C**, and **ESP32Servo**.
3. In the canonical sketch folder, copy
   `secrets.example.h` to `secrets.h`. Edit only the local `secrets.h`; it is
   ignored by Git.
4. Configure Wi-Fi SSID/password, the laptop's current LAN IPv4 address, device
   ID, and device token. The firmware device ID must match `IOT_DEVICE_ID`; its
   device token must match `IOT_DEVICE_KEY` in `iot-service/.env`.
5. Never use `localhost` or `127.0.0.1` for the ESP32 server host. The board
   must connect to the laptop's reachable LAN address on port 8001.
6. Select the correct COM port and upload the canonical sketch.

Find current IPv4 addresses from PowerShell:

```powershell
Get-NetIPAddress -AddressFamily IPv4 |
  Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' } |
  Format-Table InterfaceAlias,IPAddress
```

Use the address on the same Wi-Fi/LAN as the ESP32; the laptop's address can
change. The ESP32 requires 2.4 GHz Wi-Fi. Allow inbound TCP port 8001 through
Windows Firewall if the device cannot connect. Use an appropriate regulated
servo power supply and common ground; see
[iot-service/README.md](./iot-service/README.md) for the wiring reference.

### Manual and automated gate modes

Dashboard **Manual Open** latches the gate open until an authorized **Manual
Close** command is processed. Automated access retains its timed close behavior
(15 seconds by default). A firmware restart initializes the servo to CLOSED;
manual-open state is not persistent across power loss. No gate-position sensor
is configured, so controller acknowledgements and reported state are not
independent confirmation of physical movement.

## 8. Tests and build checks

Run backend tests:

```powershell
Set-Location D:\Gate-Security-System\backend
.\venv\Scripts\python.exe -m pytest
```

Run IoT service tests:

```powershell
Set-Location D:\Gate-Security-System\iot-service
.\venv\Scripts\python.exe -m pytest
```

Run frontend tests and production build:

```powershell
Set-Location D:\Gate-Security-System\frontend
npm test
npm run build
```

## Troubleshooting

- **Login or API says the backend is unavailable:** confirm the main backend is
  running on port 8000 and `VITE_API_BASE_URL` points to
  `http://localhost:8000/api`.
- **CORS preflight errors:** use `http://localhost:5173` for the frontend and
  ensure it is included in `FRONTEND_ORIGINS` in `backend/.env`.
- **ESP32 is disconnected:** verify the IoT service is running on port 8001,
  confirm matching device ID/key settings, use the laptop's current LAN IPv4 in
  firmware, and check Windows Firewall and 2.4 GHz Wi-Fi connectivity.
- **Backend cannot contact the IoT service:** verify
  `IOT_MICROSERVICE_URL=http://localhost:8001` and that both services have the
  same independently configured `IOT_SERVICE_SECRET`.
- **Readiness is unavailable:** check the Supabase connection string, network
  access, migrations, and pgvector extension. Readiness failures are not hidden.
- **Secret/configuration changes do not take effect:** restart the affected
  server after editing its `.env` file.

For detailed IoT protocol, API, simulator, and wiring information, see
[iot-service/README.md](./iot-service/README.md) and
[docs/IOT_GATE_INTEGRATION_ARCHITECTURE.md](./docs/IOT_GATE_INTEGRATION_ARCHITECTURE.md).
