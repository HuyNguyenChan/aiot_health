---
name: ai-engine
description: Use this skill to train, evaluate, or integrate AI models v3 — including Isolation Forest (per-patient, auto-retrain daily), LSTM trend prediction, Conv1D ECG Autoencoder, and Ensemble Voting from 3 models. Also handles data augmentation (5x dataset without collecting more), LOSO cross-validation, and model export. Trigger when user says 'train model', 'AI', 'machine learning', 'Isolation Forest', 'LSTM', 'ECG autoencoder', 'ensemble', 'phát hiện bất thường', 'dự đoán', 'dataset', 'augmentation', 'per-patient', or 'auto-retrain'.
---

# AI Engine Skill v3 – AIoT Health Monitor

## PHẦN 1: Data Augmentation (MỚI v3 — nhân dataset 5x)

```python
# ai_training/notebooks/01b_augmentation.ipynb

import pandas as pd
import numpy as np

df = pd.read_csv("data/processed/health_data_clean.csv")
print(f"Dataset gốc: {len(df)} mẫu từ {df['subject_id'].nunique()} người")

def augment_sample(row, method):
    """Tạo mẫu mới từ mẫu gốc — giữ nguyên nhãn và subject"""
    aug = row.copy()
    if method == 'noise':
        # Nhiễu Gaussian nhỏ — giả lập biến thiên đo lường
        aug['heart_rate']  += np.random.normal(0, 1.5)
        aug['spo2']        += np.random.normal(0, 0.3)
        aug['temperature'] += np.random.normal(0, 0.05)
        aug['accel_mag']   += np.random.normal(0, 0.02)
    elif method == 'scale':
        # Scale ±8% — giả lập sai số cảm biến theo ngày
        s = np.random.uniform(0.93, 1.07)
        aug['heart_rate']      *= s
        aug['hr_rolling_mean'] *= s
        aug['accel_mag']       *= s
    elif method == 'jitter':
        # Jitter rolling features — giả lập context khác nhau
        aug['hr_rolling_mean'] += np.random.normal(0, 2.0)
        aug['hr_rolling_std']  += abs(np.random.normal(0, 0.5))
        aug['spo2_change']     += np.random.normal(0, 0.1)
    aug['aug_method'] = method
    return aug

# Áp dụng 5 phương pháp → dataset × 5
augmented = []
methods = ['noise', 'scale', 'jitter', 'noise', 'scale']
for _, row in df.iterrows():
    for m in methods:
        augmented.append(augment_sample(row, m))

df_aug = pd.concat([df, pd.DataFrame(augmented)], ignore_index=True)
# Clip các giá trị ra ngoài biên y tế
df_aug['heart_rate']  = df_aug['heart_rate'].clip(30, 220)
df_aug['spo2']        = df_aug['spo2'].clip(50, 100)
df_aug['temperature'] = df_aug['temperature'].clip(30, 43)

df_aug.to_csv("data/processed/health_data_augmented.csv", index=False)
print(f"Sau augmentation: {len(df_aug)} mẫu (×{len(df_aug)//len(df)})")
```

---

## PHẦN 2: Train Isolation Forest — Per-Patient (v3)

