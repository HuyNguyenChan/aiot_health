---
name: button-menu-ui
description: Use this skill to add physical buttons (emergency, menu navigation, OK/confirm), interactive OLED menu system, configurable measurement intervals, medicine reminder alarm with OK confirmation, and detailed health metric screens (HR stats, SpO2 detail, HRV) to the ESP32 firmware. Trigger when user says 'nút nhấn', 'button', 'menu', 'khẩn cấp', 'uống thuốc', 'nhắc thuốc', 'medicine reminder', 'thời gian đo', 'cài đặt đo', 'chi tiết nhịp tim', 'chi tiết SpO2', or 'OLED menu'.
---

# Button + Menu UI Skill – AIoT Health Monitor

## Phần cứng cần thêm

| Linh kiện | Số lượng | Giá | Ghi chú |
|---|---|---|---|
| Nút nhấn tact switch 6x6mm | 3 cái | 5.000đ | Mua gói 10 cái cho tiện |
| Điện trở 10kΩ | 3 cái | 1.000đ | Pull-down (tùy chọn nếu không dùng INPUT_PULLUP) |
| Buzzer passive 5V | 1 cái | 8.000đ | Phản hồi âm thanh khi nhấn |
| LED đỏ 5mm | 1 cái | 2.000đ | Báo hiệu khi nhấn khẩn cấp |

## Sơ đồ kết nối nút nhấn

```
Nút 1 (EMERGENCY):  GPIO 11  → Nút → GND   (dùng INPUT_PULLUP nội bộ)
Nút 2 (MENU/NEXT):  GPIO 12  → Nút → GND
Nút 3 (OK/SELECT):  GPIO 13  → Nút → GND
Buzzer:             GPIO 14  → Buzzer (+) → GND (-)
LED khẩn cấp:       GPIO 21  → Điện trở 220Ω → LED → GND
```

> Tất cả dùng INPUT_PULLUP — khi nhấn = LOW, khi thả = HIGH. Không cần điện trở ngoài.

---

## Cập nhật config.h

```cpp
// ─── Nút nhấn ────────────────────────────────────
#define PIN_BTN_EMERGENCY  32   // Nút 1: Khẩn cấp (nhấn = gửi SOS ngay)
#define PIN_BTN_MENU       33   // Nút 2: Chuyển menu / Next
#define PIN_BTN_OK         13   // Nút 3: Xác nhận / OK

// ─── Phản hồi ────────────────────────────────────
#define PIN_BUZZER         14
#define PIN_LED_EMERGENCY  21

// ─── Tham số nút nhấn ────────────────────────────
#define DEBOUNCE_MS        50    // Chống rung: 50ms
#define LONG_PRESS_MS      2000  // Nhấn giữ 2s = long press
#define DOUBLE_CLICK_MS    400   // Nhấn 2 lần trong 400ms = double click

// ─── Menu ───────────────────────────────────────────
#define MENU_TIMEOUT_MS    10000 // 10s không nhấn → về màn hình chính
#define TOTAL_MENU_ITEMS   5     // Số menu item
```

---

## File: include/button_handler.h

```cpp
#pragma once
#include <Arduino.h>

// ─── Sự kiện nút nhấn ────────────────────────────
enum ButtonEvent {
    BTN_NONE,
    BTN_EMERGENCY_SHORT,   // Nhấn ngắn nút 1
    BTN_EMERGENCY_LONG,    // Nhấn giữ 2s nút 1 (xác nhận SOS)
    BTN_MENU_SHORT,        // Nhấn ngắn nút 2 (next menu item)
    BTN_MENU_LONG,         // Nhấn giữ nút 2 (về màn hình chính)
    BTN_OK_SHORT,          // Nhấn ngắn nút 3 (confirm)
    BTN_OK_DOUBLE,         // Double click nút 3 (xác nhận nhanh)
};

class ButtonHandler {
public:
    void begin();
    ButtonEvent update();       // Gọi trong loop(), trả về event nếu có
    bool isEmergencyPressed();  // Kiểm tra trực tiếp

private:
    // State tracking cho từng nút
    struct BtnState {
        int      pin;
        bool     lastState    = HIGH;
        bool     currentState = HIGH;
        uint32_t pressTime    = 0;
        uint32_t lastClickTime= 0;
        int      clickCount   = 0;
        bool     longFired    = false;
    } _emergency, _menu, _ok;

    ButtonEvent _readButton(BtnState& btn,
                            ButtonEvent shortEvt,
                            ButtonEvent longEvt,
                            ButtonEvent doubleEvt = BTN_NONE);
};
```

---

## File: src/button_handler.cpp

