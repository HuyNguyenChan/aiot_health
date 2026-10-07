# Bản Đồ Kiến Thức Cần Học Cho Đồ Án AIoT Health Monitor

Tài liệu này giúp bạn biết cần học gì, học để trả lời câu hỏi nào, và kiến thức đó nằm ở đâu trong code thật của dự án.

## 1. Bức Tranh Tổng Quan Hệ Thống

### Bạn cần hiểu

Hệ thống gồm 5 lớp:

```text
Lớp 1: Thiết bị IoT
ESP32-S3 + AD8232 + MAX30102 + MPU6050 + DS18B20 + OLED

Lớp 2: Giao tiếp
WiFi + MQTT over TLS qua HiveMQ Cloud

Lớp 3: Backend
Flask API + MQTT subscriber + AI Engine

Lớp 4: Database
Firebase Realtime Database

Lớp 5: Giao diện
Streamlit Dashboard
```

Luồng dữ liệu:

```text
ESP32 đọc cảm biến
→ đóng gói JSON
→ publish MQTT topic health/patient_001/data
→ server nhận MQTT
→ chạy rule-based + AI
→ lưu Firebase
→ dashboard đọc API và hiển thị
```

### Nằm ở đâu trong code

| Phần | File |
|---|---|
| Firmware ESP32 | `esp32_firmware/src/main.cpp` |
| Cấu hình GPIO | `esp32_firmware/include/config.h` |
| WiFi/MQTT secret | `esp32_firmware/include/secrets.h` |
| MQTT subscriber | `server/mqtt_handler.py` |
| Flask API | `server/app.py` |
| Firebase handler | `server/firebase_handler.py` |
| AI Engine | `server/ai_engine.py` |
| Dashboard | `dashboard/streamlit_app.py` |
| Component dashboard | `dashboard/components/*.py` |
| Notebook train AI | `ai_training/notebooks/*.ipynb` |

### Câu trả lời mẫu

> Hệ thống của em là pipeline AIoT realtime. ESP32-S3 thu thập dữ liệu cảm biến, gửi qua MQTT đến backend Flask. Backend xử lý cảnh báo, chạy AI, lưu Firebase. Dashboard Streamlit đọc API để hiển thị realtime.

## 2. ESP32-S3 Và Firmware Arduino

### Bạn cần học

- ESP32-S3 là vi điều khiển có WiFi.
- Firmware dùng Arduino framework qua PlatformIO.
- ESP32 đọc cảm biến, hiển thị OLED, gửi MQTT.
- Không chạy AI nặng trên ESP32, chỉ xử lý edge rule đơn giản.

### Nằm ở đâu trong code

| Nội dung | File / hàm |
|---|---|
| Hàm khởi động firmware | `esp32_firmware/src/main.cpp`, `setup()` khoảng dòng 1705 |
| Vòng lặp chính | `esp32_firmware/src/main.cpp`, `loop()` khoảng dòng 1739 |
| Cấu hình chân | `esp32_firmware/include/config.h` |
| WiFi/MQTT credentials | `esp32_firmware/include/secrets.h` |
| OLED | `setupDisplay()`, `updateDisplay()`, `renderMainScreen()` |
| Gửi dữ liệu MQTT | `publishHealthData()` khoảng dòng 1591 |

### Câu hỏi thầy có thể hỏi

**Hỏi:** ESP32 làm gì trong hệ thống?

**Trả lời:**

> ESP32-S3 là node IoT. Nó đọc cảm biến AD8232, MAX30102, MPU6050, DS18B20, hiển thị trạng thái lên OLED và gửi dữ liệu dạng JSON qua MQTT về backend.

## 3. Cấu Hình Chân GPIO

### Bạn cần học

Bạn phải nhớ các chân chính:

```text
I2C SDA = GPIO8
I2C SCL = GPIO9
DS18B20 = GPIO4
AD8232 OUTPUT = GPIO1
AD8232 LO+ = GPIO11
AD8232 LO- = GPIO12
Buttons = GPIO5, GPIO6, GPIO7
Buzzer = GPIO16
LED_ERR = GPIO17
LED_OK = GPIO18
```

