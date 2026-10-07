#include <Arduino.h>
#include <Wire.h>
#include <math.h>

#include "MAX30105.h"
#include "config.h"
#include "spo2_algorithm.h"

namespace {

MAX30105 particleSensor;

constexpr uint16_t kSampleCount = 100;
constexpr uint32_t kSampleTimeoutMs = 1200;
constexpr uint32_t kBlinkIntervalMs = 250;
constexpr uint32_t kFingerThreshold = 50000;
constexpr int32_t kHrFilterMinBpm = 40;
constexpr int32_t kHrFilterMaxBpm = 180;
constexpr int32_t kHrDoubleCountMinBpm = 130;
constexpr int32_t kHrDoubleCountMaxBpm = 190;
constexpr float kHrJumpRejectBpm = 35.0f;
constexpr uint8_t kHrMedianWindow = 3;
constexpr uint8_t kHrMinStableSamples = 3;

constexpr uint8_t kLedPin =
#ifdef LED_BUILTIN
    LED_BUILTIN;
#else
    Config::LED_OK_PIN;
#endif

uint32_t irBuffer[kSampleCount];
uint32_t redBuffer[kSampleCount];
bool sensorFound = false;
uint32_t lastBlinkMs = 0;
bool blinkState = false;
float hrFilterWindow[kHrMedianWindow] = {};
uint8_t hrFilterCount = 0;
uint8_t hrFilterIndex = 0;
uint32_t hrAcceptedCount = 0;

void resetHeartRateFilter() {
  hrFilterCount = 0;
  hrFilterIndex = 0;
  hrAcceptedCount = 0;
  for (uint8_t i = 0; i < kHrMedianWindow; ++i) {
    hrFilterWindow[i] = 0.0f;
  }
}

float medianFilteredHeartRate() {
  if (hrFilterCount == 0) {
    return 0.0f;
  }

  float sorted[kHrMedianWindow] = {};
  for (uint8_t i = 0; i < hrFilterCount; ++i) {
    sorted[i] = hrFilterWindow[i];
  }

  for (uint8_t i = 1; i < hrFilterCount; ++i) {
    const float value = sorted[i];
    int8_t j = static_cast<int8_t>(i) - 1;
    while (j >= 0 && sorted[j] > value) {
      sorted[j + 1] = sorted[j];
      --j;
    }
    sorted[j + 1] = value;
  }

  const uint8_t middle = hrFilterCount / 2;
  if ((hrFilterCount % 2U) == 1U) {
    return sorted[middle];
  }
  return (sorted[middle - 1] + sorted[middle]) / 2.0f;
}

bool updateHeartRateFilter(int32_t rawHr, float* filteredHr) {
  if (rawHr >= kHrDoubleCountMinBpm && rawHr <= kHrDoubleCountMaxBpm) {
    const int32_t correctedHr = rawHr / 2;
    if (correctedHr >= kHrFilterMinBpm && correctedHr <= 110) {
      rawHr = correctedHr;
    }
  }

  if (rawHr < kHrFilterMinBpm || rawHr > kHrFilterMaxBpm) {
    if (hrAcceptedCount >= kHrMinStableSamples && hrFilterCount > 0) {
      *filteredHr = medianFilteredHeartRate();
      return true;
    }
    return false;
  }

  if (hrFilterCount >= kHrMedianWindow) {
    const float currentMedian = medianFilteredHeartRate();
    if (currentMedian > 0.0f &&
        fabsf(static_cast<float>(rawHr) - currentMedian) > kHrJumpRejectBpm) {
      if (hrAcceptedCount >= kHrMinStableSamples) {
        *filteredHr = currentMedian;
        return true;
      }
      return false;
    }
  }

  hrFilterWindow[hrFilterIndex] = static_cast<float>(rawHr);
  hrFilterIndex = (hrFilterIndex + 1U) % kHrMedianWindow;
  if (hrFilterCount < kHrMedianWindow) {
    ++hrFilterCount;
  }
  ++hrAcceptedCount;

  *filteredHr = medianFilteredHeartRate();
  return hrAcceptedCount >= kHrMinStableSamples;
}

void blinkErrorLed() {
  const uint32_t now = millis();
  if (now - lastBlinkMs < kBlinkIntervalMs) {
    return;
  }

  lastBlinkMs = now;
  blinkState = !blinkState;
  digitalWrite(kLedPin, blinkState ? HIGH : LOW);
}

bool waitForNextSample() {
  const uint32_t start = millis();
  while (!particleSensor.available()) {
    particleSensor.check();
    if (millis() - start > kSampleTimeoutMs) {
      return false;
    }
    delay(1);
  }
  return true;
}

bool captureSamples() {
  for (uint16_t i = 0; i < kSampleCount; ++i) {
    if (!waitForNextSample()) {
      return false;
    }
    redBuffer[i] = particleSensor.getRed();
    irBuffer[i] = particleSensor.getIR();
    particleSensor.nextSample();
  }
  return true;
}

void printMetrics() {
  int32_t spo2 = 0;
  int8_t validSpo2 = 0;
  int32_t heartRate = 0;
  int8_t validHeartRate = 0;

  maxim_heart_rate_and_oxygen_saturation(
      irBuffer,
      kSampleCount,
      redBuffer,
      &spo2,
      &validSpo2,
      &heartRate,
      &validHeartRate);

  const uint32_t latestIr = irBuffer[kSampleCount - 1];
  if (latestIr < kFingerThreshold) {
    resetHeartRateFilter();
  }

  float filteredHr = 0.0f;
  const bool stableHr =
      validHeartRate && latestIr >= kFingerThreshold &&
      updateHeartRateFilter(heartRate, &filteredHr);

  Serial.print(F("HR="));
  if (stableHr) {
    Serial.print(static_cast<int>(filteredHr));
    Serial.print(F(" bpm"));
  } else {
    Serial.print(F("-- bpm"));
  }

  Serial.print(F(" | SpO2="));
  if (validSpo2 && spo2 >= 50 && spo2 <= 100) {
    Serial.print(spo2);
    Serial.print(F("%"));
  } else {
    Serial.print(F("--%"));
  }

  Serial.print(F(" | IR="));
  Serial.print(latestIr);

  Serial.print(F(" | rawHR="));
  if (validHeartRate) {
    Serial.println(heartRate);
  } else {
    Serial.println(F("--"));
  }
}

}  // namespace