```cpp
#include "button_handler.h"
#include "config.h"

void ButtonHandler::begin() {
    _emergency.pin = PIN_BTN_EMERGENCY;
    _menu.pin      = PIN_BTN_MENU;
    _ok.pin        = PIN_BTN_OK;

    for (auto* b : {&_emergency, &_menu, &_ok}) {
        pinMode(b->pin, INPUT_PULLUP);
    }
    pinMode(PIN_BUZZER,        OUTPUT);
    pinMode(PIN_LED_EMERGENCY, OUTPUT);
    digitalWrite(PIN_LED_EMERGENCY, LOW);
}

ButtonEvent ButtonHandler::_readButton(BtnState& btn,
                                        ButtonEvent shortEvt,
                                        ButtonEvent longEvt,
                                        ButtonEvent doubleEvt) {
    bool raw = digitalRead(btn.pin);

    // Debounce
    if (raw != btn.lastState) {
        btn.pressTime = millis();
        btn.lastState = raw;
    }
    if ((millis() - btn.pressTime) < DEBOUNCE_MS) return BTN_NONE;

    ButtonEvent evt = BTN_NONE;

    if (raw == LOW && btn.currentState == HIGH) {
        // Vừa nhấn xuống
        btn.currentState = LOW;
        btn.pressTime    = millis();
        btn.longFired    = false;
    }
    else if (raw == LOW && !btn.longFired) {
        // Đang giữ — check long press
        if ((millis() - btn.pressTime) >= LONG_PRESS_MS) {
            btn.longFired = true;
            evt = longEvt;
            // Buzzer dài cho long press
            tone(PIN_BUZZER, 800, 300);
        }
    }
    else if (raw == HIGH && btn.currentState == LOW) {
        // Vừa thả
        btn.currentState = HIGH;
        if (!btn.longFired) {
            // Short press — check double click
            uint32_t now = millis();
            if (doubleEvt != BTN_NONE &&
                (now - btn.lastClickTime) < DOUBLE_CLICK_MS &&
                btn.clickCount == 1) {
                btn.clickCount   = 0;
                btn.lastClickTime= 0;
                evt = doubleEvt;
                tone(PIN_BUZZER, 1200, 100);
                delay(50);
                tone(PIN_BUZZER, 1200, 100);
            } else {
                btn.clickCount    = 1;
                btn.lastClickTime = now;
            }
        }
    }
    else if (raw == HIGH && btn.clickCount == 1 &&
             (millis() - btn.lastClickTime) > DOUBLE_CLICK_MS) {
        // Single click đã timeout double click window
        btn.clickCount = 0;
        evt = shortEvt;
        tone(PIN_BUZZER, 1000, 80);  // Beep ngắn
    }

    return evt;
}

ButtonEvent ButtonHandler::update() {
    ButtonEvent e;
    if ((e = _readButton(_emergency,
                          BTN_EMERGENCY_SHORT,
                          BTN_EMERGENCY_LONG)) != BTN_NONE) return e;
    if ((e = _readButton(_menu,
                          BTN_MENU_SHORT,
                          BTN_MENU_LONG))      != BTN_NONE) return e;
    if ((e = _readButton(_ok,
                          BTN_OK_SHORT,
                          BTN_NONE,
                          BTN_OK_DOUBLE))      != BTN_NONE) return e;
    return BTN_NONE;
}

bool ButtonHandler::isEmergencyPressed() {
    return digitalRead(PIN_BTN_EMERGENCY) == LOW;
}
```

---

## File: include/menu_system.h

```cpp
#pragma once
#include <Arduino.h>
#include <Adafruit_SSD1306.h>
#include "button_handler.h"

// ─── Các màn hình ─────────────────────────────────
enum Screen {
    SCREEN_MAIN,        // Màn hình chính: HR, SpO2, Temp
    SCREEN_MENU,        // Menu chính
    SCREEN_DETAIL,      // Xem chi tiết chỉ số
    SCREEN_ALERT_LOG,   // Lịch sử cảnh báo
    SCREEN_SETTINGS,    // Cài đặt
    SCREEN_SOS_CONFIRM, // Xác nhận gửi SOS
    SCREEN_SOS_SENT,    // Thông báo SOS đã gửi
};

// ─── Menu items ───────────────────────────────────
struct MenuItem {
    const char* icon;
    const char* label;
    Screen      target;
};

class MenuSystem {
public:
    void begin(Adafruit_SSD1306* display, ButtonHandler* buttons);
    void update(ButtonEvent event);
    void render(float hr, float spo2, float temp,
                bool wifi, bool mqtt, bool edgeAlert);
    bool isSosPending();
    void clearSos();
    Screen currentScreen() { return _screen; }

private:
    Adafruit_SSD1306* _oled;
    ButtonHandler*    _buttons;
    Screen   _screen       = SCREEN_MAIN;
    int      _menuIndex    = 0;
    uint32_t _lastActivity = 0;
    bool     _sosPending   = false;
    int      _alertLogPage = 0;

    void _renderMain(float hr, float spo2, float temp, bool wifi, bool mqtt, bool alert);
    void _renderMenu();
    void _renderDetail(float hr, float spo2, float temp);
    void _renderAlertLog();
    void _renderSettings();
    void _renderSosConfirm();
    void _renderSosSent();
    void _handleMenuNav(ButtonEvent evt);
    void _handleSosConfirm(ButtonEvent evt);
    void _checkTimeout();

    static const MenuItem MENU_ITEMS[];
};
```

---

## File: src/menu_system.cpp

