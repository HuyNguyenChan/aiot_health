# Hướng Dẫn Demo Dự Án AIoT Health Monitor

Tài liệu này dùng để chạy demo đồ án một cách ổn định, có kịch bản rõ ràng và có phương án xử lý khi dữ liệu cảm biến hoặc AI chưa đủ.

## 1. Mục Tiêu Demo

Mục tiêu khi demo không phải là chứng minh hệ thống chẩn đoán y tế hoàn chỉnh. Mục tiêu là chứng minh:

1. ESP32-S3 đọc cảm biến và gửi dữ liệu realtime.
2. Backend nhận dữ liệu qua MQTT, xử lý cảnh báo và lưu Firebase.
3. Dashboard hiển thị realtime, biểu đồ, ECG, cảnh báo và báo cáo.
4. AI có vai trò hỗ trợ phát hiện bất thường, nhưng hệ thống vẫn ổn định khi dữ liệu AI chưa đủ.

Thông điệp chính khi trình bày:

```text
Hệ thống ưu tiên cảnh báo an toàn bằng rule-based, sau đó dùng AI để tăng khả năng phát hiện bất thường đa biến.
Khi dữ liệu chưa đủ cho AI, hệ thống có fallback để dashboard không bị trống và không bị crash.
```

## 2. Thứ Tự Chạy Dự Án

### Bước 1: Chạy Flask Backend

Mở terminal 1:

```bat
cd d:\HOCTAP\N3\K2\DACN1\aiot_health
.venv\Scripts\activate
cd server
python app.py
```

Log đúng cần thấy:

```text
[AI] Loaded scaler.pkl
[AI] Loaded isolation_forest.pkl
[AI] Loaded lstm_heart_predict.h5 weights with fallback architecture
[AI] ECG Autoencoder weights loaded
[MQTT] Connected
[MQTT] Subscribed: health/+/data
Running on http://127.0.0.1:5000
```

Nếu thấy lỗi `Failed to load ... directly` nhưng sau đó có dòng `weights with fallback architecture` thì vẫn ổn.

### Bước 2: Chạy Dashboard

Mở terminal 2:

```bat
cd d:\HOCTAP\N3\K2\DACN1\aiot_health
.venv\Scripts\activate
streamlit run dashboard\streamlit_app.py
```

Mở trình duyệt:

```text
http://localhost:8501
```

Trong sidebar chọn:

```text
Bệnh nhân: patient_001
Realtime update: bật
Auto refresh: 5-10 giây
```

### Bước 3: Nạp Và Monitor ESP32

Mở terminal 3:

```bat
cd d:\HOCTAP\N3\K2\DACN1\aiot_health\esp32_firmware
pio run --target upload --target monitor
```

Nếu upload xong mà terminal đứng ở:

```text
Hard resetting via RTS pin...
```

hãy bấm nút `RST/EN` trên ESP32.

## 3. Kiểm Tra Nhanh Trước Khi Demo

Mở các URL sau để kiểm tra API:

```text
http://127.0.0.1:5000/api/health/status
http://127.0.0.1:5000/api/patients
http://127.0.0.1:5000/api/health/patient_001/latest
http://127.0.0.1:5000/api/alerts/patient_001?limit=20
```

Nếu các URL trả JSON thì backend và Firebase đang hoạt động.

## 4. Kịch Bản Demo Chính Trong 15 Phút

### Phần 1: Giới Thiệu Kiến Trúc

Nói ngắn gọn:

```text
ESP32-S3 đọc cảm biến AD8232, MAX30102, MPU6050 và DS18B20.
Dữ liệu được gửi qua MQTT HiveMQ về Flask backend.
Backend xử lý rule-based alert, AI score, lưu Firebase.
Dashboard Streamlit hiển thị realtime, biểu đồ, ECG waveform, cảnh báo và báo cáo.
```

### Phần 2: Demo Dữ Liệu Realtime

Trên dashboard tab `Tổng quan`, chỉ vào:

- Nhịp tim
- SpO2
- Nhiệt độ
- Ngã
- AI Score
- Trạng thái thiết bị

