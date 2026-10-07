from __future__ import annotations

from typing import Any

import streamlit as st

from formatters import ai_score_percent, as_bool, as_float, status_dot, status_level


def render_metric_cards(
    latest: dict[str, Any],
    *,
    hr_max: int,
    spo2_min: int,
    temp_max: float,
) -> None:
    hr = as_float(latest.get("heart_rate"))
    spo2 = as_float(latest.get("spo2"))
    temp = as_float(latest.get("temperature"))
    fall = as_bool(latest.get("fall", latest.get("fall_detect", False)))
    score = ai_score_percent(latest)

    cols = st.columns(5)
    hr_level = status_level("hr", hr, hr_max, spo2_min, temp_max)
    spo2_level = status_level("spo2", spo2, hr_max, spo2_min, temp_max)
    temp_level = status_level("temp", temp, hr_max, spo2_min, temp_max)
    fall_level = status_level("fall", 1.0 if fall else 0.0, hr_max, spo2_min, temp_max)
    score_level = "danger" if score >= 67 else "warn" if score >= 34 else "ok"

    cols[0].metric(f"{status_dot(hr_level)} Nhịp tim", f"{hr:.0f} bpm" if hr else "--")
    cols[1].metric(f"{status_dot(spo2_level)} SpO2", f"{spo2:.0f}%" if spo2 else "--")
    cols[2].metric(f"{status_dot(temp_level)} Nhiệt độ", f"{temp:.1f}°C" if temp else "--")
    cols[3].metric(f"{status_dot(fall_level)} Ngã", "Có" if fall else "Không")
    cols[4].metric(f"{status_dot(score_level)} AI Score", f"{score:.0f}%")


def render_device_status(latest: dict[str, Any], service_status: dict[str, Any] | None = None) -> None:
    service_status = service_status or {}
    ecg_lead_off = as_bool(latest.get("ecg_lead_off", False))
    hr_valid = as_bool(latest.get("heart_rate_valid", latest.get("heart_rate", 0)))
    spo2_valid = as_bool(latest.get("spo2_valid", latest.get("spo2", 0)))
    mqtt_running = as_bool(service_status.get("mqtt_thread_running", False))

    cols = st.columns(4)
    values = [
        ("API", service_status.get("status", "unknown"), "ok" if service_status.get("status") == "ok" else "warn"),
        ("MQTT", "Đang chạy" if mqtt_running else "Chưa rõ", "ok" if mqtt_running else "warn"),
        ("ECG", "Điện cực rời" if ecg_lead_off else "Sẵn sàng", "danger" if ecg_lead_off else "ok"),
        ("MAX30102", "Có SpO2" if spo2_valid else "Chưa hợp lệ", "ok" if spo2_valid else "warn"),
    ]

    for col, (title, value, level) in zip(cols, values):
        col.markdown(
            f"""
            <div class="status-card">
              <div class="status-title">{status_dot(level)} {title}</div>
              <div class="status-value">{value}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    if not hr_valid:
        st.caption("HR hiện chưa hợp lệ. Với cấu hình hiện tại, HR lấy từ AD8232.")
