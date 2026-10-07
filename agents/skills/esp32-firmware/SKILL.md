---
name: esp32-firmware
description: Use this skill to write, debug, or modify ESP32 firmware v3 — reading MAX30102 (HR/SpO2), DS18B20 (temperature), MPU6050 (accelerometer), AD8232 ECG (new!), adaptive Z-score threshold (replaces hard rules), store-and-forward via SPIFFS when WiFi is lost, NTP time sync, and publishing JSON+ECG data via MQTT. Trigger when user says 'viết code ESP32', 'firmware', 'đọc cảm biến', 'main.cpp', 'kết nối WiFi', 'gửi MQTT', 'ECG', 'adaptive threshold', 'store-and-forward', or 'SPIFFS buffer'.
---

# ESP32 Firmware Skill v3 – AIoT Health Monitor

## Sơ đồ kết nối (v3 — thêm AD8232)

```
MAX30102:  VCC→3.3V  GND→GND  SDA→GPIO8  SCL→GPIO9  INT→GPIO15
DS18B20:   VCC→3.3V  GND→GND  DQ→GPIO4    (điện trở 4.7kΩ: DQ→3.3V)
MPU6050:   VCC→3.3V  GND→GND  SDA→GPIO8  SCL→GPIO9  AD0→GND
OLED:      VCC→3.3V  GND→GND  SDA→GPIO8  SCL→GPIO9
AD8232:    VCC→3.3V  GND→GND  OUTPUT→GPIO1  LO+→GPIO11  LO-→GPIO12
           (thêm tụ 100nF từ OUTPUT→GND để lọc nhiễu cao tần)
```

## File: include/offline_buffer.h (MỚI v3 — Store-and-Forward)

```cpp
#pragma once
#include <Arduino.h>
#include <SPIFFS.h>

// Lưu JSON vào SPIFFS khi mất WiFi, đồng bộ khi có mạng lại
// Đảm bảo không mất data trong trường hợp mất kết nối

void initSPIFFS() {
    if (!SPIFFS.begin(true)) {
        Serial.println("[SPIFFS] Mount failed, formatting...");
        SPIFFS.format();
        SPIFFS.begin(true);
    }
    Serial.printf("[SPIFFS] Total:%dKB  Used:%dKB\n",
                  SPIFFS.totalBytes()/1024, SPIFFS.usedBytes()/1024);
}

void bufferData(const char* json) {
    // Kiểm tra còn ít nhất 2KB trống mới ghi
    if ((SPIFFS.totalBytes() - SPIFFS.usedBytes()) < 2048) {
        Serial.println("[BUFFER] Full, skipping");
        return;
    }
    File f = SPIFFS.open(SPIFFS_BUFFER_FILE, "a");
    if (f) { f.println(json); f.close(); }
}

// Gọi sau khi WiFi+MQTT đã reconnect thành công
void syncBuffer(PubSubClient& mqtt, const char* topic) {
    if (!SPIFFS.exists(SPIFFS_BUFFER_FILE)) return;
    File f = SPIFFS.open(SPIFFS_BUFFER_FILE, "r");
    int synced = 0;
    while (f.available()) {
        String line = f.readStringUntil('\n');
        line.trim();
        if (line.length() > 5) {
            mqtt.publish(topic, line.c_str());
            synced++;
            delay(50); // tránh flood broker
        }
    }
    f.close();
    if (synced > 0) {
        SPIFFS.remove(SPIFFS_BUFFER_FILE);
        Serial.printf("[SYNC] Đồng bộ %d bản ghi offline\n", synced);
    }
}
```

## File: src/main.cpp (v3 — đầy đủ nâng cấp)

