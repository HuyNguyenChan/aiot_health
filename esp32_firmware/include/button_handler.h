#pragma once

// Header này sẽ chứa logic đọc và debounce nút nhấn:
// - SOS
// - Menu
// - OK
//
// Khi triển khai, nên tách rõ:
// - phần đọc raw state từ GPIO
// - phần debounce / long-press
// - phần sinh event cho menu hoặc cảnh báo SOS