### Nằm ở đâu trong code

`esp32_firmware/include/config.h`

Các biến quan trọng:

```cpp
constexpr uint8_t I2C_SDA_PIN = 8;
constexpr uint8_t I2C_SCL_PIN = 9;
constexpr uint8_t DS18B20_PIN = 4;
constexpr uint8_t AD8232_OUTPUT_PIN = 1;
constexpr uint8_t AD8232_LO_PLUS_PIN = 11;
constexpr uint8_t AD8232_LO_MINUS_PIN = 12;
```

### Câu trả lời mẫu

> Em gom toàn bộ cấu hình phần cứng vào `config.h` để dễ kiểm soát và tránh hard-code rải rác. Các cảm biến I2C dùng chung SDA GPIO8 và SCL GPIO9.

## 4. AD8232 ECG Và Cách Đo HR

### Bạn cần học

AD8232 không trả trực tiếp nhịp tim. Nó trả tín hiệu ECG analog.

Firmware làm 4 bước:

1. Đọc ADC từ GPIO1.
2. Kiểm tra điện cực rời bằng LO+ và LO-.
3. Thu 250 mẫu ECG ở 50Hz, tương ứng 5 giây.
4. Tìm đỉnh ECG, tính khoảng RR, đổi ra BPM.

### Nằm ở đâu trong code

| Nội dung | File / hàm |
|---|---|
| Đọc AD8232 | `readAd8232()` khoảng dòng 1112 |
| Đọc ADC oversampling | `readEcgOversampled()` |
| Tính HR từ ECG | `estimateEcgWindowHeartRate()` khoảng dòng 622 |
| Xử lý cửa sổ 250 mẫu | `processEcgWindow()` khoảng dòng 667 |
| Chấp nhận HR hợp lệ | `acceptEcgHeartRate()` |
| OLED hiển thị HR | `renderMainScreen()` khoảng dòng 1348 |
| Gửi HR lên MQTT | `publishHealthData()` khoảng dòng 1591 |

### Code quan trọng

Đọc điện cực:

```cpp
gSensor.ecgLoPlus = digitalRead(Config::AD8232_LO_PLUS_PIN) == HIGH;
gSensor.ecgLoMinus = digitalRead(Config::AD8232_LO_MINUS_PIN) == HIGH;
gSensor.ecgLeadOff = gSensor.ecgLoPlus || gSensor.ecgLoMinus;
```

Nếu điện cực rời:

```cpp
resetEcgWindowStats();
resetEcgHeartRateDetector();
return;
```

Tính HR:

```cpp
const float bpm = estimateEcgWindowHeartRate(
    gSensor.ecgMeanRaw,
    gSensor.ecgStdRaw,
    &beatCount
);
```

Gửi MQTT:

```cpp
doc["heart_rate"] = gSensor.hrValid ? static_cast<int>(gSensor.heartRate) : 0;
doc["heart_rate_source"] = "ad8232";
doc["heart_rate_valid"] = gSensor.hrValid;
```

### Trạng thái OLED

| OLED hiển thị | Ý nghĩa |
|---|---|
| `HR: dien cuc roi` | Điện cực ECG rời |
| `HR: dang do xx%` | Đang thu đủ 250 mẫu |
| `HR: 75 bpm` | Đã tính được HR |

### Câu trả lời mẫu

> AD8232 chỉ cung cấp dạng sóng ECG. Em đọc ADC ở GPIO1 với tần số 50Hz, gom 250 mẫu trong 5 giây, sau đó phát hiện đỉnh R và tính khoảng RR để suy ra BPM. Nếu LO+ hoặc LO- HIGH thì hệ thống báo điện cực rời và không hiển thị HR sai.

## 5. MAX30102 Và SpO2

### Bạn cần học

MAX30102 dùng LED đỏ và hồng ngoại để đo SpO2. Trong dự án này, MAX30102 chủ yếu dùng cho SpO2, không dùng làm nguồn HR chính.

### Nằm ở đâu trong code