```cpp
#include <Arduino.h>
#include <Wire.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <MAX30105.h>
#include <heartRate.h>
#include <spo2_algorithm.h>
#include <DallasTemperature.h>
#include <OneWire.h>
#include <MPU6050.h>
#include <Adafruit_SSD1306.h>
#include <SPIFFS.h>
#include <time.h>
#include "config.h"
#include "offline_buffer.h"

// ─── Đối tượng cảm biến ──────────────────────────
MAX30105           maxSensor;
OneWire            oneWire(PIN_DS18B20);
DallasTemperature  tempSensor(&oneWire);
MPU6050            mpu;
Adafruit_SSD1306   oled(128, 64, &Wire, -1);
WiFiClientSecure   wifiClient;
PubSubClient       mqttClient(wifiClient);

// ─── Dữ liệu sức khỏe ────────────────────────────
struct HealthData {
    float heartRate   = 0;
    float spo2        = 0;
    float temperature = 0;
    float accelX = 0, accelY = 0, accelZ = 0;
    bool  fallDetected  = false;
    bool  edgeAlert     = false;
    bool  electrodesOk  = true;  // MỚI: ECG electrode check
    float anomalyScore  = 0.0f;  // MỚI: Z-score bất thường
    String alertReason  = "";
};
HealthData data;

// ─── Adaptive Threshold — Rolling Window ─────────
// Thay thế #define cứng bằng Z-score cá nhân hóa
float hrWindow[ADAPTIVE_WINDOW]   = {};
float spo2Window[ADAPTIVE_WINDOW] = {};
int   windowIdx = 0, windowCount  = 0;

float computeZScore(float val, float* window, int n) {
    if (n < 10) return 0.0f; // Chưa đủ data để tính
    float mean = 0, var = 0;
    for (int i = 0; i < n; i++) mean += window[i] / n;
    for (int i = 0; i < n; i++) var  += powf(window[i] - mean, 2) / n;
    float sd = sqrtf(var);
    return sd > 0.5f ? fabsf(val - mean) / sd : 0.0f;
}

void updateWindow(float hrVal, float spo2Val) {
    hrWindow[windowIdx]   = hrVal;
    spo2Window[windowIdx] = spo2Val;
    windowIdx = (windowIdx + 1) % ADAPTIVE_WINDOW;
    if (windowCount < ADAPTIVE_WINDOW) windowCount++;
}

// ─── NTP — Giờ thực Việt Nam ─────────────────────
void setupNTP() {
    configTime(7 * 3600, 0, "pool.ntp.org", "time.nist.gov");
    Serial.print("[NTP] Đồng bộ giờ");
    int tries = 0;
    while (time(nullptr) < 100000 && tries++ < 20) {
        delay(500); Serial.print(".");
    }
    Serial.println(time(nullptr) > 100000 ? " OK!" : " Timeout");
}

String getTimestamp() {
    time_t now = time(nullptr);
    struct tm* t = localtime(&now);
    char buf[25];
    sprintf(buf, "%04d-%02d-%02dT%02d:%02d:%02d",
            t->tm_year+1900, t->tm_mon+1, t->tm_mday,
            t->tm_hour, t->tm_min, t->tm_sec);
    return String(buf);
}

// ─── Kết nối WiFi ────────────────────────────────
bool prevWifiState = false;

void connectWiFi() {
    Serial.printf("[WiFi] Kết nối %s", WIFI_SSID);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    uint32_t start = millis();
    while (WiFi.status() != WL_CONNECTED) {
        if (millis() - start > 15000) {
            Serial.println("\n[WiFi] Timeout! Restarting...");
            ESP.restart();
        }
        delay(500); Serial.print(".");
    }
    Serial.printf("\n[WiFi] OK | IP: %s\n", WiFi.localIP().toString().c_str());
}

// ─── Callback MQTT ────────────────────────────────
void onMqttMessage(char* topic, byte* payload, unsigned int len) {
    String msg;
    for (uint i = 0; i < len; i++) msg += (char)payload[i];
    JsonDocument cmd;
    if (!deserializeJson(cmd, msg)) {
        if (cmd["action"] == "buzzer") tone(PIN_BUZZER, 1000, 500);
        if (cmd["action"] == "led_on") digitalWrite(PIN_LED_ERR, HIGH);
    }
}

void connectMQTT() {
    wifiClient.setInsecure();
    mqttClient.setServer(MQTT_BROKER, MQTT_PORT);
    mqttClient.setCallback(onMqttMessage);
    mqttClient.setKeepAlive(MQTT_KEEPALIVE);
    mqttClient.setBufferSize(512);

    Serial.print("[MQTT] Kết nối...");
    while (!mqttClient.connected()) {
        if (mqttClient.connect(MQTT_CLIENT, MQTT_USER, MQTT_PASS)) {
            Serial.println("OK!");
            mqttClient.subscribe(TOPIC_CMD, MQTT_QOS);
            mqttClient.subscribe(TOPIC_ALERT_IN, MQTT_QOS);
            // Sync data đã buffer offline khi vừa kết nối lại
            syncBuffer(mqttClient, TOPIC_DATA);
        } else {
            Serial.printf("Lỗi=%d, thử lại sau 3s\n", mqttClient.state());
            delay(3000);
        }
    }
}

// ─── Đọc MAX30102 ─────────────────────────────────
void readMAX30102() {
    const int BUF = 100;
    uint32_t irBuf[BUF], redBuf[BUF];
    int32_t hr, sp;
    int8_t  validHR, validSP;

    for (int i = 0; i < BUF; i++) {
        while (!maxSensor.available()) maxSensor.check();
        redBuf[i] = maxSensor.getRed();
        irBuf[i]  = maxSensor.getIR();
        maxSensor.nextSample();
    }
    maxim_heart_rate_and_oxygen_saturation(irBuf, BUF, redBuf,
                                           &sp, &validSP, &hr, &validHR);
    if (validHR && hr > 20 && hr < 220) data.heartRate = hr;
    if (validSP && sp > 50 && sp <= 100) data.spo2     = sp;
}

// ─── Đọc DS18B20 ─────────────────────────────────
void readDS18B20() {
    tempSensor.requestTemperatures();
    float t = tempSensor.getTempCByIndex(0);
    if (t > 20.0f && t < 45.0f) data.temperature = t;
}

// ─── Đọc MPU6050 ─────────────────────────────────
void readMPU6050() {
    int16_t ax, ay, az, gx, gy, gz;
    mpu.getMotion6(&ax, &ay, &az, &gx, &gy, &gz);
    data.accelX = ax / 16384.0f;
    data.accelY = ay / 16384.0f;
    data.accelZ = az / 16384.0f;
    float mag = sqrtf(data.accelX*data.accelX +
                      data.accelY*data.accelY +
                      data.accelZ*data.accelZ);
    data.fallDetected = (mag < 0.3f || mag > ALERT_FALL_MAG);
}

// ─── Đọc ECG AD8232 (MỚI v3) ─────────────────────
// Gọi riêng với interval 5 giây — đọc 250 mẫu @ 50Hz
int16_t ecgBuffer[ECG_SAMPLES];

bool readECG() {
    // Kiểm tra điện cực trước
    data.electrodesOk = !(digitalRead(ECG_LO_PLUS) || digitalRead(ECG_LO_MINUS));
    if (!data.electrodesOk) return false;

    for (int i = 0; i < ECG_SAMPLES; i++) {
        // Oversampling 4x để giảm nhiễu
        int32_t raw = (analogRead(ECG_OUTPUT_PIN) + analogRead(ECG_OUTPUT_PIN)
                     + analogRead(ECG_OUTPUT_PIN) + analogRead(ECG_OUTPUT_PIN)) >> 2;
        ecgBuffer[i] = (int16_t)raw;
        delay(ECG_SAMPLE_MS);
    }
    return true;
}

// ─── Edge AI v3: Adaptive Z-score ────────────────
void runEdgeAI() {
    data.edgeAlert   = false;
    data.alertReason = "";
    data.anomalyScore = 0.0f;

    // Cập nhật rolling window
    if (data.heartRate > 0 && data.spo2 > 0) {
        updateWindow(data.heartRate, data.spo2);
    }

    // 1. Hard stop: ngưỡng y tế tuyệt đối (luôn check trước)
    if (data.spo2 > 0 && data.spo2 < ALERT_SPO2_HARD_LOW) {
        data.edgeAlert = true;
        data.anomalyScore = 1.0f;
        data.alertReason = "SPO2_CRITICAL:" + String((int)data.spo2);
    } else if (data.heartRate > ALERT_HR_HARD_HIGH) {
        data.edgeAlert = true;
        data.anomalyScore = 1.0f;
        data.alertReason = "HR_CRITICAL_HIGH:" + String((int)data.heartRate);
    } else if (data.heartRate > 0 && data.heartRate < ALERT_HR_HARD_LOW) {
        data.edgeAlert = true;
        data.anomalyScore = 1.0f;
        data.alertReason = "HR_CRITICAL_LOW:" + String((int)data.heartRate);
    } else if (data.temperature > ALERT_TEMP_HIGH) {
        data.edgeAlert = true;
        data.anomalyScore = 0.8f;
        data.alertReason = "TEMP_HIGH:" + String(data.temperature, 1);
    } else if (data.fallDetected) {
        data.edgeAlert = true;
        data.anomalyScore = 1.0f;
        data.alertReason = "FALL_DETECTED";
    } else {
        // 2. Adaptive: Z-score cá nhân hóa
        float zHR  = computeZScore(data.heartRate, hrWindow, windowCount);
        float zSpo = computeZScore(data.spo2, spo2Window, windowCount);
        data.anomalyScore = max(zHR, zSpo) / 5.0f; // normalize 0-1

        if (zHR > ADAPTIVE_Z_THRESH) {
            data.edgeAlert = true;
            data.alertReason = "HR_ZSCORE:" + String(zHR, 1);
        } else if (zSpo > ADAPTIVE_Z_THRESH) {
            data.edgeAlert = true;
            data.alertReason = "SPO2_ZSCORE:" + String(zSpo, 1);
        }
    }

    digitalWrite(PIN_LED_ERR, data.edgeAlert ? HIGH : LOW);
    digitalWrite(PIN_LED_OK,  data.edgeAlert ? LOW  : HIGH);
}

// ─── Gửi MQTT (vitals + ECG riêng) ───────────────
unsigned long lastSendMs  = 0;
unsigned long lastECGMs   = 0;
unsigned long lastDisplayMs = 0;

void publishVitals() {
    JsonDocument doc;
    doc["device_id"]    = DEVICE_ID;
    doc["ts"]           = getTimestamp();
    doc["heart_rate"]   = (int)data.heartRate;
    doc["spo2"]         = (int)data.spo2;
    doc["temperature"]  = serialized(String(data.temperature, 1));
    doc["accel_x"]      = serialized(String(data.accelX, 3));
    doc["accel_y"]      = serialized(String(data.accelY, 3));
    doc["accel_z"]      = serialized(String(data.accelZ, 3));
    doc["fall"]         = data.fallDetected;
    doc["edge_alert"]   = data.edgeAlert;
    doc["anomaly_score"]= serialized(String(data.anomalyScore, 3));
    doc["alert_reason"] = data.alertReason;
    doc["ecg_ok"]       = data.electrodesOk;  // MỚI

    char buf[512];
    size_t len = serializeJson(doc, buf);

    if (mqttClient.connected()) {
        bool ok = mqttClient.publish(TOPIC_DATA, buf, len);
        Serial.printf("[MQTT] %s | HR:%d SpO2:%d Temp:%.1f Score:%.2f\n",
                      ok?"SENT":"FAIL",
                      (int)data.heartRate, (int)data.spo2,
                      data.temperature, data.anomalyScore);
    } else {
        // Lưu vào SPIFFS — sync sau khi có mạng lại
        bufferData(buf);
        Serial.println("[BUFFER] Offline — data saved to SPIFFS");
    }
}

void publishECG() {
    // Gửi mảng ECG riêng (to hơn, ít tần suất hơn)
    if (!data.electrodesOk) return;

    JsonDocument doc;
    doc["device_id"] = DEVICE_ID;
    doc["ts"]        = getTimestamp();
    doc["type"]      = "ecg";
    JsonArray arr    = doc["samples"].to<JsonArray>();
    for (int i = 0; i < ECG_SAMPLES; i++) arr.add(ecgBuffer[i]);

    String payload;
    serializeJson(doc, payload);
    if (mqttClient.connected()) {
        mqttClient.publish(TOPIC_ECG, payload.c_str());
    }
}

// ─── OLED Display ─────────────────────────────────
void updateOLED() {
    oled.clearDisplay();
    oled.setTextSize(1); oled.setTextColor(SSD1306_WHITE);

    oled.fillRect(0, 0, 128, 10, SSD1306_WHITE);
    oled.setTextColor(SSD1306_BLACK);
    oled.setCursor(2, 1);
    oled.print(data.edgeAlert ? "!!! CANH BAO !!!" : "  AIoT Health v3");

    oled.setTextColor(SSD1306_WHITE);
    oled.setCursor(0, 14); oled.printf("HR:   %3d bpm", (int)data.heartRate);
    oled.setCursor(0, 25); oled.printf("SpO2: %3d %%",  (int)data.spo2);
    oled.setCursor(0, 36); oled.printf("Temp: %.1f C",   data.temperature);
    oled.setCursor(0, 47); oled.printf("ECG:  %s  Z:%.1f",
                                        data.electrodesOk ? "OK" : "--",
                                        data.anomalyScore * 5.0f);
    oled.setCursor(0, 57);
    oled.printf("W:%s M:%s",
        WiFi.isConnected()     ? "Y":"N",
        mqttClient.connected() ? "Y":"N");

    oled.display();
}

// ─── Setup ──────────────────────────────────────────
void setup() {
    Serial.begin(115200);
    Wire.begin(8, 9)  // ESP32-S3: SDA=GPIO8, SCL=GPIO9;
    pinMode(PIN_LED_OK,     OUTPUT);
    pinMode(PIN_LED_ERR,    OUTPUT);
    pinMode(ECG_LO_PLUS,    INPUT);   // MỚI
    pinMode(ECG_LO_MINUS,   INPUT);   // MỚI
    digitalWrite(PIN_LED_ERR, HIGH);

    initSPIFFS();  // MỚI: init offline buffer

    // OLED splash
    if (!oled.begin(SSD1306_SWITCHCAPVCC, 0x3C))
        Serial.println("[ERR] OLED không tìm thấy!");
    oled.clearDisplay();
    oled.setTextSize(2); oled.setTextColor(SSD1306_WHITE);
    oled.setCursor(5, 10); oled.print("AIoT v3");
    oled.setTextSize(1); oled.setCursor(15, 40); oled.print("+ECG +AI");
    oled.display(); delay(1500);

    // Cảm biến
    if (!maxSensor.begin(Wire, I2C_SPEED_FAST))
        Serial.println("[ERR] MAX30102 không tìm thấy!");
    maxSensor.setup(60, SAMPLE_AVG, 2, 200, 411, 4096);
    tempSensor.begin();
    mpu.initialize();
    Serial.printf("[MPU6050] %s\n", mpu.testConnection() ? "OK" : "FAIL");

    connectWiFi();
    setupNTP();    // MỚI: đồng bộ giờ thực
    connectMQTT();
    digitalWrite(PIN_LED_ERR, LOW);
    digitalWrite(PIN_LED_OK,  HIGH);
    Serial.println("[SETUP] AIoT Health Monitor v3 sẵn sàng!");
}

// ─── Loop ───────────────────────────────────────────
void loop() {
    bool wifiNow = WiFi.isConnected();

    // Phát hiện WiFi vừa kết nối lại → sync buffer
    if (wifiNow && !prevWifiState) {
        connectMQTT(); // reconnect MQTT + auto syncBuffer bên trong
    }
    prevWifiState = wifiNow;

    if (wifiNow && !mqttClient.connected()) connectMQTT();
    mqttClient.loop();

    // Đọc cảm biến
    readMAX30102();
    readDS18B20();
    readMPU6050();
    runEdgeAI();

    // Đọc ECG mỗi 5 giây (song song với vitals)
    if (millis() - lastECGMs >= 5000) {
        if (readECG()) publishECG();
        lastECGMs = millis();
    }

    // Cập nhật OLED
    if (millis() - lastDisplayMs >= DISPLAY_INTERVAL) {
        updateOLED();
        lastDisplayMs = millis();
    }

    // Gửi vitals MQTT
    if (millis() - lastSendMs >= SEND_INTERVAL_MS) {
        publishVitals();
        lastSendMs = millis();
    }
}
```

## Lỗi phổ biến v3 và cách sửa

| Lỗi | Nguyên nhân | Cách sửa |
|---|---|---|
| ECG = 0 liên tục | Điện cực bị rời (LO+ hoặc LO- = HIGH) | Kiểm tra dây điện cực, dán lại |
| ECG nhiều nhiễu | Thiếu tụ lọc / ánh sáng | Thêm tụ 100nF OUTPUT→GND |
| ADC chỉ đọc được ~3.3V | Dùng ADC2 thay ADC1 | Đổi sang GPIO 11-39 (ADC1) |
| SPIFFS mount failed | Flash chưa format | Gọi SPIFFS.format() một lần |
| Z-score luôn = 0 | Chưa đủ 10 mẫu trong window | Đợi ~50 giây để window tích lũy |
| HR = 0 liên tục | Ngón tay không phủ kín | Che kín cảm biến, ấn nhẹ |
| Temp = -127 | Thiếu điện trở 4.7kΩ | Thêm pull-up DQ→3.3V |
