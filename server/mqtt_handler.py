from __future__ import annotations

import json
import logging
import os
import ssl
import sys
import time
from pathlib import Path
from typing import Any, Callable

import paho.mqtt.client as mqtt
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")


if __package__ in (None, ""):
    sys.path.insert(0, str(PROJECT_ROOT))
    from server.firebase_handler import save_alert, save_medicine_log, save_to_firebase
else:
    from .firebase_handler import save_alert, save_medicine_log, save_to_firebase


BROKER = os.getenv("MQTT_BROKER", "").strip()
PORT = int(os.getenv("MQTT_PORT", "8883"))
USERNAME = os.getenv("MQTT_USERNAME", "").strip()
PASSWORD = os.getenv("MQTT_PASSWORD", "").strip()
CLIENT_ID = os.getenv("MQTT_CLIENT_ID", "aiot_server")
TOPIC_DATA = "health/+/data"
TOPIC_MEDICINE = "health/+/medicine"
KEEPALIVE = 60


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
LOGGER = logging.getLogger("mqtt_handler")


def _basic_detect_anomaly(data: dict[str, Any]) -> tuple[bool, str]:
    heart_rate = float(data.get("heart_rate", 0) or 0)
    spo2 = float(data.get("spo2", 0) or 0)
    temperature = float(data.get("temperature", 0) or 0)
    edge_alert = bool(data.get("edge_alert", False))
    reason = str(data.get("alert_reason", "")).strip()

    if edge_alert and reason:
        return True, reason
    if heart_rate and heart_rate > 150:
        return True, "HR_HIGH"
    if heart_rate and heart_rate < 40:
        return True, "HR_LOW"
    if spo2 and spo2 < 92:
        return True, "SPO2_LOW"
    if temperature > 38.5:
        return True, "TEMP_HIGH"
    return False, ""


def _load_ai_detector() -> Callable[[dict[str, Any]], tuple[Any, ...]]:
    try:
        if __package__ in (None, ""):
            import server.ai_engine as ai_module
        else:
            from . import ai_engine as ai_module
    except Exception as exc:
        LOGGER.warning("AI engine not available, using basic detector: %s", exc)
        return _basic_detect_anomaly

    engine_cls = getattr(ai_module, "AIEngine", None)
    if engine_cls is not None:
        try:
            engine = engine_cls()
            detect = getattr(engine, "detect_anomaly", None)
            if callable(detect):
                return detect
        except Exception as exc:
            LOGGER.warning("AIEngine init failed, using basic detector: %s", exc)

    module_detect = getattr(ai_module, "detect_anomaly", None)
    if callable(module_detect):
        return module_detect

    LOGGER.warning("AI engine missing detect_anomaly, using basic detector")
    return _basic_detect_anomaly


def _fallback_send_alert(device_id: str, data: dict[str, Any], reason: str) -> None:
    save_alert(device_id, data, reason)
    LOGGER.warning(
        "[ALERT:FALLBACK] %s | %s | HR=%s SpO2=%s Temp=%s",
        device_id,
        reason,
        data.get("heart_rate"),
        data.get("spo2"),
        data.get("temperature"),
    )


def _fallback_send_fall_alert(device_id: str, data: dict[str, Any]) -> None:
    save_alert(device_id, data, "FALL_DETECTED")
    LOGGER.warning("[FALL:FALLBACK] %s | fall=%s", device_id, data.get("fall"))


def _load_alert_sender(
    function_name: str,
    fallback: Callable[..., None],
) -> Callable[..., None]:
    try:
        if __package__ in (None, ""):
            import server.alert_bot as alert_module
        else:
            from . import alert_bot as alert_module
    except Exception as exc:
        LOGGER.warning("Alert bot not available, using fallback %s: %s", function_name, exc)
        return fallback

    fn = getattr(alert_module, function_name, None)
    if callable(fn):
        return fn

    LOGGER.warning("Alert bot missing %s, using fallback", function_name)
    return fallback


DETECT_ANOMALY = _load_ai_detector()
SEND_ALERT = _load_alert_sender("send_alert", _fallback_send_alert)
SEND_FALL_ALERT = _load_alert_sender("send_fall_alert", _fallback_send_fall_alert)


def _extract_device_id(topic: str, payload: dict[str, Any]) -> str:
    parts = topic.split("/")
    if len(parts) >= 3 and parts[0] == "health":
        return parts[1]
    return str(payload.get("device_id", "unknown"))


def _parse_json_payload(raw: bytes) -> dict[str, Any]:
    text = raw.decode("utf-8").strip()
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("Expected JSON object payload")
    return parsed


def _reason_is_success(reason_code: Any) -> bool:
    if hasattr(reason_code, "is_failure"):
        return not bool(reason_code.is_failure)
    return reason_code == 0


