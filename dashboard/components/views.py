from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd
import streamlit as st

from api_client import HealthApiClient
from components.cards import render_device_status, render_metric_cards
from components.charts import ai_score_chart, ecg_waveform, prediction_chart, vital_line
from formatters import as_bool, parse_time_frame, short_time
from styles import MEDICAL_COLORS


def render_overview(
    *,
    latest: dict[str, Any],
    history: list[dict[str, Any]],
    service_status: dict[str, Any],
    prediction: list[dict[str, Any]],
    hr_max: int,
    spo2_min: int,
    temp_max: float,
) -> None:
    st.subheader("Realtime vitals")
    if not latest:
        st.info("Chưa có dữ liệu mới nhất từ thiết bị.")
    render_metric_cards(latest, hr_max=hr_max, spo2_min=spo2_min, temp_max=temp_max)

    st.subheader("Trạng thái thiết bị")
    render_device_status(latest, service_status)

    df = parse_time_frame(history)
    st.subheader("Biểu đồ theo dõi 24h")
    if df.empty:
        st.info("Chưa có lịch sử 24h để vẽ biểu đồ.")
        return

    col_hr, col_spo2 = st.columns(2)
    if "heart_rate" in df.columns:
        fig_hr = vital_line(
            df,
            "heart_rate",
            "Heart rate",
            MEDICAL_COLORS["red"],
            title="Nhịp tim 24h - AD8232 ECG",
            y_title="Nhịp tim (bpm)",
        )
        fig_hr.add_hline(y=hr_max, line_dash="dash", line_color=MEDICAL_COLORS["amber"])
        col_hr.plotly_chart(fig_hr, use_container_width=True)
        col_hr.caption("Dữ liệu: `heart_rate` từ AD8232. Đường gạch là ngưỡng HR tối đa.")
    else:
        col_hr.info("Chưa có cột heart_rate.")

    if "spo2" in df.columns:
        fig_spo2 = vital_line(
            df,
            "spo2",
            "SpO2",
            MEDICAL_COLORS["cyan"],
            title="SpO2 24h - MAX30102",
            y_title="Độ bão hòa oxy (%)",
        )
        fig_spo2.add_hline(y=spo2_min, line_dash="dash", line_color=MEDICAL_COLORS["red"])
        fig_spo2.update_yaxes(range=[80, 101])
        col_spo2.plotly_chart(fig_spo2, use_container_width=True)
        col_spo2.caption("Dữ liệu: `spo2` từ MAX30102. Đường gạch là ngưỡng SpO2 tối thiểu.")
    else:
        col_spo2.info("Chưa có cột spo2.")

    col_temp, col_ai = st.columns(2)
    if "temperature" in df.columns:
        fig_temp = vital_line(
            df,
            "temperature",
            "Temperature",
            MEDICAL_COLORS["amber"],
            title="Nhiệt độ cơ thể 24h - DS18B20",
            y_title="Nhiệt độ (°C)",
        )
        fig_temp.add_hline(y=temp_max, line_dash="dash", line_color=MEDICAL_COLORS["red"])
        col_temp.plotly_chart(fig_temp, use_container_width=True)
        col_temp.caption("Dữ liệu: `temperature` từ DS18B20. Đường gạch là ngưỡng sốt.")
    else:
        col_temp.info("Chưa có cột temperature.")

    col_ai.plotly_chart(ai_score_chart(df), use_container_width=True)
    col_ai.caption("Dữ liệu: `ai_score` hoặc `ai_confidence`. Mốc 67% tương ứng 2/3 vote bất thường.")

    st.subheader("Dự đoán LSTM 6h tới")
    if prediction:
        st.plotly_chart(prediction_chart(prediction), use_container_width=True)
        st.caption("Dữ liệu: dự đoán từ model LSTM, đường tím gạch là HR dự đoán trong tương lai.")
    else:
        st.info("Chưa đủ dữ liệu hoặc model dự đoán chưa sẵn sàng.")


