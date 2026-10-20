/*
 * SmartGuard AI — ESP32 Physical Gate Controller Firmware
 * 
 * Hardware Connections:
 *   - ESP32 DevKit V1
 *   - Servo Motor: GPIO 18 (Gate Barrier: 0° = CLOSED, 90° = OPEN)
 *   - I2C 1602 LCD (PCF8574): SDA = GPIO 21, SCL = GPIO 22 (Address: 0x27, 16x2)
 *   (No extra sensors, buzzers, relays, or LEDs required!)
 * 
 * Connects only to the IoT microservice. Manual controls must be authorized by
 * the main backend and are forwarded by that service.
 * 
 * Required Arduino Libraries:
 *   - ArduinoJson (v6 or v7)
 *   - WebSockets by Markus Sattler
 *   - LiquidCrystal_I2C by Frank de Brabander
 *   - ESP32Servo by Kevin Harrington
 */

#include <WiFi.h>
#include <WebSocketsClient.h>
#include <ArduinoJson.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <ESP32Servo.h>
#include "secrets.h"

// =============================================================================
// CONFIGURATION & CREDENTIALS
// =============================================================================

const char* WIFI_SSID = SG_WIFI_SSID;
const char* WIFI_PASSWORD = SG_WIFI_PASSWORD;
const char* SERVER_HOST = SG_IOT_SERVER_HOST;
const uint16_t SERVER_PORT = 8001;
const char* DEVICE_ID = SG_IOT_DEVICE_ID;
const char* DEVICE_TOKEN = SG_IOT_DEVICE_TOKEN;

// Hardware Pinout Definitions
const int SERVO_PIN       = 18;
const int SDA_PIN         = 21;
const int SCL_PIN         = 22;

// Physical Angles
#define ANGLE_CLOSED      0
#define ANGLE_OPEN        90

// Timing Configurations
#define HEARTBEAT_INTERVAL_MS   10000
#define DEFAULT_OPEN_TIME_MS    15000
#define LCD_I2C_ADDR            0x27

// =============================================================================
// GLOBAL OBJECTS & STATE
// =============================================================================

WebSocketsClient webSocket;
LiquidCrystal_I2C lcd(LCD_I2C_ADDR, 16, 2);
Servo gateServo;

bool gateIsOpen = false;
bool manualLatchedOpen = false;
bool isWsConnected = false;
unsigned long lastHeartbeatTime = 0;
unsigned long gateOpenedAt = 0;
unsigned long autoCloseDurationMs = DEFAULT_OPEN_TIME_MS;
uint32_t lastCountdownSecond = UINT32_MAX;
bool isAutoCloseArmed = false;
bool wifiWasConnected = false;
bool wsClientStarted = false;
unsigned long lastWifiAttempt = 0;
uint32_t latestCommandSequence = 0;
uint32_t autoCloseCommandSequence = 0;

// =============================================================================
// LCD DISPLAY HELPER
// =============================================================================

void displayMessage(const char* line1, const char* line2) {
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print(line1 ? line1 : "");
  lcd.setCursor(0, 1);
  lcd.print(line2 ? line2 : "");
}

// =============================================================================
// GATE ACTUATOR CONTROLS
// =============================================================================

void updateOpenCountdown(unsigned long now) {
  if (!gateIsOpen || manualLatchedOpen || !isAutoCloseArmed) return;

  unsigned long elapsed = now - gateOpenedAt;
  if (elapsed >= autoCloseDurationMs) return;

  unsigned long remainingSeconds =
    (autoCloseDurationMs - elapsed + 999) / 1000;
  if (remainingSeconds == lastCountdownSecond) return;

  char countdown[17] = "                ";
  snprintf(countdown, sizeof(countdown), "Closing in: %lus", remainingSeconds);
  size_t length = strlen(countdown);
  while (length < 16) countdown[length++] = ' ';
  countdown[16] = '\0';
  lcd.setCursor(0, 1);
  lcd.print(countdown);
  lastCountdownSecond = remainingSeconds;
}

