#pragma once

// Header này dành cho dữ liệu và xử lý nhắc thuốc trên ESP32.
// Có thể mở rộng theo hướng:
// - struct lưu giờ uống thuốc
// - hàm kiểm tra tới giờ nhắc
// - hàm đồng bộ dữ liệu thuốc từ MQTT/Firebase
//
// Tách riêng module này giúp phần nhắc thuốc không làm rối main loop.