| Nội dung | File / hàm |
|---|---|
| Kiểm tra ngón tay | `updateFingerPresence()` |
| Đọc MAX30102 | `readMax30102()` khoảng dòng 1014 |
| Thu red/IR buffer | `gRedBuffer`, `gIrBuffer` |
| Tính SpO2 | `maxim_heart_rate_and_oxygen_saturation()` |
| Gửi SpO2 | `publishHealthData()` |

### Code quan trọng

```cpp
maxim_heart_rate_and_oxygen_saturation(
    gIrBuffer,
    kMaxSampleCount,
    gRedBuffer,
    &spo2,
    &validSpo2,
    &ignoredHr,
    &ignoredValidHr
);
```

### Câu trả lời mẫu

> MAX30102 được dùng để đo SpO2. Hàm thư viện xử lý buffer red/IR để tính SpO2. HR chính của dự án lấy từ ECG AD8232 để tách vai trò giữa PPG và ECG.

## 6. MPU6050 Và Phát Hiện Ngã

### Bạn cần học

MPU6050 đo gia tốc 3 trục. Hệ thống tính độ lớn vector gia tốc:

```text
accel_mag = sqrt(ax² + ay² + az²)
```

Nếu gia tốc quá lớn hoặc quá nhỏ có thể là va đập hoặc rơi tự do.

### Nằm ở đâu trong code

| Nội dung | File / hàm |
|---|---|
| Đọc MPU6050 | `readMpu6050()` khoảng dòng 1080 |
| Chuyển raw sang g | `Config::MPU_RAW_TO_G` |
| Rule phát hiện ngã | `runEdgeAi()` |
| Backend rule | `server/ai_engine.py`, `_rule_vote()` |

### Câu trả lời mẫu

> MPU6050 dùng để phát hiện ngã bằng gia tốc tổng hợp. Nếu gia tốc vượt ngưỡng hoặc có trạng thái fall từ firmware, backend tạo cảnh báo.

## 7. DS18B20 Và Nhiệt Độ

### Bạn cần học

DS18B20 là cảm biến nhiệt độ 1-Wire. Cần điện trở kéo lên 4.7k giữa DQ và 3.3V.

### Nằm ở đâu trong code

| Nội dung | File / hàm |
|---|---|
| Khởi tạo OneWire | `OneWire oneWire(Config::DS18B20_PIN)` |
| Đọc nhiệt độ | `readDs18b20()` khoảng dòng 1067 |
| Gửi nhiệt độ | `publishHealthData()` |
| OLED nhiệt độ | `renderMainScreen()` |

### Câu trả lời mẫu

> DS18B20 đo nhiệt độ cơ thể hoặc môi trường tiếp xúc. Firmware đọc theo chu kỳ riêng vì DS18B20 phản hồi chậm hơn các cảm biến khác.

## 8. OLED Dashboard Trên Thiết Bị

### Bạn cần học

OLED hiển thị trạng thái tại thiết bị:

- HR
- SpO2
- Nhiệt độ
- ECG OK/OFF
- WiFi/MQTT/NTP

### Nằm ở đâu trong code

| Nội dung | File / hàm |
|---|---|
| Khởi tạo OLED | `setupDisplay()` |
| Cập nhật OLED | `updateDisplay()` |
| Màn hình chính | `renderMainScreen()` khoảng dòng 1348 |
| Menu | `renderMenuScreen()` |
| Chi tiết HR | `renderHrDetailScreen()` |

### Câu trả lời mẫu

> OLED giúp người dùng biết trạng thái thiết bị ngay cả khi chưa mở dashboard. Ví dụ ECG lead-off, WiFi/MQTT lỗi hoặc HR đang đo.

## 9. MQTT Và HiveMQ

### Bạn cần học

MQTT là giao thức publish/subscribe nhẹ cho IoT.

ESP32 publish dữ liệu lên topic:

```text
health/patient_001/data
```

Server subscribe:

```text
health/+/data
```

### Nằm ở đâu trong code

| Nội dung | File / hàm |
|---|---|
| Broker firmware | `main.cpp`, `kMqttBroker` |
| Publish JSON | `publishHealthData()` |
| MQTT server subscriber | `server/mqtt_handler.py` |
| Xử lý data message | `_handle_data_message()` khoảng dòng 156 |
| Subscribe topic | `on_connect()` khoảng dòng 210 |

