"""Streamlit two-pass UI for auditable course equivalency decisions."""

from __future__ import annotations

import hashlib
import json
from html import escape
from typing import Any, Mapping

import pandas as pd
import streamlit as st

from equivalency_audit import (
    APPROVED,
    AMBIGUOUS,
    DECISION_STATES,
    PENDING,
    PROPOSED,
    REJECTED,
    audit_equivalency_decisions,
    detect_equivalency_candidates,
    source_attempt_id,
)


_STATE_LABELS = {
    PROPOSED: "候選／建議",
    PENDING: "待人工確認",
    APPROVED: "已核准（需證據）",
    REJECTED: "不採認",
}


def _stable_context_key(context: Mapping[str, Any] | None, target_requirements: Mapping[str, Any] | None) -> str:
    payload = {
        "context": dict(context or {}),
        "target": {
            "cohort": (target_requirements or {}).get("cohort", ""),
            "program": (target_requirements or {}).get("program", ""),
            "track": (target_requirements or {}).get("track", ""),
            "program_type": (target_requirements or {}).get("program_type", ""),
        },
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def ensure_equivalency_session(
    context: Mapping[str, Any] | None = None,
    target_requirements: Mapping[str, Any] | None = None,
    *,
    session_key: str = "equivalency_decisions",
) -> list[dict[str, Any]]:
    """Reset session-only decisions when cohort/target context changes."""

    signature_key = f"{session_key}_context_signature"
    signature = _stable_context_key(context, target_requirements)
    if st.session_state.get(signature_key) != signature:
        st.session_state[signature_key] = signature
        st.session_state[session_key] = []
    decisions = st.session_state.get(session_key, [])
    if not isinstance(decisions, list):
        decisions = []
        st.session_state[session_key] = decisions
    return decisions


def _target_plan_from_report(report: Mapping[str, Any] | None) -> Mapping[str, Any] | None:
    report = report or {}
    direct = report.get("target_requirements")
    if isinstance(direct, Mapping):
        return direct
    target_plan = report.get("target_plan")
    if isinstance(target_plan, Mapping) and isinstance(target_plan.get("target_requirements"), Mapping):
        return target_plan["target_requirements"]
    return None


def _course_label(course: Mapping[str, Any]) -> str:
    completed = float(course.get("completed_credit") or 0.0)
    total = float(course.get("total_credit") or 0.0)
    return f"{course.get('name') or course.get('raw_name') or '未命名'}｜{total:g} 學分｜已得 {completed:g}｜{source_attempt_id(course)}"


def _upsert_decision(decisions: list[dict[str, Any]], decision: dict[str, Any]) -> None:
    key = (decision.get("source_attempt_id", ""), decision.get("target_requirement_id", ""))
    for index, existing in enumerate(decisions):
        if (existing.get("source_attempt_id", ""), existing.get("target_requirement_id", "")) == key:
            decisions[index] = decision
            return
    decisions.append(decision)


def render_equivalency_workflow(
    courses: list[Mapping[str, Any]] | None,
    report: Mapping[str, Any] | None,
    context: Mapping[str, Any] | None = None,
    *,
    session_key: str = "equivalency_decisions",
) -> list[dict[str, Any]]:
    """Render the candidate/decision pass and return session decisions.

    The caller should invoke evaluation again with the returned decisions.  No
    browser upload is persisted and no decision is sent to an external system.
    """

    target_requirements = _target_plan_from_report(report)
    if not target_requirements:
        return []
    decisions = ensure_equivalency_session(context, target_requirements, session_key=session_key)
    course_rows = [course for course in (courses or []) if isinstance(course, Mapping)]
    target_rows = [row for row in target_requirements.get("requirements", []) if isinstance(row, Mapping)]
    candidates = detect_equivalency_candidates(course_rows, target_requirements)

    with st.expander("🔗 課程等價／共同修課逐筆核對（第二階段）", expanded=bool(candidates or decisions)):
        st.caption("候選只是提示，不會計入學分；只有填寫核准單位與證據引用的『已核准』綁定才會重新計算目標門檻。")
        if not course_rows:
            st.info("尚未載入成績單；上傳或抓取成績後，這裡會列出可人工核對的來源修課與目標門檻。")
        else:
            missing = []
            target_section = (report or {}).get("target", {}) if isinstance((report or {}).get("target", {}), Mapping) else {}
            for key in ("basic_core_missing", "compulsory_missing", "elective_missing"):
                for row in target_section.get(key, []) or []:
                    if isinstance(row, Mapping):
                        missing.append(
                            {
                                "目標 requirement": row.get("target_requirement_id", ""),
                                "目標課程／配額": row.get("target_requirement_name", row.get("name", "")),
                                "尚缺學分": row.get("credit", 0.0),
                            }
                        )
            if missing:
                st.markdown("**目前尚缺的目標門檻**")
                st.dataframe(pd.DataFrame(missing), use_container_width=True, hide_index=True)
            else:
                st.success("目前沒有未配置的目標課程列；仍可在下方查看已記錄決策。")

            if candidates:
                st.markdown("**系統候選（不自動採認）**")
                candidate_frame = pd.DataFrame(
                    [
                        {
                            "來源修課": item.get("source_course_name", ""),
                            "來源 attempt": item.get("source_attempt_id", ""),
                            "目標 requirement": item.get("target_requirement_id", ""),
                            "目標課程": item.get("target_requirement_name", ""),
                            "狀態": _STATE_LABELS.get(item.get("state"), item.get("state", "")),
                            "說明": item.get("reason", ""),
                        }
                        for item in candidates
                    ]
                )
                st.dataframe(candidate_frame, use_container_width=True, hide_index=True)

            source_options = [source_attempt_id(course) for course in course_rows]
            source_by_id = {source_attempt_id(course): course for course in course_rows}
            target_options = [str(row.get("id") or "") for row in target_rows if row.get("id")]
            target_by_id = {str(row.get("id")): row for row in target_rows if row.get("id")}
            if source_options and target_options:
                st.markdown("**新增／更新一筆來源 → 目標綁定**")
                source_id = st.selectbox(
                    "來源修課 attempt（精確選擇）",
                    source_options,
                    format_func=lambda value: _course_label(source_by_id[value]),
                    key=f"{session_key}_source_{_stable_context_key(context, target_requirements)}",
                )
                target_id = st.selectbox(
                    "目標 requirement（精確選擇）",
                    target_options,
                    format_func=lambda value: f"{target_by_id[value].get('name', '')}｜{target_by_id[value].get('credits', 0):g} 學分｜{value}",
                    key=f"{session_key}_target_{_stable_context_key(context, target_requirements)}",
                )
                state = st.selectbox(
                    "決策狀態",
                    DECISION_STATES,
                    format_func=lambda value: _STATE_LABELS[value],
                    key=f"{session_key}_state_{_stable_context_key(context, target_requirements)}",
                )
                source = source_by_id[source_id]
                target = target_by_id[target_id]
                source_completed = max(0.0, float(source.get("completed_credit") or 0.0))
                target_credits = max(0.0, float(target.get("credits") or 0.0))
                approved_credits = st.number_input(
                    "核准配置學分（只可使用來源已得學分）",
                    min_value=0.0,
                    max_value=min(source_completed, target_credits),
                    value=min(source_completed, target_credits) if state == APPROVED else 0.0,
                    step=0.5,
                    key=f"{session_key}_credits_{_stable_context_key(context, target_requirements)}",
                )
                authority = st.text_input(
                    "核准單位／權責人（已核准必填）",
                    key=f"{session_key}_authority_{_stable_context_key(context, target_requirements)}",
                )
                evidence = st.text_input(
                    "證據引用（手冊頁／核章／文件編號；已核准必填）",
                    key=f"{session_key}_evidence_{_stable_context_key(context, target_requirements)}",
                )
                if st.button("儲存這筆決策（僅本次工作階段）", key=f"{session_key}_save", use_container_width=True):
                    decision = {
                        "source_attempt_id": source_id,
                        "source_course_name": source.get("name") or source.get("raw_name") or "",
                        "source_credit": source.get("total_credit", 0.0),
                        "target_requirement_id": target_id,
                        "target_requirement_name": target.get("name", ""),
                        "state": state,
                        "decision": state,
                        "authority": authority.strip(),
                        "evidence_reference": evidence.strip(),
                        "approved_credits": float(approved_credits),
                        "cohort": target_requirements.get("cohort", ""),
                        "target_program": target_requirements.get("program", ""),
                        "target_track": target_requirements.get("track", ""),
                        "program_type": target_requirements.get("program_type", ""),
                    }
                    _upsert_decision(decisions, decision)
                    st.success("已記錄；請重新執行審查以套用新的逐筆決策。")
                    st.rerun()

            if decisions:
                st.markdown("**本工作階段已記錄的決策**")
                decision_frame = pd.DataFrame(
                    [
                        {
                            "來源 attempt": item.get("source_attempt_id", ""),
                            "來源課程": item.get("source_course_name", ""),
                            "目標 requirement": item.get("target_requirement_id", ""),
                            "目標課程": item.get("target_requirement_name", ""),
                            "狀態": _STATE_LABELS.get(item.get("state"), item.get("state", "")),
                            "核准單位": item.get("authority", "") or "—",
                            "證據引用": item.get("evidence_reference", "") or "—",
                            "配置學分": item.get("approved_credits", 0.0),
                        }
                        for item in decisions
                    ]
                )
                st.dataframe(decision_frame, use_container_width=True, hide_index=True)
                audit_preview = audit_equivalency_decisions(
                    course_rows,
                    target_requirements,
                    decisions,
                    context=context,
                    report=report,
                    include_candidates=False,
                )
                gate = audit_preview.get("manual_gate", {})
                if gate.get("status") == "UNKNOWN":
                    st.warning("仍有未核准／無效／不明確綁定；這些列不會計入有效學分，審查結果保留 UNKNOWN。")
                elif audit_preview.get("approved_mappings"):
                    st.success(f"已通過 {len(audit_preview['approved_mappings'])} 筆逐筆驗證；重新執行後才會反映進度。")

    return decisions


# Short aliases for callers that prefer a panel/render naming convention.
render_equivalency_panel = render_equivalency_workflow
render_course_equivalency_workflow = render_equivalency_workflow

