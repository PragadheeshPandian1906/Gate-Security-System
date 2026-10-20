# SmartGuard AI — IoT Gate Controller Microservice

The **SmartGuard AI IoT Microservice** is the single physical ESP32 connection manager. It receives automated status events from the main backend, forwards authenticated operator commands, tracks controller acknowledgements and heartbeats, and streams telemetry. Access decisions remain owned by the main backend.

---

## 1. Directory Structure

```
iot-service/
├── .env.example                          # Environment variable configuration template
├── .env                                  # Active environment configuration
├── requirements.txt                      # Python dependencies (FastAPI, uvicorn, pydantic, websockets, etc.)
├── README.md                             # This documentation
├── app/
│   ├── __init__.py
│   ├── config.py                         # Settings loaded from environment / .env
│   ├── main.py                           # FastAPI application entry point & lifespan
│   ├── api/
│   │   ├── __init__.py
│   │   └── routes.py                     # HTTP REST routes & WebSocket endpoints
│   ├── schemas/
│   │   ├── __init__.py
│   │   └── gate_status.py                # Pydantic schemas for payloads, commands, telemetry
│   └── services/
│       ├── __init__.py
│       └── device_manager.py             # ESP32 connection lifecycle, ACK tracking, event logging
├── dashboard/
│   └── index.html                        # Standalone dark-mode HTML5/CSS3 live hardware monitor
├── firmware/
│   └── esp32_gate_controller/
│       ├── esp32_gate_controller.ino     # Canonical microservice-connected sketch
│       └── secrets.example.h             # Copy locally to ignored secrets.h
├── scripts/
│   └── mock_esp32.py                     # Interactive Python simulator for hardware testing
└── tests/
    └── test_iot_service.py               # Service auth, device protocol, ordering, and status tests
```

---

## 2. Hardware Pinout & Wiring Diagram

The controller is tailored for a clean, minimal hardware build:

| Peripheral Component | ESP32 GPIO Pin | Description / Function |
| :--- | :--- | :--- |
| **Servo Motor** (Barrier Arm) | **GPIO 18** | PWM control (0° = CLOSED, 90° = OPEN) |
| **I2C LCD 1602 (SDA)** | **GPIO 21** | Serial Data line (Default I2C address: `0x27`, 16x2) |
| **I2C LCD 1602 (SCL)** | **GPIO 22** | Serial Clock line |
| **ESP32 DevKit V1** | **V5 / VIN & GND** | 5V Power for Servo & LCD Backlight |

*(No external relays, LEDs, buzzers, or obstacle sensors needed)*

---

## 3. Quickstart Guide

