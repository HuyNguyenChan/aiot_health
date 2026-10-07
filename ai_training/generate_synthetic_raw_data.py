from __future__ import annotations

import csv
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = PROJECT_ROOT / "data" / "raw" / "health_data.csv"
RANDOM_SEED = 42

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

LABEL_COUNTS = {
    "normal_rest": 140,
    "normal_light": 120,
    "normal_moderate": 120,
    "normal_morning": 100,
    "normal_postmeal": 100,
    "stress": 120,
    "anomaly_high_hr": 110,
    "anomaly_low_spo2": 110,
    "fall": 100,
}


def clipped_int(rng: np.random.Generator, mean: float, std: float, low: int, high: int) -> int:
    return int(np.clip(round(rng.normal(mean, std)), low, high))


def clipped_float(
    rng: np.random.Generator,
    mean: float,
    std: float,
    low: float,
    high: float,
    digits: int = 2,
) -> float:
    return round(float(np.clip(rng.normal(mean, std), low, high)), digits)


def vitals_for_label(rng: np.random.Generator, label: str) -> tuple[int, int, float]:
    if label == "normal_rest":
        return (
            clipped_int(rng, 78, 8, 58, 100),
            clipped_int(rng, 98, 1.2, 95, 100),
            clipped_float(rng, 36.4, 0.25, 35.8, 37.1),
        )
    if label == "normal_light":
        return (
            clipped_int(rng, 105, 9, 82, 130),
            clipped_int(rng, 97, 1.4, 94, 100),
            clipped_float(rng, 36.7, 0.28, 36.0, 37.4),
        )
    if label == "normal_moderate":
        return (
            clipped_int(rng, 132, 10, 105, 149),
            clipped_int(rng, 96, 1.6, 93, 100),
            clipped_float(rng, 37.0, 0.32, 36.2, 37.8),
        )
    if label == "normal_morning":
        return (
            clipped_int(rng, 68, 7, 50, 90),
            clipped_int(rng, 98, 1.1, 95, 100),
            clipped_float(rng, 36.1, 0.22, 35.5, 36.8),
        )
    if label == "normal_postmeal":
        return (
            clipped_int(rng, 94, 9, 72, 124),
            clipped_int(rng, 97, 1.2, 94, 100),
            clipped_float(rng, 36.8, 0.25, 36.1, 37.4),
        )
    if label == "stress":
        return (
            clipped_int(rng, 128, 11, 100, 150),
            clipped_int(rng, 96, 1.8, 93, 100),
            clipped_float(rng, 37.1, 0.35, 36.3, 38.0),
        )
    if label == "anomaly_high_hr":
        return (
            clipped_int(rng, 165, 10, 151, 190),
            clipped_int(rng, 96, 2.0, 92, 100),
            clipped_float(rng, 37.3, 0.45, 36.4, 38.4),
        )
    if label == "anomaly_low_spo2":
        return (
            clipped_int(rng, 112, 16, 75, 145),
            clipped_int(rng, 88, 2.2, 82, 91),
            clipped_float(rng, 36.8, 0.35, 36.0, 37.8),
        )
    if label == "fall":
        return (
            clipped_int(rng, 112, 18, 70, 150),
            clipped_int(rng, 96, 2.0, 92, 100),
            clipped_float(rng, 36.8, 0.35, 36.0, 37.8),
        )
    raise ValueError(f"Unknown label: {label}")


def accel_for_label(rng: np.random.Generator, label: str) -> tuple[float, float, float, bool]:
    if label == "fall":
        if rng.random() < 0.45:
            return (
                clipped_float(rng, 0.0, 0.08, -0.25, 0.25, 3),
                clipped_float(rng, 0.0, 0.08, -0.25, 0.25, 3),
                clipped_float(rng, 0.08, 0.06, 0.0, 0.25, 3),
                True,
            )
        return (
            clipped_float(rng, rng.choice([-1.8, 1.8]), 0.55, -3.0, 3.0, 3),
            clipped_float(rng, rng.choice([-1.4, 1.4]), 0.55, -3.0, 3.0, 3),
            clipped_float(rng, rng.choice([0.1, 2.8]), 0.35, -0.2, 3.4, 3),
            True,
        )

    activity = {
        "normal_rest": 0.04,
        "normal_morning": 0.06,
        "normal_postmeal": 0.08,
        "normal_light": 0.18,
        "stress": 0.16,
        "normal_moderate": 0.35,
        "anomaly_high_hr": 0.20,
        "anomaly_low_spo2": 0.10,
    }.get(label, 0.08)
    return (
        round(float(rng.normal(0.04, activity)), 3),
        round(float(rng.normal(0.03, activity)), 3),
        round(float(rng.normal(0.99, activity)), 3),
        False,
    )


def ecg_for_hr(rng: np.random.Generator, heart_rate: int) -> tuple[int, int, int]:
    baseline = 2048 + np.clip((heart_rate - 80) * 1.4, -220, 240)
    ecg_raw_avg = int(np.clip(round(rng.normal(baseline, 85)), 450, 3600))
    ecg_raw = int(np.clip(round(rng.normal(ecg_raw_avg, 420)), 0, 4095))
    ecg_mv = int(round(ecg_raw_avg * 3300 / 4095))
    return ecg_raw, ecg_mv, ecg_raw_avg


def generate_rows() -> list[dict[str, object]]:
    rng = np.random.default_rng(RANDOM_SEED)
    timestamp = datetime.now().replace(microsecond=0) - timedelta(hours=3)
    rows: list[dict[str, object]] = []

    for label, count in LABEL_COUNTS.items():
        session_id = f"synthetic_ad8232_{label}"
        for _ in range(count):
            heart_rate, spo2, temperature = vitals_for_label(rng, label)
            accel_x, accel_y, accel_z, fall_detect = accel_for_label(rng, label)
            ecg_raw, ecg_mv, ecg_raw_avg = ecg_for_hr(rng, heart_rate)

            rows.append(
                {
                    "timestamp": timestamp.isoformat(),
                    "device_id": "patient_001",
                    "heart_rate": heart_rate,
                    "heart_rate_valid": True,
                    "heart_rate_source": "synthetic_ad8232",
                    "spo2": spo2,
                    "spo2_valid": True,
                    "spo2_source": "synthetic_max30102",
                    "temperature": temperature,
                    "ecg_raw": ecg_raw,
                    "ecg_mv": ecg_mv,
                    "ecg_raw_avg": ecg_raw_avg,
                    "ecg_lead_off": False,
                    "ecg_lo_plus": False,
                    "ecg_lo_minus": False,
                    "accel_x": accel_x,
                    "accel_y": accel_y,
                    "accel_z": accel_z,
                    "fall_detect": fall_detect,
                    "label": label,
                    "session_id": session_id,
                }
            )
            timestamp += timedelta(seconds=5)

    rng.shuffle(rows)
    return rows


def main() -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    rows = generate_rows()
    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=HEADERS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} synthetic AD8232/MAX30102 rows to {OUTPUT_PATH}")
    print("This dataset is for pipeline/demo testing. Replace with real sensor rows before final evaluation.")


if __name__ == "__main__":
    main()
