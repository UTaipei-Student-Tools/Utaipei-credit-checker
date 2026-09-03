"""
Sidebar control panel for the UTaipei graduation credit check app.
"""

import os
from collections.abc import Mapping
from html import escape

import streamlit as st

from curriculum_registry import get_curriculum, list_curriculum_ids
from handbook_rules import (
    get_apc_target_requirements,
    get_default_handbook_year,
    get_rule_sets,
    get_rules_meta,
)
from input_confirmation import mask_student_id
from policy_audit import (
    get_primary_program_options,
    get_primary_requirements,
    normalize_primary_program,
)
from portal_scope import (
    SCHEDULE_SCOPE_KEY,
    SCHEDULE_SCOPE_MISMATCH,
    SCHEDULE_SCOPE_UNVERIFIED,
    SOURCE_PORTAL,
    TRANSCRIPT_SCOPE_KEY,
    add_warning,
    build_scope,
    build_upload_scope,
    clear_scope_state,
    get_warning_codes,
    initialize_scope_state,
    isolate_for_uploaded_transcript,
    public_scope_metadata,
    retain_or_isolate_schedule,
    scopes_match,
    set_active_schedule,
    set_pending_schedule,
    set_transcript_scope,
    verified_schedule_rows,
)
from schedule_parser import INVALID_PAGE, VALID_EMPTY, VALID_WITH_ROWS, parse_schedule_result
from scraper import (
    PortalError,
    PortalErrorCode,
    crawl_course_schedule,
    discover_portal_features,
    fetch_transcript_and_schedule,
)
from ui_components import render_landing_message

_SECONDARY_KINDS = {
    "單主修": "none",
    "輔系": "minor",
    "雙主修": "double_major",
}
_SETTINGS_SIGNATURE_FIELDS = (
    "admission_cohort",
    "primary_handbook_year",
    "primary_curriculum_id",
    "primary_program",
    "primary_track",
    "program_type",
    "secondary_kind",
    "target_curriculum_year",
    "target_curriculum_id",
    "target_program",
    "target_track",
    "application_year",
    "application_semester",
    "application_status",
    "school_approval_status",
    "formal_qualification_status",
    "formal_award_status",
    "shared_credits",
    "shared_approved",
    "shared_evidence_state",
    "interrupted",
    "cs_project_evidence",
    "cs_certification_a",
    "cs_certification_b",
    "cs_alternative_course",
)
_SECONDARY_CONFIRMATION_KEYS = (
    "application_year",
    "application_semester",
    "application_status",
    "school_approval_status",
    "formal_qualification_status",
    "formal_award_status",
    "shared_credits",
    "shared_approved",
    "shared_evidence_state",
    "target_curriculum_evidence_id",
    "target_version_evidence_id",
    "rule_applicability_evidence_id",
    "rule_evidence_id",
    "department_decision_evidence_id",
    "school_approval_evidence_id",
    "registrar_registration_evidence_id",
    "registrar_evidence_id",
    "formal_qualification_evidence_id",
    "formal_award_evidence_id",
)
_SECONDARY_SELF_REPORT_KEYS = {
    "application_year",
    "application_semester",
    "application_status",
    "school_approval_status",
    "formal_qualification_status",
    "formal_award_status",
    "shared_credits",
    "shared_approved",
    "shared_evidence_state",
}

# Settings widgets live outside a Streamlit form so dependent choices can
# rerun immediately.  Their values must nevertheless remain a draft until the
# user crosses the one explicit ``套用設定`` boundary.  Keep this dictionary
# session-local and limited to non-sensitive planning fields.
_SETTINGS_DRAFT_KEY = "_settings_draft"
_SETTINGS_DRAFT_FIELDS = tuple(
    dict.fromkeys(
        (
            "handbook_year",
            "primary_handbook_year",
            "admission_cohort",
            "primary_program",
            "primary_track",
            "primary_program_label",
            "primary_curriculum_id",
            "major_domain",
            "target_dept",
        )
        + _SETTINGS_SIGNATURE_FIELDS
        + ("interrupted", "cs_project_evidence", "cs_certification_a", "cs_certification_b", "cs_alternative_course")
    )
)


def _account_fingerprint(account):
    """Return the session-local opaque account binding for tests/adapters."""

    from portal_scope import account_fingerprint

    return account_fingerprint(st.session_state, account)


def _make_portal_scope(account, year, semester, *, verified=True, source=SOURCE_PORTAL):
    return build_scope(st.session_state, account, year, semester, source=source, verified=verified)


def _verified_schedule_rows(*, transcript_scope=None, year=None, semester=None):
    return verified_schedule_rows(st.session_state, transcript_scope, year=year, semester=semester)


def get_verified_schedule_rows(state=None, *, transcript_scope=None, year=None, semester=None):
    """Public analysis seam for scope-verified schedule rows."""

    state = st.session_state if state is None else state
    return verified_schedule_rows(state, transcript_scope, year=year, semester=semester)


def _secondary_kind(program_type):
    """Return the explicit additive role used by ``EvaluationRequest``."""

    return _SECONDARY_KINDS.get(str(program_type or "").strip(), "none")


def _settings_signature():
    """Return only non-sensitive settings that can affect a snapshot."""

    return tuple(st.session_state.get(key) for key in _SETTINGS_SIGNATURE_FIELDS)


def _ensure_settings_draft():
    """Return a session-local non-sensitive copy of the applied settings.

    The draft is deliberately separate from the canonical ``session_state``
    fields consumed by ``app.py``.  This lets Streamlit rerun on each
    dependent selectbox change without evaluating a half-complete request.
    """

    draft = st.session_state.get(_SETTINGS_DRAFT_KEY)
    if not isinstance(draft, dict):
        draft = {}
    for key in _SETTINGS_DRAFT_FIELDS:
        if key not in draft:
            draft[key] = st.session_state.get(key)
    if draft.get("program_type") not in _SECONDARY_KINDS:
        draft["program_type"] = "單主修"
    draft["secondary_kind"] = _secondary_kind(draft.get("program_type"))
    st.session_state[_SETTINGS_DRAFT_KEY] = draft
    return draft


def _clear_draft_secondary_confirmation(draft):
    """Clear self-reported secondary evidence in a draft after identity changes."""

    for key in _SECONDARY_CONFIRMATION_KEYS:
        if key in draft:
            draft[key] = None
    draft["interrupted"] = False


def _normalize_secondary_draft(
    draft,
    *,
    previous_program_type=None,
    previous_target_year=None,
    previous_target_id=None,
):
    """Keep target identity and self-reports coherent while editing a draft.

    A target year may survive a planning-type switch when the same year is
    available for the new role.  The target curriculum itself and all
    secondary confirmation fields are cleared whenever the role, year, or
    target identity changes.  This function never mutates canonical settings
    or analysis caches.
    """

    program_type = draft.get("program_type")
    if program_type not in _SECONDARY_KINDS:
        program_type = "單主修"
        draft["program_type"] = program_type
    target_kind = _target_registry_kind(program_type)
    old_kind = _target_registry_kind(previous_program_type)

    if not target_kind:
        draft["secondary_kind"] = "none"
        draft["target_curriculum_year"] = None
        draft["target_curriculum_id"] = None
        draft["target_program"] = None
        draft["target_track"] = None
        draft["target_dept"] = ""
        _clear_draft_secondary_confirmation(draft)
        return draft

    draft["secondary_kind"] = _secondary_kind(program_type)
    years = _curriculum_years(target_kind)
    target_year = draft.get("target_curriculum_year")
    target_year = str(target_year) if target_year not in (None, "", "未選擇") else None
    if target_year not in years:
        target_year = None
    draft["target_curriculum_year"] = target_year

    target_ids = list_curriculum_ids(kind=target_kind, cohort=target_year) if target_year else []
    target_id = draft.get("target_curriculum_id")
    if target_id not in target_ids:
        target_id = None
    draft["target_curriculum_id"] = target_id
    target_program, target_track, target_dept = _target_identity(target_id)
    draft["target_program"] = target_program
    draft["target_track"] = target_track
    draft["target_dept"] = target_dept

    identity_changed = (
        old_kind != target_kind
        or (str(previous_target_year) if previous_target_year else None) != target_year
        or previous_target_id != target_id
    )
    if identity_changed:
        _clear_draft_secondary_confirmation(draft)
    return draft