### Code server quan trọng

```python
client.subscribe(TOPIC_DATA, qos=1)
```

```python
def _handle_data_message(topic, data):
    detection = DETECT_ANOMALY(data)
    save_to_firebase(device_id, data)
```

### Câu trả lời mẫu

> MQTT giúp ESP32 gửi dữ liệu realtime mà không cần gọi HTTP nặng. Backend subscribe topic `health/+/data` để nhận dữ liệu từ nhiều bệnh nhân.

## 10. JSON Payload Từ ESP32

### Bạn cần học

Payload chính gồm:

```json
{
  "device_id": "patient_001",
  "heart_rate": 75,
  "heart_rate_source": "ad8232",
  "heart_rate_valid": true,
  "spo2": 98,
  "spo2_source": "max30102",
  "spo2_valid": true,
  "temperature": 36.8,
  "ecg_raw": 1800,
  "ecg_samples": [250],
  "accel_x": 0.01,
  "accel_y": 0.02,
  "accel_z": 0.98,
  "fall": false,
  "edge_alert": false
}
```

### Nằm ở đâu trong code

`esp32_firmware/src/main.cpp`, hàm `publishHealthData()` khoảng dòng 1591.

### Câu trả lời mẫu

> Em dùng JSON để backend dễ parse và mở rộng. Mỗi field có thêm trạng thái valid/source để biết dữ liệu đến từ cảm biến nào và có hợp lệ không.

## 11. Flask API

### Bạn cần học

Flask API cung cấp dữ liệu cho dashboard:

```text
GET /api/health/status
GET /api/patients
GET /api/health/<id>/latest
GET /api/health/<id>/history
GET /api/health/<id>/ecg_latest
GET /api/alerts/<id>
GET /api/report/<id>
POST /api/predict/<id>
```

### Nằm ở đâu trong code

`server/app.py`

| Endpoint | Hàm |
|---|---|
| `/api/health/status` | `health_status()` khoảng dòng 244 |
| `/api/patients` | `patients()` |
| `/api/health/<id>/latest` | `latest()` |
| `/api/health/<id>/history` | `history()` |
| `/api/health/<id>/ecg_latest` | `ecg_latest()` |
| `/api/alerts/<id>` | `alerts()` |
| `/api/report/<id>` | `report()` |
| `/api/predict/<id>` | `predict()` |

### Câu trả lời mẫu

> Flask API tách dashboard khỏi Firebase và MQTT. Dashboard chỉ cần gọi API, còn backend chịu trách nhiệm đọc Firebase, chạy AI và trả dữ liệu chuẩn hóa.

## 12. Firebase Realtime Database

### Bạn cần học

Firebase lưu 3 nhóm chính:

```text
patients/{device_id}/latest
patients/{device_id}/history/{date}/{time}
alerts/{device_id}/{alert_id}
```

### Nằm ở đâu trong code

`server/firebase_handler.py`

| Nội dung | Hàm |
|---|---|
| Lưu latest/history | `save_to_firebase()` khoảng dòng 82 |
| Lấy latest | `get_latest()` |
| Lấy history | `get_history()` |
| Lấy ECG latest | `get_latest_ecg()` |
| Lưu alert | `save_alert()` |
| Lấy alerts | `get_alerts()` |
| Lấy bệnh nhân | `get_all_patients()` |

### Câu trả lời mẫu

> Firebase Realtime Database lưu latest để dashboard đọc nhanh và lưu history để vẽ biểu đồ 24h. Alert được lưu riêng để hiển thị lịch sử cảnh báo.

## 13. AI Engine Tổng Quan

### Bạn cần học

AI Engine gồm:

1. Rule-based alert.
2. Isolation Forest.
3. ECG Autoencoder.
4. LSTM prediction.
5. Fallback prediction khi chưa đủ dữ liệu.

### Nằm ở đâu trong code

`server/ai_engine.py`