```cpp
#include "menu_system.h"
#include "config.h"

const MenuItem MenuSystem::MENU_ITEMS[] = {
    {"!!", "SOS Khan Cap",   SCREEN_SOS_CONFIRM},
    {"--", "Chi Tiet",       SCREEN_DETAIL    },
    {"^^", "Lich Su",        SCREEN_ALERT_LOG },
    {"::", "Cai Dat",        SCREEN_SETTINGS  },
    {"<<", "Quay Lai",       SCREEN_MAIN      },
};

void MenuSystem::begin(Adafruit_SSD1306* display, ButtonHandler* buttons) {
    _oled    = display;
    _buttons = buttons;
    _lastActivity = millis();
}

void MenuSystem::update(ButtonEvent event) {
    if (event == BTN_NONE) {
        _checkTimeout();
        return;
    }
    _lastActivity = millis();

    switch (_screen) {
        case SCREEN_MAIN:
            if (event == BTN_EMERGENCY_SHORT ||
                event == BTN_EMERGENCY_LONG) {
                _screen = SCREEN_SOS_CONFIRM;
            } else if (event == BTN_MENU_SHORT) {
                _screen     = SCREEN_MENU;
                _menuIndex  = 0;
            }
            break;

        case SCREEN_MENU:
            _handleMenuNav(event);
            break;

        case SCREEN_SOS_CONFIRM:
            _handleSosConfirm(event);
            break;

        case SCREEN_DETAIL:
        case SCREEN_ALERT_LOG:
        case SCREEN_SETTINGS:
            if (event == BTN_MENU_LONG ||
                event == BTN_MENU_SHORT) {
                _screen = SCREEN_MAIN;
            }
            break;

        case SCREEN_SOS_SENT:
            _screen = SCREEN_MAIN;
            break;

        default:
            break;
    }
}

void MenuSystem::_handleMenuNav(ButtonEvent evt) {
    if (evt == BTN_MENU_SHORT) {
        _menuIndex = (_menuIndex + 1) % TOTAL_MENU_ITEMS;
    } else if (evt == BTN_OK_SHORT || evt == BTN_OK_DOUBLE) {
        _screen = MENU_ITEMS[_menuIndex].target;
    } else if (evt == BTN_MENU_LONG) {
        _screen = SCREEN_MAIN;
    }
}

void MenuSystem::_handleSosConfirm(ButtonEvent evt) {
    if (evt == BTN_EMERGENCY_LONG || evt == BTN_OK_DOUBLE) {
        // Xác nhận SOS
        _sosPending = true;
        _screen     = SCREEN_SOS_SENT;
        // Còi báo động 3 tiếng
        for (int i = 0; i < 3; i++) {
            tone(PIN_BUZZER, 2000, 200);
            delay(300);
        }
        digitalWrite(PIN_LED_EMERGENCY, HIGH);
    } else if (evt == BTN_MENU_SHORT || evt == BTN_OK_SHORT) {
        // Hủy
        _screen = SCREEN_MAIN;
    }
}

void MenuSystem::_checkTimeout() {
    if (_screen != SCREEN_MAIN &&
        (millis() - _lastActivity) > MENU_TIMEOUT_MS) {
        _screen    = SCREEN_MAIN;
        _menuIndex = 0;
    }
}

// ─── Render functions ────────────────────────────

void MenuSystem::render(float hr, float spo2, float temp,
                        bool wifi, bool mqtt, bool edgeAlert) {
    _oled->clearDisplay();
    switch (_screen) {
        case SCREEN_MAIN:        _renderMain(hr,spo2,temp,wifi,mqtt,edgeAlert); break;
        case SCREEN_MENU:        _renderMenu(); break;
        case SCREEN_DETAIL:      _renderDetail(hr,spo2,temp); break;
        case SCREEN_ALERT_LOG:   _renderAlertLog(); break;
        case SCREEN_SETTINGS:    _renderSettings(); break;
        case SCREEN_SOS_CONFIRM: _renderSosConfirm(); break;
        case SCREEN_SOS_SENT:    _renderSosSent(); break;
    }
    _oled->display();
}

void MenuSystem::_renderMain(float hr, float spo2, float temp,
                              bool wifi, bool mqtt, bool alert) {
    // Header bar
    _oled->fillRect(0, 0, 128, 11, SSD1306_WHITE);
    _oled->setTextColor(SSD1306_BLACK);
    _oled->setTextSize(1);
    _oled->setCursor(2, 2);
    _oled->print(alert ? "!!! CANH BAO !!!" : "  AIoT Health");

    // Chỉ số chính
    _oled->setTextColor(SSD1306_WHITE);
    _oled->setTextSize(1);
    _oled->setCursor(0, 14); _oled->printf("HR:   %3d bpm", (int)hr);
    _oled->setCursor(0, 25); _oled->printf("SpO2: %3d %%",  (int)spo2);
    _oled->setCursor(0, 36); _oled->printf("Temp: %.1f C",   temp);

    // Footer: kết nối + hướng dẫn
    _oled->setCursor(0, 50);
    _oled->printf("W:%s M:%s  [1]SOS[2]Menu",
        wifi ? "Y":"N", mqtt ? "Y":"N");
}

void MenuSystem::_renderMenu() {
    _oled->setTextColor(SSD1306_WHITE);
    _oled->setTextSize(1);
    _oled->setCursor(35, 0); _oled->print("[ MENU ]");
    _oled->drawLine(0, 10, 127, 10, SSD1306_WHITE);

    // Hiển thị 3 items, item được chọn có highlight
    int start = max(0, _menuIndex - 1);
    for (int i = 0; i < 3 && (start+i) < TOTAL_MENU_ITEMS; i++) {
        int idx = start + i;
        int y   = 13 + i * 17;
        if (idx == _menuIndex) {
            _oled->fillRect(0, y-1, 128, 15, SSD1306_WHITE);
            _oled->setTextColor(SSD1306_BLACK);
        } else {
            _oled->setTextColor(SSD1306_WHITE);
        }
        _oled->setCursor(4, y+1);
        _oled->printf("%s %s", MENU_ITEMS[idx].icon, MENU_ITEMS[idx].label);
    }
    // Footer hint
    _oled->setTextColor(SSD1306_WHITE);
    _oled->setCursor(0, 57); _oled->print("[2]Next [3]OK [2L]Back");
}

void MenuSystem::_renderDetail(float hr, float spo2, float temp) {
    _oled->setTextColor(SSD1306_WHITE);
    _oled->setTextSize(1);
    _oled->setCursor(20, 0); _oled->print("CHI TIET SO LIEU");
    _oled->drawLine(0, 9, 127, 9, SSD1306_WHITE);

    _oled->setTextSize(1);
    _oled->setCursor(0, 12); _oled->printf("Nhip tim:  %d bpm",    (int)hr);
    _oled->setCursor(0, 22); _oled->printf("SpO2:      %d %%",     (int)spo2);
    _oled->setCursor(0, 32); _oled->printf("Nhiet do:  %.1f C",    temp);

    // Đánh giá trạng thái
    _oled->setCursor(0, 45);
    bool ok = (hr>50&&hr<120) && spo2>=92 && temp<38.5;
    _oled->printf("Trang thai: %s", ok ? "BINH THUONG" : "CAN CHU Y!");
    _oled->setCursor(0, 57); _oled->print("[2]Quay lai");
}

void MenuSystem::_renderSosConfirm() {
    _oled->setTextColor(SSD1306_WHITE);
    _oled->setTextSize(1);

    // Khung cảnh báo nhấp nháy
    if ((millis()/500) % 2 == 0) {
        _oled->fillRect(0, 0, 128, 64, SSD1306_WHITE);
        _oled->setTextColor(SSD1306_BLACK);
    }
    _oled->setCursor(25, 5);  _oled->print("!!! KHAN CAP !!!");
    _oled->setCursor(10, 20); _oled->print("Giu [1] 2s de gui SOS");
    _oled->setCursor(10, 35); _oled->print("Hoac [3] x2 de xac nhan");
    _oled->setCursor(15, 50); _oled->print("[2] de huy bo");
}

void MenuSystem::_renderSosSent() {
    _oled->fillRect(0, 0, 128, 64, SSD1306_WHITE);
    _oled->setTextColor(SSD1306_BLACK);
    _oled->setTextSize(1);
    _oled->setCursor(20, 10); _oled->print("DA GUI SOS!");
    _oled->setCursor(5,  25); _oled->print("Dang thong bao nguoi than");
    _oled->setCursor(5,  40); _oled->print("Xin hay cho doi...");
    _oled->setCursor(25, 55); _oled->print("[any] De tiep tuc");
}

void MenuSystem::_renderAlertLog() {
    _oled->setTextColor(SSD1306_WHITE);
    _oled->setTextSize(1);
    _oled->setCursor(10, 0); _oled->print("LICH SU CANH BAO");
    _oled->drawLine(0, 9, 127, 9, SSD1306_WHITE);
    // Placeholder - sẽ load từ SPIFFS trong production
    _oled->setCursor(0, 15); _oled->print("14:32 HR cao: 158bpm");
    _oled->setCursor(0, 25); _oled->print("12:10 SpO2 thap: 89%");
    _oled->setCursor(0, 35); _oled->print("08:45 Nhiet do: 38.7C");
    _oled->setCursor(0, 57); _oled->print("[2]Quay lai");
}

void MenuSystem::_renderSettings() {
    _oled->setTextColor(SSD1306_WHITE);
    _oled->setTextSize(1);
    _oled->setCursor(20, 0); _oled->print("CAI DAT");
    _oled->drawLine(0, 9, 127, 9, SSD1306_WHITE);
    _oled->setCursor(0, 13); _oled->print("Nguong HR cao: 150bpm");
    _oled->setCursor(0, 23); _oled->print("Nguong SpO2:   92%");
    _oled->setCursor(0, 33); _oled->print("Nguong Temp:   38.5C");
    _oled->setCursor(0, 43); _oled->print("Gui moi:       5 giay");
    _oled->setCursor(0, 57); _oled->print("[2]Quay lai");
}

bool MenuSystem::isSosPending() { return _sosPending; }
void MenuSystem::clearSos()     { _sosPending = false; digitalWrite(PIN_LED_EMERGENCY, LOW); }
```