def _commit_settings_draft():
    """Copy one coherent settings draft to canonical session state."""

    draft = _ensure_settings_draft()
    for key in _SETTINGS_DRAFT_FIELDS:
        st.session_state[key] = draft.get(key)
    st.session_state["program_type"] = draft.get("program_type") or "單主修"
    st.session_state["secondary_kind"] = _secondary_kind(st.session_state["program_type"])
    return draft


def _invalidate_analysis_caches():
    """Invalidate the one-session snapshot/artifact cache after Apply."""

    for key, value in {
        "_decision_snapshot_cache_key": None,
        "_decision_snapshot_cache_value": None,
        "_snapshot_artifact_cache": None,
        "_exports_ready": False,
        "_analysis_exported": False,
    }.items():
        st.session_state[key] = value


def _clear_secondary_confirmation_state(preserve=None):
    """Clear stale evidence after a target identity changes.

    ``preserve`` is used only by the explicit settings commit.  It contains
    the self-reports entered in the current draft; immutable/official evidence
    identifiers are always cleared because they cannot be transferred to a
    different target curriculum.
    """

    for key in _SECONDARY_CONFIRMATION_KEYS:
        if isinstance(preserve, Mapping) and key in _SECONDARY_SELF_REPORT_KEYS:
            st.session_state[key] = preserve.get(key)
        else:
            st.session_state[key] = None
    if isinstance(preserve, Mapping):
        st.session_state["interrupted"] = bool(preserve.get("interrupted", False))
    else:
        st.session_state["interrupted"] = False


def _handle_settings_apply(before, *, preserve_secondary_self_reports=None):
    """Apply the settings boundary without carrying stale target evidence."""

    after = _settings_signature()
    if before == after:
        return False
    target_axes = ("program_type", "secondary_kind", "target_curriculum_year", "target_curriculum_id")
    before_map = dict(zip(_SETTINGS_SIGNATURE_FIELDS, before, strict=True))
    after_map = dict(zip(_SETTINGS_SIGNATURE_FIELDS, after, strict=True))
    target_changed = any(before_map.get(key) != after_map.get(key) for key in target_axes)
    if target_changed:
        _clear_secondary_confirmation_state(preserve_secondary_self_reports)
    if before_map.get("admission_cohort") != after_map.get("admission_cohort"):
        st.session_state["cohort_mismatch_confirmed"] = False
    # The current form has already materialized its old widget keys.  A new
    # version makes the next rerun read the cleared canonical values instead of
    # resurrecting a stale target approval self-report.
    st.session_state["_settings_widget_version"] = int(st.session_state.get("_settings_widget_version", 0)) + 1
    _invalidate_analysis_caches()
    return True


def _init_session_state():
    # Remove keys from the pre-confirmation/login implementation.  A browser
    # session that survives an upgrade must not retain a raw account or
    # password under those names.
    for legacy_secret_key in (
        "student_id",
        "student_pwd",
        "portal_account_input",
        "portal_password_input",
    ):
        st.session_state.pop(legacy_secret_key, None)
    if "transcript_pdf_path" not in st.session_state:
        st.session_state["transcript_pdf_path"] = None
    if "schedule_html" not in st.session_state:
        st.session_state["schedule_html"] = None
    if "transcript_pdf_bytes" not in st.session_state:
        st.session_state["transcript_pdf_bytes"] = None
    if "schedule_courses" not in st.session_state:
        st.session_state["schedule_courses"] = []
    if "source_label" not in st.session_state:
        st.session_state["source_label"] = "尚未載入"
    if "upload_key_version" not in st.session_state:
        st.session_state["upload_key_version"] = 0
    if "handbook_year" not in st.session_state:
        st.session_state["handbook_year"] = get_default_handbook_year()
    if "primary_handbook_year" not in st.session_state:
        # Migrate the old single selector once, then keep the canonical
        # primary handbook year independent from the admission cohort.
        st.session_state["primary_handbook_year"] = st.session_state["handbook_year"]
    if "admission_cohort" not in st.session_state:
        st.session_state["admission_cohort"] = st.session_state["handbook_year"]
    if "cohort_mismatch_confirmed" not in st.session_state:
        st.session_state["cohort_mismatch_confirmed"] = False
    if "target_curriculum_id" not in st.session_state:
        st.session_state["target_curriculum_id"] = None
    if "target_curriculum_year" not in st.session_state:
        st.session_state["target_curriculum_year"] = None
    if "program_type" not in st.session_state:
        st.session_state["program_type"] = "單主修"
    if "secondary_kind" not in st.session_state:
        st.session_state["secondary_kind"] = _secondary_kind(st.session_state.get("program_type", "單主修"))
    if "_settings_widget_version" not in st.session_state:
        st.session_state["_settings_widget_version"] = 0
    if "school_approval_status" not in st.session_state:
        st.session_state["school_approval_status"] = "未提供官方證據"
    if "_analysis_exported" not in st.session_state:
        st.session_state["_analysis_exported"] = False
    if "_parsed_confirmation" not in st.session_state:
        st.session_state["_parsed_confirmation"] = None
    if "schedule_error_code" not in st.session_state:
        st.session_state["schedule_error_code"] = None
    if "schedule_error_message" not in st.session_state:
        st.session_state["schedule_error_message"] = ""
    # Scope migration is intentionally fail-closed: legacy schedule rows that
    # have no verified account/term binding are quarantined before app.py can
    # read them.
    initialize_scope_state(st.session_state)
    _ensure_settings_draft()