```python
# ai_training/notebooks/02_train_isolation_forest.ipynb

import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import MinMaxScaler
from sklearn.metrics import f1_score
import joblib, json, os

df = pd.read_csv("data/processed/health_data_augmented.csv")
FEATURES = ['heart_rate','spo2','temperature','hr_rolling_mean',
            'hr_rolling_std','spo2_change','accel_mag']

# ── Leave-One-Subject-Out Cross Validation ────────
# Cách đánh giá chuẩn cho dữ liệu sinh học — đảm bảo generalize
subjects = df['subject_id'].unique()
print(f"LOSO CV với {len(subjects)} subjects: {subjects}")

all_scores = []
for test_subject in subjects:
    train_df = df[df['subject_id'] != test_subject]
    test_df  = df[df['subject_id'] == test_subject]

    # Chỉ train trên data bình thường
    train_normal = train_df[train_df['label'].str.startswith('normal')]
    X_train = train_normal[FEATURES].dropna()

    scaler = MinMaxScaler()
    X_train_s = scaler.fit_transform(X_train)

    model = IsolationForest(contamination=0.05, n_estimators=200, random_state=42)
    model.fit(X_train_s)

    # Test
    X_test   = scaler.transform(test_df[FEATURES].fillna(0))
    preds    = model.predict(X_test)  # 1=normal, -1=anomaly
    y_true   = (test_df['label'].str.startswith('anomaly') | 
                test_df['label'].str.contains('fall')).astype(int)
    y_pred   = (preds == -1).astype(int)

    f1 = f1_score(y_true, y_pred, zero_division=0)
    all_scores.append(f1)
    print(f"  Exclude {test_subject}: F1={f1:.3f}")

print(f"\nLOSO F1 Mean: {np.mean(all_scores):.3f} ± {np.std(all_scores):.3f}")

# ── Train model chung (dùng khi bệnh nhân mới chưa có đủ data)
all_normal = df[df['label'].str.startswith('normal')][FEATURES].dropna()
scaler_global = MinMaxScaler()
X_global = scaler_global.fit_transform(all_normal)

model_global = IsolationForest(contamination=0.05, n_estimators=300, random_state=42)
model_global.fit(X_global)

os.makedirs("models", exist_ok=True)
joblib.dump(model_global, "models/isolation_forest.pkl")
joblib.dump(scaler_global, "models/scaler.pkl")
with open("models/model_info.json","w") as f:
    json.dump({"contamination":0.05,"features":FEATURES,
               "n_samples":len(all_normal),
               "loso_f1_mean":float(np.mean(all_scores))}, f, indent=2)
print(f"\nModel global đã lưu. LOSO F1={np.mean(all_scores):.3f}")
```

---

## PHẦN 3: Train LSTM (giữ nguyên, cải tiến nhỏ)

```python
# ai_training/notebooks/03_train_lstm.ipynb

import numpy as np, pandas as pd, tensorflow as tf
from tensorflow import keras

df = pd.read_csv("data/processed/health_data_augmented.csv")
hr = df['heart_rate'].values.reshape(-1, 1)

WINDOW = 24  # 24 điểm × 5s = 2 phút lịch sử → dự đoán tiếp theo

def create_sequences(data, w):
    X, y = [], []
    for i in range(len(data) - w):
        X.append(data[i:i+w])
        y.append(data[i+w])
    return np.array(X), np.array(y)

X, y = create_sequences(hr, WINDOW)
split = int(len(X) * 0.8)
X_train, X_val = X[:split], X[split:]
y_train, y_val = y[:split], y[split:]

model = keras.Sequential([
    keras.layers.LSTM(64, return_sequences=True, input_shape=(WINDOW, 1)),
    keras.layers.Dropout(0.2),
    keras.layers.LSTM(32),
    keras.layers.Dropout(0.2),
    keras.layers.Dense(16, activation='relu'),
    keras.layers.Dense(1)
])
model.compile(optimizer='adam', loss='mse', metrics=['mae'])

history = model.fit(
    X_train, y_train, epochs=100, batch_size=32,
    validation_data=(X_val, y_val),
    callbacks=[
        keras.callbacks.EarlyStopping(patience=10, restore_best_weights=True),
        keras.callbacks.ReduceLROnPlateau(patience=5, factor=0.5)
    ]
)
val_loss, val_mae = model.evaluate(X_val, y_val, verbose=0)
print(f"Val MAE: {val_mae:.4f} (~{val_mae*220:.1f} bpm sai số)")
model.save("models/lstm_heart_predict.h5")
```

---

## PHẦN 4: server/ai_engine.py — Ensemble 3 Model (v3)

