from __future__ import annotations

from typing import Any

import streamlit as st

from api_client import ApiResult


def render_error(result: ApiResult, label: str) -> bool:
    if result.ok:
        return False
    st.error(f"{label}: chưa lấy được dữ liệu.")
    with st.expander("Chi tiết lỗi", expanded=False):
        st.code(result.error or "Unknown error")
    return True


def render_empty(message: str) -> None:
    st.info(message)


def ensure_list(value: Any) -> list:
    return value if isinstance(value, list) else []


def ensure_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}