def _build_state(rules_meta):
    """Return settings only; raw files and account identifiers stay local."""

    program_type = st.session_state.get("program_type", "單主修")
    return {
        # ``handbook_year`` remains a compatibility alias for integrations;
        # the canonical fields below are deliberately independent.
        "handbook_year": st.session_state.get(
            "primary_handbook_year", st.session_state.get("handbook_year", get_default_handbook_year())
        ),
        "primary_handbook_year": st.session_state.get(
            "primary_handbook_year", st.session_state.get("handbook_year", get_default_handbook_year())
        ),
        "admission_cohort": st.session_state.get(
            "admission_cohort", st.session_state.get("handbook_year", get_default_handbook_year())
        ),
        "rules_meta": rules_meta,
        "major_domain": st.session_state.get("major_domain", "地球環境"),
        "program_type": program_type,
        "target_dept": st.session_state.get("target_dept", "物化系化學組"),
        "primary_program": st.session_state.get("primary_program", "地生"),
        "primary_track": st.session_state.get("primary_track", "地球環境"),
        "primary_curriculum_id": st.session_state.get("primary_curriculum_id"),
        "primary_program_label": st.session_state.get("primary_program_label", "地生（地球環境）"),
        # Derive the role from the visible planning type so a migrated session
        # cannot retain a stale ``secondary_kind`` and silently change the
        # request semantics.
        "secondary_kind": _secondary_kind(program_type),
        "target_program": st.session_state.get("target_program"),
        "target_track": st.session_state.get("target_track"),
        "target_curriculum_id": st.session_state.get("target_curriculum_id"),
        "target_curriculum_year": st.session_state.get("target_curriculum_year"),
        "target_curriculum_version_candidate": st.session_state.get("target_curriculum_id"),
        "application_year": st.session_state.get("application_year"),
        "application_semester": st.session_state.get("application_semester"),
        "application_status": st.session_state.get("application_status"),
        "school_approval_status": st.session_state.get("school_approval_status"),
        # These are self-reports only.  The service receives no opaque proof
        # from them; official decisions are read back from its snapshot.
        "application_self_report": st.session_state.get("application_status"),
        "school_approval_self_report": st.session_state.get("school_approval_status"),
        "formal_qualification_status": st.session_state.get("formal_qualification_status"),
        "formal_qualification_self_report": st.session_state.get("formal_qualification_status"),
        "formal_award_status": st.session_state.get("formal_award_status"),
        "formal_award_self_report": st.session_state.get("formal_award_status"),
        "shared_credits": st.session_state.get("shared_credits"),
        "shared_approved": st.session_state.get("shared_approved"),
        "shared_evidence_state": st.session_state.get("shared_evidence_state"),
        "interrupted": bool(st.session_state.get("interrupted", False)),
        "cohort_mismatch_confirmed": bool(st.session_state.get("cohort_mismatch_confirmed", False)),
        "cs_project_evidence": st.session_state.get("cs_project_evidence"),
        "cs_certification_a": st.session_state.get("cs_certification_a"),
        "cs_certification_b": st.session_state.get("cs_certification_b"),
        "cs_alternative_course": st.session_state.get("cs_alternative_course"),
        "has_transcript": bool(st.session_state.get("transcript_pdf_bytes") or st.session_state["transcript_pdf_path"]),
        "source_label": st.session_state.get("source_label", "尚未載入"),
        "masked_student_id": st.session_state.get("masked_student_id", "••••"),
        "schedule_error_code": st.session_state.get("schedule_error_code"),
        "schedule_error_message": st.session_state.get("schedule_error_message", ""),
        "crawl_year": str(st.session_state.get("crawl_year_input", "115")),
        "crawl_semester": str(st.session_state.get("crawl_semester_input", "1")),
        "input_warning_codes": get_warning_codes(st.session_state),
        "schedule_scope_status": public_scope_metadata(st.session_state.get(SCHEDULE_SCOPE_KEY))["status"],
        "transcript_scope_status": public_scope_metadata(st.session_state.get(TRANSCRIPT_SCOPE_KEY))["status"],
        "portal_features": st.session_state.get("portal_features", None),
    }


@st.fragment
def _render_settings_fragment(draft, settings_before, *, panel_title, expanded):
    """Render progressive settings in an isolated, fast rerun fragment."""

    # Streamlit 1.57 fragments must own the containers into which they render;
    # do not call this function inside an expander created by the parent page.
    with st.expander(panel_title, expanded=expanded):
        st.caption(
            "所有必要操作都在這裡完成；手機不需要打開側欄。"
            if not expanded
            else "可在此選擇入學年度、主修、輔系／雙主修與申請資訊。"
        )
        rules_meta = _render_handbook_selector(st, draft)
        _render_rules_meta_card(rules_meta, st)
        _render_major_settings(draft.get("primary_handbook_year"), st, draft)
        st.caption("上方選項會即時更新；完成整份設定後，再按一次「套用設定」才會開始使用新的條件。")
        if st.button("套用設定", type="primary", use_container_width=True):
            draft = _commit_settings_draft()
            if _handle_settings_apply(settings_before, preserve_secondary_self_reports=draft):
                st.session_state["_settings_apply_notice"] = True
            # The fragment keeps dependent controls responsive, while Apply
            # is the one deliberate boundary that refreshes the whole page and
            # lets app.py evaluate the newly committed snapshot exactly once.
            st.rerun()
    return rules_meta


def render_setup_panel():
    """Render the one main-page setup surface and return its current state.

    The project used to put every required control in ``st.sidebar``.  That
    made the first-run flow effectively invisible on an iPhone.  All controls
    now render through the main page once per run; the optional sidebar is
    intentionally left empty so there is no second set of widget keys.
    """

    _init_session_state()
    has_transcript = bool(st.session_state.get("transcript_pdf_bytes") or st.session_state.get("transcript_pdf_path"))
    if not has_transcript:
        render_landing_message()
    panel_title = "審查設定（點開調整）" if has_transcript else "開始設定：先選手冊、主修，再載入成績"
    # Settings widgets intentionally stay inside the fragment-owned expander
    # so dependent choices rerun immediately without rendering into an
    # externally-created container.  Only its final button crosses the
    # canonical settings boundary and can invalidate analysis caches.
    settings_before = _settings_signature()
    draft = _ensure_settings_draft()
    rules_meta = _render_settings_fragment(
        draft,
        settings_before,
        panel_title=panel_title,
        expanded=not has_transcript,
    )
    if st.session_state.pop("_settings_apply_notice", False):
        st.success("設定已套用；已依新的手冊與修讀身分更新分析條件。")
    with st.expander("成績資料與校務系統（點開載入）", expanded=not has_transcript):
        st.caption("可上傳歷年成績單，或使用校務系統抓取；手機不需要打開側欄。")
        st.markdown("---")
        _render_upload_section(st)
        st.markdown("---")
        _render_login_section(st)
        st.markdown("---")
        _render_portal_discovery_section(st)

    _render_handbook_preview(
        st,
        st.session_state.get("primary_handbook_year", st.session_state.get("handbook_year")),
        st.session_state.get("primary_program", "地生"),
        st.session_state.get("primary_track"),
        st.session_state.get("program_type", "單主修"),
        st.session_state.get("target_program"),
        st.session_state.get("target_track"),
        st.session_state.get("target_curriculum_year"),
    )
    return _build_state(rules_meta)


def render_sidebar():
    """Compatibility alias for callers that still import the old name.

    It deliberately renders the same main-page panel rather than creating a
    second sidebar widget tree.
    """

    return render_setup_panel()


