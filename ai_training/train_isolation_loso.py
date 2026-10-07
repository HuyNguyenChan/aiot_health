from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.metrics import f1_score
from sklearn.preprocessing import MinMaxScaler


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXPORT_DIR = PROJECT_ROOT / "ai_training" / "colab_export"
LABELED_PATH = EXPORT_DIR / "labeled_health_data.csv"
AUGMENTED_PATH = EXPORT_DIR / "health_data_augmented.csv"
MODEL_PATH = EXPORT_DIR / "isolation_forest.pkl"
SCALER_PATH = EXPORT_DIR / "scaler.pkl"
REPORT_PATH = EXPORT_DIR / "isolation_loso_report.json"

FEATURES = [
    "heart_rate",
    "spo2",
    "temperature",
    "hr_rolling_mean",
    "hr_rolling_std",
    "spo2_change",
    "accel_mag",
]

RANDOM_SEED = 42


def _load_labeled() -> pd.DataFrame:
    if not LABELED_PATH.exists():
        raise FileNotFoundError(
            f"Missing {LABELED_PATH}. Run ai_training/export_colab_notebook_data.py first."
        )
    return pd.read_csv(LABELED_PATH)


def _make_subject_augmented(df: pd.DataFrame, subjects: int = 4) -> pd.DataFrame:
    rng = np.random.default_rng(RANDOM_SEED)
    augmented: list[pd.DataFrame] = []

    for subject_index in range(subjects):
        clone = df.copy()
        clone["subject_id"] = f"subject_{subject_index + 1:02d}"
        clone["session"] = clone["session"].astype(str) + f"_s{subject_index + 1:02d}"

        hr_shift = rng.normal(0, 4)
        spo2_shift = rng.normal(0, 0.6)
        temp_shift = rng.normal(0, 0.15)
        motion_scale = float(np.clip(rng.normal(1.0, 0.12), 0.75, 1.35))

        clone["heart_rate"] = (clone["heart_rate"] + hr_shift + rng.normal(0, 2.5, len(clone))).clip(35, 220)
        clone["spo2"] = (clone["spo2"] + spo2_shift + rng.normal(0, 0.6, len(clone))).clip(50, 100)
        clone["temperature"] = (clone["temperature"] + temp_shift + rng.normal(0, 0.08, len(clone))).clip(30, 43)
        for axis in ["accel_x", "accel_y", "accel_z"]:
            clone[axis] = clone[axis] * motion_scale + rng.normal(0, 0.025, len(clone))

        clone["heart_rate"] = clone["heart_rate"].round().astype(int)
        clone["spo2"] = clone["spo2"].round().astype(int)
        clone["temperature"] = clone["temperature"].round(2)
        clone["accel_x"] = clone["accel_x"].round(3)
        clone["accel_y"] = clone["accel_y"].round(3)
        clone["accel_z"] = clone["accel_z"].round(3)
        augmented.append(clone)

    result = pd.concat(augmented, ignore_index=True)
    result = _add_rolling_features(result)
    return result


def _add_rolling_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
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
    df["timestamp"] = df["timestamp"].dt.strftime("%Y-%m-%dT%H:%M:%S")
    return df


def ensure_augmented_dataset() -> pd.DataFrame:
    df = _load_labeled()
    if df["subject_id"].nunique() < 2:
        df = _make_subject_augmented(df, subjects=4)
    else:
        df = _add_rolling_features(df)

    df.to_csv(AUGMENTED_PATH, index=False)
    return df


