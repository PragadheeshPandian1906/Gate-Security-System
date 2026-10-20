/*
 * ======================================================================================
 * SmartGuard AI — Physical Gate Controller Firmware (ESP32)
 * ======================================================================================
 * 
 * Target Hardware:
 *   - ESP32 WROOM-32 Development Board
 *   - SG90 Tower Pro Micro Servo Motor (Signal on GPIO 18)
 *   - 16x2 Character LCD with I2C Backpack (PCF8574 @ 0x27; SDA: GPIO 21, SCL: GPIO 22)
 * 
 * Legacy duplicate sketch. The canonical implementation is:
 *   iot-service/firmware/esp32_gate_controller/esp32_gate_controller.ino
 * This copy uses the same microservice endpoint and message protocol, but only
 * one sketch/device connection should be active for a device ID at a time.
 * 
 * Required Arduino Libraries (Install via Library Manager):
 *   1. "WebSockets" by Markus Sattler (v2.4.1 or higher)
 *   2. "ArduinoJson" by Benoit Blanchon (v6.x or v7.x)
 *   3. "ESP32Servo" by Kevin Harrington (v3.0.0 or higher)
 *   4. "LiquidCrystal_I2C" by Frank de Brabander (or Marco Schwartz)
 * 
 * Electrical & Safety Notes:
 *   - Servo Power: SG90 peaks at ~500-700mA during motor stall. Power servo from an external
 *     5V regulated supply (or 5V power bank), NEVER directly from the ESP32 3.3V GPIO pin.
 *     Ensure common GROUND (GND) is connected between the ESP32 and the servo power source.
 *   - LCD I2C Level Shifting: ESP32 I2C pins operate at 3.3V logic. If your LCD backpack
 *     is powered with 5V, ensure the I2C pull-ups do not inject 5V into GPIO 21/22. Either
 *     power LCD backpack at 5V with a bidirectional I2C level shifter or verify 3.3V compatibility.
 * ======================================================================================
 */

#include <WiFi.h>
#include <WebSocketsClient.h>
#include <ArduinoJson.h>
#include <ESP32Servo.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include "secrets.h"

const char* WIFI_SSID = SG_WIFI_SSID;
const char* WIFI_PASSWORD = SG_WIFI_PASSWORD;
const char* BACKEND_HOST = SG_IOT_SERVER_HOST;
const uint16_t BACKEND_PORT = 8001;
const char* DEVICE_ID = SG_IOT_DEVICE_ID;
const char* DEVICE_KEY = SG_IOT_DEVICE_TOKEN;

// ===== Hardware Pin Assignments =====
const int PIN_SERVO   = 18;  // PWM output for SG90
const int PIN_LCD_SDA = 21;  // I2C SDA
const int PIN_LCD_SCL = 22;  // I2C SCL
const uint8_t LCD_I2C_ADDR = 0x27;

// ===== Servo Angle Configurations =====
const int SERVO_CLOSED_ANGLE = 0;   // Barrier down (closed)
const int SERVO_OPEN_ANGLE   = 90;  // Barrier up (open)

// ===== Timing Configurations =====
const unsigned long DEFAULT_AUTO_CLOSE_MS = 15000;   // 5 seconds
const unsigned long HEARTBEAT_INTERVAL_MS = 10000;  // Send heartbeat every 10s
const unsigned long WIFI_RETRY_INTERVAL_MS = 5000;  // Wi-Fi check interval

// ===== Peripherals =====
Servo gateServo;
LiquidCrystal_I2C lcd(LCD_I2C_ADDR, 16, 2);
WebSocketsClient webSocket;

// ===== Runtime State Variables =====
bool gateIsOpen = false;
unsigned long gateOpenedAt = 0;
unsigned long autoCloseDurationMs = DEFAULT_AUTO_CLOSE_MS;
unsigned long lastHeartbeatSentAt = 0;
unsigned long lastWiFiCheckAt = 0;
bool isWsConnected = false;
uint32_t latestCommandSequence = 0;
uint32_t autoCloseCommandSequence = 0;

