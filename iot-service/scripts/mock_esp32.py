"""
SmartGuard AI — Mock ESP32 Gate Controller Simulator
Enables full hardware testing without physical microcontrollers.
Connects via WebSocket to the IoT Microservice and simulates:
  - Heartbeat transmission (uptime, heap, RSSI)
  - Gate open & close commands
  - LCD screen display updates
  - Auto-close timer simulation
  - Command Acknowledgements (ACK)
"""
import asyncio
import json
import logging
import os
import sys
import time
from typing import Optional
from urllib.parse import urlencode, urlsplit, urlunsplit
from pathlib import Path

from dotenv import load_dotenv

try:
    import websockets
except ImportError:
    print("Error: 'websockets' package required. Install with: pip install websockets")
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [ESP32-SIM] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("mock_esp32")
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

# Simulator Configurations
SERVER_URL = os.getenv("IOT_SIM_URL", "ws://127.0.0.1:8001/api/v1/ws/iot/gate")
DEVICE_ID = os.getenv("IOT_DEVICE_ID", "smartguard-esp32-01")
DEVICE_TOKEN = os.getenv("IOT_DEVICE_KEY", "")
HEARTBEAT_INTERVAL = 10  # seconds


class MockEsp32Controller:
    def __init__(self, server_url: str, device_id: str, token: str):
        separator = "&" if "?" in server_url else "?"
        self.server_url = f"{server_url}{separator}{urlencode({'device_id': device_id, 'token': token})}"
        parsed_url = urlsplit(server_url)
        self.safe_server_url = urlunsplit(
            (parsed_url.scheme, parsed_url.netloc, parsed_url.path, "", "")
        )
        self.device_id = device_id
        self.token = token
        self.gate_state = "CLOSED"
        self.gate_mode = "AUTOMATED"
        self.start_time = time.time()
        self.lcd_line1 = "SYSTEM READY"
        self.lcd_line2 = "SMARTGUARD AI"
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.auto_close_task: Optional[asyncio.Task] = None
        self.last_command_sequence = 0
        self.auto_close_sequence = 0

    def get_uptime_seconds(self) -> int:
        return int(time.time() - self.start_time)

    
    async def send_json(self, payload):
        if self.ws is not None:
            try:
                await self.ws.send(json.dumps(payload))
            except Exception as exc:
                logging.warning("Failed to send WebSocket message: %s", exc)


    async def send_heartbeat(self):
        payload = {
            "type": "HEARTBEAT",
            "device_id": self.device_id,
            "state": self.gate_state,
            "gate_mode": self.gate_mode,
            "uptime_seconds": self.get_uptime_seconds(),
            "free_heap": 184320,
            "wifi_rssi": -58,
        }
        await self.send_json(payload)
        logger.info(
            "Sent HEARTBEAT: gate=%s, uptime=%ds, rssi=-58dBm",
            self.gate_state,
            payload["uptime_seconds"],
        )

    async def send_ack(self, command_id: str, status: str, detail: str):
        payload = {
            "type": "COMMAND_ACK",
            "command_id": command_id,
            "device_id": self.device_id,
            "status": status,
            "gate_state": self.gate_state,
            "detail": detail,
        }
        await self.send_json(payload)
        logger.info(
            "Sent ACK for cmd=%s status=%s gate_state=%s",
            command_id[:8] if command_id else "unknown",
            status,
            self.gate_state,
        )

    async def _auto_close_timer(self, duration_ms: int, command_sequence: int):
        try:
            logger.info("Auto-close timer armed: %dms", duration_ms)
            await asyncio.sleep(duration_ms / 1000.0)
            if (
                command_sequence != self.last_command_sequence
                or self.gate_mode == "MANUAL_LATCHED_OPEN"
            ):
                return
            self.gate_state = "CLOSED"
            self.gate_mode = "AUTOMATED"
            self.lcd_line1 = "GATE CLOSED"
            self.lcd_line2 = "SYSTEM READY"
            logger.info("Auto-close timer expired -> Gate is now CLOSED")
            await self.send_json({
                "type": "GATE_STATE",
                "device_id": self.device_id,
                "state": self.gate_state,
                "gate_mode": self.gate_mode,
            })
        except asyncio.CancelledError:
            logger.info("Auto-close timer was cancelled.")

    async def handle_message(self, message_text: str):
        try:
            msg = json.loads(message_text)
        except json.JSONDecodeError:
            logger.error("Failed to parse JSON packet: %s", message_text)
            return

        msg_type = msg.get("type")
        cmd_id = msg.get("command_id", "unknown")

        logger.info("Received command from server: type=%s, cmd_id=%s", msg_type, cmd_id[:8])

        if msg_type == "GATE_OPEN":
            command_type = msg.get("command_type", "AUTOMATED")
            if command_type not in ("AUTOMATED", "MANUAL"):
                await self.send_ack(cmd_id, "REJECTED", "Invalid gate command type")
                return
            command_sequence = msg.get("command_sequence", 0)
            if not isinstance(command_sequence, int) or command_sequence <= self.last_command_sequence:
                await self.send_ack(cmd_id, "REJECTED", "Stale or invalid command sequence")
                return
            if self.gate_mode == "MANUAL_LATCHED_OPEN" and command_type != "MANUAL":
                self.last_command_sequence = command_sequence
                await self.send_ack(cmd_id, "REJECTED", "Manual-open latch requires manual close")
                return
            self.last_command_sequence = command_sequence
            duration_ms = msg.get("duration_ms", 15000)
            state_changed = (
                self.gate_state != "OPEN"
                or (self.gate_mode == "MANUAL_LATCHED_OPEN") != (command_type == "MANUAL")
            )
            self.gate_state = "OPEN"
            self.gate_mode = (
                "MANUAL_LATCHED_OPEN" if command_type == "MANUAL" else "AUTOMATED"
            )
            self.lcd_line1 = "MANUAL GATE OPEN" if command_type == "MANUAL" else msg.get("line1", "GATE OPEN")
            self.lcd_line2 = "WAITING TO CLOSE" if command_type == "MANUAL" else msg.get("line2", "WELCOME")
            logger.info("GATE OPENED! Servo at 90 deg. LCD: [%s | %s]", self.lcd_line1, self.lcd_line2)

            if self.auto_close_task:
                if not self.auto_close_task.done():
                    self.auto_close_task.cancel()
                self.auto_close_task = None

            await self.send_ack(cmd_id, "EXECUTED", "Manual-open latch set" if command_type == "MANUAL" else "Barrier opened to 90 degrees")

            if command_type == "AUTOMATED":
                self.auto_close_sequence = command_sequence
                self.auto_close_task = asyncio.create_task(
                    self._auto_close_timer(duration_ms, command_sequence)
                )
            if state_changed:
                await self.send_json({
                    "type": "GATE_STATE",
                    "device_id": self.device_id,
                    "state": self.gate_state,
                    "gate_mode": self.gate_mode,
                    "command_id": cmd_id,
                })

        elif msg_type == "GATE_CLOSE":
            command_type = msg.get("command_type", "AUTOMATED")
            if command_type not in ("AUTOMATED", "MANUAL"):
                await self.send_ack(cmd_id, "REJECTED", "Invalid gate command type")
                return
            command_sequence = msg.get("command_sequence", 0)
            if not isinstance(command_sequence, int) or command_sequence <= self.last_command_sequence:
                await self.send_ack(cmd_id, "REJECTED", "Stale or invalid command sequence")
                return
            if self.gate_mode == "MANUAL_LATCHED_OPEN" and command_type != "MANUAL":
                self.last_command_sequence = command_sequence
                await self.send_ack(cmd_id, "REJECTED", "Manual-open latch requires manual close")
                return
            self.last_command_sequence = command_sequence
            state_changed = self.gate_state != "CLOSED" or self.gate_mode != "AUTOMATED"
            if self.auto_close_task:
                if not self.auto_close_task.done():
                    self.auto_close_task.cancel()
                self.auto_close_task = None

            self.gate_state = "CLOSED"
            self.gate_mode = "AUTOMATED"
            self.lcd_line1 = "GATE CLOSED" if command_type == "MANUAL" else msg.get("line1", "GATE CLOSED")
            self.lcd_line2 = "SYSTEM READY" if command_type == "MANUAL" else msg.get("line2", "PLEASE WAIT")
            logger.info("GATE CLOSED! Servo at 0 deg. LCD: [%s | %s]", self.lcd_line1, self.lcd_line2)

            await self.send_ack(cmd_id, "EXECUTED", "Barrier closed to 0 degrees")
            if state_changed:
                await self.send_json({
                    "type": "GATE_STATE",
                    "device_id": self.device_id,
                    "state": self.gate_state,
                    "gate_mode": self.gate_mode,
                    "command_id": cmd_id,
                })

        elif msg_type == "DISPLAY_STATUS":
            if self.gate_mode == "MANUAL_LATCHED_OPEN":
                return
            self.lcd_line1 = msg.get("line1", "SYSTEM READY")
            self.lcd_line2 = msg.get("line2", "")
            logger.info("LCD UPDATED: [%s | %s]", self.lcd_line1, self.lcd_line2)

        elif msg_type == "STATUS_REQUEST":
            await self.send_heartbeat()

    async def run(self):
        logger.info("Starting Mock ESP32 Simulator targeting: %s", self.safe_server_url)
        while True:
            try:
                async with websockets.connect(self.server_url) as ws:
                    self.ws = ws
                    logger.info("Connected to IoT Microservice as %s!", self.device_id)

                    # Initial heartbeat
                    await self.send_heartbeat()

                    async def heartbeat_loop():
                        while True:
                            await asyncio.sleep(HEARTBEAT_INTERVAL)
                            await self.send_heartbeat()

                    hb_task = asyncio.create_task(heartbeat_loop())

                    try:
                        async for message in ws:
                            await self.handle_message(message)
                    finally:
                        hb_task.cancel()

            except (websockets.ConnectionClosedError, websockets.WebSocketException, OSError) as exc:
                error = str(exc).replace(self.token, "[redacted]") if self.token else str(exc)
                logger.warning("Connection lost (%s). Reconnecting in 3s...", error)
                self.ws = None
                await asyncio.sleep(3)


if __name__ == "__main__":
    if not DEVICE_TOKEN:
        logger.error("Set IOT_DEVICE_KEY to the configured device token before starting the simulator.")
        sys.exit(2)
    sim = MockEsp32Controller(SERVER_URL, DEVICE_ID, DEVICE_TOKEN)
    try:
        asyncio.run(sim.run())
    except KeyboardInterrupt:
        logger.info("Simulator stopped by user.")
