---
name: platformio
description: Use this skill for everything related to PlatformIO — setting up the project, configuring platformio.ini (including SPIFFS partition for offline buffer and new AD8232 ECG sensor), managing libraries, building and uploading firmware to ESP32, serial monitoring, and debugging. Trigger when user says 'PlatformIO', 'pio', 'platformio.ini', 'build', 'upload', 'lib_deps', 'monitor', 'cấu hình PlatformIO', or 'nạp code PlatformIO'.
---

# PlatformIO Skill v3 – AIoT Health Monitor

## File: platformio.ini (v3 — thêm thư viện ECG + SPIFFS)

```ini
[env:esp32-s3]
platform  = espressif32
board     = esp32-s3-devkitc-1
framework = arduino

; ─── Cổng upload & monitor ──────────────────────
monitor_speed = 115200
upload_speed  = 921600

; ─── Thư viện (v3 — thêm SPIFFS) ────────────────
lib_deps =
    sparkfun/SparkFun MAX3010x Pulse and Proximity Sensor Library @ ^1.1.2
    milesburton/DallasTemperature @ ^3.11.0
    paulstoffregen/OneWire @ ^2.3.7
    electroniccats/MPU6050 @ ^1.3.0
    adafruit/Adafruit SSD1306 @ ^2.5.7
    adafruit/Adafruit GFX Library @ ^1.11.9
    knolleary/PubSubClient @ ^2.8
    bblanchon/ArduinoJson @ ^7.0.4
    ; AD8232 dùng ADC trực tiếp, không cần thư viện riêng

; ─── Build flags ─────────────────────────────────
build_flags =
    -DCORE_DEBUG_LEVEL=1
    -DBOARD_HAS_PSRAM
    -DESP32S3
    -DARDUINO_USB_MODE=1
    -DMQTT_MAX_PACKET_SIZE=512

; ─── Partition: dành 1MB cho SPIFFS (offline buffer) ─
; Partition này cấp 1MB SPIFFS để lưu data khi mất WiFi
board_build.partitions = default_8MB.csv
; Hoặc tạo custom partition nếu cần nhiều hơn:
; board_build.partitions = custom_partitions.csv

build_type = release
```

## File: include/config.h (v3 — thêm ECG + adaptive threshold)

```cpp
#pragma once
#include "secrets.h"  // WIFI + MQTT credentials (không commit Git)

// ─── MQTT ───────────────────────────────────────────
#define MQTT_CLIENT    "esp32_patient_001"
#define MQTT_QOS       1
#define MQTT_KEEPALIVE 60

// ─── Topics ─────────────────────────────────────────
#define DEVICE_ID          "patient_001"
#define TOPIC_DATA         "health/" DEVICE_ID "/data"
#define TOPIC_ALERT_IN     "health/" DEVICE_ID "/alert"
#define TOPIC_CMD          "health/" DEVICE_ID "/cmd"
#define TOPIC_ECG          "health/" DEVICE_ID "/ecg"  // MỚI v3

// ─── Chân GPIO — cũ ──────────────────────────────
#define PIN_DS18B20    4   // GPIO4 – 1-Wire, safe on ESP32-S3
#define PIN_BUZZER     15
#define PIN_LED_OK     2
#define PIN_LED_ERR    5

// ─── Chân GPIO — ECG AD8232 MỚI v3 ──────────────
#define ECG_OUTPUT_PIN   1   // ADC1_CH0 (ESP32-S3: GPIO1-10) — tín hiệu ECG analog
#define ECG_LO_PLUS      11   // Lead-off detection +
#define ECG_LO_MINUS     12   // Lead-off detection -
// LƯU Ý: Dùng ADC1 (GPIO 11-39), KHÔNG dùng ADC2 khi WiFi bật

// ─── Ngưỡng cảnh báo cứng (emergency fallback) ───
// Adaptive threshold sẽ dùng Z-score; các giá trị này
// chỉ là hard stop cho tình huống cực đoan
#define ALERT_HR_HARD_HIGH  160   // bpm — ngưỡng tuyệt đối
#define ALERT_HR_HARD_LOW    35   // bpm — ngưỡng tuyệt đối
#define ALERT_SPO2_HARD_LOW  88   // % — ngưỡng tuyệt đối
#define ALERT_TEMP_HIGH    38.5f  // °C
#define ALERT_FALL_MAG      2.5f  // g

// ─── Adaptive threshold (Z-score rolling window) ─
#define ADAPTIVE_WINDOW     120   // 120 mẫu × 5s = 10 phút
#define ADAPTIVE_Z_THRESH   2.5f  // Z-score > 2.5 = bất thường

// ─── Cấu hình đo ─────────────────────────────────
#define SEND_INTERVAL_MS   5000   // Gửi MQTT mỗi 5 giây
#define DISPLAY_INTERVAL   1000   // Cập nhật OLED mỗi 1 giây
#define ECG_SAMPLES         250   // Số mẫu ECG mỗi lần đọc
#define ECG_SAMPLE_MS        20   // 50Hz sampling = 20ms/mẫu
#define SAMPLE_AVG            4   // Oversampling ADC

// ─── SPIFFS offline buffer ────────────────────────
#define SPIFFS_BUFFER_FILE  "/buffer.jsonl"
#define SPIFFS_MAX_KB        500  // Giới hạn buffer 500KB
```

## File: include/secrets.h (KHÔNG commit lên GitHub)

```cpp
#pragma once
#define WIFI_SSID       "Ten_WiFi_thuc"
#define WIFI_PASSWORD   "Mat_khau_thuc"
#define MQTT_BROKER     "xxxx.s2.eu.hivemq.cloud"
#define MQTT_PORT       8883
#define MQTT_USER       "hivemq_username"
#define MQTT_PASS       "hivemq_password"
```

## Lệnh PlatformIO thường dùng

```bash
# Build & Upload
pio run                           # Chỉ build kiểm tra lỗi
pio run --target upload           # Build + nạp code
pio run --target upload --target monitor  # Upload + mở Serial Monitor

# Serial Monitor đẹp hơn
pio device monitor --baud 115200 --filter colorize

# SPIFFS — upload file lên flash (nếu cần)
pio run --target uploadfs

# Quản lý
pio device list                   # Liệt kê cổng COM
pio run --target clean            # Xóa build cache
pio run --target erase            # Xóa toàn bộ flash

# VS Code shortcuts
# Ctrl+Alt+B  → Build
# Ctrl+Alt+U  → Upload
# Ctrl+Alt+M  → Serial Monitor
```

## .gitignore cho PlatformIO

```gitignore
.pio/
.vscode/.browse.c_cpp.db*
.vscode/c_cpp_properties.json
include/secrets.h
.env
*.pkl
*.h5
*.npy
data/raw/
models/
reports/
```