// Display buffer cache to avoid flickering
char currentLcdLine1[17] = "";
char currentLcdLine2[17] = "";

// ---------------------------------------------------------------------------
// LCD Display Helpers (Flicker-Free, 16-Char Clamped)
// ---------------------------------------------------------------------------
void displayMessage(const char* line1, const char* line2) {
  // Check if identical to current text to prevent screen flicker
  if (strncmp(currentLcdLine1, line1, 16) == 0 && strncmp(currentLcdLine2, line2, 16) == 0) {
    return;
  }

  strncpy(currentLcdLine1, line1, 16);
  currentLcdLine1[16] = '\0';
  strncpy(currentLcdLine2, line2, 16);
  currentLcdLine2[16] = '\0';

  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print(currentLcdLine1);
  lcd.setCursor(0, 1);
  lcd.print(currentLcdLine2);
}

// ---------------------------------------------------------------------------
// Gate Actuation
// ---------------------------------------------------------------------------
void actuateGateOpen(
  unsigned long durationMs,
  const char* line1 = "ACCESS GRANTED",
  const char* line2 = "OPENING GATE"
) {
  gateServo.write(SERVO_OPEN_ANGLE);
  gateIsOpen = true;
  gateOpenedAt = millis();
  autoCloseDurationMs = (durationMs > 0) ? durationMs : DEFAULT_AUTO_CLOSE_MS;
  autoCloseCommandSequence = latestCommandSequence;

  displayMessage(line1, line2);
  Serial.printf("[GATE] Opened (angle=%d°, auto-close=%lums)\n", SERVO_OPEN_ANGLE, autoCloseDurationMs);
}

void actuateGateClose(const char* reason = "GATE CLOSED") {
  gateServo.write(SERVO_CLOSED_ANGLE);
  gateIsOpen = false;
  gateOpenedAt = 0;

  displayMessage("GATE CLOSED", "SYSTEM READY");
  Serial.printf("[GATE] Closed (angle=%d°, reason=%s)\n", SERVO_CLOSED_ANGLE, reason);
}

// ---------------------------------------------------------------------------
// WebSocket Outgoing Message Senders
// ---------------------------------------------------------------------------
void sendCommandAck(const char* commandId, const char* status, const char* detail = nullptr) {
  if (!isWsConnected) return;

  StaticJsonDocument<256> doc;
  doc["type"] = "COMMAND_ACK";
  doc["command_id"] = commandId;
  doc["status"] = status;
  if (detail != nullptr) {
    doc["detail"] = detail;
  }

  String jsonString;
  serializeJson(doc, jsonString);
  webSocket.sendTXT(jsonString);
  Serial.printf("[WS OUT] ACK sent: %s (%s)\n", commandId, status);
}

void sendGateStateReport(const char* commandId = nullptr) {
  if (!isWsConnected) return;

  StaticJsonDocument<256> doc;
  doc["type"] = "GATE_STATE";
  doc["device_id"] = DEVICE_ID;
  doc["state"] = gateIsOpen ? "OPEN" : "CLOSED";
  if (commandId != nullptr) {
    doc["command_id"] = commandId;
  }

  String jsonString;
  serializeJson(doc, jsonString);
  webSocket.sendTXT(jsonString);
  Serial.printf("[WS OUT] State reported: %s\n", gateIsOpen ? "OPEN" : "CLOSED");
}

void sendHeartbeat() {
  if (!isWsConnected) return;

  StaticJsonDocument<256> doc;
  doc["type"] = "HEARTBEAT";
  doc["device_id"] = DEVICE_ID;
  doc["state"] = gateIsOpen ? "OPEN" : "CLOSED";

  String jsonString;
  serializeJson(doc, jsonString);
  webSocket.sendTXT(jsonString);
  Serial.println("[WS OUT] Heartbeat sent");
}