void setup() {
  pinMode(kLedPin, OUTPUT);
  digitalWrite(kLedPin, LOW);

  Serial.begin(Config::SERIAL_BAUD);
  delay(1000);

  Serial.println();
  Serial.println(F("Khoi dong MAX30102 test..."));
  Serial.printf(
      "I2C map: SDA=GPIO%u SCL=GPIO%u\n",
      static_cast<unsigned>(Config::I2C_SDA_PIN),
      static_cast<unsigned>(Config::I2C_SCL_PIN));

  Wire.begin(Config::I2C_SDA_PIN, Config::I2C_SCL_PIN);

  if (!particleSensor.begin(Wire, I2C_SPEED_STANDARD)) {
    Serial.println(F("Khong tim thay MAX30102. Kiem tra day noi va nguon."));
    sensorFound = false;
    return;
  }

  sensorFound = true;
  Serial.println(F("Da tim thay MAX30102"));

  const byte ledBrightness = 60;
  const byte sampleAverage = 4;
  const byte ledMode = 2;
  const int sampleRate = 100;
  const int pulseWidth = 411;
  const int adcRange = 4096;

  particleSensor.setup(
      ledBrightness,
      sampleAverage,
      ledMode,
      sampleRate,
      pulseWidth,
      adcRange);

  particleSensor.setPulseAmplitudeRed(0x3F);
  particleSensor.setPulseAmplitudeIR(0x3F);
  particleSensor.setPulseAmplitudeGreen(0);

  Serial.println(F("Dat ngon tay len cam bien..."));
}

void loop() {
  if (!sensorFound) {
    blinkErrorLed();
    return;
  }

  if (!captureSamples()) {
    Serial.println(F("Loi: Het thoi gian doc 100 samples tu MAX30102."));
    sensorFound = false;
    digitalWrite(kLedPin, LOW);
    return;
  }

  printMetrics();
}
`