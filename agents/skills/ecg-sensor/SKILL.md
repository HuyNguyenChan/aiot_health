---
name: ecg-sensor
description: Use this skill for everything related to the AD8232 ECG sensor — wiring, reading analog signal, bandpass filtering, training Conv1D Autoencoder on MIT-BIH PhysioNet dataset, converting model to TFLite for on-device inference, and integrating ECG anomaly detection into the server. Trigger when user says 'ECG', 'AD8232', 'điện tâm đồ', 'arrhythmia', 'MIT-BIH', 'PhysioNet', 'Conv1D', 'ECG autoencoder', or 'ECG bất thường'.
---

# ECG Sensor Skill – AIoT Health Monitor v3

## Tại sao thêm ECG?

MAX30102 chỉ cho ra **số nhịp tim (HR)** bằng quang học PPG.
AD8232 cho ra **dạng sóng điện tim** — từ đó phát hiện:
- Arrhythmia (loạn nhịp)
- Tachycardia / Bradycardia chính xác hơn
- ST-elevation (dấu hiệu nhồi máu cơ tim)
- Sóng P, QRS, T bất thường

## Phần cứng & Đấu nối

**Linh kiện:** AD8232 Module (~65,000 VNĐ, Shopee: 'ad8232 ecg module')
Kèm: 3 điện cực dán + cáp snap 3.5mm

```
AD8232         →  ESP32-S3 DevKitC-1
────────────────────────────────────────
3.3V           →  3V3
GND            →  GND
OUTPUT         →  GPIO 1  (ADC1_CH0 (ESP32-S3: GPIO1-10))
LO+            →  GPIO 11  (lead-off detection +)
LO-            →  GPIO 12  (lead-off detection -)

Thêm tụ 100nF: OUTPUT → GND  (lọc nhiễu cao tần)

Điện cực dán:
  RA  →  Cổ tay phải (hoặc dưới xương đòn phải)
  LA  →  Cổ tay trái  (hoặc dưới xương đòn trái)
  RL  →  Cạnh sườn trái (reference)
```

> **QUAN TRỌNG:** Dùng ADC1 (GPIO 11–39). ADC2 (GPIO20) bị hạn chế khi WiFi bật.

---

## Train ECG Autoencoder (Google Colab)

### Notebook: ai_training/notebooks/04_ecg_autoencoder.ipynb

```python
# Cell 1: Cài thư viện
# !pip install wfdb scipy tensorflow

import wfdb
import numpy as np
import tensorflow as tf
from tensorflow import keras
from scipy.signal import butter, filtfilt
import matplotlib.pyplot as plt

# Cell 2: Tải dataset MIT-BIH (chuẩn quốc tế — ~200MB)
# Lần đầu mất ~5 phút, sau đó cache lại
wfdb.dl_database('mitdb', './mitdb')
print("Tải xong dataset MIT-BIH!")

# Cell 3: Hàm load ECG và tạo sliding windows
def load_normal_ecg(record_ids=['100','101','103','106','107'],
                    window=250, fs=360):
    """
    Chỉ lấy nhịp bình thường (ký hiệu 'N') để train autoencoder.
    Model học pattern bình thường → tái tạo lỗi cao = bất thường.
    """
    windows = []
    for rid in record_ids:
        try:
            rec = wfdb.rdrecord(f'./mitdb/{rid}')
            ann = wfdb.rdann(f'./mitdb/{rid}', 'atr')
            sig = rec.p_signal[:, 0]  # Lead 1

            # Bandpass filter 0.5-40Hz
            b, a = butter(3, [0.5, 40], 'band', fs=fs)
            sig = filtfilt(b, a, sig)

            # Normalize 0-1
            sig = (sig - sig.min()) / (sig.max() - sig.min() + 1e-8)

            # Lấy nhịp bình thường
            normal_beats = [s for s, sym in zip(ann.sample, ann.symbol)
                           if sym == 'N']

            for beat in normal_beats[5:-5]:
                start = beat - window // 2
                end   = start + window
                if start > 0 and end < len(sig):
                    windows.append(sig[start:end])

            print(f"Record {rid}: {len(normal_beats)} nhịp bình thường")
        except Exception as e:
            print(f"Lỗi record {rid}: {e}")

    arr = np.array(windows).reshape(-1, window, 1)
    print(f"\nTổng: {len(arr)} windows từ {len(record_ids)} records")
    return arr

X_train = load_normal_ecg()

# Cell 4: Conv1D Autoencoder — nhỏ gọn, ~50KB
def build_ecg_autoencoder():
    inp = keras.Input(shape=(250, 1))

    # Encoder: nén xuống (10, 8) — latent space nhỏ
    x = keras.layers.Conv1D(16, 3, activation='relu', padding='same')(inp)
    x = keras.layers.MaxPooling1D(5)(x)              # → (50, 16)
    x = keras.layers.Conv1D(8, 3, activation='relu', padding='same')(x)
    encoded = keras.layers.MaxPooling1D(5)(x)         # → (10, 8)

    # Decoder: tái tạo lại tín hiệu gốc
    x = keras.layers.Conv1D(8, 3, activation='relu', padding='same')(encoded)
    x = keras.layers.UpSampling1D(5)(x)
    x = keras.layers.Conv1D(16, 3, activation='relu', padding='same')(x)
    x = keras.layers.UpSampling1D(5)(x)
    decoded = keras.layers.Conv1D(1, 3, activation='sigmoid', padding='same')(x)

    model = keras.Model(inp, decoded)
    model.summary()
    print(f"Số parameters: {model.count_params():,} (~{model.count_params()*4//1024}KB)")
    return model

model = build_ecg_autoencoder()
model.compile(optimizer='adam', loss='mse')

# Cell 5: Train
history = model.fit(
    X_train, X_train,        # autoencoder: reconstruct input
    epochs=50,
    batch_size=64,
    validation_split=0.15,
    callbacks=[
        keras.callbacks.EarlyStopping(patience=8, restore_best_weights=True),
        keras.callbacks.ReduceLROnPlateau(patience=4, factor=0.5)
    ],
    verbose=1
)

# Plot training curve
plt.figure(figsize=(10,4))
plt.subplot(1,2,1)
plt.plot(history.history['loss'], label='Train'); plt.plot(history.history['val_loss'], label='Val')
plt.title('Loss'); plt.legend()
plt.tight_layout(); plt.savefig('ecg_training.png', dpi=120); plt.show()

# Cell 6: Tính ngưỡng anomaly (95th percentile reconstruction error)
recon  = model.predict(X_train, verbose=0)
errors = np.mean(np.abs(recon - X_train), axis=(1, 2))

ECG_THRESHOLD = np.percentile(errors, 95)
print(f"Reconstruction error — Mean: {errors.mean():.4f}  Std: {errors.std():.4f}")
print(f"Anomaly threshold (95th perc): {ECG_THRESHOLD:.4f}")

# Kiểm tra với nhịp bất thường giả (noisy signal)
test_noisy = X_train[:5] + np.random.normal(0, 0.3, X_train[:5].shape)
recon_noisy = model.predict(test_noisy, verbose=0)
err_noisy = np.mean(np.abs(recon_noisy - test_noisy), axis=(1,2))
print(f"Noisy ECG errors: {err_noisy}")  # Phải > ECG_THRESHOLD

# Cell 7: Lưu model
model.save('ecg_autoencoder.h5')
np.save('ecg_threshold.npy', ECG_THRESHOLD)
print(f"Đã lưu model ({model.count_params()*4//1024}KB) và threshold")

# Cell 8: Download về máy
from google.colab import files
files.download('ecg_autoencoder.h5')
files.download('ecg_threshold.npy')
# Copy vào thư mục models/ của project
```

