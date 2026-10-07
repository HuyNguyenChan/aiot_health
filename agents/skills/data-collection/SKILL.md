---
name: data-collection
description: Use this skill to collect, label, and manage health sensor data for AI training v3. Handles CSV collection from MQTT (now including ECG samples and subject_id), multi-person data collection strategy, dataset augmentation (5x without extra measurement), LOSO cross-validation split, and exporting to Google Colab. Trigger when user says 'thu thập dữ liệu', 'dataset', 'gán nhãn dữ liệu', 'CSV', 'chuẩn bị AI', 'dữ liệu train', 'augmentation', 'nhiều người', or 'subject'.
---

# Data Collection Skill v3 – AIoT Health Monitor

## Chiến lược thu thập v3: ĐA NGƯỜI (quan trọng nhất!)

> **Vấn đề v2:** Dataset từ 1 người → model bị overfit vào sinh lý riêng.
> Hội đồng hỏi: "Model có hoạt động với người khác không?" → không đảm bảo.
> **Giải pháp v3:** Thu thêm từ 2-4 người, gán `subject_id` riêng.

### Kế hoạch thu thập (mỗi người ~30-45 phút)

| Trạng thái | Nhãn | Số mẫu/người | Cách thực hiện |
|---|---|---|---|
| Ngồi nghỉ yên | `normal_rest` | 60 | Ngồi yên 5 phút trước, đo 5 phút |
| Đi bộ nhẹ | `normal_light` | 30 | Đi lại trong phòng |
| Vận động vừa | `normal_moderate` | 30 | Leo cầu thang / đi bộ nhanh |
| Sau ăn no | `normal_postmeal` | 20 | 30 phút sau bữa ăn |
| Buổi sáng | `normal_morning` | 20 | Ngay sau khi thức dậy |
| Nhịp tim cao | `anomaly_high_hr` | 10 | Chạy nhanh 2 phút → đo ngay |
| SpO2 thấp nhẹ | `anomaly_low_spo2` | 10 | Nín thở 10-15s (an toàn) |
| Giả lập ngã | `fall` | 10 | Lắc mạnh thiết bị đột ngột |

**Mục tiêu:** 3-5 người × ~190 mẫu/người = **570-950 mẫu gốc**
Sau augmentation 5x → **2850-4750 mẫu** cho train AI

---

## Script thu thập v3 (data/collect_labeled.py)

```python
"""
Script thu thập dữ liệu có nhãn từ MQTT — Version 3
Mới: thêm subject_id, ECG fields, session tracking
"""
import paho.mqtt.client as mqtt
import csv, json, ssl, os, time
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

LABELS = [
    "normal_rest", "normal_light", "normal_moderate",
    "normal_postmeal", "normal_morning",
    "anomaly_high_hr", "anomaly_low_spo2", "fall"
]

OUTPUT  = "data/raw/labeled_health_data.csv"
# MỚI v3: thêm subject_id và ecg_std (đặc trưng ECG thô)
HEADERS = ["timestamp","subject_id","device_id",
           "heart_rate","spo2","temperature",
           "accel_x","accel_y","accel_z","accel_mag",
           "fall_detect","ecg_mean","ecg_std","ecg_ok",
           "label","session"]

# Chọn subject (người đo)
print("\n👤 Nhập tên/mã người đo (vd: person_01, nguyen_van_a):")
subject_id = input("Subject ID: ").strip() or "person_01"

# Chọn nhãn
print("\nChọn nhãn cho dữ liệu:")
for i, l in enumerate(LABELS):
    print(f"  {i+1}. {l}")
choice = int(input("Nhập số: ")) - 1
current_label = LABELS[choice]
session_id    = f"{subject_id}_{datetime.now().strftime('%Y%m%d_%H%M')}"

print(f"\n📡 Subject: {subject_id}")
print(f"📌 Nhãn: {current_label}")
print(f"🔑 Session: {session_id}")
print("Ctrl+C để dừng...\n")

count = 0
def on_message(client, userdata, msg):
    global count
    data = json.loads(msg.payload.decode())
    count += 1

    # Tính accel_mag từ 3 trục
    ax, ay, az = data.get("accel_x",0), data.get("accel_y",0), data.get("accel_z",0)
    mag = (ax**2 + ay**2 + az**2)**0.5

    # ECG thô (nếu có trong message) — chỉ lấy mean và std để CSV nhỏ gọn
    ecg_samples = data.get("ecg_samples", [])
    ecg_mean = sum(ecg_samples)/len(ecg_samples) if ecg_samples else 0
    ecg_std  = (sum((x-ecg_mean)**2 for x in ecg_samples)/len(ecg_samples))**0.5 if ecg_samples else 0

    row = [
        datetime.now().isoformat(), subject_id, data.get("device_id",""),
        data.get("heart_rate",0), data.get("spo2",0), data.get("temperature",0),
        round(ax,3), round(ay,3), round(az,3), round(mag,3),
        data.get("fall_detect",False),
        round(ecg_mean,1), round(ecg_std,1), data.get("ecg_ok",True),
        current_label, session_id
    ]

    with open(OUTPUT, "a", newline="") as f:
        csv.writer(f).writerow(row)

    print(f"[{count:4d}] {subject_id} | "
          f"HR:{row[3]:3.0f} SpO2:{row[4]:3.0f}% Temp:{row[5]:.1f}°C "
          f"ECG_ok:{row[13]} → {current_label}")

# Tạo file với header nếu chưa có
if not os.path.exists(OUTPUT):
    os.makedirs("data/raw", exist_ok=True)
    with open(OUTPUT, "w", newline="") as f:
        csv.writer(f).writerow(HEADERS)

client = mqtt.Client()
client.username_pw_set(os.getenv("MQTT_USERNAME"), os.getenv("MQTT_PASSWORD"))
client.tls_set(tls_version=ssl.PROTOCOL_TLS)
client.on_message = on_message
client.connect(os.getenv("MQTT_BROKER"), int(os.getenv("MQTT_PORT", 8883)))
client.subscribe("health/+/data")
client.loop_forever()
```