Nói:

```text
Mỗi bản ghi mới từ ESP32 được lưu vào Firebase ở latest và history.
Dashboard tự cập nhật theo chu kỳ realtime.
```

### Phần 3: Demo Biểu Đồ

Chỉ vào các biểu đồ:

- Nhịp tim 24h - AD8232 ECG
- SpO2 24h - MAX30102
- Nhiệt độ 24h - DS18B20
- AI Score 24h

Nói:

```text
Các biểu đồ lấy từ lịch sử Firebase. AI Score là mức độ bất thường do backend tính.
Mốc 67% tương ứng với 2/3 nguồn đánh giá đồng ý bất thường.
```

### Phần 4: Demo Cảnh Báo

Chọn một tình huống dễ demo:

- Lắc MPU6050 để mô phỏng ngã.
- Gửi payload test HR cao.
- Gửi payload test SpO2 thấp.

Sau đó mở tab `Cảnh báo`.

Nói:

```text
Cảnh báo nguy hiểm được xử lý bằng rule-based để phản ứng nhanh.
Isolation Forest hỗ trợ phát hiện pattern bất thường đa biến.
```

### Phần 5: Demo ECG

Mở tab `ECG waveform`.

Nói:

```text
AD8232 cung cấp tín hiệu ECG raw. Firmware gửi 250 mẫu tương ứng 5 giây ở tần số 50Hz.
Dashboard vẽ waveform realtime. Nếu điện cực rời, hệ thống báo lead-off thay vì đưa ra kết luận sai.
```

### Phần 6: Demo Dự Đoán LSTM

Ở tab tổng quan, chỉ vào biểu đồ dự đoán.

Nói:

```text
Khi có đủ 24 mẫu HR hợp lệ, backend dùng LSTM thật.
Nếu chưa đủ dữ liệu, backend dùng fallback trend để dashboard không bị trống khi demo.
```

### Phần 7: Demo Báo Cáo

Mở tab `Report`, bấm tải báo cáo.

Nói:

```text
Báo cáo PDF hiện là bản tối giản, tổng hợp latest vitals và các cảnh báo gần đây.
Phần này có thể mở rộng thành báo cáo y tế đầy đủ.
```

## 5. Chạy Các Trường Hợp Đặc Biệt Khi Demo

### Trường Hợp A: Bình Thường

Mục tiêu:

```text
Dashboard xanh, không có cảnh báo mới.
```

Cách làm:

1. Cắm ESP32.
2. Đảm bảo server đã chạy.
3. Mở dashboard.
4. Chờ dữ liệu MQTT đi vào server.

Log server mong đợi:

```text
[MQTT] Received topic=health/patient_001/data ...
[DATA] patient_001 | HR=... SpO2=... Temp=...
```

Nếu HR hoặc SpO2 đang bằng `0`, vẫn có thể nói:

```text
Thiết bị đang gửi dữ liệu, nhưng cảm biến chưa có giá trị hợp lệ. Dashboard vẫn hiển thị trạng thái invalid thay vì crash.
```

### Trường Hợp B: HR Cao

Mục tiêu:

```text
Tạo cảnh báo nhịp tim cao.
```

Cách demo thật:

- Nếu AD8232 đo được HR thật, chờ HR vượt ngưỡng là khó. Không nên phụ thuộc cách này.

Cách demo ổn định:

- Dùng payload test hoặc chỉnh dữ liệu test từ backend/MQTT.

Payload mẫu:

```json
{
  "device_id": "patient_001",
  "heart_rate": 170,
  "heart_rate_valid": true,
  "heart_rate_source": "demo",
  "spo2": 98,
  "spo2_valid": true,
  "temperature": 36.7,
  "accel_x": 0,
  "accel_y": 0,
  "accel_z": 1,
  "fall": false,
  "edge_alert": false,
  "alert_reason": ""
}
```

Cách nói:

```text
Đây là tình huống test để chứng minh luồng cảnh báo. Khi HR vượt ngưỡng nguy hiểm, backend sinh alert và lưu vào Firebase.
```

### Trường Hợp C: SpO2 Thấp