void showManualOpenDisplay() {
  displayMessage("MANUAL GATE OPEN", "WAITING TO CLOSE");
}

void executeGateOpen(int durationMs, bool manual) {
  gateServo.write(ANGLE_OPEN);
  gateIsOpen = true;
  manualLatchedOpen = manual;
  if (manual) {
    gateOpenedAt = 0;
    autoCloseDurationMs = 0;
    isAutoCloseArmed = false;
    lastCountdownSecond = UINT32_MAX;
    showManualOpenDisplay();
  } else {
    autoCloseDurationMs = durationMs > 0 ? durationMs : DEFAULT_OPEN_TIME_MS;
    gateOpenedAt = millis();
    lastCountdownSecond = UINT32_MAX;
    isAutoCloseArmed = true;
    autoCloseCommandSequence = latestCommandSequence;
    displayMessage("GATE OPEN", "Closing in: 15s");
  }
  Serial.println(F("[GATE] Gate opened (Servo: 90 deg)"));
}

void executeGateClose(const char* reason) {
  gateServo.write(ANGLE_CLOSED);
  gateIsOpen = false;
  manualLatchedOpen = false;
  isAutoCloseArmed = false;
  gateOpenedAt = 0;

  displayMessage("GATE CLOSED", "SYSTEM READY");
  Serial.printf(
    "[GATE] Physical close executed (Servo: %d deg, reason=%s)\n",
    ANGLE_CLOSED,
    reason ? reason : "UNSPECIFIED"
  );
}

// =============================================================================
// WEBSOCKET PROTOCOL & DISPATCH (SMARTGUARD AI MICROSERVICE)
// =============================================================================

void sendJsonPacket(JsonDocument& doc) {
  if (!isWsConnected) return;
  String payload;
  serializeJson(doc, payload);
  webSocket.sendTXT(payload);
}

void sendHeartbeat() {
  StaticJsonDocument<256> doc;
  doc["type"] = "HEARTBEAT";
  doc["device_id"] = DEVICE_ID;
  doc["gate_state"] = gateIsOpen ? "OPEN" : "CLOSED";
  doc["gate_mode"] = manualLatchedOpen ? "MANUAL_LATCHED_OPEN" : "AUTOMATED";
  doc["uptime_seconds"] = millis() / 1000;
  doc["free_heap"] = ESP.getFreeHeap();
  doc["wifi_rssi"] = WiFi.RSSI();

  sendJsonPacket(doc);
}

void sendGateState(const char* commandId = nullptr) {
  StaticJsonDocument<256> state;
  state["type"] = "GATE_STATE";
  state["device_id"] = DEVICE_ID;
  state["state"] = gateIsOpen ? "OPEN" : "CLOSED";
  state["gate_mode"] = manualLatchedOpen ? "MANUAL_LATCHED_OPEN" : "AUTOMATED";
  if (commandId) state["command_id"] = commandId;
  sendJsonPacket(state);
}

void sendAck(const char* commandId, const char* status, const char* detail) {
  StaticJsonDocument<256> doc;
  doc["type"] = "GATE_ACTION_ACK";
  doc["command_id"] = commandId;
  doc["device_id"] = DEVICE_ID;
  doc["status"] = status;  // EXECUTED or REJECTED
  doc["gate_state"] = gateIsOpen ? "OPEN" : "CLOSED";
  doc["gate_mode"] = manualLatchedOpen ? "MANUAL_LATCHED_OPEN" : "AUTOMATED";
  doc["detail"] = detail;

  sendJsonPacket(doc);
}

