---
name: project-setup
description: Use this skill to set up the upgraded AIoT health monitoring project v3 from scratch — installing all dependencies (including new ones for ECG, augmentation, PDF reports, APScheduler), creating folder structure, configuring environment variables, and initializing Firebase + HiveMQ connections. Trigger when user says 'setup project', 'khởi tạo dự án', 'cài đặt môi trường', 'bắt đầu dự án', or 'cấu hình lại project'.
---

# AIoT Health Monitor v3 – Project Setup Skill

## Cấu trúc thư mục đầy đủ (có thêm ECG + Reports)

```bash
mkdir -p aiot_health/{esp32_firmware/src,esp32_firmware/include,server,dashboard,ai_training/notebooks,data/raw,data/processed,models,reports}
cd aiot_health
touch requirements.txt .env .gitignore README.md
```

## File: requirements.txt (v3 — bổ sung mới)

```txt
# Backend & API
flask==3.0.0
flask-cors==4.0.0

# MQTT
paho-mqtt==2.0.0

# Firebase
firebase-admin==6.4.0

# AI/ML — CŨ
scikit-learn==1.4.0
tensorflow==2.15.0
pandas==2.1.0
numpy==1.26.0
joblib==1.3.0
imbalanced-learn==0.11.0

# AI/ML — MỚI v3
wfdb==4.1.2                 # Đọc dataset PhysioNet MIT-BIH cho ECG
scipy==1.12.0               # Bandpass filter tín hiệu ECG

# Scheduling — MỚI v3
APScheduler==3.10.4         # Auto-retrain model mỗi ngày lúc 2AM

# PDF Report — MỚI v3
reportlab==4.1.0            # Tạo báo cáo PDF hàng ngày

# Dashboard
streamlit==1.31.0
plotly==5.18.0

# Telegram Bot
python-telegram-bot==20.7

# Utilities
python-dotenv==1.0.0
requests==2.31.0
```

```bash
pip install -r requirements.txt
```

## File: .env (cập nhật)

```env
# WiFi
WIFI_SSID=Ten_WiFi_cua_ban
WIFI_PASSWORD=Mat_khau_WiFi

# HiveMQ Cloud
MQTT_BROKER=xxxx.s2.eu.hivemq.cloud
MQTT_PORT=8883
MQTT_USERNAME=hivemq_username
MQTT_PASSWORD=hivemq_password

# Firebase
FIREBASE_DATABASE_URL=https://aiot-health-default-rtdb.firebaseio.com
FIREBASE_KEY_PATH=firebase_key.json

# Telegram
TELEGRAM_BOT_TOKEN=xxxx:yyyy
TELEGRAM_CHAT_ID=123456789

# Flask
FLASK_PORT=5000
FLASK_DEBUG=True

# AI Config — MỚI v3
ECG_MODEL_PATH=models/ecg_autoencoder.h5
ECG_THRESHOLD_PATH=models/ecg_threshold.npy
RETRAIN_HOUR=2              # Giờ auto-retrain (2 = 2AM)
REPORT_HOUR=20              # Giờ gửi báo cáo hàng ngày
```

## Cấu trúc thư mục hoàn chỉnh v3

```
aiot_health/
├── .agent/skills/              ← Antigravity Skills v3
│   ├── project-setup/
│   ├── platformio/
│   ├── esp32-firmware/
│   ├── ecg-sensor/             ← MỚI: skill riêng cho AD8232
│   ├── ai-engine/
│   ├── data-collection/
│   ├── mqtt-backend/
│   ├── firebase-database/
│   ├── streamlit-dashboard/
│   └── telegram-alerts/
├── esp32_firmware/
│   ├── src/main.cpp
│   └── include/
│       ├── config.h
│       ├── secrets.h           ← KHÔNG commit
│       └── offline_buffer.h    ← MỚI: store-and-forward
├── server/
│   ├── app.py
│   ├── mqtt_handler.py
│   ├── firebase_handler.py
│   ├── ai_engine.py            ← Nâng cấp: ensemble 3 model
│   ├── alert_bot.py
│   └── report_generator.py     ← MỚI: tạo PDF báo cáo
├── dashboard/
│   └── streamlit_app.py        ← Thêm ECG chart + tab báo cáo
├── ai_training/notebooks/
│   ├── 01_preprocess.ipynb
│   ├── 01b_augmentation.ipynb  ← MỚI: data augmentation 5x
│   ├── 02_train_isolation_forest.ipynb
│   ├── 03_train_lstm.ipynb
│   └── 04_ecg_autoencoder.ipynb ← MỚI: Conv1D AE trên MIT-BIH
├── data/raw/
├── data/processed/
├── models/
│   ├── isolation_forest.pkl        ← per-patient: {id}_if.pkl
│   ├── scaler.pkl                  ← per-patient: {id}_scaler.pkl
│   ├── lstm_heart_predict.h5
│   ├── ecg_autoencoder.h5          ← MỚI
│   └── ecg_threshold.npy           ← MỚI
├── reports/                        ← MỚI: PDF báo cáo ngày
├── .env
├── requirements.txt
└── README.md
```

## Kiểm tra cài đặt

```bash
python -c "
import flask, paho.mqtt.client, firebase_admin
import sklearn, tensorflow, streamlit
import wfdb, scipy, reportlab, apscheduler
print('✅ Tất cả packages v3 OK!')
"
```
