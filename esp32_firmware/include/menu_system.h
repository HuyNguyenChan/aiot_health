#pragma once

// Header này dành cho menu trên OLED hoặc giao diện cục bộ của thiết bị.
// Nên giữ module này chỉ xử lý:
// - trạng thái màn hình/menu
// - điều hướng bằng nút nhấn
// - nội dung hiển thị
//
// Không nên trộn logic sensor hoặc MQTT trực tiếp vào đây để menu dễ bảo trì.
