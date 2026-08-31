"""
Admin panel helpers for updating graduation rules.
"""

import json
import os
import secrets
import tempfile

import streamlit as st


def render_admin_rules_editor(config_path):
    with st.expander("⚙️ 管理員：更新畢業規則", expanded=False):
        st.markdown(
            """
            <div style="font-size:12px; color:#94a3b8; margin-bottom:8px;">
            輸入管理員密碼後，可直接在此貼上新學年度的 <code>rules_config.json</code> 內容並儲存。
            儲存完畢後重新整理頁面即可套用新規則。
            </div>
            """,
            unsafe_allow_html=True,
        )

        admin_secret = os.environ.get("UTAIPEI_ADMIN_PASSWORD", "")
        if not admin_secret:
            try:
                admin_secret = st.secrets.get("UTAIPEI_ADMIN_PASSWORD", "")
            except FileNotFoundError:
                admin_secret = ""
        if not admin_secret:
            st.info("管理功能尚未啟用。請由部署管理員設定 UTAIPEI_ADMIN_PASSWORD。")
            return

        admin_pwd = st.text_input("管理員密碼", type="password", key="admin_pwd", placeholder="輸入管理員密碼...")
        if admin_pwd and secrets.compare_digest(admin_pwd, admin_secret):
            st.success("✅ 已驗證身分，可進行規則更新")
            current_json = _load_current_config(config_path)
            new_json_text = st.text_area(
                "貼上新的 rules_config.json 內容", value=current_json, height=300, key="admin_json_editor"
            )
            col_validate, col_save = st.columns(2)
            with col_validate:
                if st.button("🔍 驗證 JSON 格式", use_container_width=True):
                    _validate_json(new_json_text)
            with col_save:
                if st.button("💾 儲存並套用規則", use_container_width=True, type="primary"):
                    _save_json(config_path, new_json_text)
        elif admin_pwd:
            st.error("❌ 密碼錯誤，請重新輸入。")


def _load_current_config(config_path):
    if not os.path.exists(config_path):
        return ""
    try:
        with open(config_path, encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


def _validate_json(text):
    try:
        parsed = json.loads(text)
        required_keys = ["_meta", "university_common", "earth_life_major", "apc_rules", "cs_rules"]
        missing = [k for k in required_keys if k not in parsed]
        if missing:
            st.warning(f"⚠️ JSON 有效，但缺少以下必要欄位：{missing}")
        else:
            version = parsed.get("_meta", {}).get("version", "未知")
            st.success(f"✅ JSON 格式正確！偵測到學年度版本：{version}")
    except json.JSONDecodeError as e:
        st.error(f"❌ JSON 格式錯誤：{e!s}")


def _save_json(config_path, text):
    try:
        parsed = json.loads(text)
        required_keys = ["_meta", "university_common", "earth_life_major", "apc_rules", "cs_rules"]
        missing = [k for k in required_keys if k not in parsed]
        if missing:
            st.error(f"❌ 儲存失敗：缺少必要欄位 {missing}")
            return
        target_dir = os.path.dirname(os.path.abspath(config_path))
        fd, temp_path = tempfile.mkstemp(prefix="rules-", suffix=".json", dir=target_dir)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(parsed, f, ensure_ascii=False, indent=2)
                f.write("\n")
            os.replace(temp_path, config_path)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        st.success("✅ 已成功儲存新規則！請重新整理頁面讓新規則生效。")
        st.balloons()
    except json.JSONDecodeError as e:
        st.error(f"❌ JSON 格式錯誤，儲存失敗：{e!s}")