---

## Script phân tích dataset (data/analyze_dataset.py)

```python
import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv("data/raw/labeled_health_data.csv")

print("=== THỐNG KÊ DATASET v3 ===")
print(f"Tổng mẫu:      {len(df)}")
print(f"Số subjects:   {df['subject_id'].nunique()} — {list(df['subject_id'].unique())}")
print(f"\nPhân bố nhãn:\n{df['label'].value_counts()}")
print(f"\nPhân bố theo người:\n{df.groupby('subject_id')['label'].count()}")

# Cảnh báo nếu 1 người chiếm quá nhiều
for s in df['subject_id'].unique():
    pct = len(df[df['subject_id']==s]) / len(df) * 100
    status = "⚠️  Có thể bị bias" if pct > 70 else "✅"
    print(f"  {s}: {pct:.0f}% {status}")
```

---

## Tiền xử lý v3 (notebook 01_preprocess.ipynb)

```python
# Cell quan trọng: thêm feature engineering cho ECG và rolling window

df = pd.read_csv("data/raw/labeled_health_data.csv")

# Tính rolling features (cần sort theo subject + session + time)
df = df.sort_values(['subject_id', 'session', 'timestamp'])

# Rolling window trong từng session riêng
df['hr_rolling_mean'] = df.groupby(['subject_id','session'])['heart_rate'] \
                          .transform(lambda x: x.rolling(5, min_periods=1).mean())
df['hr_rolling_std']  = df.groupby(['subject_id','session'])['heart_rate'] \
                          .transform(lambda x: x.rolling(5, min_periods=1).std().fillna(0))
df['spo2_change']     = df.groupby(['subject_id','session'])['spo2'] \
                          .transform(lambda x: x.diff().fillna(0))

# Normalize PER SUBJECT — mỗi người có baseline riêng
from sklearn.preprocessing import MinMaxScaler
FEATURES = ['heart_rate','spo2','temperature','hr_rolling_mean','hr_rolling_std','spo2_change','accel_mag']

df_clean = df.dropna(subset=FEATURES).copy()
scaler_global = MinMaxScaler()
df_clean[FEATURES] = scaler_global.fit_transform(df_clean[FEATURES])

import joblib
joblib.dump(scaler_global, "models/scaler.pkl")
df_clean.to_csv("data/processed/health_data_clean.csv", index=False)
print(f"Đã lưu {len(df_clean)} mẫu sạch từ {df_clean['subject_id'].nunique()} subjects")
```