// ---------------------------------------------------------------------------
// WebSocket Incoming Message Dispatcher
// ---------------------------------------------------------------------------
void handleIncomingMessage(uint8_t* payload, size_t length) {
  StaticJsonDocument<512> doc;
  DeserializationError error = deserializeJson(doc, payload, length);

  if (error) {
    Serial.printf("[WS ERROR] JSON parse error: %s\n", error.c_str());
    return;
  }

  const char* type = doc["type"];
  if (!type) {
    Serial.println("[WS ERROR] Missing message type");
    return;
  }

  // 1. GATE_OPEN Command
  if (strcmp(type, "GATE_OPEN") == 0) {
    const char* commandId = doc["command_id"] | "";
    const char* attemptId = doc["attempt_id"] | "";
    unsigned long durationMs = doc["duration_ms"] | DEFAULT_AUTO_CLOSE_MS;
    uint32_t commandSequence = doc["command_sequence"] | 0;
    if (commandSequence == 0 || commandSequence <= latestCommandSequence) {
      sendCommandAck(commandId, "REJECTED", "Stale or invalid command sequence");
      return;
    }
    latestCommandSequence = commandSequence;
    const char* line1 = doc["line1"] | "GATE OPEN";
    const char* line2 = doc["line2"] | "WELCOME";

    Serial.printf("[WS IN] GATE_OPEN received: cmd=%s attempt=%s duration=%lums\n",
                  commandId, attemptId, durationMs);

    // Physically actuate servo
    actuateGateOpen(durationMs, line1, line2);

    // Send immediate ACK
    sendCommandAck(commandId, "EXECUTED", "Servo target set to OPEN; no position sensor");

    // Report new commanded state
    sendGateStateReport(commandId);
  }

  // 2. GATE_CLOSE Command
  else if (strcmp(type, "GATE_CLOSE") == 0) {
    const char* commandId = doc["command_id"] | "";
    const char* reason = doc["reason"] | "OPERATOR_RESET";
    uint32_t commandSequence = doc["command_sequence"] | 0;
    if (commandSequence == 0 || commandSequence <= latestCommandSequence) {
      sendCommandAck(commandId, "REJECTED", "Stale or invalid command sequence");
      return;
    }
    latestCommandSequence = commandSequence;

    Serial.printf("[WS IN] GATE_CLOSE received: cmd=%s reason=%s\n", commandId, reason);

    // Physically actuate servo
    actuateGateClose(reason);

    // Send immediate ACK
    sendCommandAck(commandId, "EXECUTED", "Servo target set to CLOSED; no position sensor");

    // Report new commanded state
    sendGateStateReport(commandId);
  }

  // 3. DISPLAY_STATUS Command
  else if (strcmp(type, "DISPLAY_STATUS") == 0) {
    const char* line1 = doc["line1"] | "";
    const char* line2 = doc["line2"] | "";
    Serial.printf("[WS IN] DISPLAY_STATUS: [%s] / [%s]\n", line1, line2);

    displayMessage(line1, line2);
  }

  else {
    Serial.printf("[WS WARNING] Unrecognized message type: %s\n", type);
  }
}

// ---------------------------------------------------------------------------
// WebSocket Event Handler
// ---------------------------------------------------------------------------
void webSocketEvent(WStype_t type, uint8_t* payload, size_t length) {
  switch (type) {
    case WStype_DISCONNECTED:
      isWsConnected = false;
      Serial.println("[WS] Disconnected from backend server");
      displayMessage("BACKEND OFFLINE", "GATE LOCKED");
      break;

    case WStype_CONNECTED:
      isWsConnected = true;
      Serial.printf("[WS] Connected to ws://%s:%u/api/v1/ws/iot/gate\n", BACKEND_HOST, BACKEND_PORT);
      displayMessage("SMARTGUARD READY", "GATE CLOSED");

      // Send initial state report
      sendGateStateReport();
      break;

    case WStype_TEXT:
      handleIncomingMessage(payload, length);
      break;

    case WStype_BIN:
      // Binary frames not used
      break;

    case WStype_ERROR:
      Serial.println("[WS] Connection Error encountered");
      break;

    default:
      break;
  }
}

