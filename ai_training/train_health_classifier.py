from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import MinMaxScaler


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TRAIN_PATH = PROJECT_ROOT / "data" / "processed" / "health_data_train.csv"
TEST_PATH = PROJECT_ROOT / "data" / "processed" / "health_data_test.csv"
MODELS_DIR = PROJECT_ROOT / "models"

MODEL_PATH = MODELS_DIR / "health_classifier.pkl"
REPORT_PATH = MODELS_DIR / "health_classifier_report.json"
SCALER_PATH = MODELS_DIR / "scaler.pkl"
ISO_MODEL_PATH = MODELS_DIR / "isolation_forest.pkl"
MODEL_INFO_PATH = MODELS_DIR / "model_info.json"

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

LABEL_TO_ID = {
    "normal_rest": 0,
    "normal_light": 1,
    "normal_moderate": 2,
    "normal_morning": 3,
    "normal_postmeal": 4,
    "stress": 5,
    "anomaly_high_hr": 6,
    "anomaly_low_spo2": 7,
    "fall": 8,
}
ID_TO_LABEL = {value: key for key, value in LABEL_TO_ID.items()}


def load_dataset(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Dataset not found: {path}")

    df = pd.read_csv(path)
    missing = sorted(set(FEATURE_COLUMNS + ["label_detail"]) - set(df.columns))
    if missing:
        raise ValueError(f"{path.name} is missing columns: {missing}")

    df = df.dropna(subset=FEATURE_COLUMNS + ["label_detail"]).copy()
    df["label_detail"] = df["label_detail"].astype(str).str.strip()
    unknown = sorted(set(df["label_detail"]) - set(LABEL_TO_ID))
    if unknown:
        raise ValueError(f"Unknown labels in {path.name}: {unknown}")

    df["class_id"] = df["label_detail"].map(LABEL_TO_ID)
    return df


def main() -> None:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    train_df = load_dataset(TRAIN_PATH)
    test_df = load_dataset(TEST_PATH)

    x_train = train_df[FEATURE_COLUMNS]
    y_train = train_df["class_id"]
    x_test = test_df[FEATURE_COLUMNS]
    y_test = test_df["class_id"]

    model = Pipeline(
        steps=[
            ("scaler", MinMaxScaler()),
            (
                "classifier",
                RandomForestClassifier(
                    n_estimators=300,
                    random_state=42,
                    class_weight="balanced",
                    min_samples_leaf=2,
                ),
            ),
        ]
    )
    model.fit(x_train, y_train)

    predictions = model.predict(x_test)
    accuracy = accuracy_score(y_test, predictions)
    labels_in_test = sorted(y_test.unique())
    report = classification_report(
        y_test,
        predictions,
        labels=labels_in_test,
        target_names=[ID_TO_LABEL[label] for label in labels_in_test],
        zero_division=0,
        output_dict=True,
    )

    anomaly_scaler = MinMaxScaler()
    normal_train = train_df[train_df["target"] == 0]
    if normal_train.empty:
        normal_train = train_df

    x_normal = anomaly_scaler.fit_transform(normal_train[FEATURE_COLUMNS])
    isolation_model = IsolationForest(
        n_estimators=250,
        contamination=0.08,
        random_state=42,
    )
    isolation_model.fit(x_normal)
    normal_scores = isolation_model.decision_function(x_normal)
    score_threshold = float(min(-0.02, np.percentile(normal_scores, 2)))

    payload = {
        "model": "RandomForestClassifier",
        "model_path": str(MODEL_PATH.relative_to(PROJECT_ROOT)),
        "feature_columns": FEATURE_COLUMNS,
        "label_to_id": LABEL_TO_ID,
        "accuracy": accuracy,
        "train_rows": int(len(train_df)),
        "test_rows": int(len(test_df)),
        "train_label_counts": train_df["label_detail"].value_counts().to_dict(),
        "test_label_counts": test_df["label_detail"].value_counts().to_dict(),
        "classification_report": report,
        "confusion_matrix": confusion_matrix(y_test, predictions, labels=labels_in_test).tolist(),
        "isolation_forest": {
            "model_path": str(ISO_MODEL_PATH.relative_to(PROJECT_ROOT)),
            "scaler_path": str(SCALER_PATH.relative_to(PROJECT_ROOT)),
            "normal_train_rows": int(len(normal_train)),
            "contamination": 0.08,
            "score_threshold": score_threshold,
        },
        "note": (
            "Model includes AD8232-derived heart_rate and ECG quality features. "
            "Keep collecting real rows after hardware changes and retrain before demo."
        ),
    }

    joblib.dump(model, MODEL_PATH)
    joblib.dump(anomaly_scaler, SCALER_PATH)
    joblib.dump(isolation_model, ISO_MODEL_PATH)
    REPORT_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    MODEL_INFO_PATH.write_text(
        json.dumps(
            {
                "features": FEATURE_COLUMNS,
                "label_to_id": LABEL_TO_ID,
                "classifier_model": str(MODEL_PATH.relative_to(PROJECT_ROOT)),
                "isolation_model": str(ISO_MODEL_PATH.relative_to(PROJECT_ROOT)),
                "scaler": str(SCALER_PATH.relative_to(PROJECT_ROOT)),
                "isolation_forest_contamination": 0.08,
                "isolation_score_threshold": score_threshold,
                "n_samples": int(len(train_df) + len(test_df)),
                "trained_with": "ai_training/train_health_classifier.py",
                "hardware_note": "heart_rate from AD8232, SpO2 from MAX30102",
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