def _handle_data_message(topic: str, data: dict[str, Any]) -> None:
    device_id = _extract_device_id(topic, data)
    data.setdefault("device_id", device_id)

    LOGGER.info(
        "[DATA] %s | HR=%s SpO2=%s Temp=%s Fall=%s Edge=%s",
        device_id,
        data.get("heart_rate"),
        data.get("spo2"),
        data.get("temperature"),
        data.get("fall"),
        data.get("edge_alert"),
    )

    detection = DETECT_ANOMALY(data)
    if len(detection) >= 3:
        is_anomaly, reason, confidence = detection[:3]
    else:
        is_anomaly, reason = detection[:2]
        confidence = 1.0 if is_anomaly else 0.0

    data["ai_score"] = round(float(confidence) * 100.0, 2)
    data["ai_confidence"] = round(float(confidence), 2)
    data["ai_reason"] = reason
    save_to_firebase(device_id, data)

    if is_anomaly:
        LOGGER.warning("[ANOMALY] %s | %s | confidence=%.2f", device_id, reason, confidence)
        SEND_ALERT(device_id, data, reason)

    if bool(data.get("fall", False)):
        LOGGER.warning("[FALL] %s | fall=true", device_id)
        SEND_FALL_ALERT(device_id, data)


def process_data_message(topic: str, data: dict[str, Any]) -> None:
    """Process a health payload from MQTT or a local demo API endpoint."""
    _handle_data_message(topic, data)


def _handle_medicine_message(topic: str, data: dict[str, Any]) -> None:
    device_id = _extract_device_id(topic, data)
    med_name = str(data.get("label") or data.get("name") or data.get("medicine_name") or "Medicine")
    event_type = str(data.get("type") or data.get("status") or "").lower()

    if event_type not in {"medicine_confirmed", "medicine_missed", "confirmed", "missed"}:
        LOGGER.info("[MEDICINE] %s | ignored type=%s payload=%s", device_id, event_type or "<empty>", data)
        return

    confirmed = event_type in {"medicine_confirmed", "confirmed"}
    save_medicine_log(device_id, med_name, confirmed)
    LOGGER.info(
        "[MEDICINE] %s | %s | confirmed=%s",
        device_id,
        med_name,
        confirmed,
    )


def on_connect(
    client: mqtt.Client,
    userdata: Any,
    flags: dict[str, Any],
    reason_code: Any,
    properties: Any = None,
) -> None:
    if not _reason_is_success(reason_code):
        LOGGER.error("[MQTT] Connect failed rc=%s", reason_code)
        return

    LOGGER.info("[MQTT] Connected to %s:%s", BROKER, PORT)
    client.subscribe(TOPIC_DATA, qos=1)
    client.subscribe(TOPIC_MEDICINE, qos=1)
    LOGGER.info("[MQTT] Subscribed: %s", TOPIC_DATA)
    LOGGER.info("[MQTT] Subscribed: %s", TOPIC_MEDICINE)


def on_disconnect(
    client: mqtt.Client,
    userdata: Any,
    disconnect_flags: Any,
    reason_code: Any,
    properties: Any = None,
) -> None:
    if _reason_is_success(reason_code):
        LOGGER.info("[MQTT] Disconnected cleanly")
        return
    LOGGER.warning("[MQTT] Connection lost rc=%s, auto-reconnect is active", reason_code)


def on_message(client: mqtt.Client, userdata: Any, msg: mqtt.MQTTMessage) -> None:
    try:
        data = _parse_json_payload(msg.payload)
        LOGGER.info("[MQTT] Received topic=%s payload=%s", msg.topic, json.dumps(data, ensure_ascii=False))

        if msg.topic.endswith("/data"):
            _handle_data_message(msg.topic, data)
        elif msg.topic.endswith("/medicine"):
            _handle_medicine_message(msg.topic, data)
        else:
            LOGGER.info("[MQTT] Ignored topic: %s", msg.topic)
    except Exception as exc:
        LOGGER.exception("[MQTT] Failed to process message on %s: %s", msg.topic, exc)


def build_client() -> mqtt.Client:
    if not BROKER:
        raise RuntimeError("Missing MQTT_BROKER in .env")
    if not USERNAME or not PASSWORD:
        raise RuntimeError("Missing MQTT_USERNAME or MQTT_PASSWORD in .env")

    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=CLIENT_ID,
        protocol=mqtt.MQTTv311,
    )
    client.username_pw_set(USERNAME, PASSWORD)
    client.tls_set(tls_version=ssl.PROTOCOL_TLS_CLIENT)
    client.reconnect_delay_set(min_delay=1, max_delay=30)
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message
    return client


def start_mqtt() -> None:
    client = build_client()
    LOGGER.info("[MQTT] Connecting to %s:%s ...", BROKER, PORT)
    client.connect(BROKER, PORT, keepalive=KEEPALIVE)
    client.loop_forever(retry_first_connection=True)


if __name__ == "__main__":
    try:
        start_mqtt()
    except KeyboardInterrupt:
        LOGGER.info("[MQTT] Stopped by user")
    except Exception as exc:
        LOGGER.exception("[MQTT] Fatal error: %s", exc)
        raise