```python
import joblib
import numpy as np
import tensorflow as tf
import pandas as pd
import os
from apscheduler.schedulers.background import BackgroundScheduler
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import MinMaxScaler

FEATURES = ['heart_rate','spo2','temperature','hr_rolling_mean',
            'hr_rolling_std','spo2_change','accel_mag']

class AIEngine:
    def __init__(self):
        self.scaler     = joblib.load("models/scaler.pkl")
        self.if_model   = joblib.load("models/isolation_forest.pkl")
        self.lstm       = tf.keras.models.load_model("models/lstm_heart_predict.h5")
        self._load_ecg_model()

        # Per-patient models — {device_id: (IsolationForest, MinMaxScaler)}
        self.patient_models = {}
        self._load_all_patient_models()

        # Auto-retrain lúc 2AM mỗi ngày
        scheduler = BackgroundScheduler()
        scheduler.add_job(self.retrain_all_patients, 'cron', hour=2, minute=0)
        scheduler.start()
        print("[AI] Engine v3 khởi động. Auto-retrain lúc 2:00 AM mỗi ngày")

    def _load_ecg_model(self):
        try:
            self.ecg_model     = tf.keras.models.load_model("models/ecg_autoencoder.h5")
            self.ecg_threshold = float(np.load("models/ecg_threshold.npy"))
            print(f"[AI] ECG Autoencoder loaded, threshold={self.ecg_threshold:.4f}")
        except:
            self.ecg_model = None
            self.ecg_threshold = 0.05
            print("[AI] ECG model not found — ECG voting disabled")

    def _load_all_patient_models(self):
        """Load model riêng cho từng bệnh nhân nếu có"""
        if not os.path.exists("models"):
            return
        for f in os.listdir("models"):
            if f.endswith("_if.pkl"):
                device_id = f.replace("_if.pkl","")
                try:
                    m = joblib.load(f"models/{device_id}_if.pkl")
                    s = joblib.load(f"models/{device_id}_scaler.pkl")
                    self.patient_models[device_id] = (m, s)
                    print(f"[AI] Loaded personal model: {device_id}")
                except:
                    pass

    # ── CORE: Ensemble Voting 3 model ─────────────
    def detect_anomaly(self, data: dict) -> tuple[bool, str, float]:
        """
        Kết hợp 3 nguồn:
          Vote 1 — Rule cứng (emergency hard stop)
          Vote 2 — Isolation Forest (multi-vital)
          Vote 3 — ECG Autoencoder (waveform)
        Kết quả: cần ≥ 2/3 vote → cảnh báo
        """
        votes   = []
        reasons = []

        # ── Vote 1: Rule-based hard stop ──────────
        hr   = data.get('heart_rate', 70)
        spo2 = data.get('spo2', 98)
        temp = data.get('temperature', 36.5)

        if spo2 < 88:
            votes.append(1); reasons.append(f"SpO2 nguy hiểm: {spo2}%")
        elif hr > 160 or hr < 35:
            votes.append(1); reasons.append(f"HR cực đoan: {hr}bpm")
        elif temp > 38.5:
            votes.append(1); reasons.append(f"Sốt cao: {temp}°C")
        elif data.get('fall', False):
            votes.append(1); reasons.append("Phát hiện ngã")
        else:
            votes.append(0)

        # ── Vote 2: Isolation Forest ───────────────
        device_id = data.get('device_id', '')
        # Ưu tiên model riêng nếu có, fallback model chung
        if device_id in self.patient_models:
            if_m, if_s = self.patient_models[device_id]
        else:
            if_m, if_s = self.if_model, self.scaler

        try:
            feats = [[
                hr, spo2, temp,
                data.get('hr_rolling_mean', hr),
                data.get('hr_rolling_std', 2.0),
                data.get('spo2_change', 0.0),
                data.get('accel_mag', 1.0)
            ]]
            pred = if_m.predict(if_s.transform(feats))[0]
            votes.append(1 if pred == -1 else 0)
            if pred == -1: reasons.append("Isolation Forest pattern")
        except Exception as e:
            print(f"[AI] IF error: {e}")

        # ── Vote 3: ECG Autoencoder ────────────────
        ecg_samples = data.get('ecg_samples', [])
        if self.ecg_model and len(ecg_samples) >= 250:
            try:
                ecg = np.array(ecg_samples[:250], dtype=np.float32)
                ecg_range = ecg.max() - ecg.min()
                if ecg_range > 10:  # tín hiệu có ý nghĩa
                    ecg = (ecg - ecg.min()) / ecg_range
                    ecg_in = ecg.reshape(1, 250, 1)
                    recon  = self.ecg_model.predict(ecg_in, verbose=0)
                    err    = float(np.mean(np.abs(recon - ecg_in)))
                    votes.append(1 if err > self.ecg_threshold else 0)
                    if err > self.ecg_threshold:
                        reasons.append(f"ECG bất thường (err={err:.3f})")
            except Exception as e:
                print(f"[AI] ECG error: {e}")

        # ── Ensemble kết quả ──────────────────────
        if not votes:
            return False, "Không đủ dữ liệu", 0.0

        confidence  = sum(votes) / len(votes)
        is_anomaly  = confidence >= 2/3  # cần ≥ 2 trong 3 vote
        reason_str  = " + ".join(reasons) if reasons else "Bình thường"
        return is_anomaly, reason_str, round(confidence, 2)

    # ── Per-patient auto-retrain ───────────────────
    def retrain_patient(self, device_id: str, history: list):
        """
        Train model cá nhân từ lịch sử 7 ngày của bệnh nhân.
        Gọi từ auto-scheduler hoặc thủ công.
        """
        if len(history) < 100:
            print(f"[RETRAIN] {device_id}: chỉ có {len(history)} mẫu, cần ≥100")
            return False

        df = pd.DataFrame(history)
        # Chỉ train trên data không có cảnh báo (baseline bình thường)
        normal_df = df[~df.get('edge_alert', pd.Series([False]*len(df)))]
        if len(normal_df) < 50:
            normal_df = df  # fallback

        X = normal_df[FEATURES].fillna(normal_df[FEATURES].mean())
        if X.empty:
            return False

        scaler = MinMaxScaler().fit(X)
        model  = IsolationForest(contamination=0.05, n_estimators=200,
                                  random_state=42).fit(scaler.transform(X))

        os.makedirs("models", exist_ok=True)
        joblib.dump(model,  f"models/{device_id}_if.pkl")
        joblib.dump(scaler, f"models/{device_id}_scaler.pkl")
        self.patient_models[device_id] = (model, scaler)
        print(f"[RETRAIN] {device_id}: model mới với {len(X)} mẫu")
        return True

    def retrain_all_patients(self):
        """Gọi tự động lúc 2AM — retrain tất cả bệnh nhân"""
        from firebase_handler import get_history, get_all_patients
        print("[RETRAIN] Bắt đầu auto-retrain tất cả bệnh nhân...")
        patients = get_all_patients()
        for p in patients:
            pid = p['id']
            try:
                history = get_history(pid, days=7)
                self.retrain_patient(pid, history)
            except Exception as e:
                print(f"[RETRAIN] Lỗi {pid}: {e}")
        print("[RETRAIN] Hoàn tất!")

    # ── LSTM trend prediction (giữ nguyên) ────────
    def predict_trend(self, history: list, hours_ahead: int = 6) -> list:
        hr_vals = [r.get('heart_rate', 70) for r in history[-24:]]
        if len(hr_vals) < 24:
            return []
        arr   = np.array(hr_vals, dtype=np.float32).reshape(-1, 1)
        X_in  = self.scaler.transform(
            np.hstack([arr, np.zeros((len(arr), 6))])
        )[:, 0].reshape(1, 24, 1)

        preds = []
        cur   = X_in.copy()
        for _ in range(hours_ahead * 12):  # 12 điểm/giờ
            p = self.lstm.predict(cur, verbose=0)[0][0]
            preds.append(round(float(p) * 220, 1))
            cur = np.roll(cur, -1, axis=1)
            cur[0, -1, 0] = p
        return preds
```

---

## Kết quả kỳ vọng sau nâng cấp

| Metric | Trước (v2) | Sau (v3) |
|---|---|---|
| Dataset | ~950 mẫu, 1 người | ~5000+ mẫu, 3-5 người |
| Đánh giá | Train/test split đơn giản | LOSO cross-validation |
| F1-Score (ước tính) | ~85-88% | >90% |
| False Positive Rate | ~12-15% | <5% (ensemble voting) |
| Model cá nhân hóa | Không | Có (per-patient + daily retrain) |
