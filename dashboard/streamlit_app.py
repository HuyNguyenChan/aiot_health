from __future__ import annotations

import time
from datetime import datetime
from typing import Any

import streamlit as st

from api_client import HealthApiClient
from components.states import ensure_dict, ensure_list, render_error
from components.views import render_alerts, render_ecg, render_overview, render_patient_info, render_report
from styles import apply_theme

try:
    from streamlit_autorefresh import st_autorefresh
except ImportError:
    st_autorefresh = None

# 1. Cấu hình trang (Nên để lên đầu)
st.set_page_config(
    page_title="AIoT Health Monitor",
    page_icon="❤️",
    layout="wide",
    initial_sidebar_state="expanded",
)
apply_theme()

# 2. Hàm chèn CSS tùy chỉnh làm đẹp UI
def inject_custom_css():
    st.markdown("""
    <style>
    /* Tạo hiệu ứng thẻ (card) cho các Metric */
    div[data-testid="metric-container"] {
        background-color: rgba(128, 128, 128, 0.05);
        border: 1px solid rgba(128, 128, 128, 0.2);
        padding: 15px;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    /* Chỉnh khoảng cách các Tab */
    .stTabs [data-baseweb="tab-list"] {
        gap: 15px;
    }
    </style>
    """, unsafe_allow_html=True)

inject_custom_css()

# ==========================================
# CÁC HÀM XỬ LÝ DỮ LIỆU (Giữ nguyên)
# ==========================================

@st.cache_data(ttl=5, show_spinner=False)
def load_patients(api_base: str) -> tuple[list[dict[str, Any]], str | None]:
    result = HealthApiClient(api_base).patients()
    return ensure_list(result.data), result.error

@st.cache_data(ttl=10, show_spinner=False)
def load_status(api_base: str) -> tuple[dict[str, Any], str | None]:
    result = HealthApiClient(api_base).status()
    return ensure_dict(result.data), result.error

@st.cache_data(ttl=2, show_spinner=False)
def load_latest(api_base: str, patient_id: str) -> tuple[dict[str, Any], str | None]:
    result = HealthApiClient(api_base).latest(patient_id)
    return ensure_dict(result.data), result.error

@st.cache_data(ttl=30, show_spinner=False)
def load_history(api_base: str, patient_id: str) -> tuple[list[dict[str, Any]], str | None]:
    result = HealthApiClient(api_base).history(patient_id, days=1)
    return ensure_list(result.data), result.error

@st.cache_data(ttl=2, show_spinner=False)
def load_ecg(api_base: str, patient_id: str) -> tuple[dict[str, Any], str | None]:
    result = HealthApiClient(api_base).ecg_latest(patient_id)
    return ensure_dict(result.data), result.error

@st.cache_data(ttl=15, show_spinner=False)
def load_alerts(api_base: str, patient_id: str) -> tuple[list[dict[str, Any]], str | None]:
    result = HealthApiClient(api_base).alerts(patient_id, limit=20)
    return ensure_list(result.data), result.error

@st.cache_data(ttl=120, show_spinner=False)
def load_prediction(api_base: str, patient_id: str) -> tuple[list[dict[str, Any]], str | None]:
    result = HealthApiClient(api_base).predict(patient_id, horizon_hours=6)
    payload = ensure_dict(result.data)
    prediction = payload.get("prediction", payload.get("predictions", []))
    return ensure_list(prediction), result.error

# ==========================================
# GIAO DIỆN SIDEBAR (Đã thiết kế lại gọn gàng hơn)
# ==========================================

with st.sidebar:
    st.title("🩺 AIoT Health Monitor")
    st.caption("Hệ thống theo dõi sức khỏe thời gian thực")
    st.divider()

    # Nhóm cài đặt kết nối
    with st.expander("🔗 Cài đặt Kết nối", expanded=False):
        api_base = st.text_input("API Base URL", value="http://localhost:5000/api")
        client = HealthApiClient(api_base)

    # Chọn bệnh nhân
    patients, patients_error = load_patients(api_base)
    patient_ids = [str(patient.get("id") or patient.get("device_id")) for patient in patients if patient.get("id") or patient.get("device_id")]
    if not patient_ids:
        patient_ids = ["patient_001"]
        
    selected_patient = st.selectbox("👤 Bệnh nhân", patient_ids)

    # Nhóm các ngưỡng cảnh báo vào container có viền
    with st.container(border=True):
        st.markdown("#### 🚨 Ngưỡng cảnh báo")
        hr_max = st.slider("HR tối đa (bpm)", 80, 200, 150, 5)
        spo2_min = st.slider("SpO2 tối thiểu (%)", 80, 100, 92, 1)
        temp_max = st.slider("Nhiệt độ tối đa (°C)", 37.0, 42.0, 38.5, 0.1)

    # Nhóm điều khiển làm mới
    st.markdown("#### 🔄 Đồng bộ dữ liệu")
    col1, col2 = st.columns([3, 1])
    realtime_enabled = col1.toggle("Realtime update", value=True)
    refresh_seconds = st.slider("Chu kỳ làm mới (giây)", 3, 60, 5)
    
    manual_refresh = st.button("Làm mới ngay", use_container_width=True, type="primary")

