from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def ai_score_percent(row: dict[str, Any] | pd.Series) -> float:
    score = row.get("ai_score", row.get("anomaly_score", None))
    if score not in (None, ""):
        value = as_float(score)
        return value if value > 1 else value * 100

    confidence = as_float(row.get("ai_confidence", row.get("confidence", 0.0)))
    return confidence if confidence > 1 else confidence * 100


def parse_time_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    if "timestamp" in df.columns:
        numeric_ts = pd.to_numeric(df["timestamp"], errors="coerce")
        if numeric_ts.notna().any():
            unit = "ms" if numeric_ts.max() > 10_000_000_000 else "s"
            df["time"] = pd.to_datetime(numeric_ts, unit=unit, errors="coerce")
        else:
            df["time"] = pd.to_datetime(df["timestamp"], errors="coerce")
    elif "time" in df.columns:
        df["time"] = pd.to_datetime(df["time"], errors="coerce")
    elif "updated_at" in df.columns:
        df["time"] = pd.to_datetime(df["updated_at"], errors="coerce")
    else:
        df["time"] = pd.date_range(end=datetime.now(), periods=len(df), freq="5min")

    df["time"] = df["time"].fillna(pd.Timestamp.now())
    return df.sort_values("time")


def status_level(metric: str, value: float, hr_max: int, spo2_min: int, temp_max: float) -> str:
    if metric == "hr":
        if value and (value < 40 or value > hr_max):
            return "danger"
        if value and (value < 60 or value > 100):
            return "warn"
        return "ok"
    if metric == "spo2":
        if value and value < spo2_min:
            return "danger"
        if value and value < 95:
            return "warn"
        return "ok"
    if metric == "temp":
        if value and value > temp_max:
            return "danger"
        if value and value > 37.5:
            return "warn"
        return "ok"
    if metric == "fall":
        return "danger" if value else "ok"
    return "ok"


def status_dot(level: str) -> str:
    return {"danger": "🔴", "warn": "🟡", "ok": "🟢"}.get(level, "⚪")


def short_time(value: Any) -> str:
    if value in (None, ""):
        return "--"
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return str(value)
    return parsed.strftime("%H:%M %d/%m")