---

## Cập nhật main.cpp — Tích hợp Button + Menu

```cpp
// Thêm vào đầu file:
#include "button_handler.h"
#include "menu_system.h"

ButtonHandler buttons;
MenuSystem    menu;

// Trong setup():
buttons.begin();
menu.begin(&oled, &buttons);

// Trong loop():
ButtonEvent evt = buttons.update();

// Xử lý SOS ngay lập tức (ưu tiên cao nhất)
if (evt == BTN_EMERGENCY_LONG) {
    menu.update(evt);  // Chuyển sang màn hình xác nhận
}

// Cập nhật menu state machine
menu.update(evt);

// Nếu SOS đã được xác nhận → gửi ngay
if (menu.isSosPending()) {
    data.edgeAlert   = true;
    data.alertReason = "SOS_MANUAL";
    publishData();   // Gửi MQTT ngay
    // Telegram sẽ nhận cảnh báo từ server
    menu.clearSos();
}

// Render màn hình (truyền dữ liệu sức khỏe mới nhất)
if (millis() - lastDisplayMs >= DISPLAY_INTERVAL) {
    menu.render(data.heartRate, data.spo2, data.temperature,
                WiFi.isConnected(), mqttClient.connected(),
                data.edgeAlert);
    lastDisplayMs = millis();
}
```

