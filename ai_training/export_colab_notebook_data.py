from __future__ import annotations

from pathlib import Path

import joblib
import pandas as pd
from sklearn.preprocessing import MinMaxScaler


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_PATH = PROJECT_ROOT / "data" / "raw" / "health_data.csv"
OUT_DIR = PROJECT_ROOT / "ai_training" / "colab_export"

LABELED_PATH = OUT_DIR / "labeled_health_data.csv"
CLEAN_PATH = OUT_DIR / "health_data_clean.csv"
SCALER_PATH = OUT_DIR / "scaler.pkl"

FEATURES = [
    "heart_rate",
    "spo2",
    "temperature",
    "hr_rolling_mean",
    "hr_rolling_std",
    "spo2_change",
    "accel_mag",
]


def main() -> None:
    if not RAW_PATH.exists():
        raise FileNotFoundError(f"Raw dataset not found: {RAW_PATH}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(RAW_PATH)

    if "subject_id" not in df.columns:
        df["subject_id"] = df.get("device_id", "patient_001").fillna("patient_001")
    if "session" not in df.columns:
        df["session"] = df.get("session_id", "session_001").fillna("session_001")

    # Match the notebook's expected names while preserving the project schema too.
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna()
    df = df[(df["heart_rate"] > 30) & (df["heart_rate"] < 220)]
    df = df[(df["spo2"] >= 50) & (df["spo2"] <= 100)]
    df = df[(df["temperature"] > 30) & (df["temperature"] < 43)]

    df = df.sort_values(["subject_id", "session", "timestamp"]).reset_index(drop=True)
    df["hr_rolling_mean"] = df.groupby(["subject_id", "session"])["heart_rate"].transform(
        lambda x: x.rolling(5, min_periods=1).mean()
    )
    df["hr_rolling_std"] = df.groupby(["subject_id", "session"])["heart_rate"].transform(
        lambda x: x.rolling(5, min_periods=1).std().fillna(0)
    )
    df["spo2_change"] = df.groupby(["subject_id", "session"])["spo2"].transform(
        lambda x: x.diff().fillna(0)
    )
    df["accel_mag"] = (df["accel_x"] ** 2 + df["accel_y"] ** 2 + df["accel_z"] ** 2) ** 0.5

    labeled_df = df.copy()
    labeled_df["timestamp"] = labeled_df["timestamp"].dt.strftime("%Y-%m-%dT%H:%M:%S")
    labeled_df.to_csv(LABELED_PATH, index=False)

    scaler = MinMaxScaler()
    df_scaled = df.copy()
    df_scaled[FEATURES] = scaler.fit_transform(df[FEATURES])
    df_scaled["timestamp"] = df_scaled["timestamp"].dt.strftime("%Y-%m-%dT%H:%M:%S")
    df_scaled.to_csv(CLEAN_PATH, index=False)
    joblib.dump(scaler, SCALER_PATH)

    print(f"Total samples: {len(df)}")
    print(f"Subjects: {df['subject_id'].nunique()}")
    print("Label counts:")
    print(df["label"].value_counts())
    print("\nSaved:")
    print(f"  {LABELED_PATH}")
    print(f"  {CLEAN_PATH}")
    print(f"  {SCALER_PATH}")


if __name__ == "__main__":
    main()
