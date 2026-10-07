from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from formatters import ai_score_percent
from styles import MEDICAL_COLORS


def vital_line(
    df: pd.DataFrame,
    y_col: str,
    name: str,
    color: str,
    *,
    title: str,
    y_title: str,
    height: int = 300,
) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=df["time"],
            y=pd.to_numeric(df[y_col], errors="coerce"),
            mode="lines",
            line={"color": color, "width": 2.2},
            name=name,
        )
    )
    fig.update_layout(
        height=height,
        title={"text": title, "x": 0.02, "xanchor": "left"},
        margin={"l": 12, "r": 12, "t": 56, "b": 12},
        legend={"orientation": "h"},
        plot_bgcolor="#ffffff",
        paper_bgcolor="#ffffff",
        xaxis_title="Thời gian",
        yaxis_title=y_title,
    )
    return fig


def ai_score_chart(df: pd.DataFrame) -> go.Figure:
    score_df = df.copy()
    score_df["ai_score_pct"] = score_df.apply(ai_score_percent, axis=1)

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=score_df["time"],
            y=score_df["ai_score_pct"],
            mode="lines",
            line={"color": MEDICAL_COLORS["purple"], "width": 2.2},
            fill="tozeroy",
            fillcolor="rgba(124, 58, 237, 0.12)",
            name="AI Score",
        )
    )
    fig.add_hline(
        y=67,
        line_dash="dash",
        line_color=MEDICAL_COLORS["purple"],
        annotation_text="Ngưỡng cảnh báo 67%",
        annotation_position="top left",
    )
    fig.update_yaxes(range=[0, 105])
    fig.update_layout(
        title={"text": "AI Score 24h - mức đồng thuận bất thường", "x": 0.02, "xanchor": "left"},
        height=300,
        margin={"l": 12, "r": 12, "t": 56, "b": 12},
        xaxis_title="Thời gian",
        yaxis_title="AI Score (%)",
    )
    return fig


def ecg_waveform(samples: list[float], *, anomaly: bool = False) -> go.Figure:
    values = samples[:250]
    time_axis = [index / 50 for index in range(len(values))]
    color = MEDICAL_COLORS["red"] if anomaly else MEDICAL_COLORS["cyan"]

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=time_axis,
            y=values,
            mode="lines",
            line={"color": color, "width": 1.7},
            name="ECG",
        )
    )
    fig.update_layout(
        title={"text": "ECG waveform realtime - 250 mẫu trong 5 giây", "x": 0.02, "xanchor": "left"},
        height=420,
        margin={"l": 12, "r": 12, "t": 58, "b": 12},
        xaxis_title="Thời gian (giây)",
        yaxis_title="Biên độ ADC",
        plot_bgcolor="#ffffff",
        paper_bgcolor="#ffffff",
    )
    return fig


def prediction_chart(predictions: list[dict]) -> go.Figure:
    pred_df = pd.DataFrame(predictions)
    if "minutes_ahead" not in pred_df.columns:
        pred_df["minutes_ahead"] = [(index + 1) * 5 for index in range(len(pred_df))]

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=pred_df["minutes_ahead"],
            y=pred_df["heart_rate"],
            mode="lines",
            line={"color": MEDICAL_COLORS["purple"], "width": 2.4, "dash": "dash"},
            name="LSTM HR",
        )
    )
    fig.update_layout(
        title={"text": "Dự đoán nhịp tim 6 giờ tới bằng LSTM", "x": 0.02, "xanchor": "left"},
        height=240,
        margin={"l": 12, "r": 12, "t": 56, "b": 12},
        xaxis_title="Phút tới",
        yaxis_title="Nhịp tim dự đoán (bpm)",
    )
    return fig