---

## Tích hợp ECG vào server/ai_engine.py

```python
# Phần ECG trong class AIEngine — thêm sau khi load các model cũ

def _load_ecg_model(self):
    """Load Conv1D Autoencoder và threshold"""
    try:
        self.ecg_model     = tf.keras.models.load_model('models/ecg_autoencoder.h5')
        self.ecg_threshold = float(np.load('models/ecg_threshold.npy'))
        print(f"[AI] ECG model loaded, threshold={self.ecg_threshold:.4f}")
    except Exception as e:
        self.ecg_model     = None
        self.ecg_threshold = 0.05
        print(f"[AI] ECG model not found: {e}")

def detect_ecg_anomaly(self, ecg_samples: list) -> tuple[bool, float]:
    """
    Phát hiện bất thường ECG dùng Conv1D Autoencoder.
    Input: danh sách 250 giá trị ADC từ AD8232
    Output: (is_anomaly, reconstruction_error)
    """
    if not self.ecg_model or len(ecg_samples) < 250:
        return False, 0.0

    ecg = np.array(ecg_samples[:250], dtype=np.float32)

    # Normalize về 0-1
    ecg_min, ecg_max = ecg.min(), ecg.max()
    if ecg_max - ecg_min < 10:
        return False, 0.0  # Tín hiệu phẳng = điện cực bị rời

    ecg = (ecg - ecg_min) / (ecg_max - ecg_min)
    ecg_input = ecg.reshape(1, 250, 1)

    # Predict
    recon = self.ecg_model.predict(ecg_input, verbose=0)
    err   = float(np.mean(np.abs(recon - ecg_input)))

    is_anomaly = err > self.ecg_threshold
    return is_anomaly, err
```

---

## API endpoint thêm vào app.py

```python
@app.route("/api/health/<device_id>/ecg_latest", methods=["GET"])
def ecg_latest(device_id):
    """Lấy bản ECG mới nhất để hiển thị trên dashboard"""
    data = get_latest_ecg(device_id)   # lưu trong Firebase riêng
    if not data:
        return jsonify({"error": "No ECG data"}), 404
    return jsonify(data)
```

---

## Câu hỏi hội đồng về ECG

**Q: Tại sao không dùng thư viện tính HR từ ECG thay vì MAX30102?**
A: MAX30102 dùng PPG (quang học) phù hợp đeo tay, độ chính xác đủ cho HR số. ECG cho thêm *dạng sóng điện* để phân tích arrhythmia — hai cảm biến bổ sung cho nhau.

**Q: Dataset MIT-BIH có đủ đại diện không?**
A: MIT-BIH có 48 bản ghi từ 47 bệnh nhân, tổng 30 phút/bản ghi, là dataset chuẩn vàng được dùng trong >2000 bài báo khoa học. Đây là lý do dùng thay vì chỉ thu thập thủ công.