def _render_handbook_selector(ui=None, draft=None):
    ui = ui or st
    draft = draft if isinstance(draft, dict) else _ensure_settings_draft()
    ui.markdown("### 📚 適用學生手冊")
    # Registry IDs, rather than legacy handbook metadata, define the available
    # admission cohorts.  This keeps 111–115 visible even when a handbook PDF
    # has aggregate-only coverage and therefore cannot auto-pass.
    years = sorted(
        {
            str(get_curriculum(curriculum_id).get("version"))
            for curriculum_id in list_curriculum_ids(kind="primary")
            if get_curriculum(curriculum_id).get("version")
        },
        key=lambda value: int(value),
    )
    if not years:
        raise RuntimeError("目前沒有可用的學生手冊規則。")
    admission_current = str(draft.get("admission_cohort") or get_default_handbook_year())
    if admission_current not in years:
        admission_current = get_default_handbook_year()
    admission = ui.selectbox(
        "入學年度",
        options=years,
        index=years.index(admission_current),
        format_func=lambda year: f"{year} 學年度手冊",
        key="admission_cohort_selector",
        help="首次入學所屬學年度；它與主修適用手冊、目標課表年度及申請年度分開保存。",
    )
    primary_current = str(
        draft.get("primary_handbook_year") or draft.get("handbook_year") or get_default_handbook_year()
    )
    if primary_current not in years:
        primary_current = get_default_handbook_year()
    primary_handbook = ui.selectbox(
        "主修適用學生手冊",
        options=years,
        index=years.index(primary_current),
        format_func=lambda year: f"{year} 學年度手冊",
        key="primary_handbook_year_selector",
        help="原主修規則版本；不會因入學年度或雙主修申請年度而自動改變。",
    )
    draft["admission_cohort"] = str(admission)
    draft["primary_handbook_year"] = str(primary_handbook)
    # Legacy integrations still read handbook_year; it now means the selected
    # primary handbook only, never the admission cohort.  Keep this alias in
    # the draft until the explicit Apply boundary.
    draft["handbook_year"] = str(primary_handbook)
    return get_rules_meta(str(primary_handbook))


def _render_upload_section(ui=None):
    ui = ui or st
    ui.markdown("### 上傳成績單")
    uploaded_pdf = ui.file_uploader(
        "歷年成績單 PDF",
        type=["pdf"],
        key=f"transcript_upload_{st.session_state['upload_key_version']}",
        help="檔案只用於本次瀏覽器工作階段的學分分析，大小上限 20 MB。",
    )
    if uploaded_pdf is not None:
        data = uploaded_pdf.getvalue()
        if len(data) > 20 * 1024 * 1024:
            ui.error("PDF 超過 20 MB，請先壓縮後再上傳。")
        elif not data.startswith(b"%PDF-"):
            ui.error("檔案內容不是有效的 PDF。")
        elif data != st.session_state.get("transcript_pdf_bytes"):
            # A user-uploaded transcript has no portal account binding.  Any
            # portal schedule must therefore be isolated before the PDF is
            # accepted; otherwise rows from a previous login could be merged
            # into this unrelated source.
            isolate_for_uploaded_transcript(st.session_state)
            st.session_state["transcript_pdf_bytes"] = data
            st.session_state["transcript_pdf_path"] = None
            st.session_state["source_label"] = "自行上傳 PDF"
            set_transcript_scope(st.session_state, build_upload_scope())
            _invalidate_analysis_caches()
            ui.success("成績單已載入，可以開始審查。")

    if ui.button("清除目前資料", use_container_width=True):
        _clear_loaded_data()
        st.session_state["upload_key_version"] += 1
        st.rerun()


def _clear_loaded_data():
    temp_path = st.session_state.get("transcript_pdf_path")
    if temp_path and os.path.basename(temp_path).startswith("utaipei-transcript-"):
        try:
            os.remove(temp_path)
        except OSError:
            pass
    clear_scope_state(st.session_state)
    for key, default in {
        "transcript_pdf_path": None,
        "transcript_pdf_bytes": None,
        "source_label": "尚未載入",
        "schedule_html": None,
        "schedule_courses": [],
        "cohort_mismatch_confirmed": False,
        "_parsed_confirmation": None,
        "_source_fingerprint": None,
        "masked_student_id": "••••",
        "_decision_snapshot_cache_key": None,
        "_decision_snapshot_cache_value": None,
        "_snapshot_artifact_cache": None,
        "_exports_ready": False,
        "_analysis_exported": False,
        "schedule_error_code": None,
        "schedule_error_message": "",
    }.items():
        st.session_state[key] = default
    st.session_state.pop("cohort_mismatch_confirmation", None)