---

## Bảng tóm tắt hành vi các nút

| Nút | Nhấn ngắn | Nhấn giữ 2s | Double click |
|---|---|---|---|
| **1 (EMERGENCY)** | Vào màn hình xác nhận SOS | Xác nhận gửi SOS ngay | — |
| **2 (MENU/NEXT)** | Mở menu / Chuyển item tiếp | Về màn hình chính | — |
| **3 (OK/SELECT)** | Chọn menu item hiện tại | — | Xác nhận nhanh SOS |

## Phản hồi âm thanh (Buzzer)

| Hành động | Âm thanh |
|---|---|
| Nhấn ngắn bất kỳ | Beep ngắn 80ms |
| Long press | Beep dài 300ms |
| SOS xác nhận | 3 tiếng kêu dài |
| Cảnh báo AI | Tiếng kêu lặp lại liên tục |

---

## PHẦN MỞ RỘNG: Màn hình chi tiết sức khỏe

### Enum Screen — thêm các màn mới

```cpp
enum Screen {
    SCREEN_MAIN,
    SCREEN_MENU,
    SCREEN_DETAIL_HR,       // Chi tiết nhịp tim
    SCREEN_DETAIL_SPO2,     // Chi tiết SpO2
    SCREEN_DETAIL_HRV,      // Chi tiết HRV / stress
    SCREEN_DETAIL_TEMP,     // Chi tiết nhiệt độ
    SCREEN_ALERT_LOG,
    SCREEN_SETTINGS,
    SCREEN_SETTINGS_INTERVAL,  // Cài thời gian đo
    SCREEN_SETTINGS_MEDICINE,  // Cài lịch uống thuốc
    SCREEN_SETTINGS_THRESHOLD, // Cài ngưỡng cảnh báo
    SCREEN_MEDICINE_ALERT,  // Nhắc uống thuốc
    SCREEN_MEDICINE_CONFIRM,// Xác nhận đã uống
    SCREEN_SOS_CONFIRM,
    SCREEN_SOS_SENT,
};
```

### Render màn chi tiết nhịp tim

```cpp
void MenuSystem::_renderDetailHR(float hr, float hrMin, float hrMax, float hrAvg) {
    _oled->clearDisplay();
    // Header
    _oled->fillRect(0,0,128,11,SSD1306_WHITE);
    _oled->setTextColor(SSD1306_BLACK);
    _oled->setCursor(10,2); _oled->print("NHIP TIM - CHI TIET");

    _oled->setTextColor(SSD1306_WHITE);
    _oled->setTextSize(1);
    _oled->setCursor(0,14); _oled->printf("Hien tai:  %3d bpm", (int)hr);
    _oled->setCursor(0,25); _oled->printf("Thap nhat: %3d bpm", (int)hrMin);
    _oled->setCursor(0,36); _oled->printf("Cao nhat:  %3d bpm", (int)hrMax);
    _oled->setCursor(0,47); _oled->printf("Trung binh:%3d bpm", (int)hrAvg);

    // Đánh giá
    _oled->setCursor(0,57);
    if (hr < 60)       _oled->print("Nhip cham - chu y!");
    else if (hr > 100) _oled->print("Nhip nhanh - chu y!");
    else               _oled->print("Binh thuong");
    _oled->display();
}
```

### Render màn chi tiết SpO2

```cpp
void MenuSystem::_renderDetailSpO2(float spo2, float spo2Min, float spo2Avg) {
    _oled->clearDisplay();
    _oled->fillRect(0,0,128,11,SSD1306_WHITE);
    _oled->setTextColor(SSD1306_BLACK);
    _oled->setCursor(15,2); _oled->print("SPO2 - NONG DO OXY");

    _oled->setTextColor(SSD1306_WHITE);
    _oled->setCursor(0,14); _oled->printf("Hien tai:  %3d %%", (int)spo2);
    _oled->setCursor(0,25); _oled->printf("Thap nhat: %3d %%", (int)spo2Min);
    _oled->setCursor(0,36); _oled->printf("Trung binh:%3d %%", (int)spo2Avg);
    _oled->setCursor(0,47);

    // Giải thích mức SpO2
    if (spo2 >= 95)      _oled->print("Binh thuong (95-100%)");
    else if (spo2 >= 92) _oled->print("Can theo doi (<95%)");
    else if (spo2 >= 90) _oled->print("! Thap - can kham !");
    else                 _oled->print("!! NGUY HIEM < 90% !!");
    _oled->display();
}
```

