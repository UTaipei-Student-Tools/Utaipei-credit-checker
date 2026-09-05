"""Public course catalog and service-boundary integration tests."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

import pytest

from curriculum_registry import get_curriculum
from graduation_service import (
    EvaluationRequest,
    _compile_attempts,
    _compile_non_credit_results,
    _compile_requirements,
    _safe_curriculum,
    evaluate,
)
from input_confirmation import NormalizedCourseRow, fingerprint_course_rows, start_confirmation
from public_course_catalog import (
    PublicCourseCatalog,
    load_public_course_catalog,
    resolve_public_evidence,
)


def _first(catalog: PublicCourseCatalog, predicate):
    return next(row for row in catalog.courses if predicate(row))


def _actual_category(row):
    return row.get("official_category")


def test_runtime_catalog_is_valid_and_contains_the_supplied_official_sets():
    catalog = load_public_course_catalog()

    assert catalog.schema == "public-course-catalog:v1"
    assert len(catalog.content_hash) == 64
    assert len(catalog.courses) == 3718
    assert len(catalog.it_memberships) == 39
    assert len(catalog.it_professional_courses) == 2
    assert catalog.covered_terms == (
        "111-1",
        "111-2",
        "112-1",
        "112-2",
        "113-1",
        "113-2",
        "114-1",
        "114-2",
        "115-1",
    )
    assert all(row.get("source_url", "").startswith("https://") for row in catalog.courses)
    assert all(Decimal(str(row["credits"])) >= 0 for row in catalog.courses)


def test_from_records_merges_professional_rows_without_hash_or_join_drift():
    professional = {
        "term": "112-1",
        "course_name": "正式資訊課程",
        "credits": 2,
        "hours": 2,
        "official_course_code": "P-001",
        "section": "01",
        "selection_code": "A1",
        "course_type": "選修",
        "class_id": "PROF",
        "official_category": "系定選修",
        "source_reference": "public-course:synthetic:professional",
        "source_url": "https://my.utaipei.edu.tw/synthetic/professional",
    }
    membership = {
        "term": "112-1",
        "course_name": "正式資訊課程",
        "credits": 2,
        "membership_id": "university_it_direct_completion",
        "catalog_matches": (professional["source_reference"],),
        "source_reference": "official-it:synthetic:1",
        "source_url": "https://genedu.utaipei.edu.tw/synthetic/it",
    }

    catalog = PublicCourseCatalog.from_records(
        (professional,),
        it_memberships=(membership,),
        it_professional_courses=(professional,),
        covered_terms=("112-1",),
    )

    assert len(catalog.courses) == 1
    evidence = resolve_public_evidence(
        {"term": "112-1", "course_name": "正式資訊課程", "credits": 2},
        catalog=catalog,
    )
    assert evidence.public_identity_state == "VERIFIED"
    assert "university_it_direct_completion" in evidence.verified_memberships


@pytest.mark.parametrize(
    "mutator",
    (
        lambda row: {**row, "source_url": "https://evil.example/course"},
        lambda row: {**row, "credits": -1},
    ),
)
def test_catalog_rejects_non_official_sources_and_negative_credits(mutator):
    base = {
        "term": "112-1",
        "course_name": "安全測試課程",
        "credits": 2,
        "official_category": "系定選修",
        "source_reference": "public-course:synthetic:1",
        "source_url": "https://my.utaipei.edu.tw/synthetic/course",
    }

    with pytest.raises(ValueError):
        PublicCourseCatalog.from_records((mutator(base),), covered_terms=("112-1",))


def test_no_id_ge_uses_exact_public_category_and_ignores_caller_membership_claims():
    catalog = load_public_course_catalog()
    row = _first(catalog, lambda item: _actual_category(item) == "國文類")

    evidence = resolve_public_evidence(
        {
            "term": row["term"],
            "course_name": row["course_name"],
            "credits": row["credits"],
            # These are caller-side claims and are deliberately ignored.
            "official_category": "體育類",
            "pool_ids": ("caller-forged-pool",),
            "source_reference": "caller-forged-source",
        },
        catalog=catalog,
    )

    assert evidence.public_identity_state == "VERIFIED"
    assert evidence.official_category == "國文類"
    assert evidence.official_category_state == "VERIFIED"
    assert "university_compulsory" in evidence.verified_memberships
    assert "university_common_excluded_from_free" in evidence.verified_memberships
    assert "university_physical_education_completion" not in evidence.verified_memberships
    assert all(item[0] != "caller-forged-pool" for item in evidence.pool_membership_evidence)
    assert evidence.candidate_source_refs


def test_lookup_is_term_bound_and_does_not_borrow_another_term():
    catalog = load_public_course_catalog()
    terms_by_code: defaultdict[str, set[str]] = defaultdict(set)
    for row in catalog.courses:
        if row.get("official_course_code"):
            terms_by_code[row["official_course_code"]].add(row["term"])
    row = next(
        item
        for item in catalog.courses
        if item.get("official_course_code")
        and len(terms_by_code[item["official_course_code"]]) == 1
    )
    other_term = next(term for term in catalog.covered_terms if term != row["term"])

    assert catalog.lookup(
        term=other_term,
        course_code=row["official_course_code"],
        credits=row["credits"],
    ) == ()
    evidence = resolve_public_evidence(
        {
            "term": other_term,
            "course_code": row["official_course_code"],
            "course_name": row["course_name"],
            "credits": row["credits"],
        },
        catalog=catalog,
    )
    assert evidence.public_identity_state == "UNKNOWN"
    assert "PUBLIC_CATALOG_NO_EXACT_MATCH" in evidence.reasons


def test_it_uses_all_candidate_proof_while_ge_category_stays_ambiguous():
    catalog = load_public_course_catalog()
    membership = next(
        item for item in catalog.it_memberships if item["source_reference"].endswith(":row20")
    )

    evidence = resolve_public_evidence(
        {
            "term": membership["term"],
            "course_name": membership["course_name"],
            "credits": membership["credits"],
        },
        catalog=catalog,
    )

    assert evidence.public_identity_state == "VERIFIED"
    assert evidence.official_category_state == "CONFLICTED"
    assert "university_it_direct_completion" in evidence.verified_memberships
    assert "ge_common_elective" in evidence.uncertain_memberships
    assert len(evidence.candidate_source_refs) == 2
    assert all(
        item[0] == "university_it_direct_completion" and item[1] == "VERIFIED"
        for item in evidence.pool_membership_evidence
        if item[3] == "public_catalog"
    )


def test_public_science_and_department_properties_require_official_all_candidate_proof():
    catalog = load_public_course_catalog()
    candidates = ()
    row = None
    for item in catalog.courses:
        if item.get("college") != "理學院" or not item.get("department_unit"):
            continue
        current = catalog.lookup(
            term=item["term"],
            course_name=item["course_name"],
            credits=item["credits"],
        )
        departments = {candidate.get("department_unit") for candidate in current}
        if current and len(departments) == 1 and all(candidate.get("college") == "理學院" for candidate in current):
            row, candidates = item, current
            break
    assert row is not None
    assert candidates

    evidence = resolve_public_evidence(
        {"term": row["term"], "course_name": row["course_name"], "credits": row["credits"]},
        catalog=catalog,
    )

    assert evidence.official_college == "理學院"
    assert evidence.official_college_state == "VERIFIED"
    assert evidence.department_membership_state == "VERIFIED"
    assert evidence.department_membership == f"official_department:{row['department_unit']}"
    assert "science_college" in evidence.verified_memberships


def test_pe_activity_is_code_based_and_english_roman_three_is_not_pe():
    catalog = load_public_course_catalog()
    pe_by_code: defaultdict[str, set[str]] = defaultdict(set)
    for row in catalog.courses:
        if row.get("official_category") == "體育類" and row.get("official_course_code"):
            pe_by_code[row["official_course_code"]].add(row["term"])
    code, terms = next((code, terms) for code, terms in pe_by_code.items() if len(terms) >= 2)
    first_term, second_term = sorted(terms)[:2]
    first = next(
        row for row in catalog.courses
        if row.get("official_category") == "體育類"
        and row.get("official_course_code") == code
        and row.get("term") == first_term
    )
    second = next(
        row for row in catalog.courses
        if row.get("official_category") == "體育類"
        and row.get("official_course_code") == code
        and row.get("term") == second_term
    )
    first_evidence = resolve_public_evidence(
        {"term": first["term"], "course_name": first["course_name"], "credits": first["credits"]},
        catalog=catalog,
    )
    second_evidence = resolve_public_evidence(
        {"term": second["term"], "course_name": second["course_name"], "credits": second["credits"]},
        catalog=catalog,
    )
    assert first_evidence.pe_activity_id == second_evidence.pe_activity_id == f"pe:{code}"
    assert "university_physical_education_completion" in first_evidence.verified_memberships

    english = next(
        row for row in catalog.courses
        if row.get("official_category") == "英文類" and "體育" in row.get("course_name", "")
    )
    english_evidence = resolve_public_evidence(
        {"term": english["term"], "course_name": english["course_name"], "credits": english["credits"]},
        catalog=catalog,
    )
    assert "university_compulsory" in english_evidence.verified_memberships
    assert "university_physical_education_completion" not in english_evidence.verified_memberships
    assert english_evidence.pe_activity_id == ""


def test_compile_attempts_uses_public_it_membership_for_no_id_rows_without_adding_credits():
    catalog = load_public_course_catalog()
    membership = next(
        item for item in catalog.it_memberships if item["source_reference"].endswith(":row20")
    )
    row = NormalizedCourseRow(
        course_code="",
        course_name=membership["course_name"],
        credits=float(membership["credits"]),
        earned_credits=float(membership["credits"]),
        status="COMPLETED",
        term=membership["term"],
        course_type="",
    )
    attempts, safe_rows = _compile_attempts((row,), {})

    assert len(attempts) == 1
    attempt = attempts[0]
    assert attempt.identity_status == "UNKNOWN"
    assert any(
        item[0] == "university_it_direct_completion"
        and item[1] == "VERIFIED"
        and item[3] == "public_catalog"
        for item in attempt.pool_membership_evidence
    )
    public_projection = safe_rows[attempt.attempt_id]["public_catalog"]
    assert public_projection["candidate_source_refs"]
    assert "university_it_direct_completion" in public_projection["verified_memberships"]

    requirement = {
        "requirement_id": "it-public-no-id",
        "name": "資訊應用與設計",
        "kind": "OFFICIAL_LISTED_COURSE_COMPLETION",
        "requirement_type": "non_credit",
        "credits": 0,
        "required_completions": 1,
        "min_earned_credits_per_completion": 2,
        "membership_id": "university_it_direct_completion",
        "evidence_state": "VERIFIED",
        "coverage_state": "COMPLETE",
        "automatic_decision": True,
        "scope_state": "VERIFIED",
        # The public IT list is term-bound, but the GE offering does not
        # inherit the student's program/track/version identity dimensions.
        "curriculum_version": "112",
        "program_slug": "earth",
        "track_slug": "department",
        "term_bound": "VERIFIED",
        "membership_version_required": False,
        "membership_program_required": False,
        "membership_track_required": False,
    }
    result = _compile_non_credit_results(
        {"non_credit_requirements": (requirement,)}, attempts, scope="primary"
    )[0]
    assert result.status == "PASS"
    assert result.affects_credit_ledger is False
    assert attempt.earned_credits == Decimal("2")


def test_compile_attempts_matches_equivalent_decimal_credit_scales_for_no_code_identity():
    record = {
        "curriculum_id": "primary:test:decimal-scale",
        "version": "112",
        "curriculum_version": "112",
        "program_slug": "earth",
        "track_slug": "earth_environment",
        "evidence_state": "VERIFIED",
        "coverage_state": "COMPLETE",
        "course_catalog": (
            {
                "id": "earth:decimal-scale-course",
                "name": "精確學分課程",
                "credits": 2.0,
                "course_code": "DEC-002",
                "component_type": "lecture",
                "requirement_type": "named_course",
                "evidence_state": "VERIFIED",
                "coverage_state": "COMPLETE",
            },
        ),
    }
    safe_record = _safe_curriculum(record)
    assert safe_record is not None
    _requirements, metadata, _provenance = _compile_requirements(safe_record, scope="primary")
    row = NormalizedCourseRow(
        course_code="",
        course_name="精確學分課程",
        credits=2,
        earned_credits=2,
        status="COMPLETED",
        term="112-1",
        course_type="",
    )

    attempts, _safe_rows = _compile_attempts((row,), metadata)

    assert len(attempts) == 1
    assert attempts[0].identity_status == "VERIFIED"
    assert attempts[0].course_id == "DEC-002"
    assert attempts[0].course_kind == "LECTURE"


def test_real_earth111_public_ge_category_never_aliases_department_or_free_pools():
    """Public GE classification must use the actual registry GE policy pool."""

    catalog = load_public_course_catalog()
    record = _safe_curriculum(get_curriculum("primary:111:earth:earth_environment"))
    assert record is not None
    _requirements, metadata, _provenance = _compile_requirements(record, scope="primary")
    rows = tuple(
        NormalizedCourseRow(
            course_code="",
            course_name=name,
            credits=2,
            earned_credits=2,
            status="COMPLETED",
            term="111-1",
            # The official transcript shape may omit course_type.  Public
            # category evidence must still classify the row correctly.
            course_type="",
        )
        for name in ("西班牙語(一)", "日語(一)")
        if any(
            item.get("term") == "111-1"
            and item.get("course_name") == name
            and item.get("credits") == 2
            and item.get("active", True) is not False
            for item in catalog.courses
        )
    )
    assert {row.course_name for row in rows} == {"西班牙語(一)", "日語(一)"}

    attempts, safe_rows = _compile_attempts(rows, metadata)
    earth_common_pool = "pool:primary:111:earth:earth_environment:common_elective"
    earth_ge_pool = "pool:primary:111:earth:earth_environment:ge_common_elective"
    earth_free_pool = "pool:primary:111:earth:earth_environment:free_elective"
    for attempt in attempts:
        verified = {
            item[0]
            for item in attempt.pool_membership_evidence
            if item[1] == "VERIFIED"
        }
        assert "ge_common_elective" in verified
        assert earth_ge_pool in verified
        assert "university_common_excluded_from_free" in verified
        assert earth_common_pool not in verified
        assert earth_free_pool not in verified
        public_evidence = safe_rows[attempt.attempt_id]["public_catalog"]
        assert earth_common_pool not in {
            item[0]
            for item in public_evidence["pool_membership_evidence"]
            if item[1] == "VERIFIED"
        }


def test_compile_requirements_preserves_server_max_and_ignores_caller_cap():
    record = {
        "curriculum_id": "target:test:max-cap",
        "curriculum_version": "115",
        "program_slug": "math",
        "track_slug": "department",
        "evidence_state": "VERIFIED",
        "coverage_state": "COMPLETE",
        "course_catalog": (
            {
                "requirement_id": "math-secondary-elective",
                "name": "數學次修選修額度",
                "credits": 3,
                "max_credits": 8,
                # This is a request-shaped forgery and is not in the safe
                # registry row schema.
                "credit_cap": 1,
                "requirement_type": "course_pool",
                "eligible_pool_ids": ("math-secondary",),
                "evidence_state": "VERIFIED",
                "coverage_state": "COMPLETE",
            },
            {
                "requirement_id": "default-cap",
                "name": "沒有上限的額度",
                "credits": 3,
                "credit_cap": 40,
                "requirement_type": "course_pool",
                "eligible_pool_ids": ("default-pool",),
                "evidence_state": "VERIFIED",
                "coverage_state": "COMPLETE",
            },
        ),
    }
    safe_record = _safe_curriculum(record)
    assert safe_record is not None
    assert "credit_cap" not in safe_record["course_catalog"][0]
    _requirements, metadata, _provenance = _compile_requirements(safe_record, scope="target")

    assert metadata["target:target:test:max-cap:math-secondary-elective"]["max_credits"] == Decimal("8")
    assert metadata["target:target:test:max-cap:default-cap"]["max_credits"] == Decimal("3")
    specs_by_id = {item.requirement_id: item for item in _requirements}
    assert specs_by_id["target:target:test:max-cap:math-secondary-elective"].max_credits == Decimal("8")
    assert specs_by_id["target:target:test:max-cap:default-cap"].max_credits == Decimal("3")


def test_public_zero_series_joins_only_safe_term_bound_descriptor():
    catalog = load_public_course_catalog()
    safe_record = _safe_curriculum(get_curriculum("primary:112:earth:earth_environment"))
    assert safe_record is not None
    life = next(
        item
        for item in safe_record["non_credit_requirements"]
        if item.get("membership_id", "").startswith("university_primary_life_guidance:")
    )
    public_row = next(
        item
        for item in catalog.courses
        if item.get("term") == "112-1"
        and item.get("official_course_code") == "28030"
        and item.get("credits") == 0
        and item.get("course_name") == life["eligible_course_names"][0]
    )

    evidence = resolve_public_evidence(
        {
            "term": public_row["term"],
            "course_name": public_row["course_name"],
            "credits": public_row["credits"],
        },
        catalog=catalog,
        handbook_metadata=(life,),
    )

    assert life["membership_id"] in evidence.verified_memberships
    assert any(
        item[0] == life["membership_id"]
        and item[1] == "VERIFIED"
        and item[3] == "public_catalog"
        for item in evidence.pool_membership_evidence
    )

    without_descriptor = resolve_public_evidence(
        {
            "term": public_row["term"],
            "course_name": public_row["course_name"],
            "credits": public_row["credits"],
        },
        catalog=catalog,
    )
    assert life["membership_id"] not in without_descriptor.verified_memberships


def test_compile_attempts_wires_safe_zero_series_metadata_to_public_evidence():
    catalog = load_public_course_catalog()
    safe_record = _safe_curriculum(get_curriculum("primary:112:earth:earth_environment"))
    assert safe_record is not None
    life = next(
        item
        for item in safe_record["non_credit_requirements"]
        if item.get("membership_id", "").startswith("university_primary_life_guidance:")
    )
    public_row = next(
        item
        for item in catalog.courses
        if item.get("term") == "112-1"
        and item.get("official_course_code") == "28030"
        and item.get("credits") == 0
        and item.get("course_name") == life["eligible_course_names"][0]
    )
    row = NormalizedCourseRow(
        course_code="",
        course_name=public_row["course_name"],
        credits=0,
        earned_credits=0,
        status="COMPLETED",
        term=public_row["term"],
        course_type="",
    )

    attempts, _safe_rows = _compile_attempts(
        (row,),
        {},
        completion_metadata=(life,),
    )

    assert attempts[0].identity_status == "VERIFIED"
    assert attempts[0].course_id == "28030"
    assert any(
        item[0] == life["membership_id"]
        and item[1] == "VERIFIED"
        and item[3] == "public_catalog"
        for item in attempts[0].pool_membership_evidence
    )


def test_compile_earth_ge_pool_unknown_component_is_unrestricted_but_named_lab_stays_strict():
    record = _safe_curriculum(get_curriculum("primary:112:earth:earth_environment"))
    assert record is not None
    specs, _metadata, _provenance = _compile_requirements(record, scope="primary")

    ge_specs = [item for item in specs if ".pool.ge_" in item.requirement_id]
    assert ge_specs
    # Aggregate GE rows carry the registry's UNKNOWN marker because they do
    # not constrain lecture/lab.  The marker must not reject lecture rows.
    assert all(item.allowed_course_kinds == () for item in ge_specs)

    lab_record = {
        "curriculum_id": "primary:test:named-lab",
        "curriculum_version": "112",
        "program_slug": "earth",
        "track_slug": "earth_environment",
        "evidence_state": "VERIFIED",
        "coverage_state": "COMPLETE",
        "course_catalog": (
            {
                "requirement_id": "named-lab",
                "name": "實驗課",
                "credits": 1,
                "requirement_type": "named_course",
                "component_type": "lab",
                "evidence_state": "VERIFIED",
                "coverage_state": "COMPLETE",
            },
        ),
    }
    lab_specs, _metadata, _provenance = _compile_requirements(lab_record, scope="primary")
    assert len(lab_specs) == 1
    assert lab_specs[0].allowed_course_kinds == ("LAB",)


def test_official_completion_require_zero_credits_rejects_positive_credit_attempt():
    row = NormalizedCourseRow(
        course_code="",
        course_name="行政門檻課程",
        credits=2,
        earned_credits=2,
        status="COMPLETED",
        term="112-1",
        course_type="",
    )
    attempts, _safe_rows = _compile_attempts((row,), {})
    requirement = {
        "requirement_id": "life-zero-only",
        "name": "生活教育門檻",
        "kind": "OFFICIAL_LISTED_COURSE_COMPLETION",
        "requirement_type": "non_credit",
        "credits": 0,
        "required_completions": 1,
        "require_zero_credits": True,
        "membership_id": "university_life_completion",
        "evidence_state": "VERIFIED",
        "coverage_state": "COMPLETE",
        "automatic_decision": True,
        "scope_state": "VERIFIED",
    }
    safe_record = _safe_curriculum({
        "curriculum_id": "primary:test:zero-only",
        "evidence_state": "VERIFIED",
        "coverage_state": "COMPLETE",
        "non_credit_requirements": (requirement,),
    })
    assert safe_record is not None
    assert safe_record["non_credit_requirements"][0]["require_zero_credits"] is True

    result = _compile_non_credit_results(
        {"non_credit_requirements": (requirement,)}, attempts, scope="primary"
    )[0]

    assert result.status == "FAIL"
    assert result.completed_count == 0
    assert result.matched_attempt_ids == ()


def test_formal_evaluate_accepts_ge_lecture_and_unknown_component_rows(monkeypatch):
    catalog = load_public_course_catalog()
    candidates = [
        item
        for item in catalog.courses
        if item.get("term") == "112-1"
        and item.get("official_category") == "藝術與美感領域"
        and item.get("credits") == 2
        and "(停開)" not in item.get("course_name", "")
    ]
    assert len(candidates) >= 2

    raw_record = {
        "curriculum_id": "primary:test:ge-unknown-component",
        "kind": "primary",
        "version": "112",
        "curriculum_version": "112",
        "program_slug": "earth",
        "track_slug": "earth_environment",
        "evidence_state": "VERIFIED",
        "coverage_state": "COMPLETE",
        "course_pools": (
            {
                "pool_id": "pool:ge_art",
                "bucket": "ge_藝術與美感領域",
                "selection_rule": "official_category_policy",
                "evidence_state": "VERIFIED",
                "coverage_state": "COMPLETE",
                "policy": {
                    "policy_id": "policy:ge-art:112",
                    "revision": "112.1",
                    "source_reference": "official:ge-art:112",
                    "evidence_state": "VERIFIED",
                    "coverage_state": "COMPLETE",
                    "automatic_decision": True,
                    "scope_state": "VERIFIED",
                    "applies_to": {
                        "curriculum_versions": ("112",),
                        "program_slugs": ("earth",),
                        "track_slugs": ("earth_environment",),
                        "roles": ("primary",),
                    },
                    "predicate": {
                        "kind": "official_category_membership",
                        "category": "藝術與美感領域",
                        "minimum_credits": 2,
                    },
                },
            },
        ),
        "course_catalog": (
            {
                "requirement_id": "ge-art-credit",
                "name": "藝術領域額度",
                "credits": 2,
                "bucket": "ge_藝術與美感領域",
                "component_type": "UNKNOWN",
                "requirement_type": "course_pool",
                "eligible_pool_ids": ("pool:ge_art",),
                "evidence_state": "VERIFIED",
                "coverage_state": "COMPLETE",
            },
        ),
    }
    safe_record = _safe_curriculum(raw_record)
    assert safe_record is not None
    debug_specs, debug_meta, _debug_provenance = _compile_requirements(safe_record, scope="primary")

    rows = tuple(
        NormalizedCourseRow(
            course_code="",
            course_name=item["course_name"],
            credits=2,
            earned_credits=2,
            status="COMPLETED",
            term="112-1",
            course_type="lecture" if index == 0 else "",
        )
        for index, item in enumerate(candidates[:2])
    )
    monkeypatch.setattr("graduation_service.get_curriculum", lambda _curriculum_id: raw_record)
    monkeypatch.setattr(
        "graduation_service.resolve_rule_context",
        lambda _request, *, evidence_resolver=None: _resolved_context(safe_record),
    )
    request = EvaluationRequest(
        admission_cohort="112",
        primary_curriculum_id=raw_record["curriculum_id"],
        confirmed_course_rows=rows,
        confirmed_course_fingerprint=fingerprint_course_rows(rows),
        transcript_confirmed=True,
        confirmation_state="CONFIRMED",
    )

    snapshot = evaluate(request)

    assert snapshot.verdict == "PASS"
    assert snapshot.allocation.status == "PASS"
    assert snapshot.allocation.credit_conservation is True
    assert snapshot.requirements[0].allowed_course_kinds == ()
    assert any(
        item[0] == "pool:ge_art"
        and item[1] == "VERIFIED"
        and item[3] == "public_catalog"
        for attempt in snapshot.attempts
        for item in attempt.pool_membership_evidence
    )


def _resolved_context(record):
    return {
        "status": "RESOLVED",
        "state": "RESOLVED",
        "can_pass": True,
        "primary_curriculum": record,
        "dimensions": {
            "primary_curriculum": {
                "status": "RESOLVED",
                "state": "RESOLVED",
                "curriculum": record,
            },
            "target_curriculum_version": {"status": "NOT_APPLICABLE", "state": "NOT_APPLICABLE"},
        },
        "blocker_codes": (),
        "warnings": (),
    }


def test_formal_evaluate_uses_waiver_authority_after_safe_curriculum(monkeypatch):
    raw_record = {
        "curriculum_id": "primary:test:waiver-safe",
        "version": "112",
        "curriculum_version": "112",
        "program_slug": "earth",
        "track_slug": "department",
        "evidence_state": "VERIFIED",
        "coverage_state": "COMPLETE",
        "non_credit_requirements": (
            {
                "requirement_id": "it-direct",
                "name": "資訊應用與設計",
                "kind": "OFFICIAL_LISTED_COURSE_COMPLETION",
                "requirement_type": "non_credit",
                "credits": 0,
                "required_completions": 1,
                "membership_id": "university_it_direct_completion",
                "waiver_allowed": True,
                "waiver_authority_ids": ("official:genedu",),
                "waiver_requirement_version": "112",
                "waiver_program_slug": "earth",
                "waiver_track_slug": "department",
                "evidence_state": "VERIFIED",
                "coverage_state": "COMPLETE",
                "automatic_decision": True,
                "scope_state": "VERIFIED",
            },
        ),
    }
    safe_record = _safe_curriculum(raw_record)
    assert safe_record is not None
    safe_requirement = safe_record["non_credit_requirements"][0]
    assert safe_requirement["waiver_authority_ids"] == ("official:genedu",)
    assert safe_requirement["waiver_requirement_version"] == "112"
    assert safe_requirement["waiver_track_slug"] == "department"

    monkeypatch.setattr("graduation_service.get_curriculum", lambda _curriculum_id: raw_record)
    monkeypatch.setattr(
        "graduation_service.resolve_rule_context",
        lambda _request, *, evidence_resolver=None: _resolved_context(safe_record),
    )
    confirmation = start_confirmation([])
    assert confirmation.valid
    request = EvaluationRequest(
        admission_cohort="112",
        primary_curriculum_id=raw_record["curriculum_id"],
        confirmed_course_rows=confirmation.rows,
        confirmed_course_fingerprint=fingerprint_course_rows(confirmation.rows),
        transcript_confirmed=True,
        confirmation_state="CONFIRMED",
        subject_ref="subject:test",
        official_evidence_ids=("waiver-it-112",),
    )

    snapshot = evaluate(
        request,
        evidence_resolver=lambda evidence_id: {
            "record_id": evidence_id,
            "record_type": "NON_CREDIT_WAIVER_RECORD",
            "requirement_id": "it-direct",
            "decision": "APPROVED",
            "evidence_state": "VERIFIED",
            "authority": "official:genedu",
            "evidence_reference": "official:waiver-it-112",
            "subject_ref": "subject:test",
            "requirement_version": "112",
            "program_slug": "earth",
            "track_slug": "department",
        },
    )

    result = next(item for item in snapshot.non_credit_results if item["requirement_id"] == "it-direct")
    assert result["status"] == "PASS"
    assert result["waived"] is True
    assert result["affects_credit_ledger"] is False


def test_formal_evaluate_preserves_trusted_not_member_after_compile(monkeypatch):
    raw_record = {
        "curriculum_id": "primary:test:not-member",
        "version": "115",
        "curriculum_version": "115",
        "program_slug": "earth",
        "track_slug": "earth_environment",
        "evidence_state": "VERIFIED",
        "coverage_state": "COMPLETE",
        "course_pools": (
            {
                "pool_id": "science-pool",
                "selection_rule": "exact_title_credit_component",
                "evidence_state": "VERIFIED",
                "pool_membership_evidence": (
                    ("science_college", "NOT_MEMBER", "official:science-negative", "registry_negative"),
                ),
                "candidate_courses": (
                    {
                        "course_id": "synthetic-science",
                        "name": "合成科學課程",
                        "credits": 3,
                        "component_type": "lecture",
                        "evidence_state": "VERIFIED",
                    },
                ),
            },
        ),
        "course_catalog": (
            {
                "id": "science-required",
                "name": "合成科學課程",
                "course_code": "synthetic-science",
                "official_course_identity": "synthetic-science",
                "credits": 3,
                "requirement_type": "named_course",
                "component_type": "lecture",
                "evidence_state": "VERIFIED",
                "coverage_state": "COMPLETE",
            },
        ),
    }
    safe_record = _safe_curriculum(raw_record)
    assert safe_record is not None
    safe_pool = safe_record["course_pools"][0]
    assert safe_pool["pool_membership_evidence"] == (
        ("science_college", "NOT_MEMBER", "official:science-negative", "registry_negative"),
    )

    monkeypatch.setattr("graduation_service.get_curriculum", lambda _curriculum_id: raw_record)
    monkeypatch.setattr(
        "graduation_service.resolve_rule_context",
        lambda _request, *, evidence_resolver=None: _resolved_context(safe_record),
    )
    row = NormalizedCourseRow(
        course_code="synthetic-science",
        course_name="合成科學課程",
        credits=3,
        earned_credits=3,
        status="COMPLETED",
        term="115-1",
        course_type="lecture",
    )
    request = EvaluationRequest(
        admission_cohort="115",
        primary_curriculum_id=raw_record["curriculum_id"],
        confirmed_course_rows=(row,),
        confirmed_course_fingerprint=fingerprint_course_rows((row,)),
        transcript_confirmed=True,
        confirmation_state="CONFIRMED",
    )

    snapshot = evaluate(request)

    attempt = snapshot.attempts[0]
    assert snapshot.allocation.credit_conservation is True
    assert snapshot.allocation.status == "PASS"
    assert any(
        item[0] == "science_college"
        and item[1] == "NOT_MEMBER"
        and item[2] == "official:science-negative"
        and item[3] == "registry_negative"
        for item in attempt.pool_membership_evidence
    )
    assert any(
        item[0] == "science_college"
        and item[1] == "NOT_MEMBER"
        for item in snapshot.curriculum["primary"]["course_pools"][0]["pool_membership_evidence"]
    )


def _math_public_catalog(*rows):
    return PublicCourseCatalog.from_records(rows, covered_terms=tuple(sorted({row["term"] for row in rows})))


def _math_catalog_row(*, term="112-2", name="C語言程式設計", credits=3, department="9200", category="系定必修", code="M-C"):
    return {
        "term": term,
        "course_name": name,
        "credits": credits,
        "hours": credits,
        "official_course_code": code,
        "section": "01",
        "official_category": category,
        "department_unit": department,
        "college": "理學院",
        "source_reference": f"public-course:math:{term}:{code}:{department}",
        "source_url": "https://my.utaipei.edu.tw/synthetic/math",
    }


def _math_primary_metadata(*, cohort="112", name="C語言程式設計", course_id="112:math:department:c"):
    return {
        "scope": "primary",
        "program_slug": "math",
        "curriculum_version": cohort,
        "course_name": name,
        "credits": 3,
        "course_id": course_id,
        "official_course_identity": course_id,
        "course_kind": "LECTURE",
        "bucket": "math_common_compulsory",
        "evidence_state": "VERIFIED",
        "coverage_state": "COMPLETE",
        "source_reference": f"handbook:{cohort}:math:primary:{name}",
    }


def _math_secondary_metadata(*, cohort="111", name="線性代數(一)", course_id="111:math:secondary:linear-1", **extra):
    return {
        "scope": "target",
        "program_slug": "math",
        "curriculum_version": cohort,
        "course_name": name,
        "credits": 3,
        "course_id": course_id,
        "official_course_identity": course_id,
        "course_kind": "LECTURE",
        "evidence_state": "VERIFIED",
        "coverage_state": "COMPLETE",
        "source_reference": f"handbook:{cohort}:math:secondary:{name}",
        **extra,
    }


def test_math_primary_approved_it_path_is_cohort_and_offering_scoped():
    catalog = _math_public_catalog(_math_catalog_row())
    evidence = resolve_public_evidence(
        {"term": "112-2", "course_name": "C語言程式設計", "credits": Decimal("3.0")},
        catalog=catalog,
        handbook_metadata=(_math_primary_metadata(),),
        program_slug="math",
    )

    assert "university_it_direct_completion" in evidence.verified_memberships
    assert any(
        item[0].startswith("PROGRAM_APPROVED_COURSE_EXEMPTION:")
        and item[1] == "VERIFIED"
        for item in evidence.pool_membership_evidence
    )

    wrong_cohort = resolve_public_evidence(
        {"term": "112-2", "course_name": "C語言程式設計", "credits": 3},
        catalog=catalog,
        handbook_metadata=(_math_primary_metadata(cohort="114", name="Python程式設計", course_id="114:math:python"),),
        program_slug="math",
    )
    assert "university_it_direct_completion" not in wrong_cohort.verified_memberships
    assert not any(
        item[0].startswith("PROGRAM_APPROVED_COURSE_EXEMPTION:")
        for item in wrong_cohort.pool_membership_evidence
    )


def test_math_primary_approved_it_path_rejects_other_department_and_elective_claims():
    catalog = _math_public_catalog(
        _math_catalog_row(department="9100", code="OTHER-C"),
    )
    evidence = resolve_public_evidence(
        {"term": "112-2", "course_name": "C語言程式設計", "credits": 3},
        catalog=catalog,
        handbook_metadata=(_math_primary_metadata(),),
        program_slug="math",
    )
    assert "university_it_direct_completion" not in evidence.verified_memberships
    assert not any(
        item[0].startswith("PROGRAM_APPROVED_COURSE_EXEMPTION:")
        for item in evidence.pool_membership_evidence
    )


def test_external_professional_membership_requires_official_department_property():
    math_evidence = resolve_public_evidence(
        {"term": "112-2", "course_name": "C語言程式設計", "credits": 3},
        catalog=_math_public_catalog(_math_catalog_row()),
    )
    assert any(
        item[0] == "external_department_or_school_professional"
        and item[1] == "NOT_MEMBER"
        and item[3] == "public_catalog_negative"
        for item in math_evidence.pool_membership_evidence
    )

    external = _math_catalog_row(
        name="外系專業課程",
        code="EXT-1",
        department="9100",
        category="系定選修",
    )
    external_evidence = resolve_public_evidence(
        {"term": "112-2", "course_name": "外系專業課程", "credits": 3},
        catalog=_math_public_catalog(external),
    )
    assert "external_department_or_school_professional" in external_evidence.verified_memberships
    assert any(
        item[0] == "external_department_or_school_professional" and item[1] == "VERIFIED"
        for item in external_evidence.pool_membership_evidence
    )

    ge_without_department = _math_catalog_row(
        name="官方共同選修",
        code="GE-1",
        department="",
        category="共同選修",
    )
    ge_evidence = resolve_public_evidence(
        {"term": "112-2", "course_name": "官方共同選修", "credits": 3},
        catalog=_math_public_catalog(ge_without_department),
    )
    assert "external_department_or_school_professional" not in ge_evidence.verified_memberships
    assert not any(
        item[0] == "external_department_or_school_professional"
        for item in ge_evidence.pool_membership_evidence
    )


def test_math_secondary_membership_is_composite_and_exact_public_offering_bound():
    metadata = _math_secondary_metadata()
    evidence = resolve_public_evidence(
        {"term": "111-1", "course_name": "線性代數(一)", "credits": Decimal("3.0")},
        catalog=_math_public_catalog(
            _math_catalog_row(
                term="111-1",
                name="線性代數(一)",
                code="L-1",
                department="9200",
                category="系定選修",
            )
        ),
        handbook_metadata=(metadata,),
        program_slug="math",
    )
    assert "math-secondary:111:線性代數_一" in evidence.verified_memberships
    assert "math-secondary:111:eligible-target-credit" in evidence.verified_memberships
    assert metadata["course_id"] not in evidence.verified_memberships

    other_department = resolve_public_evidence(
        {"term": "111-1", "course_name": "線性代數(一)", "credits": 3},
        catalog=_math_public_catalog(
            _math_catalog_row(
                term="111-1",
                name="線性代數(一)",
                code="L-1-OTHER",
                department="9100",
                category="系定選修",
            )
        ),
        handbook_metadata=(metadata,),
        program_slug="math",
    )
    assert not any(item.startswith("math-secondary:111:") for item in other_department.verified_memberships)


def test_math_secondary_ambiguous_offering_does_not_form_composite_membership():
    metadata = _math_secondary_metadata()
    evidence = resolve_public_evidence(
        {"term": "111-1", "course_name": "線性代數(一)", "credits": 3},
        catalog=_math_public_catalog(
            _math_catalog_row(term="111-1", name="線性代數(一)", code="L-MATH", department="9200"),
            _math_catalog_row(term="111-1", name="線性代數(一)", code="L-OTHER", department="9100"),
        ),
        handbook_metadata=(metadata,),
        program_slug="math",
    )
    assert not any(item.startswith("math-secondary:111:") for item in evidence.verified_memberships)


def test_math_secondary_stable_registry_identity_requires_explicit_math_owner():
    catalog = PublicCourseCatalog.from_records((), covered_terms=("111-1",))
    metadata = _math_secondary_metadata(
        department_unit="9200",
        secondary_course_key="stable-linear-1",
    )
    evidence = resolve_public_evidence(
        {"term": "111-1", "course_name": "線性代數(一)", "credits": 3},
        catalog=catalog,
        handbook_metadata=(metadata,),
        program_slug="math",
    )
    assert "math-secondary:111:stable_linear_1" in evidence.verified_memberships
    assert "math-secondary:111:eligible-target-credit" in evidence.verified_memberships

    missing_owner = resolve_public_evidence(
        {"term": "111-1", "course_name": "線性代數(一)", "credits": 3},
        catalog=catalog,
        handbook_metadata=(_math_secondary_metadata(secondary_course_key="stable-linear-1"),),
        program_slug="math",
    )
    assert not any(item.startswith("math-secondary:111:") for item in missing_owner.verified_memberships)
