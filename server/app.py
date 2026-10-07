from __future__ import annotations

import json
import math
import os
import ssl
import sys
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import paho.mqtt.client as mqtt
from dotenv import load_dotenv
from flask import Flask, Response, jsonify, request
from flask_cors import CORS
from werkzeug.exceptions import BadRequest, HTTPException, NotFound


PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")


if __package__ in (None, ""):
    sys.path.insert(0, str(PROJECT_ROOT))
    from server.firebase_handler import (
        get_alerts,
        get_all_patients,
        get_history,
        get_latest,
        get_latest_ecg,
        get_medicine_history,
        save_medicine_schedule,
    )
    from server.mqtt_handler import process_data_message, start_mqtt
else:
    from .firebase_handler import (
        get_alerts,
        get_all_patients,
        get_history,
        get_latest,
        get_latest_ecg,
        get_medicine_history,
        save_medicine_schedule,
    )
    from .mqtt_handler import process_data_message, start_mqtt


app = Flask(__name__)
CORS(app)

FLASK_PORT = int(os.getenv("FLASK_PORT", "5000"))
FLASK_DEBUG = os.getenv("FLASK_DEBUG", "false").lower() == "true"
MQTT_BROKER = os.getenv("MQTT_BROKER", "").strip()
MQTT_PORT = int(os.getenv("MQTT_PORT", "8883"))
MQTT_USERNAME = os.getenv("MQTT_USERNAME", "").strip()
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "").strip()

_mqtt_thread: threading.Thread | None = None


def error_response(message: str, status_code: int = 400, **extra: Any):
    payload = {"error": message}
    payload.update(extra)
    response = jsonify(payload)
    response.status_code = status_code
    return response


@app.errorhandler(HTTPException)
def handle_http_exception(exc: HTTPException):
    return error_response(exc.description, exc.code or 500)


@app.errorhandler(Exception)
def handle_unexpected_exception(exc: Exception):
    app.logger.exception("Unhandled error: %s", exc)
    return error_response("Internal server error", 500)


def _load_ai_predictor():
    try:
        if __package__ in (None, ""):
            import server.ai_engine as ai_module
        else:
            from . import ai_engine as ai_module
    except Exception:
        return None

    engine_cls = getattr(ai_module, "AIEngine", None)
    if engine_cls is not None:
        try:
            engine = engine_cls()
            predict = getattr(engine, "predict_trend", None)
            if callable(predict):
                return predict
        except Exception:
            return None

    predict = getattr(ai_module, "predict_trend", None)
    return predict if callable(predict) else None


PREDICT_TREND = _load_ai_predictor()


def _fallback_predict(history: list[dict[str, Any]], horizon_hours: int = 6) -> dict[str, Any]:
    heart_rates = []
    for item in history:
        value = item.get("heart_rate")
        if value in (None, "", 0):
            continue
        try:
            heart_rates.append(float(value))
        except (TypeError, ValueError):
            continue

    if not heart_rates:
        heart_rates = [75.0]

    window = heart_rates[-10:]
    average_hr = round(sum(window) / len(window), 2)
    latest_hr = round(heart_rates[-1], 2)
    baseline = round((average_hr + latest_hr) / 2.0, 2)
    now = datetime.now()

    predictions = []
    steps = max(1, int(horizon_hours) * 12)
    for step in range(1, steps + 1):
        drift = 2.5 * math.sin(step / 5.0)
        gentle_trend = min(step, 24) * 0.03
        predictions.append(
            {
                "step": step,
                "minutes_ahead": step * 5,
                "time": (now + timedelta(minutes=step * 5)).isoformat(timespec="seconds"),
                "heart_rate": round(max(50.0, min(130.0, baseline + drift + gentle_trend)), 2),
            }
        )

    return {
        "model": "fallback_demo" if len(heart_rates) == 1 and heart_rates[0] == 75.0 else "fallback_average",
        "source_points": len(window),
        "predictions": predictions,
    }


