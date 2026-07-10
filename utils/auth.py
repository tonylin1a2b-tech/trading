# utils/auth.py — 登入保護（hmac 比對 + 失敗次數鎖定）

import hmac
import time

import streamlit as st

_MAX_ATTEMPTS    = 5
_LOCKOUT_SECONDS = 300  # 5 分鐘


def check_password() -> bool:
    """
    顯示密碼輸入框。
    - 使用 hmac.compare_digest 防止 timing attack
    - 連續失敗 5 次後鎖定 5 分鐘
    - 密碼從 st.secrets["APP_PASSWORD"] 讀取，不得硬編碼
    """
    if st.session_state.get("password_correct", False):
        return True

    st.session_state.setdefault("login_attempts", 0)
    st.session_state.setdefault("login_locked_until", 0.0)

    now          = time.time()
    locked_until = st.session_state["login_locked_until"]
    if now < locked_until:
        remaining = int(locked_until - now)
        st.error(f"🔒 登入已鎖定，請 {remaining} 秒後再試")
        return False

    st.markdown("# 🔒 台股交易系統")
    st.caption("這是僅限受邀朋友使用的私人系統，請輸入存取密碼")
    pwd = st.text_input("請輸入密碼", type="password")

    if pwd:
        correct = st.secrets.get("APP_PASSWORD", "")
        if hmac.compare_digest(pwd.encode(), correct.encode()):
            st.session_state["password_correct"]  = True
            st.session_state["login_attempts"]    = 0
            st.rerun()
        else:
            st.session_state["login_attempts"] += 1
            left = _MAX_ATTEMPTS - st.session_state["login_attempts"]
            if st.session_state["login_attempts"] >= _MAX_ATTEMPTS:
                st.session_state["login_locked_until"] = now + _LOCKOUT_SECONDS
                st.session_state["login_attempts"]     = 0
                st.error(f"❌ 密碼錯誤次數過多，已鎖定 {_LOCKOUT_SECONDS // 60} 分鐘")
            else:
                st.error(f"❌ 密碼錯誤，還剩 {left} 次機會")

    return False
