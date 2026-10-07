#include <Arduino.h>
#include <math.h>

#include "config.h"

namespace {

constexpr uint16_t kSampleCount = 250;
constexpr uint8_t kOversampleCount = 4;
constexpr uint32_t kSampleIntervalMs = 20;  // 50Hz
constexpr uint16_t kMinBeatIntervalSamples = 15;   // 300ms = 200 bpm max
constexpr uint16_t kMaxBeatIntervalSamples = 100;  // 2000ms = 30 bpm min
constexpr float kPeakThresholdStdRatio = 0.65f;
constexpr float kMinPeakAboveMean = 90.0f;

uint16_t samples[kSampleCount];

uint16_t readEcgOversampled() {
  uint32_t sum = 0;
  for (uint8_t i = 0; i < kOversampleCount; ++i) {
    sum += analogRead(Config::AD8232_OUTPUT_PIN);
    delayMicroseconds(250);
  }
  return static_cast<uint16_t>(sum / kOversampleCount);
}

void printLeadStatus(bool loPlus, bool loMinus) {
  Serial.print(F("LO+="));
  Serial.print(loPlus ? F("HIGH") : F("LOW"));
  Serial.print(F(" LO-="));
  Serial.print(loMinus ? F("HIGH") : F("LOW"));
  Serial.print(F(" | "));
}

float estimateHeartRateBpm(float mean, float stdDev, bool ecgOk, uint8_t* beatCountOut) {
  *beatCountOut = 0;
  if (!ecgOk || stdDev < 10.0f) {
    return 0.0f;
  }

  const float threshold = mean + fmaxf(kMinPeakAboveMean, stdDev * kPeakThresholdStdRatio);
  uint16_t lastPeakIndex = 0;
  bool hasLastPeak = false;
  uint32_t rrSumSamples = 0;
  uint8_t rrCount = 0;
  bool aboveThreshold = false;

  for (uint16_t i = 1; i + 1 < kSampleCount; ++i) {
    const bool localPeak = samples[i] >= samples[i - 1] && samples[i] > samples[i + 1];
    const bool strongPeak = static_cast<float>(samples[i]) >= threshold;

    if (!aboveThreshold && localPeak && strongPeak &&
        (!hasLastPeak || i - lastPeakIndex >= kMinBeatIntervalSamples)) {
      if (hasLastPeak) {
        const uint16_t rrSamples = i - lastPeakIndex;
        if (rrSamples <= kMaxBeatIntervalSamples) {
          rrSumSamples += rrSamples;
          ++rrCount;
        }
      }
      lastPeakIndex = i;
      hasLastPeak = true;
      aboveThreshold = true;
      ++(*beatCountOut);
    } else if (aboveThreshold && static_cast<float>(samples[i]) < mean) {
      aboveThreshold = false;
    }
  }

  if (rrCount == 0) {
    return 0.0f;
  }

  const float avgRrSamples = static_cast<float>(rrSumSamples) / rrCount;
  return 60.0f * (1000.0f / kSampleIntervalMs) / avgRrSamples;
}

void captureAndPrintEcgWindow() {
  uint32_t sum = 0;
  uint64_t sumSquares = 0;

  for (uint16_t i = 0; i < kSampleCount; ++i) {
    const uint32_t sampleStartMs = millis();
    const uint16_t value = readEcgOversampled();

    samples[i] = value;
    sum += value;
    sumSquares += static_cast<uint64_t>(value) * value;

    const uint32_t elapsedMs = millis() - sampleStartMs;
    if (elapsedMs < kSampleIntervalMs) {
      delay(kSampleIntervalMs - elapsedMs);
    }
  }

  const float mean = static_cast<float>(sum) / kSampleCount;
  float variance = static_cast<float>(sumSquares) / kSampleCount - mean * mean;
  if (variance < 0.0f) {
    variance = 0.0f;
  }
  const float stdDev = sqrtf(variance);

  const bool loPlus = digitalRead(Config::AD8232_LO_PLUS_PIN) == HIGH;
  const bool loMinus = digitalRead(Config::AD8232_LO_MINUS_PIN) == HIGH;
  const bool ecgOk = !loPlus && !loMinus;
  uint8_t beatCount = 0;
  const float heartRateBpm = estimateHeartRateBpm(mean, stdDev, ecgOk, &beatCount);

  printLeadStatus(loPlus, loMinus);
  Serial.print(F("ECG_OK="));
  Serial.print(ecgOk ? F("true") : F("false"));
  Serial.print(F(" | mean="));
  Serial.print(static_cast<int>(roundf(mean)));
  Serial.print(F(" | std="));
  Serial.print(static_cast<int>(roundf(stdDev)));
  Serial.print(F(" | beats="));
  Serial.print(beatCount);
  Serial.print(F(" | HR="));
  if (heartRateBpm > 0.0f) {
    Serial.print(static_cast<int>(roundf(heartRateBpm)));
    Serial.println(F(" bpm"));
  } else {
    Serial.println(F("-- bpm"));
  }
}

}  // namespace

void setup() {
  Serial.begin(Config::SERIAL_BAUD);
  delay(1000);

  pinMode(Config::AD8232_OUTPUT_PIN, ANALOG);
  pinMode(Config::AD8232_LO_PLUS_PIN, INPUT);
  pinMode(Config::AD8232_LO_MINUS_PIN, INPUT);
  analogReadResolution(12);
  analogSetPinAttenuation(Config::AD8232_OUTPUT_PIN, ADC_11db);

  Serial.println();
  Serial.println(F("Bat dau test AD8232."));
  Serial.printf(
      "AD8232 map: OUTPUT=GPIO%u ADC1_CH0 LO+=GPIO%u LO-=GPIO%u\n",
      static_cast<unsigned>(Config::AD8232_OUTPUT_PIN),
      static_cast<unsigned>(Config::AD8232_LO_PLUS_PIN),
      static_cast<unsigned>(Config::AD8232_LO_MINUS_PIN));
  Serial.println(F("Luu y ESP32-S3: chi dung ADC1 GPIO1-10, khong dung ADC2 khi WiFi bat."));
  Serial.println(F("LO+/LO- HIGH = dien cuc bi roi."));
  Serial.println(F("HR duoc uoc tinh tu dinh ECG trong cua so 5 giay."));
}

void loop() {
  captureAndPrintEcgWindow();
}