### Màn hình HRV (stress indicator)

```cpp
// HRV = độ lệch chuẩn khoảng RR (tính từ MAX30102)
// HRV cao = thư giãn, HRV thấp = căng thẳng/mệt
void MenuSystem::_renderDetailHRV(float hrv) {
    _oled->clearDisplay();
    _oled->setCursor(0,0);  _oled->printf("HRV: %.1f ms", hrv);
    _oled->setCursor(0,12);
    if (hrv > 50)      _oled->print("Trang thai: Tot");
    else if (hrv > 20) _oled->print("Trang thai: Trung binh");
    else               _oled->print("Trang thai: Can nghi ngoi");
    _oled->setCursor(0,24);
    if (hrv < 20) _oled->print("Goi y: Nghi ngoi, uong nuoc");
    _oled->display();
}
```

---

## PHẦN MỞ RỘNG: Cài đặt thời gian đo

### Enum + cấu trúc

```cpp
// include/config.h — thêm vào
enum MeasureMode {
    MODE_CONTINUOUS,   // Đo mỗi 5s
    MODE_NORMAL,       // Đo mỗi 1 phút (mặc định)
    MODE_ECONOMY,      // Đo mỗi 5 phút
    MODE_CUSTOM,       // Người dùng nhập
};

// Thời gian interval theo mode (ms)
const uint32_t MODE_INTERVALS[] = {
    5000,    // CONTINUOUS
    60000,   // NORMAL
    300000,  // ECONOMY
    0        // CUSTOM — dùng customInterval
};
```

### Lưu setting vào EEPROM (nhớ sau khi tắt)

```cpp
#include <Preferences.h>

Preferences prefs;

void saveSettings(MeasureMode mode, uint32_t customMs) {
    prefs.begin("aiot", false);
    prefs.putInt("mode", (int)mode);
    prefs.putUInt("custom_ms", customMs);
    prefs.end();
}

void loadSettings(MeasureMode& mode, uint32_t& customMs) {
    prefs.begin("aiot", true);
    mode     = (MeasureMode)prefs.getInt("mode", MODE_NORMAL);
    customMs = prefs.getUInt("custom_ms", 60000);
    prefs.end();
}
```

### Màn hình cài đặt interval trên OLED

```cpp
// Khi ở SCREEN_SETTINGS_INTERVAL:
// Nút 2 = chuyển mode (cycle qua 4 mode)
// Nút 3 = xác nhận lưu
// Nút 2 giữ = hủy

const char* MODE_NAMES[] = {"Lien tuc(5s)","Thuong(1ph)","Tiet kiem(5ph)","Tuy chinh"};

void MenuSystem::_renderSettingsInterval(MeasureMode selectedMode) {
    _oled->clearDisplay();
    _oled->setCursor(5,0); _oled->print("CAI DAT THOI GIAN DO");
    _oled->drawLine(0,10,128,10,SSD1306_WHITE);
    for (int i = 0; i < 4; i++) {
        if (i == (int)selectedMode) {
            _oled->fillRect(0, 12+i*13, 128, 12, SSD1306_WHITE);
            _oled->setTextColor(SSD1306_BLACK);
        } else {
            _oled->setTextColor(SSD1306_WHITE);
        }
        _oled->setCursor(4, 14+i*13);
        _oled->print(MODE_NAMES[i]);
    }
    _oled->setTextColor(SSD1306_WHITE);
    _oled->setCursor(0,57); _oled->print("[2]Chon [3]Luu [2L]Huy");
    _oled->display();
}
```

---

## PHẦN MỞ RỘNG: Báo thức uống thuốc

### Cấu trúc dữ liệu thuốc

```cpp
// include/medicine.h
#pragma once
#include <Arduino.h>

#define MAX_MEDICINES    5   // Tối đa 5 loại thuốc
#define MAX_TIMES_PER    4   // Tối đa 4 lần/ngày mỗi thuốc
#define REMIND_TIMEOUT   60  // Giây chờ xác nhận
#define REMIND_RETRY     3   // Số lần nhắc lại
#define REMIND_INTERVAL  300 // Giây giữa các lần nhắc lại (5 phút)

struct MedicineSchedule {
    char     name[20];            // Tên thuốc
    uint8_t  times[MAX_TIMES_PER];// Giờ uống [8, 12, 18, 22]
    uint8_t  timeCount;           // Số lần/ngày
    uint8_t  pillCount;           // Số viên mỗi lần
    char     note[30];            // Ghi chú ("sau ăn", "trước khi ngủ")
    bool     enabled;             // Bật/tắt nhắc
};

struct MedicineAlert {
    int      medIndex;            // Index trong mảng schedule
    uint8_t  hour;                // Giờ dự kiến uống
    uint32_t alertStartMs;        // Millis khi bắt đầu nhắc
    uint8_t  retryCount;          // Đã nhắc bao nhiêu lần
    bool     confirmed;           // Đã xác nhận chưa
    bool     active;              // Đang hiện cảnh báo không
};
```

