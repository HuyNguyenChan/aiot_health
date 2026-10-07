from __future__ import annotations

import argparse
import json
import math
import os
import ssl
import time
import urllib.error
import urllib.request
from pathlib import Path

import paho.mqtt.client as mqtt
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env")


def build_client() -> mqtt.Client:
    broker = os.getenv("MQTT_BROKER", "").strip()
    username = os.getenv("MQTT_USERNAME", "").strip()
    password = os.getenv("MQTT_PASSWORD", "").strip()

    if not broker:
        raise RuntimeError("Missing MQTT_BROKER in .env")
    if not username or not password:
        raise RuntimeError("Missing MQTT_USERNAME or MQTT_PASSWORD in .env")

    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"demo_sender_{int(time.time())}",
        protocol=mqtt.MQTTv311,
    )
    client.username_pw_set(username, password)
    client.tls_set(tls_version=ssl.PROTOCOL_TLS_CLIENT)
    return client


def generate_ecg_samples(index: int, mode: str) -> list[int]:
    samples: list[int] = []
    baseline = 2048 + int(80 * math.sin(index / 3.0))
    beat_positions = [18, 68, 118, 168, 218]

    for sample_index in range(250):
        value = baseline
        value += int(45 * math.sin(2 * math.pi * sample_index / 125))
        value += int(12 * math.sin(2 * math.pi * sample_index / 17))

        for beat in beat_positions:
            distance = sample_index - beat
            if -2 <= distance <= 2:
                value += int(780 * math.exp(-(distance * distance) / 2.0))
            elif 3 <= distance <= 8:
                value -= int(160 * math.exp(-((distance - 5) ** 2) / 8.0))

        if mode == "ecg_anomaly":
            value += int(130 * math.sin(2 * math.pi * sample_index / 9))
            if sample_index in (40, 41, 42, 151, 152, 210):
                value += 1050
            if 85 <= sample_index <= 105:
                value -= 650

        samples.append(max(0, min(4095, value)))

    return samples