| Nội dung | Hàm |
|---|---|
| Load model | `AIEngine.__init__()` |
| Rule-based | `_rule_vote()` khoảng dòng 263 |
| Isolation Forest | `_isolation_vote()` khoảng dòng 292 |
| ECG Autoencoder | `detect_ecg_anomaly()` khoảng dòng 314 |
| Ensemble | `detect_anomaly()` khoảng dòng 329 |
| LSTM prediction | `predict_trend()` khoảng dòng 389 |

### Câu trả lời mẫu

> AI Engine chạy ở backend. Khi có dữ liệu mới, backend gọi `detect_anomaly()` để kết hợp rule-based, Isolation Forest và ECG Autoencoder. Kết quả trả về gồm boolean bất thường, lý do và confidence.

## 14. Rule-Based Alert

### Bạn cần học

Rule-based dùng cho tình huống nguy hiểm cần cảnh báo ngay:

- SpO2 quá thấp
- HR quá cao hoặc quá thấp
- Sốt cao
- Ngã
- SOS thủ công

### Nằm ở đâu trong code

`server/ai_engine.py`, hàm `_rule_vote()`.

### Câu trả lời mẫu

> Em không phụ thuộc hoàn toàn vào AI cho tình huống nguy hiểm. Rule-based đảm bảo các ngưỡng y tế quan trọng được cảnh báo ngay.

## 15. Isolation Forest

### Bạn cần học

Isolation Forest là thuật toán phát hiện bất thường không giám sát hoặc bán giám sát. Nó học phân bố dữ liệu bình thường. Điểm nào dễ bị cô lập thì được xem là bất thường.

### Feature dùng trong dự án

```text
heart_rate
spo2
temperature
hr_rolling_mean
hr_rolling_std
spo2_change
accel_mag
```

### Nằm ở đâu trong code

| Nội dung | File |
|---|---|
| Notebook train | `ai_training/notebooks/02_isolation_forest_loso.ipynb` |
| Model lưu | `models/isolation_forest.pkl` |
| Scaler | `models/scaler.pkl` |
| Load/chạy model | `server/ai_engine.py`, `_isolation_vote()` |

### Câu trả lời mẫu

> Isolation Forest học từ dữ liệu bình thường. Khi dữ liệu mới có pattern lệch như HR cao kết hợp SpO2 thấp hoặc gia tốc bất thường, model có thể đánh dấu là anomaly.

## 16. LSTM Prediction

### Bạn cần học

LSTM dùng cho chuỗi thời gian. Trong dự án, LSTM dự đoán xu hướng HR.

Điều kiện:

```text
Cần ít nhất 24 mẫu HR hợp lệ.
```

Nếu firmware gửi mỗi 5 giây:

```text
24 mẫu ≈ 2 phút dữ liệu HR hợp lệ.
```

### Nằm ở đâu trong code

| Nội dung | File |
|---|---|
| Notebook train | `ai_training/notebooks/03_lstm_heart_predict.ipynb` |
| Model lưu | `models/lstm_heart_predict.h5` |
| Dự đoán server | `server/ai_engine.py`, `predict_trend()` |
| API prediction | `server/app.py`, `predict()` |
| Fallback prediction | `server/app.py`, `_fallback_predict()` |

### Câu trả lời mẫu

> LSTM dùng để dự đoán xu hướng HR. Nếu bệnh nhân mới chưa có đủ 24 mẫu HR hợp lệ, backend dùng fallback trend để dashboard không bị trống. Khi đủ dữ liệu, backend tự dùng LSTM thật.

## 17. ECG Autoencoder

### Bạn cần học

Autoencoder học cách tái tạo ECG bình thường. Nếu ECG mới tái tạo lỗi cao, coi là bất thường.

Quy trình:

1. Tải MIT-BIH.
2. Lọc bandpass 0.5-40Hz.
3. Lấy nhịp bình thường `symbol='N'`.
4. Tạo window 250 điểm.
5. Train Conv1D Autoencoder.
6. Tính reconstruction error.
7. Threshold = percentile 95.

### Nằm ở đâu trong code

| Nội dung | File |
|---|---|
| Notebook train | `ai_training/notebooks/04_ecg_autoencoder.ipynb` |
| Model | `models/ecg_autoencoder.h5` |
| Threshold | `models/ecg_threshold.npy` |
| Load model | `server/ai_engine.py`, `_load_ecg_model()` |
| Detect ECG anomaly | `server/ai_engine.py`, `detect_ecg_anomaly()` |