void handleServerCommand(uint8_t* payload, size_t length) {
  StaticJsonDocument<512> doc;
  DeserializationError error = deserializeJson(doc, payload, length);

  if (error) {
    Serial.print(F("deserializeJson() failed: "));
    Serial.println(error.f_str());
    return;
  }

  const char* type = doc["type"];
  if (!type) return;

  const char* cmdId = doc["command_id"] | "unknown";

  if (strcmp(type, "GATE_OPEN") == 0) {
    const char* commandType = doc["command_type"] | "AUTOMATED";
    bool manualCommand = strcmp(commandType, "MANUAL") == 0;
    if (!manualCommand && strcmp(commandType, "AUTOMATED") != 0) {
      sendAck(cmdId, "REJECTED", "Invalid gate command type");
      return;
    }
    uint32_t commandSequence = doc["command_sequence"] | 0;
    if (commandSequence == 0 || commandSequence <= latestCommandSequence) {
      sendAck(cmdId, "REJECTED", "Stale or invalid command sequence");
      return;
    }
    if (manualLatchedOpen && !manualCommand) {
      latestCommandSequence = commandSequence;
      sendAck(cmdId, "REJECTED", "Manual-open latch requires manual close");
      return;
    }
    latestCommandSequence = commandSequence;
    int duration = doc["duration_ms"] | DEFAULT_OPEN_TIME_MS;
    bool stateChanged = !gateIsOpen || (manualLatchedOpen != manualCommand);
    executeGateOpen(duration, manualCommand);
    sendAck(cmdId, "EXECUTED", manualCommand
      ? "Manual-open latch set; close requires explicit manual command"
      : "Servo target set to OPEN; no position sensor");
    if (stateChanged) sendGateState(cmdId);

  } else if (strcmp(type, "GATE_CLOSE") == 0) {
    const char* commandType = doc["command_type"] | "AUTOMATED";
    bool manualCommand = strcmp(commandType, "MANUAL") == 0;
    const char* closeReason = doc["reason"] |
      (manualCommand ? "MANUAL_COMMAND" : "AUTOMATED_COMMAND");
    Serial.printf(
      "[GATE] Incoming GATE_CLOSE (command_id=%s, type=%s, reason=%s)\n",
      cmdId,
      commandType,
      closeReason
    );
    if (!manualCommand && strcmp(commandType, "AUTOMATED") != 0) {
      sendAck(cmdId, "REJECTED", "Invalid gate command type");
      return;
    }
    uint32_t commandSequence = doc["command_sequence"] | 0;
    if (commandSequence == 0 || commandSequence <= latestCommandSequence) {
      sendAck(cmdId, "REJECTED", "Stale or invalid command sequence");
      return;
    }
    if (manualLatchedOpen && !manualCommand) {
      latestCommandSequence = commandSequence;
      sendAck(cmdId, "REJECTED", "Manual-open latch requires manual close");
      return;
    }
    latestCommandSequence = commandSequence;
    bool stateChanged = gateIsOpen || manualLatchedOpen;
    executeGateClose(closeReason);
    sendAck(cmdId, "EXECUTED", "Servo target set to CLOSED; no position sensor");
    if (stateChanged) sendGateState(cmdId);

  } else if (strcmp(type, "DISPLAY_STATUS") == 0) {
    if (manualLatchedOpen) return;
    const char* l1 = doc["line1"] | "SYSTEM READY";
    const char* l2 = doc["line2"] | "";
    displayMessage(l1, l2);

  } else if (strcmp(type, "STATUS_REQUEST") == 0) {
    sendHeartbeat();
  }
}

void webSocketEvent(WStype_t type, uint8_t* payload, size_t length) {
  switch (type) {
    case WStype_DISCONNECTED:
      Serial.println(F("[WS] Disconnected from SmartGuard IoT Microservice"));
      isWsConnected = false;
      if (manualLatchedOpen) showManualOpenDisplay();
      else displayMessage("MICROSERVICE", "DISCONNECTED");
      break;

    case WStype_CONNECTED:
      Serial.println(F("[WS] Connected to SmartGuard IoT Microservice!"));
      isWsConnected = true;
      if (manualLatchedOpen) showManualOpenDisplay();
      else displayMessage("SMARTGUARD AI", "CONNECTED & RDY");
      sendHeartbeat();
      break;

    case WStype_TEXT:
      Serial.printf("[WS] Received: %s\n", payload);
      handleServerCommand(payload, length);
      break;

    default:
      break;
  }
}