def _pdf_escape(value: Any) -> str:
    return str(value).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _simple_pdf(lines: list[str]) -> bytes:
    text_ops = ["BT", "/F1 12 Tf", "50 790 Td"]
    for index, line in enumerate(lines[:34]):
        if index:
            text_ops.append("0 -20 Td")
        text_ops.append(f"({_pdf_escape(line)}) Tj")
    text_ops.append("ET")
    stream = "\n".join(text_ops).encode("latin-1", errors="replace")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj_id, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{obj_id} 0 obj\n".encode())
        pdf.extend(obj)
        pdf.extend(b"\nendobj\n")
    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode())
    pdf.extend(
        f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode()
    )
    return bytes(pdf)


def _publish_medicine_schedule(device_id: str, schedule: dict[str, Any]) -> None:
    if not MQTT_BROKER or not MQTT_USERNAME or not MQTT_PASSWORD:
        raise RuntimeError("Missing MQTT broker credentials in .env")

    topic = f"health/{device_id}/medicine"
    payload = {
        "device_id": device_id,
        "type": "set_medicine",
        "medicine": {
            "label": schedule["label"],
            "hour": schedule["hour"],
            "minute": schedule["minute"],
            "enabled": schedule["enabled"],
        },
    }

    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"schedule_api_{device_id}",
        protocol=mqtt.MQTTv311,
    )
    client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    client.tls_set(tls_version=ssl.PROTOCOL_TLS_CLIENT)
    client.connect(MQTT_BROKER, MQTT_PORT, keepalive=30)
    client.loop_start()
    try:
        result = client.publish(topic, json.dumps(payload), qos=1)
        result.wait_for_publish(timeout=10)
        if not result.is_published():
            raise RuntimeError("Timed out while publishing medicine schedule")
        client.disconnect()
    finally:
        client.loop_stop()

    if result.rc != mqtt.MQTT_ERR_SUCCESS:
        raise RuntimeError(f"Failed to publish medicine schedule, rc={result.rc}")


def _validated_int(name: str, raw_value: Any, minimum: int, maximum: int) -> int:
    try:
        value = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise BadRequest(f"'{name}' must be an integer") from exc

    if value < minimum or value > maximum:
        raise BadRequest(f"'{name}' must be between {minimum} and {maximum}")
    return value


def _ensure_mqtt_thread_started() -> None:
    global _mqtt_thread
    if _mqtt_thread and _mqtt_thread.is_alive():
        return

    _mqtt_thread = threading.Thread(target=start_mqtt, daemon=True, name="mqtt-subscriber")
    _mqtt_thread.start()
    app.logger.info("MQTT subscriber started in background thread")


@app.get("/api/health/status")
def health_status():
    mqtt_running = _mqtt_thread.is_alive() if _mqtt_thread else False
    return jsonify(
        {
            "status": "ok",
            "service": "aiot-health-api",
            "mqtt_thread_running": mqtt_running,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        }
    )


@app.get("/api/patients")
def patients():
    return jsonify(get_all_patients())


@app.get("/api/health/<device_id>/latest")
def latest(device_id: str):
    data = get_latest(device_id)
    if not data:
        raise NotFound(f"No latest health data found for device '{device_id}'")
    return jsonify(data)


@app.get("/api/health/<device_id>/history")
def history(device_id: str):
    days = _validated_int("days", request.args.get("days", 7), 1, 365)
    return jsonify(get_history(device_id, days=days))


@app.get("/api/health/<device_id>/ecg_latest")
def ecg_latest(device_id: str):
    data = get_latest_ecg(device_id)
    if not data:
        raise NotFound(f"No ECG data found for device '{device_id}'")
    return jsonify(data)


