---
name: mqtt-backend
description: Use this skill to build or debug the Python Flask backend server v3 — subscribes to MQTT vitals AND ECG topics, runs Ensemble AI (3 models), triggers per-patient model retrain, exposes REST API including ECG endpoint, and generates daily PDF reports. Trigger when user says 'viết server', 'Flask API', 'MQTT subscriber', 'nhận dữ liệu từ ESP32', 'backend', 'REST API', 'ECG API', or 'retrain'.
---

# MQTT Backend Skill v3 – AIoT Health Monitor

## File: server/mqtt_handler.py (v3)

```python
import paho.mqtt.client as mqtt
import json, ssl, os
from dotenv import load_dotenv
from firebase_handler import save_to_firebase, save_ecg_to_firebase
from ai_engine import AIEngine
from alert_bot import send_alert, send_fall_alert

load_dotenv()

BROKER   = os.getenv("MQTT_BROKER")
PORT     = int(os.getenv("MQTT_PORT", 8883))
USERNAME = os.getenv("MQTT_USERNAME")
PASSWORD = os.getenv("MQTT_PASSWORD")

ai = AIEngine()

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        # Subscribe 2 topics: vitals và ECG riêng
        client.subscribe("health/+/data", qos=1)   # vitals
        client.subscribe("health/+/ecg",  qos=0)   # ECG (QoS 0 = nhanh hơn)
        print(f"[MQTT] Kết nối OK, đang lắng nghe vitals + ECG")
    else:
        print(f"[MQTT] Lỗi kết nối: {rc}")

def on_message(client, userdata, msg):
    try:
        data = json.loads(msg.payload.decode("utf-8"))
        device_id = data.get("device_id", "unknown")
        topic = msg.topic

        # ── Xử lý ECG topic riêng ──────────────────
        if topic.endswith("/ecg"):
            save_ecg_to_firebase(device_id, data)
            return

        # ── Xử lý vitals ───────────────────────────
        print(f"[DATA] {device_id} | HR:{data.get('heart_rate')} "
              f"SpO2:{data.get('spo2')} Temp:{data.get('temperature'):.1f} "
              f"Score:{data.get('anomaly_score',0):.2f}")

        # 1. Lưu Firebase
        save_to_firebase(device_id, data)

        # 2. Ensemble AI (Rule + IF + ECG)
        is_anomaly, reason, confidence = ai.detect_anomaly(data)

        # 3. Cảnh báo nếu ensemble đồng ý
        if is_anomaly:
            print(f"[ALERT] {device_id}: {reason} (confidence={confidence:.0%})")
            send_alert(device_id, data, reason, confidence)

        # 4. Xử lý ngã ngay lập tức (ưu tiên cao nhất)
        if data.get("fall") or data.get("fall_detect"):
            send_fall_alert(device_id, data)

        # 5. Trigger retrain nếu đủ dữ liệu mới (~mỗi 500 bản ghi)
        _maybe_retrain(device_id)

    except Exception as e:
        print(f"[ERROR] on_message: {e}")

# Đếm số bản ghi — trigger retrain mỗi 500
_record_count = {}
def _maybe_retrain(device_id):
    _record_count[device_id] = _record_count.get(device_id, 0) + 1
    if _record_count[device_id] % 500 == 0:
        print(f"[RETRAIN] Trigger retrain cho {device_id}")
        from firebase_handler import get_history
        history = get_history(device_id, days=7)
        ai.retrain_patient(device_id, history)

def on_disconnect(client, userdata, rc):
    print(f"[MQTT] Mất kết nối (rc={rc}), tự reconnect...")

def start_mqtt():
    client = mqtt.Client(client_id="aiot_server_v3", protocol=mqtt.MQTTv311)
    client.username_pw_set(USERNAME, PASSWORD)
    client.tls_set(tls_version=ssl.PROTOCOL_TLS)
    client.on_connect    = on_connect
    client.on_message    = on_message
    client.on_disconnect = on_disconnect
    client.connect(BROKER, PORT, keepalive=60)
    print(f"[MQTT] Đang kết nối {BROKER}:{PORT}")
    client.loop_forever()
```

---

## File: server/app.py (v3 — thêm ECG endpoint + PDF report)

```python
from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
from firebase_handler import (get_latest, get_history, get_alerts,
                               get_all_patients, get_latest_ecg)
from ai_engine import AIEngine
from report_generator import generate_daily_report
import threading
from mqtt_handler import start_mqtt

app = Flask(__name__)
CORS(app)
ai = AIEngine()

# ── Endpoints cũ (giữ nguyên) ─────────────────────

@app.route("/api/health/status")
def status():
    return jsonify({"status": "ok", "version": "3.0.0"})

@app.route("/api/patients")
def patients():
    return jsonify(get_all_patients())

@app.route("/api/health/<device_id>/latest")
def latest(device_id):
    data = get_latest(device_id)
    return jsonify(data) if data else (jsonify({"error":"Not found"}), 404)

@app.route("/api/health/<device_id>/history")
def history(device_id):
    days = request.args.get("days", 7, type=int)
    return jsonify(get_history(device_id, days))

@app.route("/api/alerts/<device_id>")
def alerts(device_id):
    limit = request.args.get("limit", 20, type=int)
    return jsonify(get_alerts(device_id, limit))

@app.route("/api/predict/<device_id>")
def predict(device_id):
    hist = get_history(device_id, days=1)
    if not hist:
        return jsonify({"error":"Chưa đủ dữ liệu"}), 400
    return jsonify({"predictions": ai.predict_trend(hist)})

# ── Endpoints mới v3 ──────────────────────────────

@app.route("/api/health/<device_id>/ecg_latest")
def ecg_latest(device_id):
    """Lấy ECG mới nhất để hiển thị waveform trên dashboard"""
    data = get_latest_ecg(device_id)
    return jsonify(data) if data else (jsonify({"samples":[], "anomaly":False}), 200)

@app.route("/api/retrain/<device_id>", methods=["POST"])
def retrain(device_id):
    """Trigger retrain thủ công cho 1 bệnh nhân"""
    hist = get_history(device_id, days=7)
    ok   = ai.retrain_patient(device_id, hist)
    return jsonify({"success": ok, "samples": len(hist)})

@app.route("/api/report/<device_id>")
def get_report(device_id):
    """Tạo và download báo cáo PDF ngày hôm nay"""
    date = request.args.get("date", None)
    try:
        path = generate_daily_report(device_id, date)
        return send_file(path, as_attachment=True,
                         download_name=f"report_{device_id}.pdf")
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ── Khởi động ────────────────────────────────────
if __name__ == "__main__":
    t = threading.Thread(target=start_mqtt, daemon=True)
    t.start()
    print("[SERVER] AIoT Health Monitor v3 khởi động")
    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)
```