// =============================================================================
// SETUP & LOOP
// =============================================================================

void setup() {
  Serial.begin(115200);
  Serial.println(F("\n--- SmartGuard AI ESP32 Controller (Servo + LCD) ---"));

  // 1. Initialize LCD (SDA=21, SCL=22, 0x27, 16x2)
  Wire.begin(SDA_PIN, SCL_PIN);
  lcd.init();
  lcd.backlight();
  displayMessage("SMARTGUARD AI", "Starting...");

  // 2. Initialize Servo (GPIO 18)
  gateServo.setPeriodHertz(50);
  gateServo.attach(SERVO_PIN, 500, 2400);
  gateServo.write(ANGLE_CLOSED);
  gateIsOpen = false;
  Serial.printf(
    "[GATE] Physical close executed (Servo: %d deg, reason=STARTUP_SAFE_STATE)\n",
    ANGLE_CLOSED
  );

  // Start Wi-Fi asynchronously so an unavailable access point cannot block recovery.
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  lastWifiAttempt = millis();
  displayMessage("Connecting WiFi", "Please wait...");
}

void loop() {
  unsigned long now = millis();

  bool wifiConnected = WiFi.status() == WL_CONNECTED;
  if (wifiConnected && !wifiWasConnected) {
    Serial.print(F("[WIFI] Connected; ESP32 IP: "));
    Serial.println(WiFi.localIP());
    if (!manualLatchedOpen) displayMessage("WiFi Connected", "Connecting WS...");
    if (strcmp(SERVER_HOST, "localhost") == 0 ||
        strcmp(SERVER_HOST, "127.0.0.1") == 0 ||
        strlen(SERVER_HOST) == 0) {
      Serial.println(F("[CONFIG] Set SG_IOT_SERVER_HOST to the laptop LAN IPv4."));
      displayMessage("CONFIG ERROR", "Server host invalid");
    } else {
      String wsUrl = String("/api/v1/ws/iot/gate?device_id=") + DEVICE_ID + "&token=" + DEVICE_TOKEN;
      Serial.printf("[WS] Connecting to %s:%u/api/v1/ws/iot/gate\n", SERVER_HOST, SERVER_PORT);
      webSocket.begin(SERVER_HOST, SERVER_PORT, wsUrl.c_str());
      webSocket.onEvent(webSocketEvent);
      webSocket.setReconnectInterval(3000);
      webSocket.enableHeartbeat(15000, 3000, 2);
      wsClientStarted = true;
    }
  } else if (!wifiConnected && wifiWasConnected) {
    Serial.println(F("[WIFI] Connection lost; retrying without blocking."));
    isWsConnected = false;
    wsClientStarted = false;
    if (!manualLatchedOpen) displayMessage("WiFi Lost", "Retrying...");
  }
  wifiWasConnected = wifiConnected;

  if (!wifiConnected && now - lastWifiAttempt >= 10000) {
    lastWifiAttempt = now;
    Serial.println(F("[WIFI] Reconnecting..."));
    WiFi.disconnect(false, false);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  }

  if (wifiConnected && wsClientStarted) {
    webSocket.loop();
  }

  // A command handled above may have recorded a newer gateOpenedAt timestamp.
  now = millis();

  // Periodic Heartbeat to microservice
  if (isWsConnected && (now - lastHeartbeatTime >= HEARTBEAT_INTERVAL_MS)) {
    lastHeartbeatTime = now;
    sendHeartbeat();
  }

  updateOpenCountdown(now);

  // Unsigned elapsed-time comparison remains valid across millis() rollover.
  if (isAutoCloseArmed &&
      gateIsOpen &&
      !manualLatchedOpen &&
      autoCloseCommandSequence == latestCommandSequence &&
      now - gateOpenedAt >= autoCloseDurationMs) {
    executeGateClose("AUTO_CLOSE_TIMEOUT");
    sendGateState();
  }
}
