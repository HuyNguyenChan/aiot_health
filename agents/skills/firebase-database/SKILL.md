---
name: firebase-database
description: Use this skill to read, write, or structure data in Firebase Realtime Database v3 — now includes ECG latest data storage, per-patient model metadata, and report history. Trigger when user says 'lưu Firebase', 'đọc Firebase', 'cấu trúc database', 'firebase_handler', or 'Realtime Database'.
---

# Firebase Database Skill v3 – AIoT Health Monitor

## File: server/firebase_handler.py (v3)

```python
import firebase_admin
from firebase_admin import credentials, db
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

load_dotenv()

if not firebase_admin._apps:
    cred = credentials.Certificate(os.getenv("FIREBASE_KEY_PATH","firebase_key.json"))
    firebase_admin.initialize_app(cred, {
        "databaseURL": os.getenv("FIREBASE_DATABASE_URL")
    })

# ── Lưu vitals (giữ nguyên từ v2) ─────────────────
def save_to_firebase(device_id: str, data: dict):
    now      = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H%M%S")

    # Lịch sử
    db.reference(f"patients/{device_id}/history/{date_str}/{time_str}").set({
        "heart_rate":    data.get("heart_rate", 0),
        "spo2":          data.get("spo2", 0),
        "temperature":   data.get("temperature", 0),
        "accel_x":       data.get("accel_x", 0),
        "accel_y":       data.get("accel_y", 0),
        "accel_z":       data.get("accel_z", 0),
        "fall_detect":   data.get("fall", False),
        "anomaly_score": data.get("anomaly_score", 0),
        "alert_reason":  data.get("alert_reason", ""),
        "ecg_ok":        data.get("ecg_ok", True),   # MỚI v3
        "timestamp":     now.isoformat()
    })

    # Latest (cho dashboard realtime)
    db.reference(f"patients/{device_id}/latest").set({
        **{k: data.get(k) for k in
           ["heart_rate","spo2","temperature","fall","anomaly_score","alert_reason","ecg_ok"]},
        "updated_at": now.isoformat()
    })

# ── MỚI v3: Lưu ECG ───────────────────────────────
def save_ecg_to_firebase(device_id: str, data: dict):
    db.reference(f"patients/{device_id}/ecg_latest").set({
        "samples":  data.get("samples", []),
        "anomaly":  data.get("ecg_anomaly", False),
        "ts":       data.get("ts", ""),
        "updated":  datetime.now().isoformat()
    })

def get_latest_ecg(device_id: str) -> dict:
    return db.reference(f"patients/{device_id}/ecg_latest").get() or {}

# ── Get functions ──────────────────────────────────
def get_latest(device_id: str) -> dict:
    return db.reference(f"patients/{device_id}/latest").get() or {}

def get_history(device_id: str, days: int = 7) -> list:
    results = []
    for i in range(days):
        date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        day_data = db.reference(f"patients/{device_id}/history/{date}").get()
        if day_data:
            for time_key, rec in day_data.items():
                rec["date"] = date; rec["time"] = time_key
                results.append(rec)
    return sorted(results, key=lambda x: x.get("timestamp",""), reverse=True)

def save_alert(device_id: str, data: dict, reason: str, confidence: float = 1.0):
    now    = datetime.now()
    ref    = db.reference(f"patients/{device_id}/alerts")
    alerts = ref.get() or []
    alerts.insert(0, {
        "time":       now.isoformat(),
        "reason":     reason,
        "confidence": confidence,   # MỚI v3: ensemble confidence
        "heart_rate": data.get("heart_rate"),
        "spo2":       data.get("spo2"),
        "temperature":data.get("temperature"),
        "ecg_ok":     data.get("ecg_ok", True),
        "level":      _classify_severity(data, reason)
    })
    ref.set(alerts[:50])

def get_alerts(device_id: str, limit: int = 20) -> list:
    return (db.reference(f"patients/{device_id}/alerts").get() or [])[:limit]

def get_all_patients() -> list:
    data = db.reference("patients").get() or {}
    return [{"id": k, **v.get("info", {}), "latest": v.get("latest", {})}
            for k, v in data.items()]

def _classify_severity(data: dict, reason: str) -> str:
    spo2 = data.get("spo2", 100)
    hr   = data.get("heart_rate", 70)
    if spo2 < 88 or hr > 160 or hr < 35 or "NGÃ" in reason.upper():
        return "CRITICAL"
    elif spo2 < 93 or hr > 130 or hr < 50:
        return "HIGH"
    return "MEDIUM"
```

## Cấu trúc JSON Firebase v3

```json
{
  "patients": {
    "patient_001": {
      "info": { "name": "Nguyen Van A", "age": 65 },
      "latest": {
        "heart_rate": 75, "spo2": 98, "temperature": 36.8,
        "fall": false, "anomaly_score": 0.12,
        "ecg_ok": true, "updated_at": "2024-01-15T14:35:22"
      },
      "ecg_latest": {
        "samples": [1024, 1056, 1203, "...250 giá trị ADC"],
        "anomaly": false,
        "ts": "2024-01-15T14:35:20"
      },
      "history": {
        "2024-01-15": {
          "143500": {
            "heart_rate": 75, "spo2": 98, "temperature": 36.8,
            "anomaly_score": 0.12, "ecg_ok": true,
            "timestamp": "2024-01-15T14:35:00"
          }
        }
      },
      "alerts": [
        {
          "time": "2024-01-15T14:30:00",
          "reason": "Isolation Forest pattern + ECG bất thường",
          "confidence": 0.67,
          "heart_rate": 142, "spo2": 94, "level": "HIGH"
        }
      ]
    }
  }
}
```