### Step 1: Install Dependencies
From the `iot-service/` directory (or using your project's Python virtual environment):
```powershell
pip install -r requirements.txt
```

### Step 2: Configure Environment Variables
If `.env` does not already exist, copy `.env.example` to `.env`. Do not overwrite an existing `.env`; update only the named settings. Set:
```powershell
Copy-Item .env.example .env
```
Configure the IoT service in `iot-service/.env`:
```ini
IOT_SERVICE_HOST=0.0.0.0
IOT_SERVICE_PORT=8001
IOT_DEVICE_ID=smartguard-esp32-01
IOT_DEVICE_KEY=<a new random device token>
IOT_SERVICE_SECRET=<a new random service-to-service secret>
IOT_AUTO_CLOSE_DURATION_MS=15000
```
Generate each value locally with `python -c "import secrets; print(secrets.token_hex(32))"`.
Set the service secret independently in `backend/.env` as `IOT_SERVICE_SECRET` and
`iot-service/.env` as `IOT_SERVICE_SECRET`; copy the same generated value into both
files, but do not use the device token as the service secret. The backend also needs
`IOT_MICROSERVICE_URL=http://localhost:8001`. Never put real values in committed files
or browser code.

### Step 3: Run the Microservice
```powershell
Set-Location D:\Gate-Security-System\iot-service
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```
The microservice will now be listening on:
- API & Docs: `http://localhost:8001/docs`
- Standalone Monitoring Dashboard: `http://localhost:8001/` or `http://localhost:8001/monitor`
- Device WebSocket: `ws://<LAPTOP_LAN_IPV4>:8001/api/v1/ws/iot/gate`
- Telemetry WebSocket: `ws://localhost:8001/api/v1/ws/monitor`

### Step 4: Run Tests
```powershell
python -m pytest tests/test_iot_service.py -v
```

---

## 4. Hardware Simulation (Testing Without ESP32)

To test the entire pipeline without physical hardware connected:

1. Configure `IOT_DEVICE_ID` and `IOT_DEVICE_KEY` in `iot-service/.env`.
2. Start the IoT microservice on port 8001.
3. In a separate terminal, launch the simulator from `iot-service/`:
```powershell
Set-Location D:\Gate-Security-System\iot-service
python scripts\mock_esp32.py
```
4. Open `http://localhost:8001/` to monitor simulator heartbeats and reported state.
5. Trigger automated access or use the authenticated manual controls in the main
   security dashboard. The simulator validates software protocol only; it does not
   validate physical Wi-Fi, servo travel, LCD wiring, or gate position.

The simulator's default endpoint is `ws://127.0.0.1:8001/api/v1/ws/iot/gate`,
which is appropriate only because the simulator runs on the same computer. Its
`IOT_SIM_URL` can override the endpoint. Never use loopback as the ESP32 server host.

---

## 5. ESP32 Firmware Flashing

1. Open Arduino IDE or PlatformIO.
2. Install the following libraries via the Arduino Library Manager:
   - `ArduinoJson` (v6 or v7)
   - `WebSockets` by Markus Sattler
   - `LiquidCrystal_I2C` by Frank de Brabander
   - `ESP32Servo` by Kevin Harrington
3. Copy `firmware\esp32_gate_controller\secrets.example.h` to
   `firmware\esp32_gate_controller\secrets.h`. This local file is ignored by Git.
4. Set the Wi-Fi SSID/password, the current laptop LAN IPv4 address, device ID, and
   the same device token configured as `IOT_DEVICE_KEY` in `iot-service/.env`.
5. Open `firmware\esp32_gate_controller\esp32_gate_controller.ino`. This is the
   canonical microservice-connected sketch. The separate top-level
   `firmware\esp32_gate_controller` copy is a legacy duplicate; do not flash both
   sketches or connect two devices using the same device ID.
6. Select board **ESP32 Dev Module** and the correct COM port, then click **Upload**.

To find the laptop's current LAN IPv4 address in PowerShell:
```powershell
Get-NetIPAddress -AddressFamily IPv4 |
  Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' } |
  Format-Table InterfaceAlias,IPAddress
```
Choose the active Wi-Fi/Ethernet address on the same LAN as the ESP32. It may
change; recheck it before flashing. The ESP32 is 2.4-GHz Wi-Fi only. Allow inbound
TCP port 8001 in Windows Firewall if needed. Never set `SG_IOT_SERVER_HOST` to
`localhost` or `127.0.0.1`.

---

## 6. API Reference

### Automated Gate Decisions
- **`POST /api/v1/gate/status`**
  - Used by the main SmartGuard AI backend upon face/license plate evaluation.
  - Required Header: `X-Service-Secret: <IOT_SERVICE_SECRET>`
  - Request Body:
    ```json
    {
      "event_id": "uuid",
      "status": "GATE_OPEN",
      "attempt_id": "attempt-123"
    }
    ```
  - Supported statuses: `GATE_OPEN`, `GATE_CLOSED`, `MANUAL_REVIEW`.
  - Duplicate `event_id` is ignored without re-triggering the controller.

### Operator Manual Commands
- **`POST /api/v1/gate/manual-open`**
  - Main backend only: requires service authentication and a forwarded,
    JWT-validated `SECURITY` or `ADMIN` operator role and ID.
  - Request Body: `{"reason": "Authorized visitor entry"}`
  - Opens in `MANUAL_LATCHED_OPEN` mode; no auto-close timer runs.
- **`POST /api/v1/gate/manual-close`**
  - Explicitly closes the barrier and clears manual-open mode.
  - Same main-backend service authentication and operator validation as manual open.
  - Request Body: `{"reason": "Lockdown / manual close"}`
  - A reset/automated close cannot clear a manual-open latch; only this manual command can.

### Telemetry & Diagnostics
- **`GET /api/v1/health`**: Returns microservice and ESP32 health status.
- **`GET /api/v1/device/status`**: Service-authenticated telemetry snapshot (connection, heartbeat, controller-reported state, Wi-Fi RSSI, heap).
- **`GET /api/v1/device/events`**: Service-authenticated buffer of the 100 most recent hardware and backend events.

The ESP32 authenticates with `device_id` and `token` query parameters at
`ws://<LAPTOP_LAN_IPV4>:8001/api/v1/ws/iot/gate`. The IoT service binds port 8001;
the main backend remains on port 8000, and its authenticated dashboard monitor
remains at `/ws/gate/monitor`.

`ACCEPTED` means the controller received a command. The device manager waits for a
final `EXECUTED`/`COMPLETED` acknowledgement before reporting execution acknowledged.
Neither that acknowledgement nor `GATE_STATE` proves physical gate movement: this
hardware configuration has no gate-position sensor.

Manual mode is included in heartbeat and gate-state telemetry and is enforced on
the controller: automated gate commands and LCD-only status updates cannot
override an active manual-open latch. Automated access commands retain their
configured auto-close duration when manual mode is not active. The latch is held
in ESP32 RAM; after a firmware restart the controller initializes the servo to
CLOSED and reports that startup state. Persistence through power loss is not
implemented.

The standalone IoT dashboard is read-only. Use the main backend's authenticated
security dashboard for operator controls; do not place service secrets in browser
code or expose them in logs.
