from __future__ import annotations

import csv
import json
import os
import ssl
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import paho.mqtt.client as mqtt
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

LABELS = {
    0: "normal_rest",
    1: "normal_light",
    2: "normal_moderate",
    3: "normal_morning",
    4: "normal_postmeal",
    5: "stress",
    6: "anomaly_high_hr",
    7: "anomaly_low_spo2",
    8: "fall",
}

OUTPUT_PATH = PROJECT_ROOT / "data" / "raw" / "health_data.csv"
HEADERS = [
    "timestamp",
    "device_id",
    "heart_rate",
    "heart_rate_valid",
    "heart_rate_source",
    "spo2",
    "spo2_valid",
    "spo2_source",
    "temperature",
    "ecg_raw",
    "ecg_mv",
    "ecg_raw_avg",
    "ecg_lead_off",
    "ecg_lo_plus",
    "ecg_lo_minus",
    "accel_x",
    "accel_y",
    "accel_z",
    "fall_detect",
    "label",
    "session_id",
]

STATE_LOCK = threading.Lock()
STATE = {
    "label": "",
    "session_id": "",
    "count": 0,
}


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _valid_measurement(data: dict[str, Any], flag_name: str, value_name: str, low: float, high: float) -> bool:
    if flag_name in data:
        return _to_bool(data.get(flag_name))
    try:
        value = float(data.get(value_name, 0) or 0)
    except (TypeError, ValueError):
        return False
    return low <= value <= high


def ensure_output_file() -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not OUTPUT_PATH.exists():
        with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as csv_file:
            writer = csv.writer(csv_file)
            writer.writerow(HEADERS)
        return

    with OUTPUT_PATH.open("r", newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        if reader.fieldnames == HEADERS:
            return

        rows = []
        for row in reader:
            migrated = {header: row.get(header, "") for header in HEADERS}
            migrated["heart_rate_valid"] = migrated["heart_rate_valid"] or (
                35 <= float(row.get("heart_rate") or 0) <= 220
            )
            migrated["heart_rate_source"] = migrated["heart_rate_source"] or "legacy"
            migrated["spo2_valid"] = migrated["spo2_valid"] or (
                50 <= float(row.get("spo2") or 0) <= 100
            )
            migrated["spo2_source"] = migrated["spo2_source"] or "legacy"
            rows.append(migrated)

    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=HEADERS)
        writer.writeheader()
        writer.writerows(rows)


def choose_label() -> str:
    while True:
        print("\nChon nhan cho phien thu thap:\n")
        for key, label in LABELS.items():
            print(f"  {key} = {label}")

        raw = input("\nNhap so nhan: ").strip()
        try:
            index = int(raw)
        except ValueError:
            print("Gia tri khong hop le, vui long nhap so 0-8.")
            continue

        if index in LABELS:
            return LABELS[index]

        print("Lua chon ngoai pham vi, vui long nhap so 0-8.")


def start_session(label_name: str) -> None:
    session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    with STATE_LOCK:
        STATE["label"] = label_name
        STATE["session_id"] = session_id
        STATE["count"] = 0

    print(f"\nDang thu thap voi nhan: {label_name}")
    print(f"Session ID: {session_id}")
    print("Nhan Ctrl+C de dung va doi nhan.\n")


def _reason_is_success(reason_code: Any) -> bool:
    if hasattr(reason_code, "is_failure"):
        return not bool(reason_code.is_failure)
    return reason_code == 0


def on_connect(
    client: mqtt.Client,
    userdata: Any,
    flags: dict[str, Any],
    reason_code: Any,
    properties: Any = None,
) -> None:
    if not _reason_is_success(reason_code):
        print(f"[MQTT] Ket noi that bai: {reason_code}")
        return

    client.subscribe("health/+/data", qos=1)
    print("[MQTT] Da ket noi broker va subscribe health/+/data")


