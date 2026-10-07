#include <Arduino.h>
#include <DallasTemperature.h>
#include <OneWire.h>

#include "config.h"

namespace {

// OneWire là lớp giao tiếp bus 1-wire mức thấp với DS18B20 trên GPIO4.
OneWire oneWire(Config::DS18B20_PIN);

// DallasTemperature bọc phía trên OneWire để việc request/read nhiệt độ đơn giản hơn.
DallasTemperature temperatureSensors(&oneWire);

// Lưu thời điểm đọc gần nhất để loop chạy theo kiểu non-blocking.
uint32_t lastReadMs = 0;

void printTemperatureStatus(float temperatureC) {
  // DS18B20 thường trả -127C khi không đọc được dữ liệu hợp lệ:
  // hở dây, sai chân, mất nguồn hoặc thiếu pull-up 4.7k.
  if (temperatureC == DEVICE_DISCONNECTED_C || temperatureC <= -127.0f) {
    Serial.println(F("Loi: thieu dien tro pull-up 4.7kO!"));
    return;
  }

  // In giá trị nhiệt độ ra Serial để theo dõi trực tiếp trên monitor.
  Serial.print(F("Nhiet do: "));
  Serial.print(temperatureC, 2);
  Serial.println(F(" C"));

  // Theo yêu cầu test, chỉ cần cảnh báo khi vượt 38.0C.
  if (temperatureC > 38.0f) {
    Serial.println(F("CANH BAO: Nhiet do cao!"));
  }
}

}  // namespace

void setup() {
  Serial.begin(Config::SERIAL_BAUD);

  // Chờ ngắn để Serial Monitor kịp attach sau khi board reset.
  delay(1000);

  // Khởi tạo thư viện DS18B20.
  temperatureSensors.begin();

  Serial.println();
  Serial.println(F("Bat dau test DS18B20 tren GPIO4."));
}

void loop() {
  const uint32_t now = millis();

  // Đọc nhiệt độ mỗi 2 giây theo đúng yêu cầu, không dùng delay dài để giữ loop thông thoáng.
  if (now - lastReadMs < Config::TEMPERATURE_READ_INTERVAL_MS) {
    return;
  }

  lastReadMs = now;

  // Gửi lệnh cho DS18B20 đo nhiệt độ ở chu kỳ hiện tại.
  temperatureSensors.requestTemperatures();

  // Lấy nhiệt độ của cảm biến đầu tiên trên bus 1-wire.
  const float temperatureC = temperatureSensors.getTempCByIndex(0);
  printTemperatureStatus(temperatureC);
}
