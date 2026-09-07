"""Streamlit two-pass UI for auditable course equivalency decisions."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

import pandas as pd
import streamlit as st

from equivalency_audit import (
    APPROVED,
    DECISION_STATES,
    PENDING,
    PROPOSED,
    REJECTED,
    audit_equivalency_decisions,
    detect_equivalency_candidates,
    source_attempt_id,
)
from snapshot_renderer import clean_student_facing_text, format_handbook_citation

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


def _course_label(course: Mapping[str, Any] | None) -> str:
    if not isinstance(course, Mapping):
        return "未命名課程｜0 學分｜已得 0 學分"
    name = course.get("name") or course.get("course_name") or course.get("raw_name") or "未命名課程"
    try:
        completed = float(course.get("earned_credits") or course.get("completed_credit") or 0.0)
    except (TypeError, ValueError):
        completed = 0.0
    try:
        total = float(course.get("credits") or course.get("total_credit") or 0.0)
    except (TypeError, ValueError):
        total = 0.0
    term = course.get("academic_term") or course.get("term") or ""
    term_info = f"｜{term}" if term else ""
    return f"{name}{term_info}｜{total:g} 學分｜已得 {completed:g} 學分"


def _format_target_requirement_label(
    target_id: Any,
    target_name: str = "",
    target_record: Mapping[str, Any] | None = None,
    default_label: str = "目標要求",
) -> str:
    """Format target requirement into clean human-readable Traditional Chinese."""
    if target_record and isinstance(target_record, Mapping):
        category = target_record.get("category") or target_record.get("requirement_type") or ""
        rname = target_record.get("name") or target_name
        if category and rname:
            return f"{category}（{rname}）"
        if category:
            return str(category)
        if rname:
            return str(rname)

    clean_name = str(target_name or "").strip()
    raw = str(target_id or "").strip()

    if not raw and clean_name:
        return clean_name
    if not raw:
        return default_label

    # Dotted requirement patterns: e.g. apc.dm.115.chemistry.calculus_1
    if raw.startswith("apc.dm.") or "apc.dm" in raw:
        parts = raw.split(".")
        scope = "雙主修" if "dm" in parts else ""
        dept = "物化系" if "apc" in parts else ""
        track = "化學組" if "chemistry" in parts else ("物理組" if "physics" in parts else "")
        cat = "必修" if any(p in parts for p in ("compulsory", "core")) else ("選修" if "elective" in parts else "")
        info = f"{scope}{dept}{f'（{track}）' if track else ''}{cat}".strip()
        if clean_name:
            return f"{info}：{clean_name}" if info else clean_name
        return info or default_label

    # Citation patterns: e.g. target:115:apc:chemistry:compulsory:chem_lab_1
    if ":" in raw:
        citation = format_handbook_citation(raw)
        if citation and citation != raw and ":" not in citation:
            if clean_name and clean_name not in citation:
                return f"{citation}（{clean_name}）"
            return citation
        # Unmapped colon pattern, uuid, custom scheme, etc.
        if clean_name:
            return f"{default_label}（{clean_name}）"
        return default_label

    # Fallback to cleaned text if it does not contain machine symbols
    cleaned = clean_student_facing_text(raw)
    if cleaned and cleaned != raw and ":" not in cleaned and not any(k in cleaned for k in ("apc.", "uuid:", "custom:")):
        if clean_name and clean_name not in cleaned:
            return f"{cleaned}（{clean_name}）"
        return cleaned

    if clean_name:
        return clean_name
    return default_label


def _build_candidate_frame(
    candidates: Sequence[Mapping[str, Any]],
    target_by_id: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    target_by_id = target_by_id or {}
    rows = []
    for idx, item in enumerate(candidates):
        if not isinstance(item, Mapping):
            continue
        target_id = str(item.get("target_requirement_id") or "")
        target_name = item.get("target_requirement_name") or ""
        target_record = target_by_id.get(target_id)
        target_label = _format_target_requirement_label(target_id, target_name, target_record)
        rows.append(
            {
                "來源修課": item.get("source_course_name") or "修課紀錄",
                "來源修課編號": f"第 {idx + 1} 門修課",
                "目標要求": target_label,
                "目標課程": target_name or target_label,
                "狀態": _STATE_LABELS.get(item.get("state"), clean_student_facing_text(item.get("state", ""))),
                "說明": clean_student_facing_text(item.get("reason", "")),
            }
        )
    return pd.DataFrame(rows)


def _build_decision_frame(
    decisions: Sequence[Mapping[str, Any]],
    target_by_id: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    target_by_id = target_by_id or {}
    rows = []
    for idx, item in enumerate(decisions):
        if not isinstance(item, Mapping):
            continue
        target_id = str(item.get("target_requirement_id") or "")
        target_name = item.get("target_requirement_name") or ""
        target_record = target_by_id.get(target_id)
        target_label = _format_target_requirement_label(target_id, target_name, target_record)
        try:
            approved_credits = float(item.get("approved_credits", 0.0) or 0.0)
        except (TypeError, ValueError):
            approved_credits = 0.0
        rows.append(
            {
                "來源修課編號": f"第 {idx + 1} 門修課",
                "來源課程": item.get("source_course_name") or "修課紀錄",
                "目標要求": target_label,
                "目標課程": target_name or target_label,
                "狀態": _STATE_LABELS.get(item.get("state"), clean_student_facing_text(item.get("state", ""))),
                "核准單位": clean_student_facing_text(item.get("authority", "") or "—"),
                "證據引用": clean_student_facing_text(item.get("evidence_reference", "") or "—"),
                "配置學分": approved_credits,
            }
        )
    return pd.DataFrame(rows)


def _build_missing_frame(missing_items: Sequence[Mapping[str, Any]]) -> pd.DataFrame:
    rows = []
    for row in missing_items:
        if not isinstance(row, Mapping):
            continue
        target_id = str(row.get("target_requirement_id") or "")
        target_name = row.get("target_requirement_name") or row.get("name") or ""
        category_hint = row.get("category") or "目標要求"
        target_label = _format_target_requirement_label(
            target_id, target_name, default_label=category_hint
        )
        try:
            credit_val = float(row.get("credit", 0.0) or 0.0)
        except (TypeError, ValueError):
            credit_val = 0.0
        rows.append(
            {
                "目標要求": target_label,
                "目標課程／配額": target_name or target_label,
                "尚缺學分": credit_val,
            }
        )
    return pd.DataFrame(rows)


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
    target_by_id = {str(row.get("id")): row for row in target_rows if row.get("id")}
    candidates = detect_equivalency_candidates(course_rows, target_requirements)

    with st.expander("🔗 課程等價／共同修課逐筆核對（第二階段）", expanded=bool(candidates or decisions)):
        st.caption("候選只是提示，不會計入學分；只有填寫核准單位與證據引用的『已核准』綁定才會重新計算目標門檻。")
        if not course_rows:
            st.info("尚未載入成績單；上傳或抓取成績後，這裡會列出可人工核對的來源修課與目標門檻。")
        else:
            raw_missing = []
            target_section = (report or {}).get("target", {}) if isinstance((report or {}).get("target", {}), Mapping) else {}
            for key, cat_label in (
                ("basic_core_missing", "基礎核心必修"),
                ("compulsory_missing", "專業必修"),
                ("elective_missing", "專業選修"),
            ):
                for row in target_section.get(key, []) or []:
                    if isinstance(row, Mapping):
                        row_dict = dict(row)
                        row_dict.setdefault("category", cat_label)
                        raw_missing.append(row_dict)
            if raw_missing:
                st.markdown("**目前尚缺的目標門檻**")
                missing_frame = _build_missing_frame(raw_missing)
                st.dataframe(missing_frame, use_container_width=True, hide_index=True)
            else:
                st.success("目前沒有未配置的目標課程列；仍可在下方查看已記錄決策。")

            if candidates:
                st.markdown("**系統候選（不自動採認）**")
                candidate_frame = _build_candidate_frame(candidates, target_by_id)
                st.dataframe(candidate_frame, use_container_width=True, hide_index=True)

            source_options = [source_attempt_id(course) for course in course_rows]
            source_by_id = {source_attempt_id(course): course for course in course_rows}
            target_options = [str(row.get("id") or "") for row in target_rows if row.get("id")]
            if source_options and target_options:
                st.markdown("**新增／更新一筆來源 → 目標綁定**")
                source_id = st.selectbox(
                    "來源修課（精確選擇）",
                    source_options,
                    format_func=lambda value: _course_label(source_by_id[value]),
                    key=f"{session_key}_source_{_stable_context_key(context, target_requirements)}",
                )
                target_id = st.selectbox(
                    "目標要求（精確選擇）",
                    target_options,
                    format_func=lambda value: f"{target_by_id[value].get('name', '')}｜{target_by_id[value].get('credits', 0):g} 學分",
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
                source_completed = max(0.0, float(source.get("earned_credits") or source.get("completed_credit") or 0.0))
                target_credits = max(0.0, float(target.get("credits") or target.get("total_credit") or 0.0))
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
                        "source_course_name": source.get("name") or source.get("course_name") or source.get("raw_name") or "",
                        "source_credit": float(source.get("credits") or source.get("total_credit") or 0.0),
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
                decision_frame = _build_decision_frame(decisions, target_by_id)
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
                    st.warning("仍有未核准／無效／不明確綁定；這些列不會計入有效學分，審查結果保留『待確認』。")
                elif audit_preview.get("approved_mappings"):
                    st.success(f"已通過 {len(audit_preview['approved_mappings'])} 筆逐筆驗證；重新執行後才會反映進度。")

    return decisions


# Short aliases for callers that prefer a panel/render naming convention.
render_equivalency_panel = render_equivalency_workflow
render_course_equivalency_workflow = render_equivalency_workflow
