---
name: telegram-alerts
description: Use this skill to set up, configure, or debug Telegram Bot alerts v3 — now includes ensemble AI confidence score in messages, ECG anomaly notifications, automatic daily PDF report delivery, and medicine missed alerts. Trigger when user says 'Telegram', 'cảnh báo', 'thông báo', 'bot', 'alert_bot', 'gửi tin nhắn', 'báo cáo PDF', or 'nhắc thuốc'.
---

# Telegram Alerts Skill v3 – AIoT Health Monitor

## Thiết lập bot (giữ nguyên từ v2)

1. Tìm `@BotFather` → `/newbot` → Copy TOKEN
2. Tìm `@userinfobot` → `/start` → Copy CHAT_ID
3. Lưu vào `.env`: `TELEGRAM_BOT_TOKEN=...` và `TELEGRAM_CHAT_ID=...`

## File: server/alert_bot.py (v3)

```python
import requests, os
from datetime import datetime
from dotenv import load_dotenv
from firebase_handler import save_alert

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")
BASE_URL  = f"https://api.telegram.org/bot{BOT_TOKEN}"

def send_message(text: str, parse_mode: str = "HTML") -> bool:
    try:
        r = requests.post(f"{BASE_URL}/sendMessage",
                          json={"chat_id": CHAT_ID, "text": text,
                                "parse_mode": parse_mode}, timeout=5)
        return r.status_code == 200
    except Exception as e:
        print(f"[TELEGRAM] Lỗi: {e}")
        return False

def send_document(file_path: str, caption: str = "") -> bool:
    """MỚI v3: Gửi file PDF báo cáo"""
    try:
        with open(file_path, "rb") as f:
            r = requests.post(f"{BASE_URL}/sendDocument",
                              data={"chat_id": CHAT_ID, "caption": caption},
                              files={"document": f}, timeout=15)
        return r.status_code == 200
    except Exception as e:
        print(f"[TELEGRAM] Lỗi gửi file: {e}")
        return False

# ── Cảnh báo sức khỏe (v3: thêm confidence + ECG) ─
def send_alert(device_id: str, data: dict, reason: str, confidence: float = 1.0):
    hr   = data.get("heart_rate", 0)
    spo2 = data.get("spo2", 0)
    temp = data.get("temperature", 0)
    now  = datetime.now().strftime("%H:%M:%S %d/%m/%Y")
    ecg_ok = data.get("ecg_ok", True)

    if spo2 < 88 or hr > 160 or hr < 35 or "NGÃ" in reason.upper():
        level = "🔴 KHẨN CẤP"
    elif confidence >= 0.67:
        level = "🟠 CẢNH BÁO CAO"
    else:
        level = "🟡 CẢNH BÁO"

    # MỚI v3: thêm dòng confidence và ECG status
    msg = (
        f"<b>{level} — AIoT Health v3</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 Bệnh nhân: <code>{device_id}</code>\n"
        f"🕒 {now}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"❤️ Nhịp tim:  <b>{hr} bpm</b>\n"
        f"🫁 SpO₂:      <b>{spo2}%</b>\n"
        f"🌡️ Nhiệt độ:  <b>{temp}°C</b>\n"
        f"📊 ECG:       {'✅ Bình thường' if ecg_ok else '⚠️ Điện cực lỏng'}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ Lý do: {reason}\n"
        f"🤖 AI Confidence: <b>{int(confidence*100)}%</b> "
        f"({'3/3' if confidence==1 else '2/3' if confidence>=0.67 else '1/3'} model đồng ý)\n"
        f"\n<i>Vui lòng kiểm tra ngay!</i>"
    )

    send_message(msg)
    save_alert(device_id, data, reason, confidence)

# ── Cảnh báo ngã (khẩn cấp nhất) ─────────────────
def send_fall_alert(device_id: str, data: dict):
    now = datetime.now().strftime("%H:%M:%S %d/%m/%Y")
    msg = (
        f"🚨🚨🚨 <b>PHÁT HIỆN NGÃ!</b> 🚨🚨🚨\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 <code>{device_id}</code>  🕒 {now}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"❤️ HR: {data.get('heart_rate')} bpm\n"
        f"🫁 SpO₂: {data.get('spo2')}%\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"<b>⚡ KIỂM TRA NGAY LẬP TỨC!</b>"
    )
    send_message(msg)
    save_alert(device_id, data, "PHÁT HIỆN NGÃ", 1.0)

# ── Báo cáo hàng ngày + gửi PDF (MỚI v3) ─────────
def send_daily_report(device_id: str, stats: dict):
    date = datetime.now().strftime("%d/%m/%Y")
    msg = (
        f"📊 <b>Báo cáo sức khỏe {date}</b>\n"
        f"👤 Bệnh nhân: <code>{device_id}</code>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"❤️ HR TB: {stats.get('hr_avg',0):.0f} bpm "
        f"(min:{stats.get('hr_min',0):.0f} max:{stats.get('hr_max',0):.0f})\n"
        f"🫁 SpO₂ TB: {stats.get('spo2_avg',0):.1f}%\n"
        f"🌡️ Nhiệt độ TB: {stats.get('temp_avg',0):.1f}°C\n"
        f"🚨 Cảnh báo: {stats.get('alert_count',0)} lần\n"
        f"🤖 Bất thường AI: {stats.get('anomaly_count',0)} lần\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Tình trạng: {stats.get('status','Bình thường')}"
    )
    send_message(msg)

    # Gửi kèm file PDF nếu có
    from report_generator import generate_daily_report
    try:
        pdf_path = generate_daily_report(device_id)
        send_document(pdf_path, caption=f"📄 Báo cáo chi tiết {date}")
    except Exception as e:
        print(f"[TELEGRAM] Không gửi được PDF: {e}")

# ── Scheduler: 20:00 mỗi ngày gửi báo cáo ─────────
def start_daily_scheduler():
    from apscheduler.schedulers.background import BackgroundScheduler
    from firebase_handler import get_all_patients, get_history

    def _daily_job():
        patients = get_all_patients()
        for p in patients:
            pid = p['id']
            try:
                hist = get_history(pid, days=1)
                df   = __import__('pandas').DataFrame(hist)
                stats = {
                    "hr_avg":       df['heart_rate'].mean()    if 'heart_rate' in df else 0,
                    "hr_min":       df['heart_rate'].min()     if 'heart_rate' in df else 0,
                    "hr_max":       df['heart_rate'].max()     if 'heart_rate' in df else 0,
                    "spo2_avg":     df['spo2'].mean()          if 'spo2' in df else 0,
                    "temp_avg":     df['temperature'].mean()   if 'temperature' in df else 0,
                    "alert_count":  int(df.get('edge_alert', __import__('pandas').Series()).sum()) if 'edge_alert' in df.columns else 0,
                    "anomaly_count":int((df.get('anomaly_score', __import__('pandas').Series()) > 0.67).sum()) if 'anomaly_score' in df.columns else 0,
                    "status":       "Cần chú ý" if df.get('anomaly_score', __import__('pandas').Series()).mean() > 0.3 else "Bình thường"
                }
                send_daily_report(pid, stats)
            except Exception as e:
                print(f"[DAILY] Lỗi {pid}: {e}")

    scheduler = BackgroundScheduler()
    scheduler.add_job(_daily_job, 'cron', hour=20, minute=0)
    scheduler.start()
    print("[TELEGRAM] Daily report scheduler: 20:00 mỗi ngày")

# ── Test ─────────────────────────────────────────────
if __name__ == "__main__":
    ok = send_message(
        "✅ <b>AIoT Health Bot v3 đã khởi động!</b>\n"
        "Hệ thống giám sát: MAX30102 + DS18B20 + MPU6050 + <b>AD8232 ECG</b>\n"
        "AI: Ensemble 3 model (Rule + IF + Conv1D ECG)"
    )
    print("Test:", "Thành công!" if ok else "Thất bại")
```
