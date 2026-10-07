from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import MinMaxScaler


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_PATH = PROJECT_ROOT / "data" / "raw" / "health_data.csv"
OUT_DIR = PROJECT_ROOT / "data" / "processed"

REAL_CLEAN_PATH = OUT_DIR / "health_data_real_clean.csv"
FEATURES_PATH = OUT_DIR / "health_data_features.csv"
TRAIN_PATH = OUT_DIR / "health_data_train.csv"
TEST_PATH = OUT_DIR / "health_data_test.csv"
SCALED_PATH = OUT_DIR / "health_data_train_scaled.csv"
SUMMARY_PATH = OUT_DIR / "dataset_summary.json"

RANDOM_SEED = 42
FEATURE_COLUMNS = [
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

OPTIONAL_COLUMNS_DEFAULTS = {
    "heart_rate_valid": True,
    "heart_rate_source": "legacy",
    "spo2_valid": True,
    "spo2_source": "legacy",
    "ecg_raw": 0,
    "ecg_mv": 0,
    "ecg_raw_avg": 0,
    "ecg_lead_off": False,
    "ecg_lo_plus": False,
    "ecg_lo_minus": False,
}


def _to_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    return text in {"true", "1", "yes", "y"}


def load_raw() -> pd.DataFrame:
    if not RAW_PATH.exists():
        raise FileNotFoundError(f"Raw dataset not found: {RAW_PATH}")

    df = pd.read_csv(RAW_PATH)
    required = {
        "timestamp",
        "device_id",
        "heart_rate",
        "spo2",
        "temperature",
        "accel_x",
        "accel_y",
        "accel_z",
        "fall_detect",
        "label",
        "session_id",
    }
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    for column, default in OPTIONAL_COLUMNS_DEFAULTS.items():
        if column not in df.columns:
            df[column] = default
    return df


def clean_real_data(df: pd.DataFrame) -> pd.DataFrame:
    clean = df.copy()
    clean["timestamp"] = pd.to_datetime(clean["timestamp"], errors="coerce")
    clean["label"] = clean["label"].fillna("").astype(str).str.strip()
    clean["session_id"] = clean["session_id"].fillna("").astype(str).str.strip()

    numeric_columns = [
        "heart_rate",
        "spo2",
        "temperature",
        "accel_x",
        "accel_y",
        "accel_z",
        "ecg_raw",
        "ecg_mv",
        "ecg_raw_avg",
    ]
    for column in numeric_columns:
        clean[column] = pd.to_numeric(clean[column], errors="coerce")
    clean["fall_detect"] = clean["fall_detect"].map(_to_bool)
    for column in ["heart_rate_valid", "spo2_valid", "ecg_lead_off", "ecg_lo_plus", "ecg_lo_minus"]:
        clean[column] = clean[column].map(_to_bool)

    clean = clean.dropna(subset=["timestamp", "heart_rate", "spo2", "temperature"])
    clean = clean[clean["label"] != ""]
    clean = clean[(clean["heart_rate"] >= 35) & (clean["heart_rate"] <= 220)]
    clean = clean[(clean["spo2"] >= 50) & (clean["spo2"] <= 100)]
    clean = clean[(clean["temperature"] >= 30) & (clean["temperature"] <= 43)]
    clean = clean[clean["heart_rate_valid"]]
    clean = clean[clean["spo2_valid"]]
    clean = clean[~clean["ecg_lead_off"]]

    clean["heart_rate_source"] = clean["heart_rate_source"].fillna("").astype(str).str.strip()
    clean["spo2_source"] = clean["spo2_source"].fillna("").astype(str).str.strip()
    clean.loc[clean["heart_rate_source"] == "", "heart_rate_source"] = "legacy"
    clean.loc[clean["spo2_source"] == "", "spo2_source"] = "legacy"
    clean.loc[clean["ecg_raw_avg"] <= 0, "ecg_raw_avg"] = 2048
    clean.loc[clean["ecg_mv"] <= 0, "ecg_mv"] = 1650
    clean = clean.drop_duplicates()
    clean = clean.sort_values("timestamp").reset_index(drop=True)
    clean["source"] = "real"
    clean["is_synthetic"] = False
    return clean


def add_features(df: pd.DataFrame) -> pd.DataFrame:
    featured = df.copy()
    featured.loc[featured["ecg_raw_avg"] <= 0, "ecg_raw_avg"] = 2048
    featured.loc[featured["ecg_mv"] <= 0, "ecg_mv"] = 1650
    featured["ecg_lead_off"] = featured["ecg_lead_off"].astype(bool).astype(int)
    featured["accel_mag"] = np.sqrt(
        featured["accel_x"].pow(2) + featured["accel_y"].pow(2) + featured["accel_z"].pow(2)
    )
    featured["hrv_proxy"] = (
        featured.groupby("session_id")["heart_rate"]
        .rolling(5, min_periods=2)
        .std()
        .reset_index(level=0, drop=True)
        .fillna(0)
    )
    featured["hr_mean_5"] = (
        featured.groupby("session_id")["heart_rate"]
        .rolling(5, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )
    featured["spo2_drop"] = (
        featured.groupby("session_id")["spo2"].diff().fillna(0).clip(upper=0).abs()
    )
    return featured


def derive_training_labels(df: pd.DataFrame) -> pd.DataFrame:
    labeled = df.copy()
    labeled["label_detail"] = labeled["label"]

    labeled.loc[labeled["heart_rate"] > 150, "label_detail"] = "anomaly_high_hr"
    labeled.loc[labeled["spo2"] < 92, "label_detail"] = "anomaly_low_spo2"
    labeled.loc[labeled["fall_detect"], "label_detail"] = "fall"

    anomaly_labels = {
        "anomaly_high_hr",
        "anomaly_low_spo2",
        "fall",
    }
    labeled["is_anomaly"] = labeled["label_detail"].isin(anomaly_labels)
    labeled["target"] = labeled["is_anomaly"].astype(int)
    return labeled


def fill_ecg_columns(sample: pd.DataFrame, rng: np.random.Generator) -> None:
    count = len(sample)
    sample["heart_rate_valid"] = True
    sample["heart_rate_source"] = "synthetic_ad8232"
    sample["spo2_valid"] = True
    sample["spo2_source"] = "synthetic_max30102"
    sample["ecg_lead_off"] = False
    sample["ecg_lo_plus"] = False
    sample["ecg_lo_minus"] = False

    centered_hr = sample["heart_rate"].astype(float).to_numpy()
    baseline = 2048 + np.clip((centered_hr - 80) * 1.5, -180, 180)
    sample["ecg_raw_avg"] = np.round(baseline + rng.normal(0, 45, size=count)).astype(int)
    sample["ecg_raw"] = sample["ecg_raw_avg"] + np.round(rng.normal(0, 80, size=count)).astype(int)
    sample["ecg_raw"] = sample["ecg_raw"].clip(0, 4095)
    sample["ecg_raw_avg"] = sample["ecg_raw_avg"].clip(0, 4095)
    sample["ecg_mv"] = np.round(sample["ecg_raw_avg"] * 3300 / 4095).astype(int)


def make_synthetic_labeled_data(base: pd.DataFrame) -> pd.DataFrame:
    rng = np.random.default_rng(RANDOM_SEED)
    normal = base[~base["is_anomaly"]].copy()
    if normal.empty:
        normal = base.copy()

    synthetic_sets: list[pd.DataFrame] = []
    templates = [
        ("normal_rest", 80),
        ("normal_light", 80),
        ("normal_moderate", 80),
        ("normal_morning", 80),
        ("normal_postmeal", 80),
        ("stress", 80),
        ("anomaly_high_hr", 80),
        ("anomaly_low_spo2", 80),
        ("fall", 80),
    ]

    for label, count in templates:
        sample = normal.sample(n=count, replace=True, random_state=RANDOM_SEED + len(synthetic_sets))
        sample = sample.reset_index(drop=True)
        sample["source"] = f"synthetic_{label}"
        sample["is_synthetic"] = True
        sample["label"] = label
        sample["label_detail"] = label
        sample["is_anomaly"] = label in {"anomaly_high_hr", "anomaly_low_spo2", "fall"}
        sample["target"] = sample["is_anomaly"].astype(int)
        sample["fall_detect"] = False

        # These ranges are seeded from the collected baseline rows, then shifted into
        # plausible zones for each class used by the project label menu.
        if label == "normal_rest":
            sample["heart_rate"] = rng.integers(70, 101, size=count)
            sample["spo2"] = rng.integers(96, 101, size=count)
            sample["temperature"] = np.round(rng.uniform(35.8, 36.8, size=count), 2)
            sample["accel_x"] = np.round(rng.normal(0.0, 0.04, size=count), 3)
            sample["accel_y"] = np.round(rng.normal(0.0, 0.04, size=count), 3)
            sample["accel_z"] = np.round(rng.normal(0.98, 0.04, size=count), 3)
        elif label == "normal_light":
            sample["heart_rate"] = rng.integers(90, 121, size=count)
            sample["spo2"] = rng.integers(95, 101, size=count)
            sample["temperature"] = np.round(rng.uniform(36.0, 37.1, size=count), 2)
            sample["accel_x"] = np.round(rng.normal(0.12, 0.18, size=count), 3)
            sample["accel_y"] = np.round(rng.normal(0.08, 0.18, size=count), 3)
            sample["accel_z"] = np.round(rng.normal(1.0, 0.18, size=count), 3)
        elif label == "normal_moderate":
            sample["heart_rate"] = rng.integers(115, 146, size=count)
            sample["spo2"] = rng.integers(94, 100, size=count)
            sample["temperature"] = np.round(rng.uniform(36.3, 37.5, size=count), 2)
            sample["accel_x"] = np.round(rng.normal(0.2, 0.35, size=count), 3)
            sample["accel_y"] = np.round(rng.normal(0.15, 0.35, size=count), 3)
            sample["accel_z"] = np.round(rng.normal(1.05, 0.35, size=count), 3)
        elif label == "normal_morning":
            sample["heart_rate"] = rng.integers(62, 91, size=count)
            sample["spo2"] = rng.integers(96, 101, size=count)
            sample["temperature"] = np.round(rng.uniform(35.6, 36.6, size=count), 2)
            sample["accel_x"] = np.round(rng.normal(0.02, 0.07, size=count), 3)
            sample["accel_y"] = np.round(rng.normal(0.02, 0.07, size=count), 3)
            sample["accel_z"] = np.round(rng.normal(0.98, 0.07, size=count), 3)
        elif label == "normal_postmeal":
            sample["heart_rate"] = rng.integers(88, 126, size=count)
            sample["spo2"] = rng.integers(95, 101, size=count)
            sample["temperature"] = np.round(rng.uniform(36.2, 37.3, size=count), 2)
            sample["accel_x"] = np.round(rng.normal(0.04, 0.09, size=count), 3)
            sample["accel_y"] = np.round(rng.normal(0.04, 0.09, size=count), 3)
            sample["accel_z"] = np.round(rng.normal(0.99, 0.09, size=count), 3)
        elif label == "stress":
            sample["heart_rate"] = rng.integers(120, 151, size=count)
            sample["spo2"] = rng.integers(94, 100, size=count)
            sample["temperature"] = np.round(rng.uniform(36.4, 37.8, size=count), 2)
            sample["accel_x"] = np.round(rng.normal(0.08, 0.16, size=count), 3)
            sample["accel_y"] = np.round(rng.normal(0.08, 0.16, size=count), 3)
            sample["accel_z"] = np.round(rng.normal(1.0, 0.16, size=count), 3)
        elif label == "anomaly_high_hr":
            sample["heart_rate"] = rng.integers(151, 186, size=count)
            sample["spo2"] = rng.integers(92, 99, size=count)
            sample["temperature"] = np.round(rng.uniform(36.5, 38.2, size=count), 2)
        elif label == "anomaly_low_spo2":
            sample["heart_rate"] = rng.integers(85, 141, size=count)
            sample["spo2"] = rng.integers(84, 92, size=count)
            sample["temperature"] = np.round(rng.uniform(36.0, 37.8, size=count), 2)
        elif label == "fall":
            sample["heart_rate"] = rng.integers(85, 150, size=count)
            sample["spo2"] = rng.integers(92, 100, size=count)
            sample["temperature"] = np.round(rng.uniform(36.0, 37.6, size=count), 2)
            sample["fall_detect"] = True
            sample["accel_x"] = np.round(rng.uniform(-2.7, 2.7, size=count), 3)
            sample["accel_y"] = np.round(rng.uniform(-2.7, 2.7, size=count), 3)
            sample["accel_z"] = np.round(rng.choice([0.05, 2.8], size=count), 3)

        fill_ecg_columns(sample, rng)
        synthetic_sets.append(sample)

    synthetic = pd.concat(synthetic_sets, ignore_index=True)
    synthetic["timestamp"] = pd.date_range(
        start=base["timestamp"].max() + pd.Timedelta(seconds=5),
        periods=len(synthetic),
        freq="5s",
    )
    synthetic["device_id"] = synthetic["device_id"].fillna("patient_001")
    synthetic["session_id"] = "synthetic_label_demo"
    return synthetic


def save_scaled_training(train_df: pd.DataFrame) -> None:
    scaler = MinMaxScaler()
    scaled = train_df.copy()
    scaled[FEATURE_COLUMNS] = scaler.fit_transform(scaled[FEATURE_COLUMNS])
    scaled.to_csv(SCALED_PATH, index=False)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    raw = load_raw()
    real_clean = clean_real_data(raw)
    real_featured = derive_training_labels(add_features(real_clean))
    synthetic = make_synthetic_labeled_data(real_featured)
    training = pd.concat([real_featured, synthetic], ignore_index=True)
    training = derive_training_labels(add_features(training)).sort_values("timestamp").reset_index(drop=True)

    stratify = training["label_detail"] if training["label_detail"].nunique() > 1 else None
    train_df, test_df = train_test_split(
        training,
        test_size=0.2,
        random_state=RANDOM_SEED,
        stratify=stratify,
    )
    train_df = train_df.sort_values("timestamp").reset_index(drop=True)
    test_df = test_df.sort_values("timestamp").reset_index(drop=True)

    real_featured.to_csv(REAL_CLEAN_PATH, index=False)
    training.to_csv(FEATURES_PATH, index=False)
    train_df.to_csv(TRAIN_PATH, index=False)
    test_df.to_csv(TEST_PATH, index=False)
    save_scaled_training(train_df)

    summary = {
        "raw_rows": int(len(raw)),
        "real_clean_rows": int(len(real_featured)),
        "training_rows": int(len(training)),
        "train_rows": int(len(train_df)),
        "test_rows": int(len(test_df)),
        "feature_columns": FEATURE_COLUMNS,
        "label_counts": training["label_detail"].value_counts().to_dict(),
        "source_counts": training["source"].value_counts().to_dict(),
        "note": (
            "Synthetic rows for labels 0-8 are generated from collected baseline data for demo training. "
            "After the hardware update, heart_rate is expected from AD8232 and SpO2 from MAX30102. "
            "Keep collecting real rows for every label and regenerate these files when available."
        ),
    }
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
