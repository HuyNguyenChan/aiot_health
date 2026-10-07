---
name: streamlit-dashboard
description: Use this skill to build or update the Streamlit v3 dashboard — now includes realtime ECG waveform chart (from Firebase ECG data), PDF report download button, confidence score display for ensemble AI, and medicine compliance tab. Trigger when user says 'dashboard', 'giao diện', 'Streamlit', 'biểu đồ', 'hiển thị dữ liệu', 'web app', 'ECG chart', 'PDF report', or 'confidence score'.
---

# Streamlit Dashboard Skill v3 – AIoT Health Monitor

## File: dashboard/streamlit_app.py (v3)

```python
import streamlit as st
import plotly.graph_objects as go
import requests
import time
import pandas as pd
from datetime import datetime

st.set_page_config(
    page_title="AIoT Health Monitor v3",
    page_icon="❤️", layout="wide",
    initial_sidebar_state="expanded"
)

API_BASE = "http://localhost:5000/api"

# ── Sidebar ──────────────────────────────────────────
with st.sidebar:
    st.title("⚕️ AIoT Health v3")
    st.markdown("---")

    try:
        patients = requests.get(f"{API_BASE}/patients", timeout=3).json()
        patient_ids = [p["id"] for p in patients]
    except:
        patient_ids = ["patient_001"]

    selected = st.selectbox("👤 Bệnh nhân", patient_ids)
    refresh  = st.slider("🔄 Cập nhật (giây)", 3, 60, 5)

    st.markdown("---")
    st.markdown("**Ngưỡng cảnh báo:**")
    hr_max   = st.number_input("HR tối đa", value=120, min_value=80, max_value=200)
    spo2_min = st.number_input("SpO₂ tối thiểu", value=92, min_value=80, max_value=100)
    temp_max = st.number_input("Nhiệt độ tối đa", value=38.0, min_value=37.0, max_value=42.0)

    st.markdown("---")
    # Download PDF báo cáo hôm nay (MỚI v3)
    st.markdown("**Báo cáo PDF:**")
    if st.button("📄 Tải báo cáo hôm nay"):
        try:
            r = requests.get(f"{API_BASE}/report/{selected}", timeout=10)
            st.download_button(
                label="💾 Download PDF",
                data=r.content,
                file_name=f"report_{selected}_{datetime.today().date()}.pdf",
                mime="application/pdf"
            )
        except:
            st.error("Không tạo được báo cáo")

# ── Cache data ────────────────────────────────────
@st.cache_data(ttl=refresh)
def fetch_latest(pid):
    try: return requests.get(f"{API_BASE}/health/{pid}/latest", timeout=3).json()
    except: return {}

@st.cache_data(ttl=30)
def fetch_history(pid, days=1):
    try: return requests.get(f"{API_BASE}/health/{pid}/history?days={days}", timeout=3).json()
    except: return []

@st.cache_data(ttl=refresh)
def fetch_ecg(pid):
    """MỚI v3: lấy ECG waveform mới nhất"""
    try: return requests.get(f"{API_BASE}/health/{pid}/ecg_latest", timeout=3).json()
    except: return {}

@st.cache_data(ttl=60)
def fetch_alerts(pid):
    try: return requests.get(f"{API_BASE}/alerts/{pid}", timeout=3).json()
    except: return []

def status_icon(value, metric):
    if metric == "hr":
        if value < 60 or value > hr_max: return "🔴"
        elif value < 65 or value > 100:  return "🟡"
        return "🟢"
    elif metric == "spo2":
        if value < spo2_min: return "🔴"
        elif value < 95:     return "🟡"
        return "🟢"
    elif metric == "temp":
        if value > temp_max: return "🔴"
        elif value > 37.5:   return "🟡"
        return "🟢"
    return "⚪"

# ── Tabs (MỚI v3 — tách ECG ra tab riêng) ─────────
tab_vitals, tab_ecg, tab_alerts = st.tabs([
    "❤️ Chỉ số sức khỏe",
    "📊 ECG Realtime",
    "🚨 Cảnh báo"
])

latest  = fetch_latest(selected)
history = fetch_history(selected, days=1)
alerts  = fetch_alerts(selected)

# ══════════════════════════════════════════════════
# Tab 1: Vitals
# ══════════════════════════════════════════════════
with tab_vitals:
    st.title(f"Giám sát Sức khỏe — {selected}")

    hr   = latest.get("heart_rate", 0)
    spo2 = latest.get("spo2", 0)
    temp = latest.get("temperature", 0)
    fall = latest.get("fall", False)
    conf = latest.get("anomaly_score", 0)

    # Metric cards
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1: st.metric(f"{status_icon(hr,'hr')} Nhịp tim", f"{hr} bpm")
    with c2: st.metric(f"{status_icon(spo2,'spo2')} SpO₂", f"{spo2}%")
    with c3: st.metric(f"{status_icon(temp,'temp')} Nhiệt độ", f"{temp}°C")
    with c4: st.metric("🚶 Ngã", "⚠️ CÓ NGÃ" if fall else "✅ Bình thường")
    with c5:
        # MỚI v3: hiển thị AI confidence
        conf_pct = int(conf * 100)
        st.metric("🤖 AI Score", f"{conf_pct}%",
                  help="0% = bình thường, 100% = tất cả 3 model đồng ý bất thường")

    st.markdown("---")

    if history:
        df = pd.DataFrame(history)
        df["time"] = pd.to_datetime(df.get("timestamp", df.index))
        df = df.sort_values("time")

        col_l, col_r = st.columns(2)
        with col_l:
            st.subheader("📈 Nhịp tim 24h")
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=df["time"], y=df["heart_rate"],
                                     mode="lines", line=dict(color="#e74c3c",width=2)))
            fig.add_hline(y=hr_max, line_dash="dash", line_color="orange")
            fig.update_layout(height=280, margin=dict(l=0,r=0,t=20,b=0))
            st.plotly_chart(fig, use_container_width=True)

        with col_r:
            st.subheader("🫁 SpO₂ 24h")
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=df["time"], y=df["spo2"],
                                     fill="tozeroy", fillcolor="rgba(52,152,219,0.1)",
                                     mode="lines", line=dict(color="#3498db",width=2)))
            fig.add_hline(y=spo2_min, line_dash="dash", line_color="red")
            fig.update_layout(height=280, yaxis=dict(range=[85,101]),
                              margin=dict(l=0,r=0,t=20,b=0))
            st.plotly_chart(fig, use_container_width=True)

        # MỚI v3: AI Confidence Score trend
        if "anomaly_score" in df.columns:
            st.subheader("🤖 Lịch sử Ensemble AI Score")
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=df["time"], y=df["anomaly_score"]*100,
                fill="tozeroy", fillcolor="rgba(155,89,182,0.1)",
                mode="lines", line=dict(color="#9b59b6", width=2),
                name="AI Score (%)"
            ))
            fig.add_hline(y=67, line_dash="dash", line_color="red",
                          annotation_text="Ngưỡng cảnh báo (2/3 vote)")
            fig.update_layout(height=200, yaxis=dict(range=[0,105]),
                              margin=dict(l=0,r=0,t=20,b=0))
            st.plotly_chart(fig, use_container_width=True)

        # Dự đoán LSTM
        col_pred = st.columns(1)[0]
        st.subheader("🔮 Dự đoán LSTM 6h tới")
        try:
            pred = requests.get(f"{API_BASE}/predict/{selected}", timeout=5).json()
            preds = pred.get("predictions", [])
            if preds:
                fig = go.Figure()
                fig.add_trace(go.Scatter(y=preds, mode="lines",
                                         line=dict(color="#9b59b6",dash="dot",width=2)))
                fig.update_layout(height=180, margin=dict(l=0,r=0,t=20,b=0))
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Cần thêm dữ liệu để dự đoán")
        except:
            st.warning("AI server chưa sẵn sàng")

# ══════════════════════════════════════════════════
# Tab 2: ECG Realtime (MỚI v3)
# ══════════════════════════════════════════════════
with tab_ecg:
    st.title("📊 Tín hiệu ECG Realtime")

    ecg_data = fetch_ecg(selected)
    samples  = ecg_data.get("samples", [])
    is_anom  = ecg_data.get("anomaly", False)
    ecg_ts   = ecg_data.get("ts", "")

    if len(samples) == 250:
        color = "red" if is_anom else "#00d4ff"
        t     = [i * 0.02 for i in range(250)]  # 0-5 giây @ 50Hz

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=t, y=samples, mode="lines",
            line=dict(color=color, width=1.5),
            name="ECG Signal"
        ))
        fig.update_layout(
            title=f"ECG {'⚠️ BẤT THƯỜNG' if is_anom else '✅ Bình thường'} — {ecg_ts[:19]}",
            xaxis_title="Thời gian (giây)",
            yaxis_title="Amplitude (ADC value)",
            height=300,
            paper_bgcolor='rgba(0,0,0,0)',
            margin=dict(l=40,r=20,t=40,b=40)
        )
        st.plotly_chart(fig, use_container_width=True)

        if is_anom:
            st.error("🚨 ECG Autoencoder phát hiện tín hiệu bất thường!")
        else:
            st.success("✅ Tín hiệu ECG trong ngưỡng bình thường")

        st.caption("💡 Model Conv1D Autoencoder train trên dataset MIT-BIH (PhysioNet)")
    elif ecg_data:
        st.warning("⚠️ Điện cực bị rời — vui lòng kiểm tra kết nối AD8232")
    else:
        st.info("📡 Chưa nhận được dữ liệu ECG từ thiết bị")

# ══════════════════════════════════════════════════
# Tab 3: Cảnh báo
# ══════════════════════════════════════════════════
with tab_alerts:
    st.title("🚨 Lịch sử Cảnh báo")
    if alerts:
        df_a = pd.DataFrame(alerts[:20])
        df_a["time"] = pd.to_datetime(df_a["time"]).dt.strftime("%H:%M %d/%m")
        # MỚI v3: hiển thị confidence
        cols_show = [c for c in ["time","reason","confidence","heart_rate","spo2","level"]
                     if c in df_a.columns]
        st.dataframe(df_a[cols_show].rename(columns={
            "time":"Thời gian","reason":"Lý do","confidence":"Confidence",
            "heart_rate":"HR","spo2":"SpO₂","level":"Mức độ"
        }), hide_index=True, use_container_width=True)
    else:
        st.success("✅ Không có cảnh báo nào")

# ── Auto refresh ──────────────────────────────────
st.caption(f"🕒 Cập nhật: {datetime.now().strftime('%H:%M:%S')} | Mỗi {refresh}s")
time.sleep(refresh)
st.rerun()
```

## Chạy dashboard

```bash
cd dashboard
streamlit run streamlit_app.py
# → http://localhost:8501
```
