#include <Arduino.h>
#include <Wire.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <time.h>
#include <math.h>

#include <OneWire.h>
#include <DallasTemperature.h>
#include <MPU6050.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

#include "MAX30105.h"
#include "spo2_algorithm.h"
#include "config.h"
#include "secrets.h"

namespace {

constexpr char DEVICE_ID[] = "patient_001";
constexpr char MQTT_BROKER[] = "5c8137ba9bc24241bbe92500a0ab993d.s1.eu.hivemq.cloud";
constexpr char TOPIC_DATA[] = "health/patient_001/data";
constexpr char TOPIC_ALERT[] = "health/patient_001/alert";
constexpr char TOPIC_MEDICINE[] = "health/patient_001/medicine";
constexpr char TOPIC_CMD[] = "health/patient_001/cmd";
constexpr char TOPIC_STATUS[] = "health/patient_001/status";

constexpr uint32_t ECG_DT = 20;                 // 50 Hz
constexpr uint16_t ECG_N = 250;                 // 5 seconds
constexpr uint8_t ECG_OVERSAMPLE = 4;
constexpr uint16_t ECG_RR_MIN = 15;
constexpr uint16_t ECG_RR_MAX = 100;
constexpr uint32_t ECG_HR_STALE = 8000;
constexpr float ECG_STD_RATIO = 0.65f;
constexpr float ECG_MIN_PEAK = 90.0f;

constexpr uint32_t MPU_DT = 500;
constexpr uint32_t FINGER_DT = 500;
constexpr uint32_t SENSOR_DT = 60000;           // thay cho menu chọn thời gian đo
constexpr uint32_t NTP_RETRY_DT = 15000;
constexpr uint32_t MAX_TIMEOUT = 1200;
constexpr uint32_t FINGER_THRESHOLD = 50000;
constexpr uint16_t MAX_N = 100;
constexpr long UTC_OFFSET = 7L * 3600L;
constexpr uint32_t BUZZ_ON = 200;
constexpr uint32_t BUZZ_OFF = 350;
constexpr uint32_t BLINK_DT = 400;

constexpr int32_t HR_MIN = 40;
constexpr int32_t HR_MAX = 180;
constexpr uint8_t HR_MEDIAN_N = 3;
constexpr uint8_t HR_STABLE_N = 3;

struct Button {
  uint8_t pin;
  bool lastRaw = HIGH, stable = HIGH, longFired = false;
  uint32_t lastDebounce = 0, pressStart = 0;
};

enum BtnEvent { BTN_NONE, BTN_SOS_SHORT, BTN_SOS_LONG, BTN_OK_SHORT };

struct SensorState {
  bool maxFound = false, dsFound = false, mpuFound = false, oledFound = false;
  bool finger = false, hrValid = false, spo2Valid = false;
  bool ecgLoPlus = false, ecgLoMinus = false, ecgLeadOff = false;
  bool fall = false, alert = false;
  float hr = 0, spo2 = 0, temp = 0;
  float ax = 0, ay = 0, az = 0, amag = 0;
  uint16_t ecgRaw = 0, ecgMv = 0, ecgMin = Config::ADC_MAX_RAW, ecgMax = 0;
  uint32_t ecgSum = 0, ecgCount = 0, ecgLastHrMs = 0;
  uint16_t ecgIdx = 0;
  float ecgMean = 0, ecgStd = 0, ecgLastBpm = 0;
  uint8_t ecgBeats = 0;
  char ecgStatus[24] = "waiting";
  uint32_t ir = 0, red = 0;
  float hrMin = 999, hrMax = 0, hrSum = 0, hrSqSum = 0;
  uint32_t hrCount = 0;
  float spo2Min = 100, spo2Max = 0, spo2Sum = 0;
  uint32_t spo2Count = 0;
  float hrWin[HR_MEDIAN_N] = {};
  uint8_t hrWinCount = 0, hrWinIdx = 0;
  uint32_t hrAccepted = 0, hrRejected = 0;
  char reason[48] = "";
};

struct NetState {
  bool wifi = false, mqtt = false, ntp = false;
  uint32_t lastWifi = 0, lastMqtt = 0, lastNtp = 0;
};

struct MedicineState {
  bool enabled = false, active = false, acknowledged = false;
  int hour = 8, minute = 0, lastYday = -1;
  char label[32] = "Thuoc";
};

struct AppState {
  uint32_t lastEcg = 0, lastMpu = 0, lastFinger = 0, lastTemp = 0, lastSpo2 = 0;
  uint32_t lastDisplay = 0, lastPublish = 0, lastBuzzer = 0;
  bool buzzer = false, sos = false, lastFall = false;
  char status[48] = "Booting";
};

MAX30105 maxSensor;
OneWire oneWire(Config::DS18B20_PIN);
DallasTemperature ds18b20(&oneWire);
MPU6050 mpu;
Adafruit_SSD1306 display(Config::OLED_WIDTH, Config::OLED_HEIGHT, &Wire, Config::OLED_RESET_PIN);
WiFiClientSecure wifiClient;
PubSubClient mqtt(wifiClient);

SensorState S;
NetState N;
MedicineState M;
AppState A;
Button btnSos{Config::BUTTON_SOS_PIN}, btnOk{Config::BUTTON_OK_PIN};
uint32_t irBuf[MAX_N], redBuf[MAX_N];
uint16_t ecgBuf[ECG_N];

void copyText(char *dst, size_t n, const char *src) { if (n) snprintf(dst, n, "%s", src ? src : ""); }
bool i2cOnline(uint8_t addr) { Wire.beginTransmission(addr); return Wire.endTransmission() == 0; }
void beep(uint16_t f, uint16_t d) { tone(Config::BUZZER_PIN, f, d); }

bool localTime(tm *t) { return getLocalTime(t, 10); }
void timeString(char *buf, size_t n) {
  tm t;
  if (localTime(&t)) strftime(buf, n, "%Y-%m-%d %H:%M:%S", &t);
  else snprintf(buf, n, "unsynced");
}
/// pub
void jsonPublish(const char *topic, JsonDocument &doc) {
  char payload[4096];
  size_t len = serializeJson(doc, payload, sizeof(payload));
  mqtt.publish(topic, payload, len);
}

void publishAlert(const char *type, const char *reason) {
  if (!mqtt.connected()) return;
  JsonDocument doc;
  doc["device_id"] = DEVICE_ID;
  doc["type"] = type;
  doc["reason"] = reason;
  doc["medicine_active"] = M.active;
  char t[24]; timeString(t, sizeof(t)); doc["time"] = t;
  jsonPublish(TOPIC_ALERT, doc);
}

void publishMedicine(const char *state) {
  if (!mqtt.connected()) return;
  JsonDocument doc;
  doc["device_id"] = DEVICE_ID;
  doc["type"] = state;
  doc["label"] = M.label;
  doc["hour"] = M.hour;
  doc["minute"] = M.minute;
  char t[24]; timeString(t, sizeof(t)); doc["time"] = t;
  jsonPublish(TOPIC_MEDICINE, doc);
}

void triggerSos(const char *src) {
  A.sos = true;
  copyText(S.reason, sizeof(S.reason), "SOS_MANUAL");
  publishAlert("sos", src);
}

void applyMedicine(JsonVariantConst root) {
  JsonVariantConst med = root["medicine"].isNull() ? root : root["medicine"];
  if (!med["label"].isNull()) copyText(M.label, sizeof(M.label), med["label"]);
  if (!med["name"].isNull()) copyText(M.label, sizeof(M.label), med["name"]);
  if (!med["hour"].isNull()) M.hour = med["hour"].as<int>();
  if (!med["minute"].isNull()) M.minute = med["minute"].as<int>();
  M.enabled = med["enabled"].isNull() ? true : med["enabled"].as<bool>();
  M.acknowledged = false;
  publishMedicine("medicine_schedule_updated");
}

void onMqtt(char *topic, byte *payload, unsigned int len) {
  char msg[384];
  unsigned int n = min<unsigned int>(len, sizeof(msg) - 1);
  memcpy(msg, payload, n); msg[n] = 0;
  Serial.printf("[MQTT] %s -> %s\n", topic, msg);

  JsonDocument doc;
  if (deserializeJson(doc, msg)) return;
  if (String(topic) == TOPIC_MEDICINE) { applyMedicine(doc.as<JsonVariantConst>()); return; }

  const char *act = doc["action"] | "";
  if (!strcmp(act, "sos")) triggerSos("remote_cmd");
  else if (!strcmp(act, "clear_sos")) A.sos = false;
  else if (!strcmp(act, "medicine_ack")) { M.active = false; M.acknowledged = true; }
  else if (!strcmp(act, "set_medicine")) applyMedicine(doc.as<JsonVariantConst>());
}

void handleWiFi() {
  N.wifi = WiFi.status() == WL_CONNECTED;
  if (N.wifi || millis() - N.lastWifi < Config::WIFI_RECONNECT_INTERVAL_MS) return;
  N.lastWifi = millis();
  Serial.printf("[WiFi] Connecting to %s\n", WIFI_SSID);
  WiFi.disconnect(); WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
}

void syncNtp() {
  if (!N.wifi) { N.ntp = false; return; }
  if (N.ntp || millis() - N.lastNtp < NTP_RETRY_DT) return;
  N.lastNtp = millis();
  configTime(UTC_OFFSET, 0, "pool.ntp.org", "time.nist.gov");
  tm t; N.ntp = localTime(&t);
}

void handleMqtt() {
  N.mqtt = mqtt.connected();
  if (!N.wifi || N.mqtt || millis() - N.lastMqtt < Config::MQTT_RECONNECT_INTERVAL_MS) return;
  N.lastMqtt = millis();
  Serial.println("[MQTT] Connecting...");
  if (!mqtt.connect(DEVICE_ID, MQTT_USER, MQTT_PASS, TOPIC_STATUS, 1, true, "offline")) {
    Serial.printf("fail rc=%d\n", mqtt.state()); return;
  }
  mqtt.subscribe(TOPIC_CMD);
  mqtt.subscribe(TOPIC_ALERT);
  mqtt.subscribe(TOPIC_MEDICINE);
  mqtt.publish(TOPIC_STATUS, "online", true);
  N.mqtt = true;
}

BtnEvent readButton(Button &b, BtnEvent shortEv, BtnEvent longEv) {
  bool raw = digitalRead(b.pin);
  uint32_t now = millis();
  if (raw != b.lastRaw) { b.lastRaw = raw; b.lastDebounce = now; }
  if (now - b.lastDebounce < Config::BUTTON_DEBOUNCE_MS) return BTN_NONE;
  if (raw != b.stable) {
    b.stable = raw;
    if (raw == LOW) { b.pressStart = now; b.longFired = false; return BTN_NONE; }
    return b.longFired ? BTN_NONE : shortEv;
  }
  if (b.stable == LOW && !b.longFired && now - b.pressStart >= Config::BUTTON_LONG_PRESS_MS) {
    b.longFired = true;
    return longEv;
  }
  return BTN_NONE;
}

void handleButton(BtnEvent e) {
  if (e == BTN_SOS_SHORT) beep(1400, 100);
  else if (e == BTN_SOS_LONG) { beep(1800, 250); triggerSos("button_sos_long"); }
  else if (e == BTN_OK_SHORT) {
    beep(1200, 70);
    if (M.active) { M.active = false; M.acknowledged = true; publishMedicine("medicine_confirmed"); }
    else if (A.sos) A.sos = false;
  }
}

void resetEcgStats() {
  S.ecgMin = Config::ADC_MAX_RAW; S.ecgMax = 0; S.ecgSum = 0; S.ecgCount = 0; S.ecgIdx = 0;
  S.ecgMean = 0; S.ecgStd = 0; S.ecgLastBpm = 0; S.ecgBeats = 0;
  copyText(S.ecgStatus, sizeof(S.ecgStatus), "waiting");
}

void resetHr() {
  S.hrValid = false; S.hr = 0; S.ecgLastHrMs = 0;
  S.hrWinCount = S.hrWinIdx = 0; S.hrAccepted = S.hrRejected = 0;
  for (float &v : S.hrWin) v = 0;
}

uint16_t ecgMv(uint16_t raw) { return (uint32_t)raw * Config::ADC_REFERENCE_MV / Config::ADC_MAX_RAW; }
uint16_t readEcgRaw() {
  uint32_t sum = 0;
  for (uint8_t i = 0; i < ECG_OVERSAMPLE; i++) { sum += analogRead(Config::AD8232_OUTPUT_PIN); delayMicroseconds(250); }
  return sum / ECG_OVERSAMPLE;
}

void statAdd(float v, float *minV, float *maxV, float *sum, uint32_t *count) {
  if (v < *minV) *minV = v;
  if (v > *maxV) *maxV = v;
  *sum += v; (*count)++;
}

void acceptHr(float bpm) {
  if (bpm < HR_MIN || bpm > HR_MAX) return;
  S.hr = S.hrValid ? S.hr * 0.72f + bpm * 0.28f : bpm;
  S.hrValid = true; S.ecgLastHrMs = millis();
  statAdd(S.hr, &S.hrMin, &S.hrMax, &S.hrSum, &S.hrCount);
  S.hrSqSum += S.hr * S.hr;
}

float estimateHr(float mean, float stdDev, uint8_t *beats) {
  *beats = 0;
  if (stdDev < 10) return 0;
  float th = mean + fmaxf(ECG_MIN_PEAK, stdDev * ECG_STD_RATIO);
  uint16_t last = 0; bool hasLast = false, above = false;
  uint32_t rrSum = 0; uint8_t rrN = 0;

  for (uint16_t i = 1; i + 1 < ECG_N; i++) {
    bool peak = ecgBuf[i] >= ecgBuf[i - 1] && ecgBuf[i] > ecgBuf[i + 1] && ecgBuf[i] >= th;
    if (!above && peak && (!hasLast || i - last >= ECG_RR_MIN)) {
      if (hasLast && i - last <= ECG_RR_MAX) { rrSum += i - last; rrN++; }
      last = i; hasLast = true; above = true; (*beats)++;
    } else if (above && ecgBuf[i] < mean) above = false;
  }
  return rrN ? 60.0f * (1000.0f / ECG_DT) / (float(rrSum) / rrN) : 0;
}

void processEcgWindow() {
  uint32_t sum = 0; uint64_t sq = 0;
  for (uint16_t v : ecgBuf) { sum += v; sq += uint64_t(v) * v; }
  S.ecgMean = float(sum) / ECG_N;
  float var = float(sq) / ECG_N - S.ecgMean * S.ecgMean;
  S.ecgStd = sqrtf(max(0.0f, var));
  S.ecgLastBpm = estimateHr(S.ecgMean, S.ecgStd, &S.ecgBeats);

  if (S.ecgLastBpm > 0) { acceptHr(S.ecgLastBpm); copyText(S.ecgStatus, sizeof(S.ecgStatus), "HR ok"); }
  else if (S.hrValid && millis() - S.ecgLastHrMs > ECG_HR_STALE) { S.hrValid = false; copyText(S.ecgStatus, sizeof(S.ecgStatus), "HR stale"); }
  else if (S.ecgStd < 10) copyText(S.ecgStatus, sizeof(S.ecgStatus), "tin hieu phang");
  else if (S.ecgBeats < 2) copyText(S.ecgStatus, sizeof(S.ecgStatus), "chua bat dinh");
  else copyText(S.ecgStatus, sizeof(S.ecgStatus), "HR invalid");

  Serial.printf("[ECG] mean=%.0f std=%.0f beats=%u bpm=%.1f valid=%s %s\n",
                S.ecgMean, S.ecgStd, S.ecgBeats, S.ecgLastBpm, S.hrValid ? "true" : "false", S.ecgStatus);
}

void readAd8232() {
  S.ecgLoPlus = digitalRead(Config::AD8232_LO_PLUS_PIN) == HIGH;
  S.ecgLoMinus = digitalRead(Config::AD8232_LO_MINUS_PIN) == HIGH;
  S.ecgLeadOff = S.ecgLoPlus || S.ecgLoMinus;
  if (S.ecgLeadOff) {
    S.ecgRaw = S.ecgMv = 0; resetEcgStats(); resetHr(); copyText(S.ecgStatus, sizeof(S.ecgStatus), "dien cuc roi"); return;
  }

  uint16_t raw = readEcgRaw();
  S.ecgRaw = raw; S.ecgMv = ecgMv(raw);
  if (!S.ecgCount) S.ecgMin = S.ecgMax = raw;
  S.ecgMin = min(S.ecgMin, raw); S.ecgMax = max(S.ecgMax, raw);
  S.ecgSum += raw; S.ecgCount++;
  ecgBuf[S.ecgIdx++] = raw;
  if (S.ecgIdx >= ECG_N) { S.ecgIdx = 0; processEcgWindow(); }
  else if (S.hrValid && millis() - S.ecgLastHrMs > ECG_HR_STALE) S.hrValid = false;
}

bool waitMaxSample() {
  uint32_t start = millis();
  while (!maxSensor.available()) {
    maxSensor.check();
    if (millis() - A.lastEcg >= ECG_DT) { A.lastEcg = millis(); readAd8232(); }
    if (millis() - start > MAX_TIMEOUT) return false;
    delay(1);
  }
  return true;
}

void pollFinger() {
  if (!S.maxFound) { S.finger = false; return; }
  maxSensor.check();
  uint32_t ir = maxSensor.getIR();
  if (ir) S.ir = ir;
  S.finger = S.ir > FINGER_THRESHOLD;
  if (!S.finger) S.spo2Valid = false;
}

void readMax30102() {
  if (!S.maxFound) { S.spo2Valid = false; return; }
  for (uint16_t i = 0; i < MAX_N; i++) {
    if (!waitMaxSample()) { S.spo2Valid = false; copyText(S.reason, sizeof(S.reason), "MAX_TIMEOUT"); return; }
    redBuf[i] = maxSensor.getRed(); irBuf[i] = maxSensor.getIR(); maxSensor.nextSample();
  }
  S.red = redBuf[MAX_N - 1]; S.ir = irBuf[MAX_N - 1]; S.finger = S.ir > FINGER_THRESHOLD;
  if (!S.finger) { S.spo2Valid = false; S.spo2 = 0; return; }

  int32_t ignoreHr = 0, spo2 = 0; int8_t validHr = 0, validSpo2 = 0;
  maxim_heart_rate_and_oxygen_saturation(irBuf, MAX_N, redBuf, &spo2, &validSpo2, &ignoreHr, &validHr);
  S.spo2Valid = validSpo2 && spo2 >= 50 && spo2 <= 100;
  if (S.spo2Valid) { S.spo2 = spo2; statAdd(S.spo2, &S.spo2Min, &S.spo2Max, &S.spo2Sum, &S.spo2Count); }
}

void readTemp() {
  if (!S.dsFound) return;
  ds18b20.requestTemperatures();
  float t = ds18b20.getTempCByIndex(0);
  if (t > -55 && t < 125 && t != DEVICE_DISCONNECTED_C) S.temp = t + 1.0f;
}

void readMpu() {
  if (!S.mpuFound) return;
  int16_t ax, ay, az, gx, gy, gz;
  mpu.getMotion6(&ax, &ay, &az, &gx, &gy, &gz);
  S.ax = float(ax) / Config::MPU_RAW_TO_G;
  S.ay = float(ay) / Config::MPU_RAW_TO_G;
  S.az = float(az) / Config::MPU_RAW_TO_G;
  S.amag = sqrtf(S.ax * S.ax + S.ay * S.ay + S.az * S.az);
  S.fall = S.amag > Config::FALL_G_HIGH || S.amag < Config::FALL_G_LOW;
}

void runAlertLogic() {
  S.alert = false; copyText(S.reason, sizeof(S.reason), "");
  if (S.fall) { S.alert = true; copyText(S.reason, sizeof(S.reason), "FALL_DETECTED"); }
  else if (S.hrValid && S.hr > Config::HEART_RATE_HIGH_BPM) { S.alert = true; copyText(S.reason, sizeof(S.reason), "HR_HIGH"); }
  else if (S.hrValid && S.hr < Config::HEART_RATE_LOW_BPM) { S.alert = true; copyText(S.reason, sizeof(S.reason), "HR_LOW"); }
  else if (S.spo2Valid && S.spo2 < Config::SPO2_LOW_PERCENT) { S.alert = true; copyText(S.reason, sizeof(S.reason), "SPO2_LOW"); }
  else if (S.temp > Config::TEMPERATURE_FEVER_C) { S.alert = true; copyText(S.reason, sizeof(S.reason), "TEMP_HIGH"); }
}

void checkMedicine() {
  if (!M.enabled || !N.ntp) return;
  tm t; if (!localTime(&t)) return;
  if (t.tm_yday == M.lastYday) return;
  if (t.tm_hour == M.hour && t.tm_min == M.minute) {
    M.active = true; M.acknowledged = false; M.lastYday = t.tm_yday;
    publishMedicine("medicine_due");
  }
}

void refreshStatus() {
  if (M.active) copyText(A.status, sizeof(A.status), "Medicine reminder");
  else if (S.ecgLeadOff) copyText(A.status, sizeof(A.status), "ECG lead off");
  else if (S.alert) copyText(A.status, sizeof(A.status), S.reason);
  else if (!N.wifi) copyText(A.status, sizeof(A.status), "WiFi reconnecting");
  else if (!N.mqtt) copyText(A.status, sizeof(A.status), "MQTT reconnecting");
  else if (!N.ntp) copyText(A.status, sizeof(A.status), "NTP syncing");
  else copyText(A.status, sizeof(A.status), "Normal");
}

void updateOutputs() {
  bool alarm = S.alert || M.active || A.sos;
  digitalWrite(Config::LED_ERR_PIN, alarm);
  digitalWrite(Config::LED_OK_PIN, !alarm);
  if (!alarm) { if (A.buzzer) { noTone(Config::BUZZER_PIN); A.buzzer = false; } return; }

  uint32_t now = millis();
  if (now - A.lastBuzzer >= (A.buzzer ? BUZZ_ON : BUZZ_OFF)) {
    A.lastBuzzer = now; A.buzzer = !A.buzzer;
    if (A.buzzer) beep(M.active ? 1800 : 2200, BUZZ_ON); else noTone(Config::BUZZER_PIN);
  }
}

void drawHeader(const char *title, bool inv = false) {
  display.setTextSize(1);
  if (inv) { display.fillRect(0, 0, Config::OLED_WIDTH, 11, SSD1306_WHITE); display.setTextColor(SSD1306_BLACK); }
  else display.setTextColor(SSD1306_WHITE);
  display.setCursor(0, 2); display.print(title);
  display.setTextColor(SSD1306_WHITE);
}

void headerTime(char *buf, size_t n) {
  tm t;
  if (!localTime(&t)) { snprintf(buf, n, "Dang dong bo gio"); return; }
  const char *wd[] = {"CN", "T2", "T3", "T4", "T5", "T6", "T7"};
  snprintf(buf, n, "%s %02d/%02d %02d:%02d", wd[t.tm_wday], t.tm_mday, t.tm_mon + 1, t.tm_hour, t.tm_min);
}

void drawMain() {
  char h[24], status[14];
  headerTime(h, sizeof(h)); snprintf(status, sizeof(status), "%.13s", A.status);
  drawHeader(h, S.alert || M.active || A.sos);

  display.setCursor(0, 14);
  if (S.ecgLeadOff) display.print("HR:   dien cuc roi");
  else if (S.hrValid) display.printf("HR:   %3d bpm", int(S.hr));
  else display.printf("HR:   dang do %3u%%", uint32_t(S.ecgIdx) * 100U / ECG_N);

  display.setCursor(0, 25);
  if (!S.finger) display.print("SpO2: dat tay");
  else if (S.spo2Valid) display.printf("SpO2: %3d %%", int(S.spo2));
  else display.print("SpO2: dang do");

  display.setCursor(0, 36); display.printf("Temp: %.1f C", S.temp);
  display.setCursor(76, 36); display.print("ECG:"); display.print(S.ecgLeadOff ? "OFF" : "OK");
  display.setCursor(0, 47); display.print("ECG: "); display.print(S.hrValid ? status : S.ecgStatus);
  display.setCursor(0, 57); display.printf("W:%s M:%s T:%s", N.wifi ? "Y" : "N", N.mqtt ? "Y" : "N", N.ntp ? "Y" : "N");
}

void drawMedicine() {
  drawHeader("Medicine Alert", (millis() / BLINK_DT) % 2 == 0);
  display.setCursor(0, 16); display.print("Time to take:");
  display.setCursor(0, 28); display.print(M.label);
  display.setCursor(0, 40); display.printf("At %02d:%02d", M.hour, M.minute);
  display.setCursor(0, 52); display.print("OK: confirmed");
}

void updateDisplay() {
  if (!S.oledFound) return;
  display.clearDisplay();
  M.active ? drawMedicine() : drawMain();
  display.display();
}
// gui
void publishData() {
  if (!mqtt.connected()) return;
  JsonDocument doc;
  doc["device_id"] = DEVICE_ID;
  doc["ts"] = N.ntp ? long(time(nullptr)) : long(millis() / 1000UL);
  doc["heart_rate"] = S.hrValid ? int(S.hr) : 0;
  doc["heart_rate_source"] = "ad8232";
  doc["heart_rate_valid"] = S.hrValid;
  doc["spo2"] = S.spo2Valid ? int(S.spo2) : 0;
  doc["spo2_source"] = "max30102";
  doc["spo2_valid"] = S.spo2Valid;
  doc["temperature"] = S.temp;
  doc["ecg_raw"] = S.ecgLeadOff ? 0 : S.ecgRaw;
  doc["ecg_mv"] = S.ecgLeadOff ? 0 : S.ecgMv;
  doc["ecg_lead_off"] = S.ecgLeadOff;
  doc["ecg_window_mean"] = int(roundf(S.ecgMean));
  doc["ecg_window_std"] = int(roundf(S.ecgStd));
  doc["ecg_beats"] = S.ecgBeats;
  doc["accel_x"] = S.ax; doc["accel_y"] = S.ay; doc["accel_z"] = S.az;
  doc["fall"] = S.fall;
  doc["edge_alert"] = S.alert || A.sos;
  doc["alert_reason"] = A.sos ? "SOS_MANUAL" : S.reason;
  doc["status"] = A.status;
  doc["medicine_active"] = M.active;
  doc["medicine_label"] = M.label;
  jsonPublish(TOPIC_DATA, doc);
}

void initPins() {
  pinMode(Config::LED_OK_PIN, OUTPUT); pinMode(Config::LED_ERR_PIN, OUTPUT); pinMode(Config::BUZZER_PIN, OUTPUT);
  pinMode(Config::BUTTON_SOS_PIN, INPUT_PULLUP); pinMode(Config::BUTTON_OK_PIN, INPUT_PULLUP);
  pinMode(Config::AD8232_OUTPUT_PIN, ANALOG); pinMode(Config::AD8232_LO_PLUS_PIN, INPUT); pinMode(Config::AD8232_LO_MINUS_PIN, INPUT);
  analogReadResolution(12); analogSetPinAttenuation(Config::AD8232_OUTPUT_PIN, ADC_11db);
}

void setupDisplay() {
  S.oledFound = display.begin(SSD1306_SWITCHCAPVCC, Config::OLED_I2C_ADDRESS);
  if (!S.oledFound) { Serial.println("[ERR] OLED not found"); return; }
  display.clearDisplay(); display.setTextColor(SSD1306_WHITE); display.setTextSize(1);
  display.setCursor(10, 20); display.println("AIoT Health");
  display.setCursor(10, 36); display.println("Booting..."); display.display();
}

void setupSensors() {
  S.maxFound = maxSensor.begin(Wire, I2C_SPEED_FAST);
  if (S.maxFound) { maxSensor.setup(60, 4, 2, 100, 411, 4096); maxSensor.setPulseAmplitudeGreen(0); }
  ds18b20.begin(); S.dsFound = ds18b20.getDeviceCount() > 0;
  S.mpuFound = i2cOnline(0x68); if (S.mpuFound) { mpu.initialize(); S.mpuFound = mpu.testConnection(); }
  Serial.printf("[SENSOR] MAX=%d DS=%d MPU=%d OLED=%d\n", S.maxFound, S.dsFound, S.mpuFound, S.oledFound);
}

void setupNet() {
  WiFi.mode(WIFI_STA);
  if (Config::MQTT_USE_INSECURE_TLS) wifiClient.setInsecure();
  mqtt.setServer(MQTT_BROKER, Config::MQTT_TLS_PORT);
  mqtt.setCallback(onMqtt);
  mqtt.setKeepAlive(60);
  mqtt.setBufferSize(4096);
}

}  // namespace