# Xử lý tự động làm mới
if realtime_enabled and st_autorefresh is not None:
    refresh_count = st_autorefresh(
        interval=refresh_seconds * 1000,
        key="health_dashboard_autorefresh",
    )
elif realtime_enabled:
    refresh_count = int(time.time() // refresh_seconds)
    st.toast("Cài `streamlit-autorefresh` để tính năng Realtime mượt mà hơn.", icon="⚠️")
else:
    refresh_count = 0

if manual_refresh:
    st.cache_data.clear()

# ==========================================
# LẤY DỮ LIỆU
# ==========================================

selected_patient_row = next((patient for patient in patients if str(patient.get("id") or patient.get("device_id")) == selected_patient), {})

service_status, status_error = load_status(api_base)
latest, latest_error = load_latest(api_base, selected_patient)
history, history_error = load_history(api_base, selected_patient)
ecg_data, ecg_error = load_ecg(api_base, selected_patient)
alerts, alerts_error = load_alerts(api_base, selected_patient)
prediction, prediction_error = load_prediction(api_base, selected_patient)

if patients_error:
    st.toast("Không lấy được danh sách bệnh nhân từ API. Đang dùng patient_001 mặc định.", icon="ℹ️")

# ==========================================
# GIAO DIỆN CHÍNH (MAIN CONTENT)
# ==========================================

# Khối Header hiển thị trạng thái hệ thống
with st.container():
    st.markdown("## 📊 Dashboard Tổng Quan")
    
    # Sử dụng columns để dàn đều các thông số quan trọng
    api_cols = st.columns(4)
    api_cols[0].metric("ID Bệnh nhân", selected_patient)
    api_cols[1].metric("Trạng thái API", "Hoạt động" if service_status.get("status", "unknown") == "ok" else "Lỗi", 
                       delta="Online" if not status_error else "Offline", delta_color="normal" if not status_error else "inverse")
    api_cols[2].metric("Luồng MQTT", "Đang chạy" if service_status.get("mqtt_thread_running") else "Chưa rõ")
    api_cols[3].metric("Lần cập nhật cuối", datetime.now().strftime('%H:%M:%S'))

st.divider()

# Phân bố không gian bằng Tabs
tab_overview, tab_ecg, tab_alerts, tab_report = st.tabs(
    ["📈 Tổng quan & Chỉ số", "🫀 ECG Waveform", "⚠️ Cảnh báo AI", "📄 Báo cáo Y tế"]
)

with tab_overview:
    if latest_error:
        render_error(type("Result", (), {"ok": False, "error": latest_error})(), "Dữ liệu Vitals mới nhất")
    
    render_overview(
        latest=latest,
        history=history,
        service_status=service_status,
        prediction=prediction,
        hr_max=hr_max,
        spo2_min=spo2_min,
        temp_max=temp_max,
    )
    
    st.markdown("<br>", unsafe_allow_html=True)
    with st.expander("📋 Thông tin chi tiết bệnh nhân", expanded=True):
        render_patient_info(selected_patient_row, latest)

    if history_error:
        st.info("ℹ️ Lịch sử dữ liệu (History API) chưa sẵn sàng hoặc rỗng.")
    if prediction_error:
        st.info("ℹ️ Chức năng dự đoán LSTM chưa sẵn sàng.")

with tab_ecg:
    if ecg_error:
        st.warning("⚠️ Endpoint ECG chưa sẵn sàng. Chưa thể hiển thị biểu đồ sóng realtime lúc này.")
    else:
        st.markdown("#### Biểu đồ điện tâm đồ (ECG) Thời gian thực")
    render_ecg(ecg_data)

with tab_alerts:
    if alerts_error:
        st.info("ℹ️ Hệ thống cảnh báo (Alert API) chưa có dữ liệu hoặc chưa sẵn sàng.")
    render_alerts(alerts)

with tab_report:
    render_report(client, selected_patient, latest, alerts)

# Footer tinh tế hơn
st.markdown("---")
col_footer1, col_footer2 = st.columns(2)
with col_footer1:
    st.caption("AIoT Health Monitor v1.0")
with col_footer2:
    if realtime_enabled and st_autorefresh is None:
        st.caption("*(Chế độ realtime đang chạy qua cache TTL fallback)*")