### Câu trả lời mẫu

> ECG Autoencoder không chẩn đoán bệnh. Nó chỉ đánh giá waveform có giống pattern ECG bình thường đã học hay không. Nếu reconstruction error vượt threshold thì đánh dấu bất thường.

## 18. Data Preprocessing Và Augmentation

### Bạn cần học

Các bước xử lý dữ liệu:

1. Load dữ liệu có nhãn.
2. Làm sạch giá trị bất hợp lý.
3. Tạo rolling feature.
4. Scale bằng MinMaxScaler.
5. Augment dữ liệu bằng noise, scale, jitter.

### Nằm ở đâu trong code

| Notebook | Mục đích |
|---|---|
| `01_preprocess.ipynb` | Làm sạch và tạo feature |
| `01b_augmentation.ipynb` | Nhân dữ liệu 5 lần |
| `02_isolation_forest_loso.ipynb` | Train Isolation Forest |
| `03_lstm_heart_predict.ipynb` | Train LSTM |
| `04_ecg_autoencoder.ipynb` | Train ECG Autoencoder |

### Câu trả lời mẫu

> Em tiền xử lý dữ liệu bằng cách loại giá trị không hợp lệ, tạo rolling mean/std cho HR, tính thay đổi SpO2 và gia tốc tổng hợp. Sau đó em dùng augmentation để tăng độ đa dạng dữ liệu.

## 19. Dashboard Streamlit

### Bạn cần học

Dashboard gồm:

- Realtime vitals.
- Device status.
- Chart HR, SpO2, Temperature.
- AI Score chart.
- ECG waveform.
- Alert history.
- Patient info.
- Report.

### Nằm ở đâu trong code

| Nội dung | File |
|---|---|
| Entry point | `dashboard/streamlit_app.py` |
| API client | `dashboard/api_client.py` |
| Format dữ liệu | `dashboard/formatters.py` |
| Theme/CSS | `dashboard/styles.py` |
| Metric cards | `dashboard/components/cards.py` |
| Charts | `dashboard/components/charts.py` |
| Views/tabs | `dashboard/components/views.py` |

### Hàm quan trọng

```text
render_overview()
render_ecg()
render_alerts()
render_report()
render_metric_cards()
vital_line()
ai_score_chart()
ecg_waveform()
prediction_chart()
```

### Câu trả lời mẫu

> Dashboard được tách component để dễ mở rộng. `api_client.py` gọi API, `views.py` dựng các tab, `charts.py` dựng biểu đồ Plotly, `cards.py` dựng metric cards.

## 20. Telegram Alert

### Bạn cần học

Telegram là kênh cảnh báo ngoài dashboard. Nếu alert bot chưa hoàn chỉnh, server dùng fallback lưu alert vào Firebase.

### Nằm ở đâu trong code

| Nội dung | File |
|---|---|
| Load alert sender | `server/mqtt_handler.py`, `_load_alert_sender()` |
| Fallback alert | `_fallback_send_alert()` |
| Fallback fall alert | `_fallback_send_fall_alert()` |
| File bot | `server/alert_bot.py` |

### Câu trả lời mẫu

> Telegram là kênh mở rộng để gửi cảnh báo ra ngoài. Nếu bot chưa cấu hình, backend vẫn lưu alert vào Firebase để dashboard hiển thị.

## 21. PDF Report

### Bạn cần học

PDF report hiện là bản tối giản phục vụ demo:

- Patient ID
- Latest vitals
- Status
- Recent alerts

### Nằm ở đâu trong code

`server/app.py`

| Nội dung | Hàm |
|---|---|
| Tạo PDF đơn giản | `_simple_pdf()` |
| Escape text PDF | `_pdf_escape()` |
| Endpoint report | `report()` |

### Câu trả lời mẫu

> PDF report hiện là bản tối giản để chứng minh pipeline báo cáo. Sau này có thể thay bằng thư viện tạo PDF chuyên nghiệp và template y tế đầy đủ.

## 22. Các Model Và File Lưu Ở Đâu