### MedicineManager class

```cpp
// src/medicine_manager.cpp

class MedicineManager {
public:
    MedicineSchedule schedules[MAX_MEDICINES];
    MedicineAlert    currentAlert;
    int              medicineCount = 0;

    void begin() {
        loadFromPrefs();
        currentAlert.active = false;
    }

    // Gọi trong loop() mỗi phút — kiểm tra có đến giờ uống thuốc không
    void checkSchedule(int currentHour, int currentMinute) {
        if (currentMinute != 0) return; // Chỉ check đầu giờ
        for (int m = 0; m < medicineCount; m++) {
            if (!schedules[m].enabled) continue;
            for (int t = 0; t < schedules[m].timeCount; t++) {
                if (schedules[m].times[t] == currentHour) {
                    triggerAlert(m, currentHour);
                    return;
                }
            }
        }
    }

    void triggerAlert(int medIdx, uint8_t hour) {
        currentAlert = {
            .medIndex     = medIdx,
            .hour         = hour,
            .alertStartMs = millis(),
            .retryCount   = 0,
            .confirmed    = false,
            .active       = true
        };
        // Buzzer nhắc nhở (3 beep nhẹ)
        for (int i = 0; i < 3; i++) {
            tone(PIN_BUZZER, 1500, 150);
            delay(300);
        }
    }

    // Gọi khi người dùng nhấn nút OK
    bool confirmMedicine() {
        if (!currentAlert.active) return false;
        currentAlert.confirmed = true;
        currentAlert.active    = false;
        saveTodayLog(currentAlert.medIndex, currentAlert.hour, true);
        tone(PIN_BUZZER, 2000, 500); // Beep xác nhận
        return true;
    }

    // Nhắc lại sau REMIND_INTERVAL giây nếu không xác nhận
    bool checkRetry() {
        if (!currentAlert.active || currentAlert.confirmed) return false;
        uint32_t elapsed = (millis() - currentAlert.alertStartMs) / 1000;
        if (elapsed > REMIND_TIMEOUT) {
            if (currentAlert.retryCount < REMIND_RETRY) {
                currentAlert.retryCount++;
                currentAlert.alertStartMs = millis();
                triggerAlert(currentAlert.medIndex, currentAlert.hour);
                return true;
            } else {
                // Hết lần nhắc — đánh dấu bỏ lỡ
                saveTodayLog(currentAlert.medIndex, currentAlert.hour, false);
                currentAlert.active = false;
                return false; // Báo server gửi Telegram
            }
        }
        return false;
    }

    int getRemainingSeconds() {
        if (!currentAlert.active) return 0;
        uint32_t elapsed = (millis() - currentAlert.alertStartMs) / 1000;
        return max(0, (int)(REMIND_TIMEOUT - elapsed));
    }

    void saveTodayLog(int medIdx, uint8_t hour, bool taken);
    void loadFromPrefs();
    void saveToPrefs();
};
```

### Màn hình nhắc uống thuốc — nhấp nháy

```cpp
void MenuSystem::_renderMedicineAlert(MedicineManager& med) {
    MedicineAlert& alert = med.currentAlert;
    MedicineSchedule& sch = med.schedules[alert.medIndex];
    int remaining = med.getRemainingSeconds();

    // Nhấp nháy header mỗi 500ms
    bool blink = (millis() / 500) % 2 == 0;
    if (blink) {
        _oled->fillRect(0,0,128,11,SSD1306_WHITE);
        _oled->setTextColor(SSD1306_BLACK);
    } else {
        _oled->setTextColor(SSD1306_WHITE);
    }
    _oled->setCursor(5,2); _oled->print("!! NHAC UONG THUOC !!");

    _oled->setTextColor(SSD1306_WHITE);
    _oled->setCursor(0,14); _oled->printf("Thuoc: %s", sch.name);
    _oled->setCursor(0,25); _oled->printf("So vien: %d vien", sch.pillCount);
    _oled->setCursor(0,36); _oled->printf("Ghi chu: %s", sch.note);
    _oled->setCursor(0,47); _oled->printf("Con lai: %ds (lan %d/%d)",
                                           remaining,
                                           alert.retryCount+1,
                                           REMIND_RETRY);
    _oled->setCursor(0,57);
    _oled->print("[3]Da uong  [2]Nhac sau");
    _oled->display();
}
```

### Tích hợp vào loop() chính

