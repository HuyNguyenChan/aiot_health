from __future__ import annotations

import streamlit as st


MEDICAL_COLORS = {
    "blue": "#0f7cba",
    "cyan": "#00a8e8",
    "green": "#1f9d78",
    "red": "#d64545",
    "amber": "#f59e0b",
    "purple": "#7c3aed",
    "ink": "#172033",
    "muted": "#667085",
    "surface": "#ffffff",
    "band": "#f6f9fc",
    "border": "#d9e2ec",
}


def apply_theme() -> None:
    st.markdown(
        """
        <style>
        .stApp {
            background: #f6f9fc !important;
            color: #172033 !important;
        }
        [data-testid="stAppViewContainer"] {
            background: #f6f9fc !important;
        }
        [data-testid="stHeader"] {
            background: rgba(246, 249, 252, 0.92) !important;
        }
        [data-testid="stSidebar"] {
            background: #ffffff !important;
            border-right: 1px solid #d9e2ec;
        }
        [data-testid="stSidebar"] * {
            color: #172033 !important;
        }
        [data-testid="stSidebar"] p,
        [data-testid="stSidebar"] label,
        [data-testid="stSidebar"] span {
            color: #344054 !important;
        }
        [data-testid="stSidebar"] h1,
        [data-testid="stSidebar"] h2,
        [data-testid="stSidebar"] h3 {
            color: #0f7cba !important;
        }
        [data-testid="stSidebar"] small,
        [data-testid="stSidebar"] .stCaptionContainer,
        [data-testid="stSidebar"] [data-testid="stCaptionContainer"] p {
            color: #667085 !important;
        }
        [data-testid="stSidebar"] div[data-baseweb="select"] > div,
        [data-testid="stSidebar"] input,
        [data-testid="stSidebar"] textarea {
            background: #ffffff !important;
            color: #172033 !important;
            border-color: #c8d4e0 !important;
        }
        [data-testid="stSidebar"] div[data-baseweb="select"] span {
            color: #172033 !important;
        }
        [data-testid="stSidebar"] [data-testid="stSlider"] * {
            color: #344054 !important;
        }
        [data-testid="stSidebar"] hr {
            border-color: #d9e2ec !important;
        }
        h1, h2, h3, h4, h5, h6, p, label, span {
            color: #172033;
        }
        .block-container {
            padding-top: 1.5rem;
            padding-bottom: 2rem;
            max-width: 1500px;
        }
        div[data-testid="stMetric"] {
            background: #ffffff;
            border: 1px solid #d9e2ec;
            border-radius: 8px;
            padding: 14px 16px;
            box-shadow: 0 1px 2px rgba(16, 24, 40, 0.04);
        }
        div[data-testid="stMetric"] * {
            color: #172033 !important;
        }
        div[data-testid="stMetricLabel"] p,
        div[data-testid="stMetricLabel"] label,
        div[data-testid="stMetricLabel"] span {
            color: #667085 !important;
            font-weight: 600;
        }
        div[data-testid="stMetricValue"],
        div[data-testid="stMetricValue"] div,
        div[data-testid="stMetricValue"] label {
            color: #172033 !important;
            font-weight: 800 !important;
        }
        div[data-testid="stMetricDelta"] svg,
        div[data-testid="stMetricDelta"] p {
            color: #1f9d78 !important;
            fill: #1f9d78 !important;
        }
        [data-testid="stTabs"] button p {
            color: #172033 !important;
            font-weight: 700;
        }
        .status-card {
            background: #ffffff;
            border: 1px solid #d9e2ec;
            border-radius: 8px;
            padding: 14px 16px;
            min-height: 92px;
        }
        .status-title {
            color: #667085 !important;
            font-size: 0.86rem;
            font-weight: 700;
            margin-bottom: 0.35rem;
        }
        .status-value {
            color: #172033 !important;
            font-size: 1.25rem;
            font-weight: 750;
        }
        .soft-note {
            color: #667085 !important;
            font-size: 0.9rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