def render_patient_info(patient: dict[str, Any], latest: dict[str, Any]) -> None:
    st.subheader("Thông tin bệnh nhân")
    patient_info = patient.get("info", {}) if patient else {}
    rows = {
        "Patient ID": patient.get("id", latest.get("device_id", "--")) if patient else latest.get("device_id", "--"),
        "Tên": patient_info.get("name", "--"),
        "Tuổi": patient_info.get("age", "--"),
        "Giới tính": patient_info.get("gender", "--"),
        "Cập nhật cuối": short_time(latest.get("updated_at", latest.get("timestamp", latest.get("ts")))),
        "Trạng thái": latest.get("status", "--"),
        "Chế độ đo": latest.get("measure_mode", "--"),
    }
    st.dataframe(pd.DataFrame(rows.items(), columns=["Trường", "Giá trị"]), hide_index=True, use_container_width=True)


def render_ecg(ecg_data: dict[str, Any]) -> None:
    st.subheader("ECG waveform realtime")
    samples = ecg_data.get("samples", ecg_data.get("ecg_samples", []))
    lead_off = as_bool(ecg_data.get("lead_off", ecg_data.get("ecg_lead_off", False)))
    anomaly = as_bool(ecg_data.get("anomaly", ecg_data.get("ecg_anomaly", False)))

    if lead_off:
        st.warning("Điện cực ECG đang rời. Kiểm tra LO+/LO- và miếng dán AD8232.")

    if isinstance(samples, list) and len(samples) >= 250:
        st.plotly_chart(ecg_waveform(samples, anomaly=anomaly), use_container_width=True)
        st.caption("Dữ liệu: `ecg_samples`, 250 mẫu tương ứng 5 giây ở tần số 50Hz.")
        if anomaly:
            st.error("ECG bất thường theo Autoencoder.")
        elif not lead_off:
            st.success("ECG trong ngưỡng bình thường.")
    elif ecg_data:
        st.info("Đã có dữ liệu ECG nhưng chưa đủ 250 mẫu để vẽ cửa sổ 5 giây.")
    else:
        st.info("Chưa có dữ liệu ECG realtime. Cần endpoint `/api/health/{id}/ecg_latest` hoặc lưu ecg_samples vào Firebase.")


def render_alerts(alerts: list[dict[str, Any]]) -> None:
    st.subheader("Alert history")
    if not alerts:
        st.success("Không có cảnh báo gần đây.")
        return

    df = pd.DataFrame(alerts[:20])
    if "confidence" not in df.columns:
        df["confidence"] = df.get("ai_confidence", df.get("ai_score", 0.0))
    if "time" not in df.columns:
        df["time"] = df.get("timestamp", df.get("created_at", ""))

    cols = [col for col in ["time", "reason", "confidence", "heart_rate", "spo2", "temperature", "level"] if col in df.columns]
    table = df[cols].rename(
        columns={
            "time": "Thời gian",
            "reason": "Lý do",
            "confidence": "Confidence",
            "heart_rate": "HR",
            "spo2": "SpO2",
            "temperature": "Nhiệt độ",
            "level": "Mức độ",
        }
    )
    st.dataframe(table, hide_index=True, use_container_width=True)


def render_report(client: HealthApiClient, patient_id: str, latest: dict[str, Any], alerts: list[dict[str, Any]]) -> None:
    st.subheader("Báo cáo")
    st.caption("Báo cáo hôm nay dùng endpoint `/api/report/{id}`. Nếu server chưa có endpoint, dashboard sẽ hiển thị trạng thái chưa sẵn sàng.")

    col_summary, col_download = st.columns([2, 1])
    with col_summary:
        st.markdown("**Tóm tắt nhanh**")
        st.write(
            {
                "patient_id": patient_id,
                "latest_status": latest.get("status", "--"),
                "latest_update": latest.get("updated_at", latest.get("ts", "--")),
                "alerts_20_latest": len(alerts),
            }
        )

    with col_download:
        if st.button("Tải báo cáo hôm nay", use_container_width=True):
            result = client.report_pdf(patient_id)
            if result.ok and result.data:
                st.download_button(
                    "Download PDF",
                    data=result.data,
                    file_name=f"report_{patient_id}_{datetime.today().date()}.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                )
            else:
                st.error("Endpoint report chưa sẵn sàng hoặc server không trả PDF.")