Mục tiêu:

```text
Tạo cảnh báo thiếu oxy.
```

Payload mẫu:

```json
{
  "device_id": "patient_001",
  "heart_rate": 82,
  "heart_rate_valid": true,
  "spo2": 86,
  "spo2_valid": true,
  "temperature": 36.6,
  "accel_x": 0,
  "accel_y": 0,
  "accel_z": 1,
  "fall": false,
  "edge_alert": false,
  "alert_reason": ""
}
```

Cách nói:

```text
SpO2 thấp là tình huống nguy hiểm, nên rule-based cảnh báo ngay, không chờ AI.
```

### Trường Hợp D: Ngã

Mục tiêu:

```text
Dashboard và alert history hiển thị phát hiện ngã.
```

Cách demo thật:

- Lắc mạnh hoặc xoay nhanh module MPU6050.
- Không nên làm rơi thiết bị thật.

Payload mẫu:

```json
{
  "device_id": "patient_001",
  "heart_rate": 88,
  "heart_rate_valid": true,
  "spo2": 97,
  "spo2_valid": true,
  "temperature": 36.8,
  "accel_x": 3.1,
  "accel_y": 0.2,
  "accel_z": 0.1,
  "fall": true,
  "edge_alert": true,
  "alert_reason": "FALL_DETECTED"
}
```

Cách nói:

```text
Ngã được xử lý ở cả edge device và backend. Điều này giúp cảnh báo nhanh ngay cả khi AI chưa phân tích xong.
```

### Trường Hợp E: ECG Điện Cực Rời

Mục tiêu:

```text
Chứng minh hệ thống biết trạng thái lỗi cảm biến ECG.
```

Cách làm:

- Tháo một điện cực AD8232.
- Quan sát OLED hoặc Serial.

OLED có thể hiện:

```text
HR: dien cuc roi
ECG: OFF
```

Serial có thể hiện:

```text
[ECG] LO+=HIGH LO-=LOW ...
```

Cách nói:

```text
ECG là tín hiệu nhạy với tiếp xúc điện cực. Khi lead-off, hệ thống không cố dự đoán sai mà báo lỗi cảm biến.
```

### Trường Hợp F: ECG Có Tín Hiệu Nhưng Chưa Có HR

OLED có thể hiện:

```text
HR: dang do 45%
ECG: chua bat dinh
```

Ý nghĩa:

```text
Thiết bị đang thu đủ 250 mẫu ECG trong 5 giây. Nếu chưa bắt được đỉnh R rõ thì HR chưa hợp lệ.
```

Cách nói:

```text
HR từ ECG cần cửa sổ tín hiệu đủ sạch. Nếu tín hiệu nhiễu hoặc người dùng cử động, hệ thống tiếp tục đo thay vì hiển thị HR sai.
```

### Trường Hợp G: LSTM Chưa Đủ Dữ Liệu

Điều kiện LSTM thật:

```text
Cần ít nhất 24 mẫu HR hợp lệ.
Mỗi mẫu khoảng 5 giây.
=> tối thiểu khoảng 2 phút dữ liệu HR hợp lệ.
```

Nếu chưa đủ:

```text
Backend dùng fallback_demo.
Dashboard vẫn có đường dự đoán để không bị trống.
```

Cách nói:

```text
Với bệnh nhân mới, hệ thống chưa có đủ lịch sử cho LSTM. Vì vậy backend dùng fallback trend.
Khi đủ 24 mẫu HR hợp lệ, backend tự chuyển sang LSTM thật.
```

### Trường Hợp H: Isolation Forest Chưa Đáng Tin Do Sensor Lỗi

Ví dụ dữ liệu lỗi:

```text
HR = 0
SpO2 = 0
accel_x = 0
accel_y = 0
accel_z = 0
```

Cách nói:

```text
AI chỉ có ý nghĩa khi dữ liệu đầu vào hợp lệ. Nếu cảm biến trả 0 hoặc invalid, dashboard ưu tiên hiển thị trạng thái thiết bị để tránh diễn giải sai.
```

