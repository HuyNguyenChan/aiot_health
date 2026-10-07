from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import firebase_admin
from dotenv import load_dotenv
from firebase_admin import credentials, db


PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")


def _firebase_key_path() -> Path:
    raw_path = os.getenv("FIREBASE_KEY_PATH", "server/firebase_key.json")
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def _ensure_firebase_initialized() -> None:
    if firebase_admin._apps:
        return

    database_url = os.getenv("FIREBASE_DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("Missing FIREBASE_DATABASE_URL in .env")

    key_path = _firebase_key_path()
    if not key_path.exists():
        raise RuntimeError(f"Firebase key file not found: {key_path}")

    cred = credentials.Certificate(str(key_path))
    firebase_admin.initialize_app(cred, {"databaseURL": database_url})


def _ref(path: str):
    _ensure_firebase_initialized()
    return db.reference(path)


def _now() -> datetime:
    return datetime.now()


def _sort_timestamp(record: dict[str, Any]) -> str:
    timestamp = record.get("timestamp") or record.get("updated_at") or record.get("time")
    if isinstance(timestamp, str) and timestamp:
        return timestamp

    date_part = str(record.get("date", ""))
    time_part = str(record.get("time_key", ""))
    return f"{date_part}T{time_part}"


def _normalize_dict(raw: Any) -> dict[str, Any]:
    return raw if isinstance(raw, dict) else {}


def classify_severity(data: dict[str, Any], reason: str) -> str:
    spo2 = float(data.get("spo2", 100) or 100)
    heart_rate = float(data.get("heart_rate", 70) or 70)
    reason_upper = str(reason).upper()

    if (
        spo2 < 90
        or heart_rate > 150
        or heart_rate < 40
        or "FALL" in reason_upper
        or "SOS" in reason_upper
    ):
        return "CRITICAL"
    if spo2 < 93 or heart_rate > 130 or heart_rate < 50:
        return "HIGH"
    return "MEDIUM"


def save_to_firebase(device_id: str, data: dict[str, Any]) -> None:
    now = _now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H%M%S")

    latest_payload = dict(data)
    latest_payload["updated_at"] = now.isoformat()

    history_payload = dict(data)
    history_payload["timestamp"] = now.isoformat()

    _ref(f"patients/{device_id}/latest").set(latest_payload)
    _ref(f"patients/{device_id}/history/{date_str}/{time_str}").set(history_payload)


def get_latest(device_id: str) -> dict[str, Any]:
    return _ref(f"patients/{device_id}/latest").get() or {}


def get_latest_ecg(device_id: str) -> dict[str, Any]:
    latest = get_latest(device_id)
    if not latest:
        return {}

    samples = latest.get("ecg_samples")
    if not isinstance(samples, list) or len(samples) < 250:
        history = get_history(device_id, days=1)
        raw_values = [
            int(record.get("ecg_raw", 0) or 0)
            for record in history
            if not bool(record.get("ecg_lead_off", False)) and int(record.get("ecg_raw", 0) or 0) > 0
        ]
        samples = raw_values[-250:]

    return {
        "device_id": device_id,
        "ts": latest.get("ts"),
        "timestamp": latest.get("updated_at"),
        "samples": samples if isinstance(samples, list) else [],
        "lead_off": bool(latest.get("ecg_lead_off", False)),
        "anomaly": float(latest.get("ai_confidence", 0) or 0) >= (2 / 3),
        "ecg_raw": latest.get("ecg_raw", 0),
        "ecg_mv": latest.get("ecg_mv", 0),
        "mean": latest.get("ecg_window_mean", 0),
        "std": latest.get("ecg_window_std", 0),
        "beats": latest.get("ecg_beats", 0),
    }


def get_history(device_id: str, days: int = 7) -> list[dict[str, Any]]:
    days = max(1, int(days))
    records: list[dict[str, Any]] = []

    for offset in range(days):
        date_str = (_now() - timedelta(days=offset)).strftime("%Y-%m-%d")
        day_data = _ref(f"patients/{device_id}/history/{date_str}").get() or {}
        if not isinstance(day_data, dict):
            continue

        for time_key, record in day_data.items():
            if not isinstance(record, dict):
                continue
            item = dict(record)
            item["date"] = date_str
            item["time_key"] = time_key
            records.append(item)

    return sorted(records, key=_sort_timestamp)


def save_alert(device_id: str, data: dict[str, Any], reason: str) -> None:
    now = _now()
    alert_path = f"alerts/{device_id}"
    alert_ref = _ref(alert_path)
    existing_raw = alert_ref.get() or {}
    existing = _normalize_dict(existing_raw)

    alert_key = now.strftime("%Y%m%d%H%M%S%f")
    alert_payload = {
        "device_id": device_id,
        "time": now.isoformat(),
        "reason": reason,
        "level": classify_severity(data, reason),
        "heart_rate": data.get("heart_rate"),
        "spo2": data.get("spo2"),
        "temperature": data.get("temperature"),
        "fall": data.get("fall", False),
        "edge_alert": data.get("edge_alert", False),
        "confidence": data.get("ai_confidence", 1.0 if data.get("edge_alert", False) else 0.0),
    }
    existing[alert_key] = alert_payload

    latest_50 = sorted(
        existing.items(),
        key=lambda item: str(item[1].get("time", "")),
        reverse=True,
    )[:50]
    alert_ref.set({key: value for key, value in latest_50})


def get_alerts(device_id: str, limit: int = 20) -> list[dict[str, Any]]:
    limit = max(1, int(limit))
    raw_alerts = _ref(f"alerts/{device_id}").get() or {}
    alerts = _normalize_dict(raw_alerts)

    items = []
    for alert_key, alert_data in alerts.items():
        if not isinstance(alert_data, dict):
            continue
        item = dict(alert_data)
        item["id"] = alert_key
        items.append(item)

    return sorted(items, key=lambda item: str(item.get("time", "")), reverse=True)[:limit]


def save_medicine_log(device_id: str, med_name: str, confirmed: bool) -> None:
    now = _now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H%M%S")
    payload = {
        "medicine_name": med_name,
        "confirmed": bool(confirmed),
        "status": "confirmed" if confirmed else "missed",
        "timestamp": now.isoformat(),
    }
    _ref(f"patients/{device_id}/medicine_logs/{date_str}/{time_str}").set(payload)


def get_medicine_history(device_id: str, days: int = 30) -> list[dict[str, Any]]:
    days = max(1, int(days))
    records: list[dict[str, Any]] = []

    for offset in range(days):
        date_str = (_now() - timedelta(days=offset)).strftime("%Y-%m-%d")
        day_data = _ref(f"patients/{device_id}/medicine_logs/{date_str}").get() or {}
        if not isinstance(day_data, dict):
            continue

        for time_key, record in day_data.items():
            if not isinstance(record, dict):
                continue
            item = dict(record)
            item["date"] = date_str
            item["time_key"] = time_key
            records.append(item)

    return sorted(records, key=_sort_timestamp, reverse=True)


def save_medicine_schedule(device_id: str, schedule: dict[str, Any]) -> dict[str, Any]:
    payload = dict(schedule)
    payload["updated_at"] = _now().isoformat()
    _ref(f"patients/{device_id}/medicine_schedule").set(payload)
    return payload


def get_all_patients() -> list[dict[str, Any]]:
    raw_patients = _ref("patients").get() or {}
    patients = _normalize_dict(raw_patients)

    results = []
    for device_id, patient_data in patients.items():
        patient = patient_data if isinstance(patient_data, dict) else {}
        results.append(
            {
                "id": device_id,
                "info": patient.get("info", {}),
                "latest": patient.get("latest", {}),
            }
        )

    return sorted(results, key=lambda item: item["id"])


__all__ = [
    "classify_severity",
    "get_alerts",
    "get_all_patients",
    "get_history",
    "get_latest_ecg",
    "get_latest",
    "get_medicine_history",
    "save_alert",
    "save_medicine_log",
    "save_medicine_schedule",
    "save_to_firebase",
]