void setup() {
  Serial.begin(Config::SERIAL_BAUD);
  delay(500);
  initPins();
  Wire.begin(Config::I2C_SDA_PIN, Config::I2C_SCL_PIN, Config::I2C_CLOCK_HZ);
  setupDisplay();
  setupSensors();
  setupNet();
  copyText(A.status, sizeof(A.status), "Booting");
  A.lastEcg = millis() - ECG_DT;
  A.lastSpo2 = A.lastTemp = millis() - SENSOR_DT;
  Serial.println("[BOOT] AIoT Health compact firmware ready");
}

void loop() {
  uint32_t now = millis();

  bool oldWifi = N.wifi;
  handleWiFi();
  N.wifi = WiFi.status() == WL_CONNECTED;
  if (N.wifi && !oldWifi) Serial.printf("[WiFi] OK | IP: %s\n", WiFi.localIP().toString().c_str());
  syncNtp();
  handleMqtt();
  mqtt.loop();
  N.mqtt = mqtt.connected();

  handleButton(readButton(btnSos, BTN_SOS_SHORT, BTN_SOS_LONG));
  handleButton(readButton(btnOk, BTN_OK_SHORT, BTN_NONE));

  if (now - A.lastEcg >= ECG_DT) { A.lastEcg = now; readAd8232(); }
  if (now - A.lastMpu >= MPU_DT) { A.lastMpu = now; readMpu(); }
  if (now - A.lastFinger >= FINGER_DT) { A.lastFinger = now; pollFinger(); }
  if (now - A.lastTemp >= SENSOR_DT) { A.lastTemp = now; readTemp(); }
  if (now - A.lastSpo2 >= SENSOR_DT) { A.lastSpo2 = now; readMax30102(); }

  runAlertLogic();
  if (S.fall && !A.lastFall) Serial.println("NGA PHAT HIEN!");
  A.lastFall = S.fall;
  checkMedicine();
  refreshStatus();
  updateOutputs();

  if (now - A.lastDisplay >= Config::DISPLAY_REFRESH_INTERVAL_MS) { A.lastDisplay = now; updateDisplay(); }
  if (now - A.lastPublish >= Config::MQTT_PUBLISH_INTERVAL_MS) { A.lastPublish = now; publishData(); }
}