def on_disconnect(
    client: mqtt.Client,
    userdata: Any,
    disconnect_flags: Any,
    reason_code: Any,
    properties: Any = None,
) -> None:
    if _reason_is_success(reason_code):
        print("[MQTT] Da ngat ket noi.")
        return
    print(f"[MQTT] Mat ket noi (rc={reason_code}), dang tu reconnect...")


def on_message(client: mqtt.Client, userdata: Any, msg: mqtt.MQTTMessage) -> None:
    try:
        data = json.loads(msg.payload.decode("utf-8"))
        if not isinstance(data, dict):
            return
    except Exception as exc:
        print(f"[ERROR] Payload khong hop le tren topic {msg.topic}: {exc}")
        return

    with STATE_LOCK:
        label_name = STATE["label"]
        session_id = STATE["session_id"]
        STATE["count"] += 1
        count = STATE["count"]

    fall_detect = bool(data.get("fall_detect", data.get("fall", False)))
    row = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "device_id": data.get("device_id", ""),
        "heart_rate": data.get("heart_rate", 0),
        "heart_rate_valid": _valid_measurement(data, "heart_rate_valid", "heart_rate", 35, 220),
        "heart_rate_source": data.get("heart_rate_source", ""),
        "spo2": data.get("spo2", 0),
        "spo2_valid": _valid_measurement(data, "spo2_valid", "spo2", 50, 100),
        "spo2_source": data.get("spo2_source", ""),
        "temperature": data.get("temperature", 0),
        "ecg_raw": data.get("ecg_raw", 0),
        "ecg_mv": data.get("ecg_mv", 0),
        "ecg_raw_avg": data.get("ecg_raw_avg", data.get("ecg_raw", 0)),
        "ecg_lead_off": _to_bool(data.get("ecg_lead_off", False)),
        "ecg_lo_plus": _to_bool(data.get("ecg_lo_plus", False)),
        "ecg_lo_minus": _to_bool(data.get("ecg_lo_minus", False)),
        "accel_x": data.get("accel_x", 0),
        "accel_y": data.get("accel_y", 0),
        "accel_z": data.get("accel_z", 0),
        "fall_detect": fall_detect,
        "label": label_name,
        "session_id": session_id,
    }

    with OUTPUT_PATH.open("a", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=HEADERS)
        writer.writerow(row)

    print(
        f"[{count}] HR:{row['heart_rate']}({row['heart_rate_source']}) "
        f"SpO2:{row['spo2']} ECG:{'OFF' if row['ecg_lead_off'] else 'OK'} "
        f"Temp:{float(row['temperature']):.1f} -> {label_name}",
        flush=True,
    )


def build_client() -> mqtt.Client:
    broker = os.getenv("MQTT_BROKER", "").strip()
    port = int(os.getenv("MQTT_PORT", "8883"))
    username = os.getenv("MQTT_USERNAME", "").strip()
    password = os.getenv("MQTT_PASSWORD", "").strip()

    if not broker:
        raise RuntimeError("Missing MQTT_BROKER in .env")
    if not username or not password:
        raise RuntimeError("Missing MQTT_USERNAME or MQTT_PASSWORD in .env")

    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id="data_collector",
        protocol=mqtt.MQTTv311,
    )
    client.username_pw_set(username, password)
    client.tls_set(tls_version=ssl.PROTOCOL_TLS_CLIENT)
    client.reconnect_delay_set(min_delay=1, max_delay=30)
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message
    client.connect(broker, port, keepalive=60)
    return client


def ask_change_label() -> bool:
    answer = input("\nBan co muon chon nhan khac khong? [y/N]: ").strip().lower()
    return answer in {"y", "yes", "1"}


def main() -> None:
    ensure_output_file()
    client = build_client()
    client.loop_start()

    try:
        while True:
            label_name = choose_label()
            start_session(label_name)

            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                print("\nDa dung session hien tai.")
                if ask_change_label():
                    continue
                break
    finally:
        client.loop_stop()
        client.disconnect()
        print(f"\nDa luu du lieu vao: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
