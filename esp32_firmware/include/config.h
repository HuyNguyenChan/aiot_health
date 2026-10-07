#pragma once

#include <Arduino.h>

// File này là nơi gom toàn bộ cấu hình tĩnh của firmware:
// - chân GPIO
// - thông số bus giao tiếp
// - ngưỡng cảnh báo
// - các chu kỳ thời gian trong loop
//
// Dự án hiện đã chuyển sang ESP32-S3 N16R8.
// Các chân dưới đây là "app wiring" của dự án, không phải chân cố định theo board.
// Nghĩa là khi đổi sang kit ESP32-S3, cần đấu dây cảm biến/nút/LED đúng theo map này.
//
// Mục tiêu là mọi "con số cấu hình" đều nằm ở một chỗ để:
// - dễ đọc
// - dễ đổi phần cứng
// - tránh hard-code rải rác trong nhiều file
//
// Dùng namespace Config giúp truy cập rõ nghĩa, ví dụ:
// Config::LED_OK_PIN, Config::MQTT_TLS_PORT...
namespace Config {

// =========================================================
// Serial / Debug
// =========================================================

// Tốc độ UART dùng cho Serial Monitor.
// AGENTS.md yêu cầu baudrate là 115200 nên toàn bộ firmware nên thống nhất giá trị này.
constexpr uint32_t SERIAL_BAUD = 115200;

// =========================================================
// I2C Bus
// =========================================================

// ESP32 dùng chung một bus I2C cho:
// - MAX30102
// - MPU6050
// - OLED SSD1306
//
// Trên board ESP32-S3 DevKitC-1 mà project đang dùng thực tế,
// GPIO22 không được breakout ra header. Vì vậy ta chọn cặp I2C khác
// có sẵn trên board, dễ đấu dây và không đụng USB native.
//
// SDA = GPIO8
// SCL = GPIO9
constexpr uint8_t I2C_SDA_PIN = 8;
constexpr uint8_t I2C_SCL_PIN = 9;

// Tốc độ I2C 400kHz (Fast Mode).
// Mức này phù hợp cho cảm biến và OLED khi cần phản hồi nhanh hơn 100kHz.
// Nếu hệ thống bị nhiễu hoặc dây quá dài, có thể cần giảm xuống 100000.
constexpr uint32_t I2C_CLOCK_HZ = 400000;

// =========================================================
// Cảm biến nhiệt DS18B20
// =========================================================

// Chân data của DS18B20.
// AGENTS.md yêu cầu thêm điện trở kéo lên 4.7k giữa DQ và 3.3V.
constexpr uint8_t DS18B20_PIN = 4;

// =========================================================
// Cảm biến ECG AD8232
// =========================================================

// AD8232 dùng nguồn 3.3V và GND chung với ESP32-S3.
// Nên đặt tụ 100nF giữa OUTPUT và GND gần module để giảm nhiễu cao tần.
//
// ESP32-S3: ADC1_CH0 là GPIO1. Tránh dùng ADC2 cho ECG vì ADC2 dễ xung đột WiFi.
constexpr uint8_t AD8232_OUTPUT_PIN = 1;

// Hai chân lead-off của AD8232 báo điện cực bị rời.
// Module AD8232 thường xuất HIGH khi điện cực tương ứng chưa tiếp xúc tốt.
constexpr uint8_t AD8232_LO_PLUS_PIN = 11;
constexpr uint8_t AD8232_LO_MINUS_PIN = 12;

constexpr uint16_t ADC_MAX_RAW = 4095;
constexpr uint16_t ADC_REFERENCE_MV = 3300;

// =========================================================
// Nút nhấn
// =========================================================

// Tất cả nút nhấn dùng INPUT_PULLUP.
// Điều đó có nghĩa là:
// - không nhấn  -> digitalRead() trả HIGH
// - đang nhấn   -> digitalRead() trả LOW
//
// Khi viết code xử lý nút, cần nhớ logic này để không bị ngược trạng thái.
// ESP32-S3 DevKitC-1 không có các chân 25/32/33 như map ESP32 cũ,
// nên chuyển sang các GPIO liền nhau, dễ cắm trên breadboard.
constexpr uint8_t BUTTON_SOS_PIN = 5;
constexpr uint8_t BUTTON_MENU_PIN = 6;
constexpr uint8_t BUTTON_OK_PIN = 7;

// =========================================================
// LED / Buzzer
// =========================================================

// Buzzer dùng để phát cảnh báo âm thanh cục bộ.
// LED_ERR báo lỗi, LED_OK báo trạng thái hoạt động bình thường.
// Chọn các GPIO output có thật trên board S3 và tránh các chân đặc biệt
// như USB D+/D-, BOOT strap hoặc UART debug mặc định.
constexpr uint8_t BUZZER_PIN = 16;
constexpr uint8_t LED_ERR_PIN = 17;
constexpr uint8_t LED_OK_PIN = 18;

// =========================================================
// OLED SSD1306
// =========================================================

// Kích thước màn OLED phổ biến 128x64.
// Nếu sau này đổi sang màn 128x32 thì cần đổi lại hai giá trị này.
constexpr uint8_t OLED_WIDTH = 128;
constexpr uint8_t OLED_HEIGHT = 64;

// Nhiều module SSD1306 I2C không nối chân reset riêng,
// nên thư viện Adafruit thường dùng -1 để biểu thị "không có chân reset cứng".
constexpr int8_t OLED_RESET_PIN = -1;

// Địa chỉ I2C phổ biến của SSD1306 là 0x3C.
// Một số module khác có thể là 0x3D, nên nếu không quét thấy màn hình hãy kiểm tra chỗ này.
constexpr uint8_t OLED_I2C_ADDRESS = 0x3C;

// =========================================================
// MQTT / TLS
// =========================================================

// Port tiêu chuẩn cho MQTT over TLS.
// HiveMQ Cloud và nhiều broker cloud thường dùng cổng này.
constexpr uint16_t MQTT_TLS_PORT = 8883;

// Dev mode có thể dùng WiFiClientSecure::setInsecure() để bỏ qua kiểm tra certificate.
// Tiện cho giai đoạn thử nghiệm, nhưng khi triển khai thật nên thay bằng CA cert chuẩn.
constexpr bool MQTT_USE_INSECURE_TLS = true;

// =========================================================
// Ngưỡng cảnh báo sức khỏe / va chạm
// =========================================================

// Nếu heart rate vượt quá ngưỡng này thì xem là nhịp tim cao bất thường.
constexpr float HEART_RATE_HIGH_BPM = 150.0f;

// Nếu heart rate thấp hơn ngưỡng này thì xem là nhịp tim thấp bất thường.
constexpr float HEART_RATE_LOW_BPM = 40.0f;

// SpO2 thấp hơn ngưỡng này thì xem là thiếu oxy máu ở mức cần cảnh báo.
constexpr float SPO2_LOW_PERCENT = 92.0f;

// Nhiệt độ cao hơn mức này thì xem là sốt.
constexpr float TEMPERATURE_FEVER_C = 38.5f;

// Ngưỡng phát hiện ngã theo gia tốc tổng hợp:
// - quá lớn: có thể là va đập mạnh
// - quá nhỏ: có thể là trạng thái rơi tự do ngắn
constexpr float FALL_G_HIGH = 2.5f;
constexpr float FALL_G_LOW = 0.3f;

// MPU6050 thường trả gia tốc raw, muốn đổi ra đơn vị g thì chia cho hệ số này
// khi cảm biến đang ở dải đo mặc định ±2g.
constexpr float MPU_RAW_TO_G = 16384.0f;

// =========================================================
// Chu kỳ thời gian cho loop không chặn
// =========================================================

// Chu kỳ đọc nhóm cảm biến chính như MAX30102 hoặc MPU6050.
// Giá trị này ảnh hưởng trực tiếp đến độ mượt của dữ liệu realtime.
constexpr uint32_t SENSOR_READ_INTERVAL_MS = 1000;

// DS18B20 phản hồi chậm hơn nên thường đọc theo chu kỳ thưa hơn cảm biến khác.
constexpr uint32_t TEMPERATURE_READ_INTERVAL_MS = 2000;

// Chu kỳ làm tươi nội dung OLED.
// Không nên refresh quá nhanh vì gây tốn CPU và làm màn nhấp nháy.
constexpr uint32_t DISPLAY_REFRESH_INTERVAL_MS = 500;

// Chu kỳ publish dữ liệu từ ESP32 lên MQTT.
// Nếu giảm quá thấp sẽ tăng lưu lượng mạng và tải broker.
constexpr uint32_t MQTT_PUBLISH_INTERVAL_MS = 5000;

// Nếu MQTT bị ngắt kết nối, đây là khoảng nghỉ giữa hai lần reconnect.
constexpr uint32_t MQTT_RECONNECT_INTERVAL_MS = 5000;

// Tương tự cho WiFi: tránh việc retry liên tục quá nhanh làm loop bị nghẽn.
constexpr uint32_t WIFI_RECONNECT_INTERVAL_MS = 10000;

// Thời gian debounce nút nhấn để lọc rung tiếp điểm cơ khí.
// 50ms là mức phổ biến và đủ an toàn cho nút nhấn tay.
constexpr uint32_t BUTTON_DEBOUNCE_MS = 50;

// Giữ nút lâu hơn mốc này thì có thể coi là long press.
// Phù hợp cho các tác vụ như SOS, xác nhận, hoặc mở menu đặc biệt.
constexpr uint32_t BUTTON_LONG_PRESS_MS = 2000;

// Thời lượng buzzer kêu khi có cảnh báo cục bộ.
constexpr uint32_t ALERT_BUZZER_DURATION_MS = 750;

// Chu kỳ chớp LED trạng thái/lỗi trong các hiệu ứng không chặn.
constexpr uint32_t STATUS_LED_BLINK_INTERVAL_MS = 250;

}  // namespace Config