## 6. Khi Nào Nói Là AI Thật, Khi Nào Nói Là Fallback?

### AI thật

| Module | Khi nào là thật |
|---|---|
| Isolation Forest | Khi có vitals hợp lệ và model đã load |
| LSTM | Khi có ít nhất 24 mẫu HR hợp lệ |
| ECG Autoencoder | Khi có đủ 250 mẫu `ecg_samples` |

### Fallback/mock

| Module | Khi nào fallback |
|---|---|
| LSTM | HR chưa đủ 24 mẫu hoặc model trả rỗng |
| Report | PDF hiện là bản tối giản để demo |
| ECG waveform | Nếu chưa có `ecg_samples`, dashboard có thể dùng lịch sử `ecg_raw` gần nhất |

Không nên giấu fallback. Nói thẳng:

```text
Fallback giúp hệ thống vận hành ổn định khi bệnh nhân mới chưa có đủ dữ liệu. Đây là cơ chế thường gặp trong hệ thống thực tế.
```

## 7. Câu Trả Lời Khi Hội Đồng Hỏi Khó

### Hỏi: AI có chẩn đoán bệnh không?

Trả lời:

```text
Không. AI trong hệ thống đóng vai trò hỗ trợ phát hiện bất thường và ưu tiên cảnh báo.
Hệ thống không thay thế bác sĩ và không đưa ra chẩn đoán y khoa.
```

### Hỏi: Tại sao vừa dùng rule vừa dùng AI?

Trả lời:

```text
Rule-based dùng cho các ngưỡng nguy hiểm cần phản ứng ngay.
AI dùng để phát hiện pattern bất thường đa biến mà rule đơn giản khó bao phủ.
```

### Hỏi: Tại sao LSTM chưa dự đoán thật?

Trả lời:

```text
LSTM cần chuỗi thời gian đủ dài và HR hợp lệ. Với bệnh nhân mới chưa đủ dữ liệu, hệ thống dùng fallback trend.
Khi đủ dữ liệu, backend tự dùng LSTM thật.
```

### Hỏi: Tại sao ECG không phải lúc nào cũng có HR?

Trả lời:

```text
ECG phụ thuộc nhiều vào tiếp xúc điện cực và nhiễu chuyển động.
Firmware chỉ chấp nhận HR khi bắt được đỉnh ECG hợp lệ, tránh hiển thị số sai.
```

### Hỏi: Vì sao cần Firebase?

Trả lời:

```text
Firebase lưu latest, history và alerts theo thời gian thực.
Nó giúp dashboard và các module khác đọc lại dữ liệu mà không phụ thuộc trực tiếp vào ESP32.
```

## 8. Checklist Trước Khi Vào Demo

- [ ] Server Flask chạy.
- [ ] Dashboard mở được.
- [ ] MQTT connected.
- [ ] Firebase có `patients/patient_001/latest`.
- [ ] ESP32 publish dữ liệu mới.
- [ ] Dashboard không bị trắng chữ.
- [ ] Alert history có ít nhất một cảnh báo mẫu.
- [ ] Report PDF tải được.
- [ ] LSTM chart không trống nhờ fallback.
- [ ] ECG tab không crash khi thiếu dữ liệu.
- [ ] Nếu demo ECG thật, LO+ và LO- phải LOW.
- [ ] Nếu demo SpO2, đặt tay lên MAX30102 trước vài giây.
- [ ] Nếu demo fall, kiểm tra MPU6050 không trả toàn 0.

## 9. Kiến Trúc Demo Khuyên Dùng

```text
ESP32-S3
  -> MQTT HiveMQ
  -> Flask Backend
      -> Rule-based alert
      -> Isolation Forest AI Score
      -> LSTM nếu đủ dữ liệu, fallback nếu chưa đủ
      -> ECG Autoencoder nếu đủ ecg_samples
  -> Firebase Realtime Database
      -> patients/{id}/latest
      -> patients/{id}/history
      -> alerts/{id}
  -> Streamlit Dashboard
      -> Realtime vitals
      -> Charts
      -> ECG waveform
      -> Alerts
      -> Report
```
