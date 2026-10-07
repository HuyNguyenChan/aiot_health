from __future__ import annotations

import json
import logging
import math
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import MinMaxScaler


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODELS_DIR = PROJECT_ROOT / "models"

LOGGER = logging.getLogger("ai_engine")

V3_FEATURE_COLUMNS = [
    "heart_rate",
    "spo2",
    "temperature",
    "hr_rolling_mean",
    "hr_rolling_std",
    "spo2_change",
    "accel_mag",
]

LEGACY_FEATURE_COLUMNS = [
    "heart_rate",
    "spo2",
    "temperature",
    "accel_mag",
    "hrv_proxy",
    "hr_mean_5",
    "spo2_drop",
    "ecg_raw_avg",
    "ecg_mv",
    "ecg_lead_off",
]

LSTM_WINDOW = 24
STEP_MINUTES = 5


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        LOGGER.warning("[AI] Could not read %s: %s", path.name, exc)
        return {}


class AIEngine:
    def __init__(self) -> None:
        self.model_info = _load_json(MODELS_DIR / "model_info.json")
        self.scaler = self._load_joblib("scaler.pkl")
        self.if_model = self._load_joblib("isolation_forest.pkl")
        self.lstm = self._load_lstm("lstm_heart_predict.h5")

        self.feature_columns = self._resolve_feature_columns()
        self.patient_models: dict[str, tuple[Any, Any]] = {}
        self._load_all_patient_models()
        self._load_ecg_model()

    def _resolve_feature_columns(self) -> list[str]:
        info_features = self.model_info.get("features")
        if isinstance(info_features, list) and info_features:
            return [str(feature) for feature in info_features]

        scaler_features = getattr(self.scaler, "feature_names_in_", None)
        if scaler_features is not None:
            return [str(feature) for feature in scaler_features]

        return V3_FEATURE_COLUMNS

    def _load_joblib(self, filename: str) -> Any | None:
        path = MODELS_DIR / filename
        if not path.exists():
            LOGGER.warning("[AI] Missing model file: %s", path)
            return None
        try:
            model = joblib.load(path)
            LOGGER.info("[AI] Loaded %s", filename)
            return model
        except Exception as exc:
            LOGGER.warning("[AI] Failed to load %s: %s", filename, exc)
            return None

    def _load_lstm(self, filename: str) -> Any | None:
        path = MODELS_DIR / filename
        if not path.exists():
            LOGGER.warning("[AI] Missing model file: %s", path)
            return None
        try:
            import tensorflow as tf

            model = tf.keras.models.load_model(path, compile=False)
            LOGGER.info("[AI] Loaded %s", filename)
            return model
        except Exception as exc:
            LOGGER.warning("[AI] Failed to load %s directly: %s", filename, exc)

        try:
            import tensorflow as tf

            model = tf.keras.Sequential(
                [
                    tf.keras.layers.Input(shape=(LSTM_WINDOW, 1), name="input_layer"),
                    tf.keras.layers.LSTM(64, return_sequences=True),
                    tf.keras.layers.Dropout(0.2),
                    tf.keras.layers.LSTM(32),
                    tf.keras.layers.Dropout(0.2),
                    tf.keras.layers.Dense(16, activation="relu"),
                    tf.keras.layers.Dense(1),
                ]
            )
            model.load_weights(path)
            LOGGER.info("[AI] Loaded %s weights with fallback architecture", filename)
            return model
        except Exception as exc:
            LOGGER.warning("[AI] Failed to load %s with fallback architecture: %s", filename, exc)
            return None

    def _load_ecg_model(self) -> None:
        self.ecg_model = None
        self.ecg_threshold = 0.05

        model_path = MODELS_DIR / "ecg_autoencoder.h5"
        threshold_path = MODELS_DIR / "ecg_threshold.npy"
        if not model_path.exists() or not threshold_path.exists():
            LOGGER.warning("[AI] ECG model not found; ECG voting disabled")
            return

        try:
            import tensorflow as tf

            self.ecg_model = tf.keras.models.load_model(model_path, compile=False)
            self.ecg_threshold = float(np.load(threshold_path))
            LOGGER.info("[AI] ECG Autoencoder loaded, threshold=%.4f", self.ecg_threshold)
            return
        except Exception as exc:
            LOGGER.warning("[AI] ECG model direct load failed: %s", exc)

        try:
            import tensorflow as tf

            inputs = tf.keras.layers.Input(shape=(250, 1), name="ecg_window")
            x = tf.keras.layers.Conv1D(16, 3, padding="same", activation="relu")(inputs)
            x = tf.keras.layers.MaxPooling1D(5, padding="same")(x)
            x = tf.keras.layers.Conv1D(8, 3, padding="same", activation="relu")(x)
            encoded = tf.keras.layers.MaxPooling1D(5, padding="same", name="latent_10x8")(x)
            x = tf.keras.layers.Conv1D(8, 3, padding="same", activation="relu")(encoded)
            x = tf.keras.layers.UpSampling1D(5)(x)
            x = tf.keras.layers.Conv1D(16, 3, padding="same", activation="relu")(x)
            x = tf.keras.layers.UpSampling1D(5)(x)
            outputs = tf.keras.layers.Conv1D(
                1,
                3,
                padding="same",
                activation="sigmoid",
                name="reconstruction",
            )(x)
            self.ecg_model = tf.keras.Model(inputs, outputs, name="ecg_conv1d_autoencoder")
            self.ecg_model.load_weights(model_path)
            self.ecg_threshold = float(np.load(threshold_path))
            LOGGER.info("[AI] ECG Autoencoder weights loaded, threshold=%.4f", self.ecg_threshold)
        except Exception as exc:
            self.ecg_model = None
            self.ecg_threshold = 0.05
            LOGGER.warning("[AI] ECG model fallback load failed: %s", exc)

    def _load_all_patient_models(self) -> None:
        if not MODELS_DIR.exists():
            return

        for if_path in MODELS_DIR.glob("*_if.pkl"):
            device_id = if_path.name.removesuffix("_if.pkl")
            scaler_path = MODELS_DIR / f"{device_id}_scaler.pkl"
            if not scaler_path.exists():
                continue
            try:
                self.patient_models[device_id] = (joblib.load(if_path), joblib.load(scaler_path))
                LOGGER.info("[AI] Loaded personal model: %s", device_id)
            except Exception as exc:
                LOGGER.warning("[AI] Failed to load personal model %s: %s", device_id, exc)

    @staticmethod
    def _accel_mag(data: dict[str, Any]) -> float:
        explicit = data.get("accel_mag")
        if explicit not in (None, ""):
            return _as_float(explicit)

        ax = _as_float(data.get("accel_x"), 0.0)
        ay = _as_float(data.get("accel_y"), 0.0)
        az = _as_float(data.get("accel_z"), 1.0)
        if ax == 0.0 and ay == 0.0 and az == 0.0 and not _as_bool(data.get("fall", False)):
            return 1.0
        return math.sqrt(ax * ax + ay * ay + az * az)

    def _feature_values(self, data: dict[str, Any]) -> dict[str, float]:
        heart_rate = _as_float(data.get("heart_rate"), 70.0)
        spo2 = _as_float(data.get("spo2"), 98.0)
        temperature = _as_float(data.get("temperature"), 36.5)
        accel_mag = self._accel_mag(data)
        hr_rolling_mean = _as_float(
            data.get("hr_rolling_mean", data.get("hr_mean_5", data.get("hr_mean5", heart_rate))),
            heart_rate,
        )
        hr_rolling_std = _as_float(
            data.get("hr_rolling_std", data.get("hrv_proxy", data.get("hr_std5", 2.0))),
            2.0,
        )
        spo2_change = _as_float(
            data.get("spo2_change", data.get("spo2_drop", data.get("spo2_diff", 0.0))),
            0.0,
        )
        ecg_lead_off = 1.0 if _as_bool(data.get("ecg_lead_off", False)) else 0.0

        return {
            "heart_rate": heart_rate,
            "spo2": spo2,
            "temperature": temperature,
            "hr_rolling_mean": hr_rolling_mean,
            "hr_rolling_std": hr_rolling_std,
            "spo2_change": spo2_change,
            "accel_mag": accel_mag,
            "hr_mean_5": hr_rolling_mean,
            "hrv_proxy": hr_rolling_std,
            "spo2_drop": spo2_change,
            "ecg_raw_avg": _as_float(data.get("ecg_raw_avg", data.get("ecg_raw", 2048.0)), 2048.0),
            "ecg_mv": _as_float(data.get("ecg_mv"), 1650.0),
            "ecg_lead_off": ecg_lead_off,
        }

    def _make_feature_frame(self, data: dict[str, Any], columns: list[str] | None = None) -> pd.DataFrame:
        values = self._feature_values(data)
        selected_columns = columns or self.feature_columns
        row = {column: values.get(column, 0.0) for column in selected_columns}
        return pd.DataFrame([row], columns=selected_columns)

    def _rule_vote(self, data: dict[str, Any]) -> tuple[int, list[str]]:
        values = self._feature_values(data)
        hr = values["heart_rate"]
        spo2 = values["spo2"]
        temp = values["temperature"]
        accel_mag = values["accel_mag"]
        reasons: list[str] = []

        edge_reason = str(data.get("alert_reason", "")).strip()
        if _as_bool(data.get("edge_alert", False)) and edge_reason:
            reasons.append(edge_reason)
            return 1, reasons
        if spo2 and spo2 < 88:
            reasons.append(f"SpO2 nguy hiem: {spo2:.0f}%")
            return 1, reasons
        if hr > 160 or (0 < hr < 35):
            reasons.append(f"HR cuc doan: {hr:.0f}bpm")
            return 1, reasons
        if temp > 38.5:
            reasons.append(f"Sot cao: {temp:.1f}C")
            return 1, reasons
        if _as_bool(data.get("fall", data.get("fall_detect", False))):
            reasons.append("Phat hien nga")
            return 1, reasons
        if accel_mag > 2.5 or accel_mag < 0.3:
            reasons.append(f"Gia toc bat thuong: {accel_mag:.2f}g")
            return 1, reasons
        return 0, reasons

    def _isolation_vote(self, data: dict[str, Any]) -> tuple[int, str | None]:
        device_id = str(data.get("device_id", "")).strip()
        if device_id in self.patient_models:
            model, scaler = self.patient_models[device_id]
            columns = list(getattr(scaler, "feature_names_in_", self.feature_columns))
        else:
            model, scaler = self.if_model, self.scaler
            columns = self.feature_columns

        if model is None or scaler is None:
            raise RuntimeError("Model not ready")

        features = self._make_feature_frame(data, columns)
        prediction = int(model.predict(scaler.transform(features))[0])
        if prediction == -1:
            try:
                score = float(model.decision_function(scaler.transform(features))[0])
                return 1, f"Isolation Forest pattern (score={score:.3f})"
            except Exception:
                return 1, "Isolation Forest pattern"
        return 0, None

    def detect_ecg_anomaly(self, ecg_samples: list[Any]) -> tuple[bool, float]:
        if self.ecg_model is None or len(ecg_samples) < 250:
            return False, 0.0

        ecg = np.asarray(ecg_samples[:250], dtype=np.float32)
        ecg_range = float(ecg.max() - ecg.min())
        if ecg_range < 10:
            return False, 0.0

        ecg = (ecg - float(ecg.min())) / ecg_range
        ecg_input = ecg.reshape(1, 250, 1)
        recon = self.ecg_model.predict(ecg_input, verbose=0)
        error = float(np.mean(np.abs(recon - ecg_input)))
        return error > self.ecg_threshold, error

    def detect_anomaly(self, data: dict[str, Any]) -> tuple[bool, str, float]:
        try:
            if self.if_model is None or self.scaler is None:
                return False, "Model not ready", 0.0

            votes: list[int] = []
            reasons: list[str] = []

            rule_vote, rule_reasons = self._rule_vote(data)
            votes.append(rule_vote)
            reasons.extend(rule_reasons)
            if rule_vote == 1:
                return True, " + ".join(reasons), 1.0

            if_vote, if_reason = self._isolation_vote(data)
            votes.append(if_vote)
            if if_reason:
                reasons.append(if_reason)

            ecg_samples = data.get("ecg_samples", data.get("ecg_window", []))
            if isinstance(ecg_samples, list) and len(ecg_samples) >= 250 and not _as_bool(data.get("ecg_lead_off", False)):
                ecg_anomaly, ecg_error = self.detect_ecg_anomaly(ecg_samples)
                votes.append(1 if ecg_anomaly else 0)
                if ecg_anomaly:
                    reasons.append(f"ECG bat thuong (err={ecg_error:.3f})")

            confidence = sum(votes) / len(votes) if votes else 0.0
            is_anomaly = confidence >= (2 / 3)
            reason = " + ".join(reasons) if reasons else "Binh thuong"
            return is_anomaly, reason, round(confidence, 2)
        except Exception as exc:
            LOGGER.warning("[AI] detect_anomaly failed: %s", exc)
            return False, "Model not ready", 0.0

    def retrain_patient(self, device_id: str, history: list[dict[str, Any]]) -> bool:
        if len(history) < 100:
            LOGGER.info("[RETRAIN] %s: only %s samples, need >=100", device_id, len(history))
            return False

        df = pd.DataFrame(history)
        rows = [self._feature_values(row) for row in df.to_dict("records")]
        train_df = pd.DataFrame(rows)

        if "edge_alert" in df:
            train_df = train_df[~df["edge_alert"].fillna(False).astype(bool).to_numpy()]
        if len(train_df) < 50:
            train_df = pd.DataFrame(rows)

        X = train_df[V3_FEATURE_COLUMNS].fillna(train_df[V3_FEATURE_COLUMNS].mean())
        scaler = MinMaxScaler().fit(X)
        model = IsolationForest(contamination=0.05, n_estimators=200, random_state=42)
        model.fit(scaler.transform(X))

        MODELS_DIR.mkdir(exist_ok=True)
        joblib.dump(model, MODELS_DIR / f"{device_id}_if.pkl")
        joblib.dump(scaler, MODELS_DIR / f"{device_id}_scaler.pkl")
        self.patient_models[device_id] = (model, scaler)
        LOGGER.info("[RETRAIN] %s: saved personal model with %s samples", device_id, len(X))
        return True

    def predict_trend(self, history: list[dict[str, Any]], n: int = 72, steps: int | None = None) -> list[dict[str, float | int]]:
        total_steps = int(steps if steps is not None else n)
        if self.lstm is None:
            LOGGER.warning("[AI] LSTM model not ready")
            return []

        heart_rates = [
            _as_float(item.get("heart_rate"))
            for item in history
            if 30 <= _as_float(item.get("heart_rate")) <= 220
        ]
        if len(heart_rates) < LSTM_WINDOW:
            LOGGER.warning("[AI] Not enough HR history for LSTM: %s/%s", len(heart_rates), LSTM_WINDOW)
            return []

        try:
            current = np.asarray(heart_rates[-LSTM_WINDOW:], dtype=np.float32).reshape(1, LSTM_WINDOW, 1)
            predictions: list[dict[str, float | int]] = []
            for index in range(max(0, total_steps)):
                pred = float(self.lstm.predict(current, verbose=0).reshape(-1)[0])
                pred = max(30.0, min(220.0, pred))
                predictions.append(
                    {
                        "step": index + 1,
                        "minutes_ahead": (index + 1) * STEP_MINUTES,
                        "heart_rate": round(pred, 2),
                    }
                )
                current = np.roll(current, -1, axis=1)
                current[0, -1, 0] = pred
            return predictions
        except Exception as exc:
            LOGGER.warning("[AI] LSTM prediction failed: %s", exc)
            return []


__all__ = ["AIEngine"]