@app.post("/api/demo/health/<device_id>")
def demo_health(device_id: str):
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise BadRequest("Request body must be a JSON object")

    payload = dict(body)
    payload["device_id"] = device_id
    process_data_message(f"health/{device_id}/data", payload)
    return jsonify({"ok": True, "device_id": device_id})


@app.get("/api/alerts/<device_id>")
def alerts(device_id: str):
    limit = _validated_int("limit", request.args.get("limit", 20), 1, 100)
    return jsonify(get_alerts(device_id, limit=limit))


@app.get("/api/report/<device_id>")
def report(device_id: str):
    latest_data = get_latest(device_id)
    if not latest_data:
        raise NotFound(f"No health data found for device '{device_id}'")

    recent_alerts = get_alerts(device_id, limit=5)
    lines = [
        "AIoT Health Monitor - Daily Report",
        f"Patient: {device_id}",
        f"Generated: {datetime.now().isoformat(timespec='seconds')}",
        "",
        f"Heart rate: {latest_data.get('heart_rate', '--')} bpm",
        f"SpO2: {latest_data.get('spo2', '--')} %",
        f"Temperature: {latest_data.get('temperature', '--')} C",
        f"Fall: {latest_data.get('fall', False)}",
        f"AI Score: {latest_data.get('ai_score', latest_data.get('ai_confidence', 0))}",
        f"Status: {latest_data.get('status', '--')}",
        "",
        "Recent alerts:",
    ]
    if recent_alerts:
        lines.extend(
            f"- {alert.get('time', '')}: {alert.get('reason', '')} ({alert.get('level', '')})"
            for alert in recent_alerts
        )
    else:
        lines.append("- No recent alerts")

    return Response(
        _simple_pdf(lines),
        mimetype="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=report_{device_id}.pdf"},
    )


@app.post("/api/predict/<device_id>")
def predict(device_id: str):
    body = request.get_json(silent=True) or {}
    if body is not None and not isinstance(body, dict):
        raise BadRequest("Request body must be a JSON object")

    days = _validated_int("days", body.get("days", 1), 1, 30)
    horizon_hours = _validated_int("horizon_hours", body.get("horizon_hours", 6), 1, 24)
    history_data = get_history(device_id, days=days)
    if not history_data:
        raise NotFound(f"No history data found for device '{device_id}'")

    if callable(PREDICT_TREND):
        try:
            prediction = PREDICT_TREND(history_data)
            if prediction:
                return jsonify({"device_id": device_id, "prediction": prediction, "model": "ai_engine"})
        except Exception as exc:
            app.logger.warning("AI prediction failed, using fallback: %s", exc)

    fallback = _fallback_predict(history_data, horizon_hours=horizon_hours)
    return jsonify({"device_id": device_id, **fallback})


@app.get("/api/medicine/<device_id>/history")
def medicine_history(device_id: str):
    days = _validated_int("days", request.args.get("days", 30), 1, 365)
    return jsonify(get_medicine_history(device_id, days=days))


@app.post("/api/medicine/<device_id>/schedule")
def medicine_schedule(device_id: str):
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise BadRequest("Request body must be a JSON object")

    label = str(body.get("label") or body.get("name") or "").strip()
    if not label:
        raise BadRequest("'label' is required")

    schedule = {
        "label": label,
        "hour": _validated_int("hour", body.get("hour"), 0, 23),
        "minute": _validated_int("minute", body.get("minute"), 0, 59),
        "enabled": bool(body.get("enabled", True)),
    }

    saved_schedule = save_medicine_schedule(device_id, schedule)
    _publish_medicine_schedule(device_id, schedule)

    return jsonify(
        {
            "message": "Medicine schedule saved and published",
            "device_id": device_id,
            "schedule": saved_schedule,
        }
    ), 201


def main() -> None:
    _ensure_mqtt_thread_started()
    app.run(host="0.0.0.0", port=FLASK_PORT, debug=FLASK_DEBUG, use_reloader=False)


if __name__ == "__main__":
    main()