---

## File: server/report_generator.py (MỚI v3)

```python
"""
Tự động tạo báo cáo PDF hàng ngày.
Gọi từ: (1) app.py endpoint, (2) Telegram bot daily job
"""
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer,
                                 Table, TableStyle)
import datetime, os

def generate_daily_report(device_id: str, date: str = None) -> str:
    if not date:
        date = datetime.date.today().isoformat()

    from firebase_handler import get_history, get_alerts
    history = get_history(device_id, days=1)
    alerts  = get_alerts(device_id, limit=50)

    os.makedirs("reports", exist_ok=True)
    filename = f"reports/{device_id}_{date}.pdf"

    doc    = SimpleDocTemplate(filename, pagesize=A4)
    styles = getSampleStyleSheet()
    story  = []

    # Tiêu đề
    story.append(Paragraph(f"Báo cáo Sức khỏe Ngày {date}", styles['Title']))
    story.append(Paragraph(f"Bệnh nhân: {device_id}", styles['Normal']))
    story.append(Spacer(1, 12))

    if history:
        import pandas as pd
        df = pd.DataFrame(history)

        # Bảng thống kê
        story.append(Paragraph("Thống kê chỉ số sức khỏe", styles['Heading2']))
        stats_data = [["Chỉ số", "Trung bình", "Thấp nhất", "Cao nhất"]]
        for col, lbl in [("heart_rate","Nhịp tim (bpm)"),
                         ("spo2","SpO₂ (%)"),
                         ("temperature","Nhiệt độ (°C)")]:
            if col in df.columns:
                stats_data.append([
                    lbl,
                    f"{df[col].mean():.1f}",
                    f"{df[col].min():.1f}",
                    f"{df[col].max():.1f}"
                ])
        t = Table(stats_data, colWidths=[200, 100, 100, 100])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.darkblue),
            ('TEXTCOLOR',  (0,0), (-1,0), colors.white),
            ('FONTNAME',   (0,0), (-1,0), 'Helvetica-Bold'),
            ('GRID',       (0,0), (-1,-1), 0.5, colors.grey),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.lightgrey]),
        ]))
        story.append(t)
        story.append(Spacer(1, 12))

    # Bảng cảnh báo
    story.append(Paragraph(f"Cảnh báo ({len(alerts)} lần)", styles['Heading2']))
    if alerts:
        alert_data = [["Thời gian", "Lý do", "HR", "SpO₂", "Mức độ"]]
        for a in alerts[:10]:
            alert_data.append([
                a.get('time','')[:16],
                a.get('reason','')[:30],
                str(a.get('heart_rate','')),
                str(a.get('spo2','')),
                a.get('level','')
            ])
        at = Table(alert_data, colWidths=[90, 180, 50, 50, 70])
        at.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.red),
            ('TEXTCOLOR',  (0,0), (-1,0), colors.white),
            ('FONTSIZE',   (0,0), (-1,-1), 8),
            ('GRID',       (0,0), (-1,-1), 0.5, colors.grey),
        ]))
        story.append(at)
    else:
        story.append(Paragraph("✅ Không có cảnh báo nào trong ngày", styles['Normal']))

    doc.build(story)
    print(f"[REPORT] Đã tạo: {filename}")
    return filename
```

---

## Firebase: thêm hàm get_latest_ecg và save_ecg_to_firebase

```python
# Thêm vào server/firebase_handler.py

def save_ecg_to_firebase(device_id: str, data: dict):
    """Lưu ECG samples vào Firebase (ghi đè latest)"""
    ref = db.reference(f"patients/{device_id}/ecg_latest")
    ref.set({
        "samples":  data.get("samples", []),
        "anomaly":  data.get("ecg_anomaly", False),
        "ts":       data.get("ts", ""),
        "updated":  datetime.now().isoformat()
    })

def get_latest_ecg(device_id: str) -> dict:
    """Lấy ECG mới nhất để hiển thị trên dashboard"""
    ref = db.reference(f"patients/{device_id}/ecg_latest")
    return ref.get() or {}
```

## Test API v3

```bash
# Endpoints cũ
curl http://localhost:5000/api/health/status
curl http://localhost:5000/api/health/patient_001/latest

# Endpoints mới v3
curl http://localhost:5000/api/health/patient_001/ecg_latest
curl -X POST http://localhost:5000/api/retrain/patient_001
curl "http://localhost:5000/api/report/patient_001" -o report.pdf
```