### Thư mục model

```text
models/
├── isolation_forest.pkl
├── scaler.pkl
├── model_info.json
├── lstm_heart_predict.h5
├── ecg_autoencoder.h5
├── ecg_threshold.npy
├── health_classifier.pkl
└── health_classifier_report.json
```

### Ý nghĩa

| File | Ý nghĩa |
|---|---|
| `isolation_forest.pkl` | Model phát hiện bất thường đa biến |
| `scaler.pkl` | Chuẩn hóa feature cho Isolation Forest |
| `model_info.json` | Metadata model |
| `lstm_heart_predict.h5` | Model LSTM dự đoán HR |
| `ecg_autoencoder.h5` | Model Autoencoder ECG |
| `ecg_threshold.npy` | Ngưỡng reconstruction error |

## 23. Các Lệnh Cần Nhớ

### Chạy server

```bat
cd d:\HOCTAP\N3\K2\DACN1\aiot_health
.venv\Scripts\activate
cd server
python app.py
```

### Chạy dashboard

```bat
cd d:\HOCTAP\N3\K2\DACN1\aiot_health
.venv\Scripts\activate
streamlit run dashboard\streamlit_app.py
```

### Nạp firmware

```bat
cd d:\HOCTAP\N3\K2\DACN1\aiot_health\esp32_firmware
pio run --target upload --target monitor
```

### Build firmware

```bat
cd d:\HOCTAP\N3\K2\DACN1\aiot_health\esp32_firmware
pio run
```

## 24. Các Câu Hỏi Hội Đồng Hay Hỏi

### AI ở đâu?

> AI chạy ở backend Python, trong `server/ai_engine.py`. ESP32 chỉ thu dữ liệu và gửi MQTT.

### Train AI như thế nào?

> Em dùng notebook trong `ai_training/notebooks`. Dữ liệu được làm sạch, tạo feature rolling, augmentation, sau đó train Isolation Forest, LSTM và ECG Autoencoder.

### Tại sao không chạy AI trên ESP32?

> ESP32 có tài nguyên hạn chế. Backend phù hợp hơn để chạy model Python, lưu log, cập nhật model và kết nối dashboard.

### Tại sao dùng Firebase?

> Firebase giúp lưu realtime latest/history/alerts và dashboard có thể đọc dữ liệu ổn định.

### Nếu cảm biến lỗi thì sao?

> Payload có các field `*_valid` và status. Dashboard hiển thị sensor invalid hoặc lead-off thay vì cố đưa ra kết luận sai.

### Nếu chưa đủ dữ liệu LSTM thì sao?

> Backend dùng fallback prediction để demo không bị trống. Khi đủ 24 mẫu HR hợp lệ, hệ thống dùng LSTM thật.

### Hệ thống có chẩn đoán bệnh không?

> Không. Hệ thống chỉ hỗ trợ theo dõi và cảnh báo bất thường, không thay thế bác sĩ.

## 25. Thứ Tự Ưu Tiên Khi Học

Nếu thời gian ít, học theo thứ tự:

1. Luồng tổng thể ESP32 → MQTT → Backend → Firebase → Dashboard.
2. `publishHealthData()` gửi JSON như thế nào.
3. `server/mqtt_handler.py` nhận MQTT và gọi AI.
4. `server/firebase_handler.py` lưu latest/history/alerts.
5. `server/ai_engine.py` rule-based và Isolation Forest.
6. Dashboard đọc API và hiển thị biểu đồ.
7. AD8232 đo ECG và HR.
8. LSTM fallback.
9. ECG Autoencoder.
10. PDF report và Telegram.

## 26. Tóm Tắt Một Câu Để Nói Với Hội Đồng

```text
Đây là hệ thống AIoT theo dõi sức khỏe realtime: ESP32-S3 thu dữ liệu cảm biến, gửi qua MQTT đến backend, backend chạy cảnh báo và AI, lưu Firebase, dashboard hiển thị realtime và lịch sử cảnh báo. AI chính là Isolation Forest, còn LSTM và ECG Autoencoder là module mở rộng cho dự đoán xu hướng và phân tích waveform ECG.
```