// ---------------------------------------------------------------------------
// Wi-Fi Connection Manager
// ---------------------------------------------------------------------------
void connectWiFi() {
  displayMessage("Connecting WiFi", "Please wait...");
  Serial.printf("Connecting to Wi-Fi SSID: %s", WIFI_SSID);

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  unsigned long startAttempt = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - startAttempt < 15000) {
    delay(500);
    Serial.print(".");
  }
  Serial.println();

  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("Wi-Fi Connected! ESP32 IP: ");
    Serial.println(WiFi.localIP());
    displayMessage("WiFi Connected", "Connecting WS...");
  } else {
    Serial.println("Wi-Fi connection timed out. Will retry in background.");
    displayMessage("WiFi Failed", "Retrying...");
  }
}

// ---------------------------------------------------------------------------
// Arduino Setup
// ---------------------------------------------------------------------------
void setup() {
  Serial.begin(115200);
  delay(200);
  Serial.println("\n=== SmartGuard AI Physical Gate Controller Initializing ===");

  // 1. Initialize LCD (I2C)
  Wire.begin(PIN_LCD_SDA, PIN_LCD_SCL);
  lcd.init();
  lcd.backlight();
  displayMessage("SMARTGUARD", "STARTING...");

  // 2. Initialize Servo
  gateServo.setPeriodHertz(50);                      // Standard 50Hz servo PWM
  gateServo.attach(PIN_SERVO, 500, 2400);            // 500us to 2400us pulse widths
  gateServo.write(SERVO_CLOSED_ANGLE);               // Default safe closed state
  gateIsOpen = false;

  // 3. Connect to Wi-Fi
  connectWiFi();

  // 4. Configure WebSocket Client
  // Format URL query parameters with authentication credentials
  if (strcmp(BACKEND_HOST, "localhost") == 0 ||
      strcmp(BACKEND_HOST, "127.0.0.1") == 0 ||
      strlen(BACKEND_HOST) == 0) {
    Serial.println("[CONFIG] Set SG_IOT_SERVER_HOST to the laptop LAN IPv4.");
    displayMessage("CONFIG ERROR", "Server host invalid");
    return;
  }

  String wsUrl = "/api/v1/ws/iot/gate?device_id=";
  wsUrl += DEVICE_ID;
  wsUrl += "&token=";
  wsUrl += DEVICE_KEY;

  webSocket.begin(BACKEND_HOST, BACKEND_PORT, wsUrl.c_str());
  webSocket.onEvent(webSocketEvent);
  webSocket.setReconnectInterval(3000);  // Retry every 3 seconds if disconnected
  webSocket.enableHeartbeat(15000, 3000, 2);

  Serial.println("Initialization complete. Entering loop...");
}

// ---------------------------------------------------------------------------
// Main Arduino Loop (Non-Blocking)
// ---------------------------------------------------------------------------
void loop() {
  unsigned long now = millis();

  // 1. Service WebSocket packets
  webSocket.loop();

  // 2. Check physical automatic gate-closing timer (using non-blocking millis)
  if (gateIsOpen &&
      autoCloseCommandSequence == latestCommandSequence &&
      (now - gateOpenedAt >= autoCloseDurationMs)) {
    Serial.println("[TIMER] Auto-close duration elapsed. Closing gate barrier.");
    actuateGateClose("AUTO_CLOSE_TIMEOUT");
    sendGateStateReport();
  }

  // 3. Periodic Keep-Alive Heartbeat
  if (isWsConnected && (now - lastHeartbeatSentAt >= HEARTBEAT_INTERVAL_MS)) {
    lastHeartbeatSentAt = now;
    sendHeartbeat();
  }

  // 4. Check Wi-Fi connection health
  if (now - lastWiFiCheckAt >= WIFI_RETRY_INTERVAL_MS) {
    lastWiFiCheckAt = now;
    if (WiFi.status() != WL_CONNECTED) {
      Serial.println("[WIFI] Connection lost. Attempting reconnection...");
      displayMessage("WiFi Reconnect", "Please wait...");
      WiFi.reconnect();
    }
  }
}
