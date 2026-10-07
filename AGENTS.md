# AGENTS.md — Hướng dẫn cho OpenAI Codex
# ĐỌC FILE NÀY TRƯỚC KHI LÀM BẤT KỲ TASK NÀO

## Tổng quan project
Dự án AIoT theo dõi sức khỏe thời gian thực .
ESP32-S3 thu thập HR, SpO2, nhiệt độ, gia tốc → WiFi/MQTT → Python server
→ AI phát hiện bất thường → Firebase → Streamlit dashboard + Telegram.

## Tech Stack
- Firmware:   C++ Arduino trên ESP32, build bằng PlatformIO
- Protocol:   MQTT over TLS (HiveMQ Cloud, port 8883)
- Backend:    Python 3.11, Flask, paho-mqtt, firebase-admin
- AI/ML:      scikit-learn (Isolation Forest), TensorFlow/Keras (LSTM)
- Database:   Firebase Realtime Database
- Dashboard:  Streamlit + Plotly
- Alerts:     Telegram Bot API

## Cấu trúc thư mục
aiot_health/
├── AGENTS.md                    ← file này
├── .env                         ← credentials (KHÔNG commit)
├── .gitignore
├── esp32_firmware/
│   ├── platformio.ini
│   ├── src/main.cpp
│   └── include/
│       ├── config.h             ← hằng số, GPIO, thresholds
│       ├── secrets.h            ← WiFi/MQTT pass (KHÔNG commit)
│       ├── button_handler.h
│       ├── menu_system.h
│       └── medicine.h
├── server/
│   ├── app.py                   ← Flask API entry point
│   ├── mqtt_handler.py
│   ├── firebase_handler.py
│   ├── ai_engine.py
│   ├── alert_bot.py
│   ├── medicine_manager.py
│   └── requirements.txt
├── dashboard/
│   └── streamlit_app.py
├── ai_training/notebooks/
├── data/{raw,processed}/
├── models/
└── agents/skills/               ← Skills cho Codex

## Quy tắc bắt buộc — Firmware C++
- Framework: Arduino qua PlatformIO (KHÔNG dùng Arduino IDE)
- Mọi config: esp32_firmware/platformio.ini
- Secrets: include/secrets.h (KHÔNG commit, đã có trong .gitignore)
- Board mục tiêu hiện tại: ESP32-S3 DevKitC-1
- I2C Bus: SDA=GPIO8, SCL=GPIO9 (MAX30102 + MPU6050 + OLED cùng bus)
- DS18B20: GPIO4, PHẢI có điện trở pull-up 4.7kΩ giữa DQ và 3.3V
- Nút nhấn: GPIO5=SOS | GPIO6=Menu | GPIO7=OK (INPUT_PULLUP, nhấn=LOW)
- Buzzer: GPIO16 (tone/noTone) | LED_ERR: GPIO17 | LED_OK: GPIO18
- Serial baud: 115200
- MQTT TLS port: 8883, dùng WiFiClientSecure với setInsecure() cho dev

## Quy tắc bắt buộc — Python
- Virtual env: .venv/ (chạy source .venv/bin/activate trước)
- Biến môi trường: load từ .env bằng python-dotenv
- KHÔNG hardcode bất kỳ credential nào trong source code
- Firebase key path: server/firebase_key.json

## JSON format từ ESP32 → MQTT
{
  "device_id":   "patient_001",
  "ts":          1705300000,
  "heart_rate":  75,
  "spo2":        98,
  "temperature": 36.8,
  "accel_x":     0.01,
  "accel_y":    -0.02,
  "accel_z":     0.98,
  "fall":        false,
  "edge_alert":  false,
  "alert_reason": ""
}

## MQTT Topics
- Data publish:    health/{device_id}/data
- Alert subscribe: health/{device_id}/alert
- Medicine:        health/{device_id}/medicine
- Command:         health/{device_id}/cmd

## Ngưỡng cảnh báo (Edge AI trên ESP32)
- HR cao:  > 150 bpm   | HR thấp: < 40 bpm
- SpO2:    < 92%       | Sốt: > 38.5°C
- Ngã:     sqrt(ax²+ay²+az²)/16384 > 2.5 hoặc < 0.3

## Lệnh build/run
pio run                                        # build firmware
pio run --target upload                        # upload lên ESP32
pio run --target upload --target monitor       # upload + serial monitor
pio device monitor --filter colorize           # chỉ monitor
cd server && python app.py                     # chạy server
streamlit run dashboard/streamlit_app.py       # chạy dashboard