def _render_rules_meta_card(rules_meta, ui=None):
    ui = ui or st
    rules_version = escape(str(rules_meta.get("version", "N/A")))
    rules_updated = escape(str(rules_meta.get("last_updated", "N/A")))
    source_file = escape(str(rules_meta.get("evidence_file") or rules_meta.get("source_file", "未標示")))
    verification = escape(str(rules_meta.get("verification", "尚未標示")))
    ui.markdown(
        f"""
        <section class="sidebar-rules-card" aria-label="目前規則版本">
            <div class="sidebar-eyebrow">📋 目前規則版本</div>
            <div class="sidebar-rules-version">{rules_version} 學年度手冊</div>
            <div class="sidebar-meta">最後更新：{rules_updated}</div>
            <div class="sidebar-meta">來源：{source_file}</div>
            <div class="sidebar-meta">核對：{verification}</div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def _course_preview_lines(courses, limit=18):
    """Format a compact, readable course catalogue preview."""

    if not courses:
        return "尚無可顯示的逐課清單。"
    items = list(courses.items()) if isinstance(courses, dict) else list(courses)
    labels = []
    for item in items[:limit]:
        if isinstance(item, tuple):
            name, credit = item
            labels.append(f"{name}（{float(credit):g} 學分）")
        else:
            labels.append(str(item))
    suffix = f"…另有 {len(items) - limit} 門" if len(items) > limit else ""
    return "、".join(labels) + suffix


def _render_handbook_preview(
    ui,
    cohort,
    primary_program,
    primary_track,
    program_type,
    target_program,
    target_track,
    target_curriculum_year=None,
):
    """Show a native expandable preview of the selected handbook subjects."""

    cohort = str(cohort or get_default_handbook_year())
    title = f"{cohort} 學年度手冊｜科目與門檻預覽（點開查看）"
    with ui.expander(title, expanded=False):
        try:
            plan = get_primary_requirements(cohort, primary_program, primary_track)
            selected_track = plan.get("track") or primary_track
            selected_label = f"{plan.get('program', primary_program)}{f'（{selected_track}）' if selected_track else ''}"
            ui.markdown(
                f"**目前選擇：** {selected_label}"
            )
            for item in plan.get("breakdown", []):
                ui.markdown(f"- **{item.get('label', '門檻')}**：{float(item.get('required', 0.0) or 0.0):g} 學分")

            if primary_program == "地生":
                rules = get_rule_sets(cohort)
                earth = rules.get("earth_life_major", {})
                common = earth.get("common_compulsory", {})
                if common:
                    ui.markdown(
                        f"**系共同必修（{sum(float(value) for value in common.values()):g} 學分）**\n\n"
                        + _course_preview_lines(common)
                    )
                selected_domain = primary_track if primary_track in earth.get("domains", {}) else "地球環境"
                domain = earth.get("domains", {}).get(selected_domain, {})
                if domain:
                    ui.markdown(
                        f"**{selected_domain} 專業必修（{sum(float(value) for value in domain.values()):g} 學分）**\n\n"
                        + _course_preview_lines(domain)
                    )
                domain_electives = earth.get("domain_electives", {}).get(selected_domain, {})
                if domain_electives:
                    ui.markdown(
                        f"**{selected_domain} 專業選修（可選課目示例）**\n\n"
                        + _course_preview_lines(domain_electives)
                    )
            elif primary_program == "物化":
                track = "物理組" if primary_track in {"電子物理", "物理組"} else "化學組"
                target = get_apc_target_requirements(cohort, track, "雙主修" if program_type == "雙主修" else "輔系")
                ui.markdown(f"**物化系{track}基礎／核心課目**\n\n{_course_preview_lines({row['name']: row['credits'] for row in target['requirements'] if row['kind'] == 'course'})}")
                if target.get("warnings"):
                    ui.caption("；".join(target["warnings"]))
            else:
                ui.info("此系所目前以官方門檻總額規劃為主；逐課課表仍需依系所資料人工核對。")

            if program_type in {"雙主修", "輔系"} and target_program:
                target_label = "物化系" if target_program == "物化" else f"{target_program}系"
                target_role = "雙主修" if program_type == "雙主修" else "輔系"
                target_cohort = str(target_curriculum_year or cohort)
                ui.markdown(f"#### 目標{target_role}：{target_label}{f'（{target_track}）' if target_track else ''}")
                if target_program == "資科":
                    cs_rules = get_rule_sets(target_cohort).get("cs_rules", {})
                    cs = cs_rules.get("double_major" if program_type == "雙主修" else "minor", {})
                    if cs and cs.get("compulsory"):
                        ui.markdown(
                            f"**指定必修（{float(cs.get('compulsory_req', 0.0) or 0.0):g} 學分）**\n\n"
                            + _course_preview_lines(cs.get("compulsory", {}))
                        )
                    else:
                        ui.warning("此目標版本目前沒有足夠的資科逐課資料；需人工確認，不能由預覽判定通過。")
                elif target_program == "物化":
                    track = "物理組" if target_track in {"電子物理", "物理組"} else "化學組"
                    target = get_apc_target_requirements(target_cohort, track, target_role)
                    ui.markdown(f"**基礎必修（{target['base_required']:g} 學分）**\n\n" + _course_preview_lines({row['name']: row['credits'] for row in target['requirements'] if row['kind'] == 'course'}))
                else:
                    ui.caption("此目標系目前顯示已核對門檻總額；逐課清單需由系所確認。")
        except Exception:
            ui.info("目前無法載入逐課預覽；仍可依上方選定手冊進行成績單分析。")


def _program_scope_slug(program):
    return {"地生": "earth", "物化": "apc", "資科": "cs", "數學": "math"}.get(program)


def _track_scope_slug(program, track):
    return {
        ("地生", "地球環境"): "earth_environment",
        ("地生", "生命科學"): "life_science",
        ("物化", "電子物理"): "physics",
        ("物化", "物理組"): "physics",
        ("物化", "化學組"): "chemistry",
    }.get((program, track))


def _primary_registry_id(cohort, program, track):
    slug = _program_scope_slug(program)
    track_slug = _track_scope_slug(program, track)
    for curriculum_id in list_curriculum_ids(kind="primary", cohort=cohort):
        record = get_curriculum(curriculum_id)
        if record.get("program_slug") == slug and record.get("track_slug") == track_slug:
            return curriculum_id
    return None


def _curriculum_label(curriculum_id):
    try:
        record = get_curriculum(curriculum_id)
    except (KeyError, TypeError, ValueError):
        return str(curriculum_id)
    names = {"earth": "地生", "apc": "物化", "cs": "資科", "math": "數學"}
    tracks = {
        "earth_environment": "地球環境",
        "life_science": "生命科學",
        "physics": "物理組",
        "chemistry": "化學組",
    }
    program = names.get(record.get("program_slug"), str(record.get("program") or "未命名系所"))
    track = tracks.get(record.get("track_slug"))
    target_marker = {
        "double_major_target": "雙主修目標",
        "minor_target": "輔系目標",
    }.get(record.get("kind"), "主修")
    return f"{record.get('version', '未知')}｜{target_marker}｜{program}{f'（{track}）' if track else ''}"


def _curriculum_years(kind):
    """Return years backed by the selected registry role, in order."""

    years = {
        str(get_curriculum(curriculum_id).get("version"))
        for curriculum_id in list_curriculum_ids(kind=kind)
        if get_curriculum(curriculum_id).get("version")
    }
    return sorted(years, key=lambda value: int(value))


def _target_identity(curriculum_id):
    """Translate a registry ID to display identity without fuzzy matching."""

    if not curriculum_id:
        return None, None, ""
    record = get_curriculum(curriculum_id)
    program_names = {"earth": "地生", "apc": "物化", "cs": "資科", "math": "數學"}
    track_names = {
        "earth_environment": "地球環境",
        "life_science": "生命科學",
        "physics": "電子物理",
        "chemistry": "化學組",
    }
    target_program = program_names.get(record.get("program_slug"))
    target_track = track_names.get(record.get("track_slug"))
    target_dept = ""
    if target_program == "資科":
        target_dept = "資科系"
    elif target_program == "物化":
        target_dept = "物化系物理組" if target_track == "電子物理" else "物化系化學組"
    elif target_program == "地生":
        target_dept = "地生系"
    elif target_program == "數學":
        target_dept = "數學系"
    return target_program, target_track, target_dept


def _target_registry_kind(program_type):
    return {"輔系": "minor", "雙主修": "target"}.get(program_type)


def _render_major_settings(handbook_year, ui=None, draft=None):
    ui = ui or st
    draft = draft if isinstance(draft, dict) else _ensure_settings_draft()
    ui.markdown("### 主修與修讀身分")

    # Capture the previous draft context before rendering the dependent
    # widgets.  The comparison below clears only stale secondary evidence;
    # canonical settings remain untouched until the final Apply button.
    previous_program_type = draft.get("program_type")
    previous_target_year = draft.get("target_curriculum_year")
    previous_target_id = draft.get("target_curriculum_id")

    primary_handbook_year = str(draft.get("primary_handbook_year") or handbook_year or get_default_handbook_year())
    options = get_primary_program_options(primary_handbook_year) or ["地生（地球環境）"]
    current_label = draft.get("primary_program_label")
    if current_label not in options:
        current_label = options[0]
    selected_label = ui.selectbox(
        "主修系所／組別",
        options=options,
        index=options.index(current_label),
        help="主修系所依『主修適用學生手冊』判定；入學年度與目標課表年度分開設定。",
    )
    primary_program, primary_track = normalize_primary_program(selected_label, primary_handbook_year)
    draft["primary_program_label"] = selected_label
    draft["primary_program"] = primary_program
    draft["primary_track"] = primary_track
    draft["primary_handbook_year"] = primary_handbook_year
    draft["handbook_year"] = primary_handbook_year
    draft["primary_curriculum_id"] = _primary_registry_id(primary_handbook_year, primary_program, primary_track)
    draft["major_domain"] = primary_track if primary_program == "地生" else "地球環境"

    planning_options = ["單主修", "輔系", "雙主修"]
    current_program_type = draft.get("program_type")
    if current_program_type not in planning_options:
        current_program_type = "單主修"
    program_type = ui.selectbox(
        "規劃類型",
        options=planning_options,
        index=planning_options.index(current_program_type),
        help="先選修讀身分；選擇輔系或雙主修後，會立即顯示目標課表年度。",
    )
    draft["program_type"] = program_type
    draft["secondary_kind"] = _secondary_kind(program_type)

    target_kind = _target_registry_kind(program_type)
    target_years = _curriculum_years(target_kind) if target_kind else []
    target_year_options = ["未選擇", *target_years]
    current_target_year = str(draft.get("target_curriculum_year") or "未選擇")
    if current_target_year not in target_year_options:
        current_target_year = "未選擇"
    selected_target_year = ui.selectbox(
        "輔系／雙主修目標課表年度",
        options=target_year_options,
        index=target_year_options.index(current_target_year),
        format_func=lambda year: "未選擇" if year == "未選擇" else f"{year} 學年度課表",
        disabled=(program_type == "單主修"),
        help="先選目標課表年度，再顯示該年度有正式登錄的輔系／雙主修系所。",
    )
    draft["target_curriculum_year"] = (
        str(selected_target_year) if target_kind and selected_target_year != "未選擇" else None
    )

    target_ids = (
        list_curriculum_ids(kind=target_kind, cohort=draft["target_curriculum_year"])
        if target_kind and draft["target_curriculum_year"]
        else []
    )
    current_target = draft.get("target_curriculum_id")
    if current_target not in target_ids:
        current_target = None
    target_select_options = [None, *target_ids]
    selected_target = ui.selectbox(
        "輔系／雙主修目標系所／組別",
        options=target_select_options,
        index=target_select_options.index(current_target),
        format_func=lambda value: "未選擇" if value is None else _curriculum_label(value),
        disabled=(program_type == "單主修" or not draft["target_curriculum_year"]),
        help="只列出所選年度、所選修讀類型的版本；候選不等於校方核准，仍需官方證據。",
    )
    draft["target_curriculum_id"] = selected_target if target_kind else None
    _normalize_secondary_draft(
        draft,
        previous_program_type=previous_program_type,
        previous_target_year=previous_target_year,
        previous_target_id=previous_target_id,
    )

    target_program, target_track, target_dept = _target_identity(draft.get("target_curriculum_id"))
    draft["target_program"] = target_program
    draft["target_track"] = target_track
    draft["target_dept"] = target_dept
    # Streamlit otherwise reuses the previous widget state when only the
    # target options change.  A non-sensitive identity token gives secondary
    # confirmation widgets a new instance after a role/year/target switch,
    # preventing stale self-reports from reappearing in the new draft.
    secondary_context = ":".join(
        (
            str(program_type),
            str(draft.get("target_curriculum_year") or "none"),
            str(draft.get("target_curriculum_id") or "none"),
        )
    )

    def draft_select(label, key, values, *, format_func=None):
        current = draft.get(key)
        index = values.index(current) if current in values else 0
        select_kwargs = {"options": values, "index": index}
        if format_func is not None:
            select_kwargs["format_func"] = format_func
        if key in _SECONDARY_CONFIRMATION_KEYS:
            select_kwargs["key"] = f"settings_{key}_{secondary_context}"
        selected = ui.selectbox(label, **select_kwargs)
        # Preserve ``None`` as the internal unknown/unfilled state when the
        # first display option is merely the safe default.  A later explicit
        # choice is copied into the draft immediately.
        draft[key] = None if current is None and selected == values[0] else selected
        return draft[key]

    if program_type in {"輔系", "雙主修"}:
        target_role = program_type
        ui.markdown(f"#### {target_role}申請與正式資格")
        ui.caption("申請、自述核准、正式取得資格與正式授予是不同狀態；填寫自述不會直接判定通過。")
        app_year_options = ["未填寫", "111", "112", "113", "114", "115"]
        draft_select(
            "申請年度（使用者自述）",
            "application_year",
            app_year_options,
            format_func=lambda year: "未填寫" if year == "未填寫" else f"{year} 學年度",
        )
        draft_select("申請學期（使用者自述）", "application_semester", ["未填寫", "1", "2"])
        draft_select(
            "申請狀態（使用者自述，不是官方核准）",
            "application_status",
            ["未申請", "申請中", "已申請", "未通過", "不確定"],
        )
        draft_select(
            "系所／學校核准狀態（使用者自述，不是官方證據）",
            "school_approval_status",
            ["未提供官方證據", "自述已送出", "自述已核准", "不確定"],
        )
        draft_select(
            "正式取得資格（使用者自述，非校方紀錄）",
            "formal_qualification_status",
            ["未提供官方證據", "自述已取得", "自述未取得", "不確定"],
        )
        draft_select(
            "正式授予（使用者自述，非校方紀錄）",
            "formal_award_status",
            ["未提供官方證據", "自述已授予", "自述未授予", "不確定"],
        )
        if program_type == "雙主修":
            shared_state = draft_select(
                "共同修課（使用者自述；未提供官方綁定）",
                "shared_evidence_state",
                ["unanswered", "confirmed_zero", "approved"],
                format_func=lambda value: {
                    "unanswered": "未回答／不確定",
                    "confirmed_zero": "自述已確認 0 學分",
                    "approved": "自述已核准共同修課（1–6）",
                }.get(value, "未回答／不確定"),
            ) or "unanswered"
            if shared_state == "approved":
                current_shared_credits = float(draft.get("shared_credits") or 1.0)
                draft["shared_credits"] = ui.number_input(
                    "共同修課學分（自述）",
                    min_value=1.0,
                    max_value=6.0,
                    value=min(max(current_shared_credits, 1.0), 6.0),
                    step=0.5,
                    key=f"settings_shared_credits_{secondary_context}",
                )
                draft["shared_approved"] = True
            elif shared_state == "confirmed_zero":
                draft["shared_credits"] = 0.0
                draft["shared_approved"] = True
            else:
                draft["shared_credits"] = None
                draft["shared_approved"] = None
            draft["interrupted"] = ui.checkbox(
                "曾休學／中斷修業（使用者自述）",
                value=bool(draft.get("interrupted", False)),
                key=f"settings_interrupted_{secondary_context}",
            )
        else:
            draft["shared_credits"] = None
            draft["shared_approved"] = None
            draft["shared_evidence_state"] = None
            draft["interrupted"] = False
    else:
        for key in (
            "application_year",
            "application_semester",
            "application_status",
            "school_approval_status",
            "formal_qualification_status",
            "formal_award_status",
            "shared_credits",
            "shared_approved",
            "shared_evidence_state",
        ):
            draft[key] = None
        draft["interrupted"] = False

    if primary_program == "資科":
        ui.markdown("#### 資科系門檻（使用者自述）")
        cs_options = ["unknown", "completed", "incomplete"]
        draft["cs_project_evidence"] = ui.selectbox(
            "專題狀態",
            options=cs_options,
            index=cs_options.index(draft["cs_project_evidence"])
            if draft.get("cs_project_evidence") in cs_options
            else 0,
            format_func=lambda value: {
                "unknown": "不確定／需人工確認",
                "completed": "已完成",
                "incomplete": "未完成",
            }.get(value, "不確定／需人工確認"),
        )
        draft["cs_certification_a"] = ui.number_input(
            "認證 A 件數",
            min_value=0,
            max_value=20,
            value=int(draft.get("cs_certification_a") or 0),
            step=1,
        )
        draft["cs_certification_b"] = ui.number_input(
            "認證 B 件數",
            min_value=0,
            max_value=20,
            value=int(draft.get("cs_certification_b") or 0),
            step=1,
        )
        draft["cs_alternative_course"] = ui.selectbox(
            "替代課程狀態",
            options=cs_options,
            index=cs_options.index(draft["cs_alternative_course"])
            if draft.get("cs_alternative_course") in cs_options
            else 0,
            format_func=lambda value: {
                "unknown": "不確定／需人工確認",
                "completed": "已完成",
                "incomplete": "未完成",
            }.get(value, "不確定／需人工確認"),
        )


def _render_login_section(ui=None):
    """Render a single, clearing credential form on the main page.

    The password intentionally has no explicit widget key.  It is passed from
    this local form scope directly to the scraper and is never copied into
    ``st.session_state`` or the state object returned to ``app.py``.
    """

    ui = ui or st
    ui.markdown("### 校務系統（選用）")
    ui.caption("雲端出口可能被校務系統封鎖；抓取失敗時可改用上方 PDF。送出後密碼欄位會清除。")
    with ui.form("portal_credentials_form", clear_on_submit=True):
        account = ui.text_input(
            "學號 / Account",
            value="",
            placeholder="請輸入您的學號",
        )
        password = ui.text_input(
            "密碼 / Password",
            type="password",
            placeholder="僅本次送出使用，不會保存",
        )
        ui.markdown("#### 課表抓取學期設定")
        col_y, col_s = ui.columns(2)
        with col_y:
            year = ui.selectbox(
                "課表學年度",
                options=["113", "114", "115", "116"],
                index=2,
                key="crawl_year_input",
                help="只決定要抓哪一學期的課表；不會改變上方的學生手冊版本。",
            )
        with col_s:
            semester = ui.selectbox(
                "學期",
                options=["1", "2"],
                index=0,
                key="crawl_semester_input",
                help="選擇要抓取的課表學期",
            )
        scrape_clicked = ui.form_submit_button(
            "實時抓取成績＋課表",
            type="primary",
            use_container_width=True,
            help="登入並抓取歷年成績與設定學期課表",
        )
        schedule_clicked = ui.form_submit_button(
            "只更新這學期課表",
            use_container_width=True,
            help="僅登入抓取所選學期的選課課表並合併",
        )
        discover_clicked = ui.form_submit_button(
            "檢查校務功能入口",
            use_container_width=True,
            help="只確認功能入口是否可達；實際資料仍須各自查詢與驗證",
        )

    if scrape_clicked or schedule_clicked or discover_clicked:
        account = account.strip()
        # Clear keys from older widget versions even if a browser session
        # survives an upgrade.  Current form values remain local variables
        # and are cleared by ``clear_on_submit`` after this run.
        for legacy_secret_key in (
            "student_id",
            "student_pwd",
            "portal_account_input",
            "portal_password_input",
        ):
            st.session_state.pop(legacy_secret_key, None)
        if scrape_clicked:
            _attempt_live_scrape(account, password, year=year, semester=semester, ui=ui)
        elif schedule_clicked:
            _attempt_schedule_crawl(account, password, year=year, semester=semester, ui=ui)
        else:
            _discover_portal_capabilities(account, password, ui=ui)

    if st.session_state.get("schedule_courses"):
        schedule_courses = st.session_state["schedule_courses"]
        schedule_credits = sum(float(course.get("total_credit") or 0.0) for course in schedule_courses)
        ui.caption(f"已載入 {len(schedule_courses)} 門課表課程、共 {schedule_credits:g} 學分，將以修讀中納入進度條。")


def _render_portal_discovery_section(ui=None):
    """Show previously discovered portal capabilities without credentials."""

    ui = ui or st
    features = _sanitize_portal_features(st.session_state.get("portal_features"))
    st.session_state["portal_features"] = features
    if features:
        with ui.expander("已發現的校務系統功能", expanded=False):
            for item in features:
                ui.markdown(f"- **{item.get('fncid', '功能')}**：{item.get('name', '')}，狀態：`{item.get('status', '')}`")


_PORTAL_FEATURE_LABELS = {
    "AG102": "歷年成績單下載",
    "AG104": "開課選課資料查詢 / 班級課表",
    "AG107": "教學評量查詢",
    "AG108": "教學評量填答率查詢",
}


def _sanitize_portal_features(features):
    """Return only known, non-sensitive portal capability summaries."""

    if isinstance(features, (str, bytes, bytearray)):
        return ()
    try:
        items = iter(features)
    except TypeError:
        return ()

    sanitized = []
    seen = set()
    for item in items:
        if not isinstance(item, Mapping):
            continue
        fncid = item.get("fncid")
        if not isinstance(fncid, str):
            continue
        fncid = fncid.strip().upper()
        label = _PORTAL_FEATURE_LABELS.get(fncid)
        if not label or fncid in seen:
            continue
        seen.add(fncid)
        status = "入口可達" if item.get("status") == "入口可達" else "入口不可達／需重試"
        sanitized.append({"fncid": fncid, "name": label, "status": status})
    return tuple(sanitized)


def _portal_error(ui, message):
    """Display a non-sensitive portal error message."""

    if isinstance(message, PortalError):
        safe_message = f"{message}（錯誤代碼：{message.code.value}）"
    else:
        safe_message = str(message)
        if any(token.lower() in safe_message.lower() for token in ("cookie", "password", "<html", "set-cookie")):
            safe_message = "校務系統操作失敗；請改用 PDF 或稍後重試。"
    (ui or st).error(safe_message)


def _discover_portal_capabilities(account, password, ui=None):
    ui = ui or st
    account = str(account or "").strip()
    if not account or not password:
        _portal_error(ui, "⚠️ 請先填寫學號與密碼；也可以直接上傳歷年成績單 PDF。")
        return
    try:
        features = discover_portal_features(account, password)
        st.session_state["portal_features"] = _sanitize_portal_features(features)
        ui.success("已完成校務功能入口檢查；入口可達不代表查詢資料已成功。")
    except PortalError as exc:
        _portal_error(ui, exc)
    except Exception:
        _portal_error(ui, "功能探勘失敗；請確認帳號密碼，或改用 PDF 上傳。")


def _commit_transcript_result(pdf_content, account, *, year=None, semester=None):
    """Commit a validated portal transcript with an explicit scope."""

    st.session_state["transcript_pdf_path"] = None
    st.session_state["transcript_pdf_bytes"] = pdf_content
    st.session_state["source_label"] = "校務系統即時抓取"
    st.session_state["masked_student_id"] = mask_student_id(account)
    if year is not None and semester is not None:
        set_transcript_scope(
            st.session_state,
            build_scope(st.session_state, account, year, semester, source=SOURCE_PORTAL, verified=True),
        )


def _commit_schedule_result(account, year, semester, parsed_courses):
    """Commit or hold a verified schedule according to transcript provenance."""

    schedule_scope = build_scope(st.session_state, account, year, semester, source=SOURCE_PORTAL, verified=True)
    transcript_scope = st.session_state.get(TRANSCRIPT_SCOPE_KEY)
    if isinstance(transcript_scope, Mapping) and transcript_scope.get("source") == SOURCE_PORTAL:
        if not scopes_match(transcript_scope, schedule_scope):
            # A schedule-only request for another term/account is useful as a
            # private candidate, but it cannot become the active rows for the
            # currently loaded transcript.
            set_pending_schedule(st.session_state, parsed_courses, schedule_scope)
            add_warning(st.session_state, SCHEDULE_SCOPE_MISMATCH)
            return False
        # A full fetch has just verified this transcript and schedule under
        # one account/term.  Isolate any older active rows first, then commit
        # the new pair atomically.
        has_old_data = bool(
            st.session_state.get("schedule_courses")
            or st.session_state.get(SCHEDULE_SCOPE_KEY)
            or st.session_state.get("_portal_pending_schedule_courses")
            or st.session_state.get("_portal_pending_schedule_scope")
        )
        if has_old_data:
            retain_or_isolate_schedule(st.session_state, schedule_scope)
        return set_active_schedule(st.session_state, parsed_courses, schedule_scope)
    # No transcript yet: keep a private pending schedule for a later matching
    # portal transcript.  It is deliberately not active analysis input, and
    # an uploaded transcript can never auto-bind it.
    if transcript_scope is None:
        set_pending_schedule(st.session_state, parsed_courses, schedule_scope)
        return False
    set_pending_schedule(st.session_state, parsed_courses, schedule_scope)
    if isinstance(transcript_scope, Mapping):
        add_warning(st.session_state, SCHEDULE_SCOPE_UNVERIFIED)
    return False


def _schedule_error_from_result(result):
    """Turn an untrusted partial-result code into a safe PortalError."""

    raw_code = getattr(result, "schedule_error_code", None)
    if raw_code is None:
        return PortalError(PortalErrorCode.SCHEDULE_INVALID_PAGE)
    try:
        code = raw_code if isinstance(raw_code, PortalErrorCode) else PortalErrorCode(str(raw_code))
    except ValueError:
        code = PortalErrorCode.SCHEDULE_INVALID_PAGE
    return PortalError(code)


def _attempt_live_scrape(account, password, year=None, semester=None, ui=None):
    ui = ui or st
    account = str(account or "").strip()
    if not account or not password:
        _portal_error(ui, "⚠️ 請先填寫學號與密碼；也可以直接上傳歷年成績單 PDF。")
        return
    year = year or st.session_state.get("crawl_year_input", "115")
    semester = semester or st.session_state.get("crawl_semester_input", "1")
    try:
        # Keep all network results in local variables.  Login and transcript
        # failures remain all-or-nothing; a schedule failure is handled below
        # after the transcript has passed validation.
        result = fetch_transcript_and_schedule(account, password, year=year, semester=semester)
        schedule_status = getattr(result, "schedule_status", INVALID_PAGE)
        parsed_courses = list(getattr(result, "schedule_courses", ()) or ())
        pdf_content = bytes(getattr(result, "pdf_bytes", b"") or b"")
        if not pdf_content.startswith(b"%PDF-"):
            raise PortalError(PortalErrorCode.PDF_NOT_FOUND)
    except PortalError as exc:
        _portal_error(ui, exc)
        ui.warning("本次成績與課表均未套用；先前已確認資料未變更。")
        return
    except Exception:
        _portal_error(ui, "抓取失敗；請確認帳號密碼，若目前是雲端環境請改用 PDF 上傳。")
        ui.warning("本次成績與課表均未套用；先前已確認資料未變更。")
        return

    if schedule_status not in {VALID_EMPTY, VALID_WITH_ROWS}:
        # The transcript is independently verified and may be adopted.  An
        # existing schedule survives only when its account/term scope matches
        # the just-authenticated request exactly; legacy or mismatched rows are
        # quarantined by the scope boundary.
        _commit_transcript_result(pdf_content, account, year=year, semester=semester)
        retained = retain_or_isolate_schedule(
            st.session_state,
            build_scope(st.session_state, account, year, semester, source=SOURCE_PORTAL, verified=True),
        )
        schedule_error = _schedule_error_from_result(result)
        st.session_state["schedule_error_code"] = schedule_error.code.value
        st.session_state["schedule_error_message"] = schedule_error.message
        st.session_state["collapse_sidebar_flag"] = False
        _portal_error(ui, schedule_error)
        ui.success(
            "本次成績單已採用；課表仍待確認，"
            + ("同一帳號／學期的既有課表已保留。" if retained else "不相符或未驗證的既有課表已隔離。")
        )
        ui.warning(
            "課表未套用。請稍後重試「只更新這學期課表」，或改用已確認的課表資料；"
            "也可在上方成績確認表新增課程並將狀態設為「修習中」。"
            "在課表辨識成功或您完成確認前，不會把它當成合法空課表。"
        )
        return

    # Atomic commit after both independently validated results are available.
    _commit_transcript_result(pdf_content, account, year=year, semester=semester)
    st.session_state["schedule_html"] = None
    _commit_schedule_result(account, year, semester, parsed_courses)
    st.session_state["schedule_error_code"] = None
    st.session_state["schedule_error_message"] = ""
    st.session_state["collapse_sidebar_flag"] = True
    if parsed_courses:
        credits = sum(float(course.get("total_credit") or 0.0) for course in parsed_courses)
        ui.success(f"歷年成績與 {year}-{semester} 課表抓取成功：{len(parsed_courses)} 門、{credits:g} 學分。")
    else:
        ui.info(f"歷年成績抓取成功；{year}-{semester} 課表為合法空結果，未找到可納入的課程。")


def _attempt_schedule_crawl(account, password, year=None, semester=None, ui=None):
    ui = ui or st
    account = str(account or "").strip()
    if not account or not password:
        _portal_error(ui, "⚠️ 請先填寫學號與密碼；也可以直接上傳歷年成績單 PDF。")
        return
    year = year or st.session_state.get("crawl_year_input", "115")
    semester = semester or st.session_state.get("crawl_semester_input", "1")
    try:
        schedule_html = crawl_course_schedule(account, password, year=year, semester=semester)
        parsed = parse_schedule_result(schedule_html, academic_year=year, semester=semester)
        if parsed.status == INVALID_PAGE:
            raise PortalError(PortalErrorCode.SCHEDULE_INVALID_PAGE)
        parsed_courses = list(parsed.courses)
    except PortalError as exc:
        # A failed refresh cannot make an older term/account schedule current.
        # Keep it only when the existing verified scope is exactly the
        # requested one; otherwise the scope helper quarantines it.
        requested_scope = build_scope(st.session_state, account, year, semester, source=SOURCE_PORTAL, verified=True)
        has_existing_schedule = bool(
            st.session_state.get("schedule_courses")
            or st.session_state.get(SCHEDULE_SCOPE_KEY)
            or st.session_state.get("_portal_pending_schedule_courses")
            or st.session_state.get("_portal_pending_schedule_scope")
        )
        if has_existing_schedule:
            retain_or_isolate_schedule(st.session_state, requested_scope)
        _portal_error(ui, exc)
        ui.warning("本次新課表未套用；先前已確認的課表資料未變更。")
        return
    except Exception:
        _portal_error(ui, "課表抓取失敗；請確認帳號密碼，若目前是雲端環境請改用 PDF 上傳。")
        ui.warning("本次新課表未套用；先前已確認的課表資料未變更。")
        return

    # Commit only after transport and parser both identify a valid page.
    st.session_state["schedule_html"] = None
    adopted = _commit_schedule_result(account, year, semester, parsed_courses)
    st.session_state["schedule_error_code"] = None
    st.session_state["schedule_error_message"] = ""
    # A schedule-only fetch must not relabel an existing transcript.  When no
    # transcript exists yet, the newly confirmed schedule is the only source
    # for the masked identity hint and may establish it safely.
    if not (st.session_state.get("transcript_pdf_bytes") or st.session_state.get("transcript_pdf_path")):
        st.session_state["masked_student_id"] = mask_student_id(account)
    if parsed_courses and adopted:
        credits = sum(float(course.get("total_credit") or 0.0) for course in parsed_courses)
        ui.success(f"成功解析 {year}-{semester} 課表 {len(parsed_courses)} 門、{credits:g} 學分，已納入修讀中進度。")
    elif not parsed_courses and adopted:
        ui.info(f"已確認 {year}-{semester} 為合法空課表，未找到可納入的選課。")
    elif parsed_courses:
        ui.info("課表已安全保存為待用資料；目前成績來源未具備相同校務帳號綁定，尚未納入分析。")
    else:
        ui.info("課表頁面已確認為合法空結果，但目前成績來源尚未完成相同帳號綁定。")
