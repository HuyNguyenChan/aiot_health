#include <Arduino.h>
#include <Wire.h>
#include <math.h>

#include <MPU6050.h>
#include "config.h"

namespace {

MPU6050 mpu;
uint32_t lastReadMs = 0;
bool sensorFound = false;
constexpr uint8_t kMpu6050I2cAddress = 0x68;
constexpr uint32_t kReconnectIntervalMs = 1500;
uint32_t lastReconnectMs = 0;

bool isMpu6050Online() {
  Wire.beginTransmission(kMpu6050I2cAddress);
  return Wire.endTransmission() == 0;
}

void printMagnitudeStatus(int16_t ax, int16_t ay, int16_t az, float magnitude) {
  Serial.print(F("ax="));
  Serial.print(ax);
  Serial.print(F(" ay="));
  Serial.print(ay);
  Serial.print(F(" az="));
  Serial.print(az);
  Serial.print(F(" | mag="));
  Serial.print(magnitude, 2);

  if (magnitude > 2.5f || magnitude < 0.3f) {
    Serial.println(F(" -> NGA PHAT HIEN!"));
  } else {
    Serial.println(F(" -> Binh thuong"));
  }
}

}  // namespace

void setup() {
  Serial.begin(Config::SERIAL_BAUD);
  delay(1000);

  Wire.begin(Config::I2C_SDA_PIN, Config::I2C_SCL_PIN, Config::I2C_CLOCK_HZ);
  Serial.printf(
      "I2C map: SDA=GPIO%u SCL=GPIO%u\n",
      static_cast<unsigned>(Config::I2C_SDA_PIN),
      static_cast<unsigned>(Config::I2C_SCL_PIN));

  sensorFound = isMpu6050Online();
  if (!sensorFound) {
    Serial.println(F("WARN: MPU6050 chua online tren I2C (0x68)."));
    return;
  }

  mpu.initialize();
  sensorFound = mpu.testConnection();
  Serial.println(sensorFound ? F("MPU6050 connected: OK")
                             : F("WARN: MPU6050 testConnection() that bai."));
}

void loop() {
  if (!sensorFound) {
    const uint32_t now = millis();
    if (now - lastReconnectMs >= kReconnectIntervalMs) {
      lastReconnectMs = now;
      sensorFound = isMpu6050Online();
      if (sensorFound) {
        mpu.initialize();
        sensorFound = mpu.testConnection();
        Serial.println(sensorFound ? F("MPU6050 connected: OK")
                                   : F("WARN: MPU6050 testConnection() that bai."));
      }
    }
    return;
  }

  const uint32_t now = millis();
  if (now - lastReadMs < 500) {
    return;
  }
  lastReadMs = now;

  int16_t axRaw = 0;
  int16_t ayRaw = 0;
  int16_t azRaw = 0;
  int16_t gxRaw = 0;
  int16_t gyRaw = 0;
  int16_t gzRaw = 0;

  mpu.getMotion6(&axRaw, &ayRaw, &azRaw, &gxRaw, &gyRaw, &gzRaw);

  const float ax = static_cast<float>(axRaw);
  const float ay = static_cast<float>(ayRaw);
  const float az = static_cast<float>(azRaw);
  const float magnitude = sqrtf(ax * ax + ay * ay + az * az) / 16384.0f;

  printMagnitudeStatus(axRaw, ayRaw, azRaw, magnitude);
}