def run_loso(df: pd.DataFrame) -> tuple[list[dict[str, float | str]], float, float]:
    subjects = sorted(df["subject_id"].dropna().unique())
    results: list[dict[str, float | str]] = []

    for test_sub in subjects:
        train_df = df[df["subject_id"] != test_sub]
        test_df = df[df["subject_id"] == test_sub]
        train_normal = train_df[train_df["label"].str.startswith("normal")]
        x_train = train_normal[FEATURES].dropna()

        scaler = MinMaxScaler().fit(x_train)
        model = IsolationForest(contamination=0.05, n_estimators=200, random_state=42)
        model.fit(scaler.transform(x_train))

        x_test = scaler.transform(test_df[FEATURES].fillna(0))
        preds = model.predict(x_test)
        y_true = (
            test_df["label"].str.startswith("anomaly") | (test_df["label"] == "fall")
        ).astype(int)
        y_pred = (preds == -1).astype(int)
        f1 = f1_score(y_true, y_pred, zero_division=0)
        results.append({"excluded_subject": str(test_sub), "f1": float(f1)})
        print(f"  Exclude {test_sub}: F1={f1:.3f}")

    f1_values = [float(item["f1"]) for item in results]
    mean_f1 = float(np.mean(f1_values)) if f1_values else 0.0
    std_f1 = float(np.std(f1_values)) if f1_values else 0.0
    print(f"LOSO F1 Mean: {mean_f1:.3f} ± {std_f1:.3f}")
    return results, mean_f1, std_f1


def train_global(df: pd.DataFrame) -> tuple[IsolationForest, MinMaxScaler]:
    all_normal = df[df["label"].str.startswith("normal")][FEATURES].dropna()
    scaler = MinMaxScaler()
    model = IsolationForest(contamination=0.05, n_estimators=300, random_state=42)
    model.fit(scaler.fit_transform(all_normal))
    joblib.dump(model, MODEL_PATH)
    joblib.dump(scaler, SCALER_PATH)
    return model, scaler


def print_test_cases(model: IsolationForest, scaler: MinMaxScaler) -> list[dict[str, object]]:
    test_cases = [
        {"name": "Binh thuong", "data": [70, 98, 36.5, 70, 2, 0, 1.0]},
        {"name": "Nhip tim cao", "data": [155, 97, 36.8, 145, 8, -1, 1.1]},
        {"name": "SpO2 thap", "data": [88, 87, 36.5, 88, 3, -2, 1.0]},
        {"name": "Sot cao", "data": [100, 96, 39.5, 98, 4, 0, 1.0]},
        {"name": "Phat hien nga", "data": [90, 97, 36.8, 88, 5, 0, 3.2]},
    ]
    print("\n=== KET QUA TEST AI ===")
    outputs: list[dict[str, object]] = []
    for tc in test_cases:
        x_t = scaler.transform(pd.DataFrame([tc["data"]], columns=FEATURES))
        pred = int(model.predict(x_t)[0])
        score = float(model.decision_function(x_t)[0])
        status = "Binh thuong" if pred == 1 else "Bat thuong"
        print(f"{tc['name']:20s}: {status} (score={score:.3f})")
        outputs.append({"name": tc["name"], "status": status, "score": score})
    return outputs


def main() -> None:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    df = ensure_augmented_dataset()
    print(f"Loaded augmented dataset: {len(df)} rows, {df['subject_id'].nunique()} subjects")

    loso_results, mean_f1, std_f1 = run_loso(df)
    model, scaler = train_global(df)
    print(f"Model luu OK! LOSO F1={mean_f1:.3f}")
    test_outputs = print_test_cases(model, scaler)

    report = {
        "dataset": str(AUGMENTED_PATH.relative_to(PROJECT_ROOT)),
        "features": FEATURES,
        "rows": int(len(df)),
        "subjects": sorted(df["subject_id"].unique().tolist()),
        "loso": {
            "results": loso_results,
            "f1_mean": mean_f1,
            "f1_std": std_f1,
        },
        "model_path": str(MODEL_PATH.relative_to(PROJECT_ROOT)),
        "scaler_path": str(SCALER_PATH.relative_to(PROJECT_ROOT)),
        "test_cases": test_outputs,
        "note": (
            "Saved under ai_training/colab_export to match Notebook 02 without "
            "overwriting production models that use the ECG feature schema."
        ),
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