```cpp
// Trong loop() — thêm sau phần đọc cảm biến

// 1. Check lịch uống thuốc (cần có giờ thực từ NTP hoặc DS3231)
static uint32_t lastMinuteCheck = 0;
if (millis() - lastMinuteCheck >= 60000) {
    medManager.checkSchedule(currentHour, currentMinute);
    lastMinuteCheck = millis();
}

// 2. Xử lý retry nếu không xác nhận
if (medManager.currentAlert.active) {
    bool missed = !medManager.checkRetry();
    if (missed) {
        // Gửi MQTT báo server → server gửi Telegram cho người thân
        publishMedicineMissed(medManager.currentAlert.medIndex);
    }
    // Override màn hình bình thường bằng màn nhắc thuốc
    menu.forceScreen(SCREEN_MEDICINE_ALERT);
}

// 3. Nút OK xác nhận uống thuốc
if (evt == BTN_OK_SHORT && menu.currentScreen() == SCREEN_MEDICINE_ALERT) {
    if (medManager.confirmMedicine()) {
        menu.forceScreen(SCREEN_MEDICINE_CONFIRM);
        publishMedicineConfirmed(medManager.currentAlert.medIndex);
    }
}

// 4. Nút MENU = nhắc sau (snooze)
if (evt == BTN_MENU_SHORT && menu.currentScreen() == SCREEN_MEDICINE_ALERT) {
    medManager.currentAlert.alertStartMs = millis(); // Reset timer
    menu.forceScreen(SCREEN_MAIN);
}
```

### MQTT messages cho thuốc

```cpp
// Gửi khi đã uống
void publishMedicineConfirmed(int medIdx) {
    JsonDocument doc;
    doc["type"]       = "medicine_confirmed";
    doc["device_id"]  = DEVICE_ID;
    doc["med_name"]   = medManager.schedules[medIdx].name;
    doc["time"]       = getCurrentTimeString();
    char buf[256]; serializeJson(doc, buf);
    mqttClient.publish("health/" DEVICE_ID "/medicine", buf);
}

// Gửi khi bỏ lỡ
void publishMedicineMissed(int medIdx) {
    JsonDocument doc;
    doc["type"]       = "medicine_missed";
    doc["device_id"]  = DEVICE_ID;
    doc["med_name"]   = medManager.schedules[medIdx].name;
    doc["retry_count"]= medManager.currentAlert.retryCount;
    char buf[256]; serializeJson(doc, buf);
    mqttClient.publish("health/" DEVICE_ID "/medicine", buf);
}
```

### Server Python — nhận và xử lý medicine events

```python
# Thêm vào server/mqtt_handler.py

def on_message(client, userdata, msg):
    data = json.loads(msg.payload.decode())

    # Xử lý sự kiện thuốc
    if data.get("type") == "medicine_confirmed":
        save_medicine_log(data["device_id"], data["med_name"],
                          data["time"], confirmed=True)
        print(f"[MED] {data['device_id']} đã uống {data['med_name']}")

    elif data.get("type") == "medicine_missed":
        save_medicine_log(data["device_id"], data["med_name"],
                          confirmed=False)
        # Gửi cảnh báo Telegram cho người thân
        send_medicine_missed_alert(data["device_id"], data["med_name"],
                                   data["retry_count"])

# alert_bot.py — thêm hàm
def send_medicine_missed_alert(device_id, med_name, retries):
    msg = (
        f"💊 <b>Chưa uống thuốc!</b>\n"
        f"👤 Bệnh nhân: <code>{device_id}</code>\n"
        f"💊 Thuốc: {med_name}\n"
        f"🔔 Đã nhắc {retries} lần nhưng chưa xác nhận\n"
        f"⚠️ Vui lòng kiểm tra!"
    )
    send_message(msg)
```

### Dashboard — hiển thị tuân thủ thuốc

```python
# dashboard/streamlit_app.py — thêm tab mới

tab1, tab2 = st.tabs(["❤️ Sức khỏe", "💊 Thuốc"])

with tab2:
    st.subheader("Lịch sử uống thuốc 7 ngày")
    med_data = requests.get(f"{API_BASE}/medicine/{selected}/history").json()

    # Tỷ lệ tuân thủ từng ngày
    compliance = {day: data["rate"] for day, data in med_data.items()}
    fig = px.bar(x=list(compliance.keys()),
                 y=list(compliance.values()),
                 color=list(compliance.values()),
                 color_continuous_scale=["red","yellow","green"],
                 range_color=[0, 100])
    st.plotly_chart(fig, use_container_width=True)

    # Bảng chi tiết
    st.dataframe(pd.DataFrame(med_data))
```

## Lấy giờ thực cho ESP32 (cần cho lịch thuốc)

```cpp
// Dùng NTP qua WiFi — thêm vào setup()
#include <time.h>

void setupTime() {
    configTime(7 * 3600, 0, "pool.ntp.org"); // UTC+7 = Việt Nam
    Serial.print("Đồng bộ giờ");
    while (time(nullptr) < 100000) {
        delay(500); Serial.print(".");
    }
    Serial.println(" OK!");
}

int getCurrentHour() {
    time_t now = time(nullptr);
    struct tm* t = localtime(&now);
    return t->tm_hour;
}

int getCurrentMinute() {
    time_t now = time(nullptr);
    struct tm* t = localtime(&now);
    return t->tm_min;
}

String getCurrentTimeString() {
    time_t now = time(nullptr);
    struct tm* t = localtime(&now);
    char buf[20];
    sprintf(buf, "%02d:%02d:%02d", t->tm_hour, t->tm_min, t->tm_sec);
    return String(buf);
}
```