def make_payload(device_id: str, index: int, mode: str) -> dict:
    base_hr = 76 + 4 * math.sin(index / 4.0)
    spo2 = 98
    temperature = 36.6
    fall = False
    edge_alert = False
    alert_reason = ""

    if mode == "high_hr":
        base_hr = 145 + min(index, 15) * 1.8 + 3 * math.sin(index / 3.0)
        alert_reason = "DEMO_HIGH_HR"
    elif mode == "low_spo2":
        spo2 = max(86, 98 - index // 2)
        alert_reason = "DEMO_LOW_SPO2"
    elif mode == "fall":
        fall = index >= 10
        edge_alert = fall
        alert_reason = "DEMO_FALL" if fall else ""
    elif mode == "stress":
        base_hr = 88 + min(index, 25) * 1.2 + 5 * math.sin(index / 5.0)
        temperature = 36.8
    elif mode == "ecg_anomaly":
        base_hr = 112 + 10 * math.sin(index / 3.0)
        edge_alert = True
        alert_reason = "DEMO_ECG_ANOMALY"
    elif mode == "ecg_lead_off":
        base_hr = 0
        alert_reason = "DEMO_ECG_LEAD_OFF"

    heart_rate = int(round(max(45, min(180, base_hr))))
    if mode == "ecg_lead_off":
        heart_rate = 0
    if mode == "high_hr" and heart_rate > 150:
        edge_alert = True

    ecg_lead_off = mode == "ecg_lead_off"
    ecg_samples = [] if ecg_lead_off else generate_ecg_samples(index, mode)
    ecg_mean = round(sum(ecg_samples) / len(ecg_samples), 2) if ecg_samples else 0
    ecg_std = (
        round((sum((sample - ecg_mean) ** 2 for sample in ecg_samples) / len(ecg_samples)) ** 0.5, 2)
        if ecg_samples
        else 0
    )

    payload = {
        "device_id": device_id,
        "ts": int(time.time()),
        "heart_rate": heart_rate,
        "heart_rate_valid": not ecg_lead_off,
        "heart_rate_source": "demo",
        "spo2": int(spo2),
        "spo2_valid": True,
        "spo2_source": "demo",
        "temperature": round(temperature, 1),
        "accel_x": 0.02,
        "accel_y": -0.01,
        "accel_z": 1.0 if not fall else 3.1,
        "fall": fall,
        "edge_alert": edge_alert,
        "alert_reason": alert_reason,
        "ecg_lead_off": ecg_lead_off,
        "ecg_lo_plus": ecg_lead_off,
        "ecg_lo_minus": ecg_lead_off,
        "ecg_raw": ecg_samples[-1] if ecg_samples else 0,
        "ecg_mv": round(((ecg_samples[-1] if ecg_samples else 0) / 4095.0) * 3300.0, 2),
        "ecg_raw_avg": int(round(ecg_mean)),
        "ecg_window_mean": ecg_mean,
        "ecg_window_std": ecg_std,
        "ecg_beats": 0 if ecg_lead_off else 5,
        "status": f"demo_{mode}",
        "measure_mode": "Demo",
    }
    if ecg_samples:
        payload["ecg_samples"] = ecg_samples
    return payload


def print_payload(index: int, count: int, payload: dict) -> None:
    print(
        f"{index + 1:02d}/{count} -> "
        f"HR={payload['heart_rate']} SpO2={payload['spo2']} "
        f"Temp={payload['temperature']} Fall={payload['fall']}"
    )


def send_by_api(args: argparse.Namespace) -> None:
    api_base = args.api_base.rstrip("/")
    url = f"{api_base}/api/demo/health/{args.device_id}"
    print(f"Sending demo data via local API {url} ...")

    for index in range(args.count):
        payload = make_payload(args.device_id, index, args.mode)
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                if response.status >= 400:
                    raise RuntimeError(f"API returned HTTP {response.status}")
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Cannot send demo data to Flask API: {exc}") from exc

        print_payload(index, args.count, payload)
        time.sleep(args.delay)


def send_by_mqtt(args: argparse.Namespace) -> None:
    broker = os.getenv("MQTT_BROKER", "").strip()
    port = int(os.getenv("MQTT_PORT", "8883"))
    topic = f"health/{args.device_id}/data"

    client = build_client()
    print(f"Connecting MQTT {broker}:{port} ...")
    client.connect(broker, port, keepalive=30)
    client.loop_start()
    time.sleep(1.0)

    try:
        for index in range(args.count):
            payload = make_payload(args.device_id, index, args.mode)
            result = client.publish(topic, json.dumps(payload), qos=1)
            result.wait_for_publish(timeout=5)
            print_payload(index, args.count, payload)
            time.sleep(args.delay)
    finally:
        client.loop_stop()
        client.disconnect()


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish demo health data to MQTT.")
    parser.add_argument("--device-id", default="patient_001")
    parser.add_argument("--count", type=int, default=36)
    parser.add_argument("--delay", type=float, default=0.5)
    parser.add_argument("--api-base", default="http://127.0.0.1:5000")
    parser.add_argument("--transport", choices=["auto", "mqtt", "api"], default="auto")
    parser.add_argument(
        "--mode",
        choices=["normal", "stress", "high_hr", "low_spo2", "fall", "ecg", "ecg_anomaly", "ecg_lead_off"],
        default="normal",
    )
    args = parser.parse_args()

    if args.transport == "api":
        send_by_api(args)
    elif args.transport == "mqtt":
        send_by_mqtt(args)
    else:
        try:
            send_by_mqtt(args)
        except Exception as exc:
            print(f"MQTT failed: {exc}")
            print("Fallback to local Flask API. Make sure server/app.py is running.")
            send_by_api(args)

    print("Done. Now open dashboard or call /api/predict/patient_001.")


if __name__ == "__main__":
    main()
