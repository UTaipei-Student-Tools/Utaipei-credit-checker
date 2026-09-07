"""Regression contracts for evidence-backed 111/115 handbook coverage.

The expected values in this file are copied from the checked-in official-source
research matrices.  They deliberately assert provenance and fail-closed states
instead of treating a readable aggregate as a student's approval.
"""

from __future__ import annotations

import re

from curriculum_registry import COMPLETE, CONFLICTED, PARTIAL, get_curriculum, list_curriculum_ids
from handbook_rules import get_apc_target_requirements, get_handbook_config, get_rule_sets


def test_111_and_115_have_explicit_source_scoped_handbooks():
    for year in ("111", "115"):
        handbook = get_handbook_config(year)
        meta = handbook["_meta"]

        assert meta["version"] == year
        assert meta["academic_year"] == year
        assert meta["source_file"] == f"3-理學院{' (' + year + ')' if year != '111' else ''}.pdf"
        assert meta["source_url"].startswith("https://curr.utaipei.edu.tw/")
        assert meta["source_pages"]["earth_life"]
        assert meta["source_pages"]["apc"]
        assert meta["source_pages"]["math"]
        assert meta["source_pages"]["cs"]
        assert meta["evidence_state"] == "VERIFIED"
        # The handbook-level state remains PARTIAL because other scopes still
        # contain aggregate-only or conflicting rules; Earth is independently
        # complete on its own source-backed scope.
        assert meta["coverage_state"] == PARTIAL
        assert meta["automation_sufficiency"] == PARTIAL
        assert meta["coverage_by_scope"]["primary.earth"] == COMPLETE
        assert meta["coverage_by_scope"]["double_major"] == COMPLETE


def test_all_handbook_versions_keep_auditable_source_metadata():
    for year in ("111", "112", "113", "114", "115"):
        meta = get_handbook_config(year)["_meta"]
        assert meta["academic_year"] == year
        assert meta["source_file"].endswith(".pdf")
        assert meta["source_url"].startswith("https://curr.utaipei.edu.tw/")
        assert meta["evidence_state"] == "VERIFIED"
        assert meta["verification_status"] == "VERIFIED"
        assert meta["coverage_state"] == PARTIAL
        assert meta["automation_sufficiency"] == PARTIAL
        assert meta["manual_review_reason"]
        assert set(meta["coverage_by_scope"]) >= {
            "primary.earth", "primary.apc", "primary.math", "primary.cs",
            "minor.earth", "minor.apc", "minor.math", "minor.cs", "double_major",
        }


def test_111_and_115_primary_rules_do_not_use_neighbor_year_course_names():
    rules_111 = get_rule_sets("111")
    rules_115 = get_rule_sets("115")

    # APC 111 keeps the old 3-credit force-mechanics and semiconductor naming;
    # 115 has the separately verified 2-credit mechanics row.
    assert rules_111["apc_rules"]["divisions"]["物理組"]["compulsory"]["力學(一)"] == 3
    assert "書報討論" not in rules_111["earth_life_major"]["common_compulsory"]
    assert rules_115["apc_rules"]["divisions"]["物理組"]["compulsory"]["力學(一)"] == 2
    assert rules_115["apc_rules"]["divisions"]["化學組"]["compulsory"]["化學數學(一)"] == 2

    # CS 111 and CS 115 have distinct named core/elective catalogues.
    assert "Java軟體實務" in rules_111["cs_rules"]["department_courses"]
    assert "程式設計技巧" in rules_115["cs_rules"]["department_courses"]
    assert "人工智慧" in rules_115["cs_rules"]["department_courses"]
    assert "人工智慧概論" not in rules_115["cs_rules"]["department_courses"]


def test_111_and_115_primary_registry_rows_are_auditable_and_not_empty():
    scopes = (
        "primary:111:earth:earth_environment",
        "primary:111:apc:physics",
        "primary:111:math",
        "primary:111:cs",
        "primary:115:earth:earth_environment",
        "primary:115:apc:chemistry",
        "primary:115:math:math_scientific_computing",
        "primary:115:cs",
    )
    for curriculum_id in scopes:
        curriculum = get_curriculum(curriculum_id)
        assert curriculum["course_catalog"], curriculum_id
        assert curriculum["coverage_state"] in {COMPLETE, PARTIAL}
        if curriculum_id.split(":")[2] in {"earth", "apc"}:
            assert curriculum["coverage_state"] == COMPLETE
            assert curriculum["pass_eligible"] is True
        elif curriculum_id.split(":")[2] == "math":
            assert curriculum["pass_eligible"] is True
        else:
            assert curriculum["coverage_state"] == COMPLETE
            assert curriculum["pass_eligible"] is True
        for row in curriculum["course_catalog"]:
            assert row["curriculum_version"] == curriculum["version"]
            assert row["source_url"].startswith("https://curr.utaipei.edu.tw/")
            assert row["pdf_page"]
            assert row["printed_page"]
            assert row["original_clause"]
            assert row["evidence_state"] in {"VERIFIED", CONFLICTED}


def test_115_cs_secondary_catalog_has_exact_official_named_requirements():
    for prefix in ("minor", "target:double_major"):
        curriculum = get_curriculum(f"{prefix}:115:cs")
        assert curriculum["aggregate_status"] == "VERIFIED"
        assert curriculum["coverage_state"] == COMPLETE
        assert curriculum["pass_eligible"] is True
        named = {row["name"] for row in curriculum["course_catalog"] if row["kind"] in {"course", "MINOR_COURSE"}}
        expected = {"計算機概論", "C程式設計"}
        if prefix == "target:double_major":
            expected |= {"Java程式設計", "資料結構", "演算法"}
        assert named == expected
        assert all(row["source_reference"] and row["evidence_state"] == "VERIFIED" for row in curriculum["course_catalog"])

def test_apc_equivalency_scope_is_year_and_component_specific():
    old = get_rule_sets("114")["apc_rules"]
    new = get_rule_sets("115")["apc_rules"]

    assert "微積分(一)" not in old["basic_core"]
    assert "微積分(一)" in new["basic_core"]
    assert old["basic_core"]["普通物理實驗(一)"] == 1
    assert old["basic_core"]["普通化學實驗(一)"] == 1
    # In 115 the lab component moved into the selected track's professional
    # compulsory table; it is not silently kept in the common core.
    assert "普通物理實驗(一)" not in new["basic_core"]
    assert "普通化學實驗(一)" not in new["basic_core"]
    assert new["divisions"]["物理組"]["compulsory"]["普通物理實驗(一)"] == 1
    assert new["divisions"]["化學組"]["compulsory"]["普通化學實驗(一)"] == 1


def test_apc_primary_common_catalog_is_track_scoped_and_keeps_cross_labs_candidates():
    old_physics = [
        "普通物理學(一)",
        "普通物理實驗(一)",
        "普通化學(一)",
        "普通物理學(二)",
        "普通物理實驗(二)",
        "普通化學(二)",
        "應用科學專題(一)",
        "應用科學專題(二)",
    ]
    old_chemistry = [
        "普通物理學(一)",
        "普通化學(一)",
        "普通化學實驗(一)",
        "普通物理學(二)",
        "普通化學(二)",
        "普通化學實驗(二)",
        "應用科學專題(一)",
        "應用科學專題(二)",
    ]
    for year in ("111", "112", "113", "114"):
        configured = get_rule_sets(year)["apc_rules"]
        assert list(configured["common_catalog"]) == [
            "普通物理學(一)",
            "普通物理實驗(一)",
            "普通化學(一)",
            "普通化學實驗(一)",
            "普通物理學(二)",
            "普通物理實驗(二)",
            "普通化學(二)",
            "普通化學實驗(二)",
            "應用科學專題(一)",
            "應用科學專題(二)",
        ]
        assert sum(configured["common_catalog"].values()) == 18
        for track, expected in (("physics", old_physics), ("chemistry", old_chemistry)):
            curriculum = get_curriculum(f"primary:{year}:apc:{track}")
            common = next(
                pool for pool in curriculum["course_pools"].values()
                if pool["bucket"] == "apc_common_compulsory"
            )
            assert [candidate["name"] for candidate in common["candidate_courses"]] == expected
            assert common["required_credits"] == 16
            assert sum(candidate["credits"] for candidate in common["candidate_courses"]) == 16

            cross = next(
                pool for pool in curriculum["course_pools"].values()
                if pool["bucket"] == "apc_cross_track_lab_candidates"
            )
            excluded = (
                {"普通化學實驗(一)", "普通化學實驗(二)"}
                if track == "physics"
                else {"普通物理實驗(一)", "普通物理實驗(二)"}
            )
            assert {candidate["name"] for candidate in cross["candidate_courses"]} == excluded
            assert cross["required_credits"] is None
            assert cross["candidate_only"] is True
            assert cross["policy"]["eligible_for_free_elective_policy"] is True
            assert not any(
                row["name"] in excluded
                for row in curriculum["course_catalog"]
                if row["bucket"] == "apc_common"
            )

    for track in ("physics", "chemistry"):
        curriculum = get_curriculum(f"primary:115:apc:{track}")
        common = next(
            pool for pool in curriculum["course_pools"].values()
            if pool["bucket"] == "apc_common_compulsory"
        )
        assert [candidate["name"] for candidate in common["candidate_courses"]] == [
            "普通物理學(一)", "普通化學(一)", "微積分(一)",
            "普通物理學(二)", "普通化學(二)", "微積分(二)",
        ]
        assert common["required_credits"] == 18
        assert not any(
            pool["bucket"] == "apc_cross_track_lab_candidates"
            for pool in curriculum["course_pools"].values()
        )


def test_apc_primary_elective_catalogues_are_cohort_scoped_and_complete():
    expected_counts = {
        "111": {"physics": 35, "chemistry": 37},
        "112": {"physics": 31, "chemistry": 38},
        "113": {"physics": 25, "chemistry": 28},
        "114": {"physics": 25, "chemistry": 28},
        "115": {"physics": 28, "chemistry": 29},
    }
    expected_pages = {
        "111": {"physics": "8-9", "chemistry": "17-18"},
        "112": {"physics": "8-9", "chemistry": "17-18"},
        "113": {"physics": "9-10", "chemistry": "21-22"},
        "114": {"physics": "10-11", "chemistry": "21-23"},
        "115": {"physics": "10-11", "chemistry": "22-23"},
    }
    for year, tracks in expected_counts.items():
        for track, expected_count in tracks.items():
            curriculum = get_curriculum(f"primary:{year}:apc:{track}")
            elective = next(
                pool for pool in curriculum["course_pools"].values()
                if pool["bucket"] == "apc_track_elective"
            )
            assert len(elective["candidate_courses"]) == expected_count
            assert elective["coverage_state"] == COMPLETE
            assert elective["evidence_state"] == "VERIFIED"
            assert elective["pdf_page"] == expected_pages[year][track]
            assert elective["source_reference"].startswith(
                f"research/apc_cs_handbook_matrix_111_115.md#apc-{year}-primary-"
            )
            assert all(candidate["candidate_only"] for candidate in elective["candidate_courses"])
            assert all(candidate["requirement_type"] == "candidate_course" for candidate in elective["candidate_courses"])
            assert all(candidate["college"] == "理學院" for candidate in elective["candidate_courses"])
            assert all(candidate["membership_ids"] == ("science_college",) for candidate in elective["candidate_courses"])

    # Same-looking course names in different years stay independent source
    # candidates; a later catalogue cannot silently fill an earlier one.
    assert "光電數值方法" in {
        row["name"] for row in get_curriculum("primary:111:apc:physics")["course_pools"][
            "pool:primary:111:apc:physics:apc_track_elective"
        ]["candidate_courses"]
    }
    assert "光電數值方法" not in {
        row["name"] for row in get_curriculum("primary:112:apc:physics")["course_pools"][
            "pool:primary:112:apc:physics:apc_track_elective"
        ]["candidate_courses"]
    }
    assert "周遊Fun 科學" in {
        row["name"] for row in get_curriculum("primary:115:apc:chemistry")["course_pools"][
            "pool:primary:115:apc:chemistry:apc_track_elective"
        ]["candidate_courses"]
    }
    assert "周遊Fun 科學" not in {
        row["name"] for row in get_curriculum("primary:114:apc:chemistry")["course_pools"][
            "pool:primary:114:apc:chemistry:apc_track_elective"
        ]["candidate_courses"]
    }

    physics_114 = get_curriculum("primary:114:apc:physics")["course_pools"][
        "pool:primary:114:apc:physics:apc_track_elective"
    ]["candidate_courses"]
    assert [row["name"] for row in physics_114] == [
        "計算機概論", "電子物理導論", "微積分(一)", "微積分(二)",
        "電路學(一)", "電路學(二)", "力學(二)", "熱物理",
        "電腦在物理上的應用(一)", "電腦在物理上的應用(二)", "相對論",
        "統計物理", "物理數學(三)", "量子力學(一)", "藝術與物理學",
        "光學材料", "聲音與影像的科學", "電磁波", "量子計算導論", "計算物理",
        "半導體材料與元件", "量子力學(二)", "半導體元件", "積體光學", "自旋電子學導論",
    ]
    assert [row["credits"] for row in physics_114] == [3] * 25


def test_apc_primary_credits_and_project_notes_match_each_handbook_year():
    expected = {
        "111": {"physics": (16, 44, 25), "chemistry": (16, 45, 24)},
        "112": {"physics": (16, 44, 25), "chemistry": (16, 45, 24)},
        "113": {"physics": (16, 44, 25), "chemistry": (16, 45, 24)},
        "114": {"physics": (16, 44, 25), "chemistry": (16, 45, 24)},
        "115": {"physics": (18, 42, 25), "chemistry": (18, 42, 25)},
    }
    for year, tracks in expected.items():
        for track, (common_credits, required_credits, elective_credits) in tracks.items():
            curriculum = get_curriculum(f"primary:{year}:apc:{track}")
            pools = curriculum["course_pools"]
            common = next(pool for pool in pools.values() if pool["bucket"] == "apc_common_compulsory")
            required = next(pool for pool in pools.values() if pool["bucket"] == "apc_track_compulsory")
            elective = next(pool for pool in pools.values() if pool["bucket"] == "apc_track_elective")
            assert common["required_credits"] == common_credits
            assert required["required_credits"] == required_credits
            assert elective["required_credits"] == elective_credits
            assert curriculum["thresholds"] == {
                "total": 128,
                "university_common": 28,
                "major_common": common_credits,
                "track_required": required_credits,
                "elective": elective_credits,
                "free": 15,
            }
            assert curriculum["coverage_state"] == COMPLETE
            assert curriculum["pass_eligible"] is True

    for track in ("physics", "chemistry"):
        curriculum = get_curriculum(f"primary:115:apc:{track}")
        elective = next(pool for pool in curriculum["course_pools"].values() if pool["bucket"] == "apc_track_elective")
        for index, semester in enumerate(("大二上", "大二下", "大三上", "大三下", "大四上", "大四下"), start=1):
            candidate = next(
                row for row in elective["candidate_courses"] if row["name"] == f"專題研究({['一', '二', '三', '四', '五', '六'][index - 1]})"
            )
            assert candidate["course_metadata"]["official_note"] == f"限{semester}學期修"
            assert candidate["course_metadata"]["semester_restriction"] == f"限{semester}學期修"


def test_apc_unresolved_quota_is_candidate_only_and_year_scoped():
    old = get_apc_target_requirements("111", "化學組", "雙主修")
    assert old["evidence_state"] == "VERIFIED"
    assert old["coverage_state"] == PARTIAL
    assert old["other_required"] == 24
    assert old["other_required_catalog"] == {}
    assert old["other_required_candidates"]
    assert any("額外目標必修24" in warning for warning in old["warnings"])
    assert all(
        row["kind"] == "course" and row["source_url"] and row["pdf_page"] and row["printed_page"]
        for row in old["requirements"][:-1]
    )
    assert all(row["automatic_decision"] is False for row in old["requirements"])

    physics = get_apc_target_requirements("115", "物理組", "雙主修")
    names = [row["name"] for row in physics["requirements"] if row["kind"] == "course"]
    assert names == [
        "普通物理學(一)", "普通化學(一)", "普通物理實驗(一)", "微積分(一)",
        "普通物理學(二)", "普通化學(二)", "普通物理實驗(二)", "微積分(二)",
    ]
    assert physics["other_required"] == 20
    assert physics["other_required_catalog"] == {}
    assert physics["coverage_state"] == PARTIAL
    assert all(row["source_url"] and row["original_clause"] for row in physics["requirements"])
    assert {row["component"] for row in physics["requirements"] if row["kind"] == "course" and row["is_lab"]} == {"lab"}


def test_every_year_role_scope_exposes_a_pool_without_promoting_candidates():
    """Every registry scope has a traceable pool and explicit row semantics."""

    for curriculum_id in list_curriculum_ids():
        curriculum = get_curriculum(curriculum_id)
        pools = curriculum["course_pools"]
        assert pools, curriculum_id
        for pool_id, pool in pools.items():
            assert pool_id == pool["pool_id"]
            assert pool["schema"] == "pool:v1"
            assert pool["curriculum_version"] == curriculum["version"]
            assert pool["allow_user_claimed_department"] is False
            assert pool["source_url"].startswith("https://curr.utaipei.edu.tw/")
            assert pool["pdf_page"]
            assert pool["printed_page"]
            for candidate in pool["candidate_courses"]:
                assert candidate["candidate_only"] is True
                assert candidate["requirement_type"] == "candidate_course"
                assert candidate["pool_ids"] == (pool_id,)
                assert candidate["curriculum_version"] == curriculum["version"]

        for row in curriculum["course_catalog"]:
            assert row["candidate_only"] is False
            assert row["requirement_type"] != "candidate_course"
            if row["requirement_type"] in {"named_course", "required_course"}:
                assert row["pool_ids"]
                assert row["eligible_pool_ids"] == ()
            elif row.get("pool_requirement"):
                # A scoped unresolved candidate pool may identify its own
                # pool while remaining a non-promoted quota row.  Named and
                # candidate rows still keep their original identity rules.
                if row.get("candidate_only"):
                    assert row["pool_ids"]
                elif any("unresolved_" in pool_id for pool_id in row["pool_ids"]):
                    assert row["pool_ids"] == row["eligible_pool_ids"]
                else:
                    assert row["pool_ids"] == ()
                assert row["eligible_pool_ids"]


def test_minor_quota_pools_are_disjoint_from_named_requirement_pools():
    """A quota can never be satisfied by a fixed named-course pool."""

    minor_ids = [item for item in list_curriculum_ids() if item.startswith("minor:")]
    assert minor_ids
    for curriculum_id in minor_ids:
        curriculum = get_curriculum(curriculum_id)
        rows = curriculum["course_catalog"]
        named_pool_ids = {
            pool_id
            for row in rows
            if row["requirement_type"] in {"named_course", "required_course"}
            for pool_id in row["pool_ids"]
        }
        quota_rows = [row for row in rows if row.get("pool_requirement")]
        for row in quota_rows:
            assert set(row["eligible_pool_ids"]).isdisjoint(named_pool_ids), (
                curriculum_id,
                row["id"],
            )
            for pool_id in row["eligible_pool_ids"]:
                assert curriculum["course_pools"][pool_id]["required_credits"] == row["required_credits"]


def test_earth_primary_complete_example_includes_shared_and_non_credit_gates():
    curriculum = get_curriculum("primary:115:earth:earth_environment")

    assert curriculum["coverage_state"] == COMPLETE
    assert curriculum["pass_eligible"] is True
    assert curriculum["thresholds"]["university_common"] == 28
    assert curriculum["thresholds"]["free"] == 15
    assert {row["name"] for row in curriculum["university_requirements"] if row["credits"] > 0} >= {
        "國文(一):閱讀與思辨",
        "國文(二):語文表達",
        "英文(一)",
        "英文(二)",
        "英文(三)",
        "通識共同選修",
    }
    assert len(
        [row for row in curriculum["university_requirements"] if row["requirement_type"] == "course_pool"]
    ) == 5
    assert curriculum["non_credit_requirements"][0]["name"] == "體育"
    assert curriculum["non_credit_requirements"][0]["semesters_required"] == 4


def test_earth_primary_credit_structure_keeps_common_elective_year_scoped():
    """Only the 111 handbook makes common electives an independent minimum."""

    for year in ("111", "112", "113", "114", "115"):
        curriculum = get_curriculum(f"primary:{year}:earth:earth_environment")
        assert curriculum["thresholds"]["total"] == 128
        assert curriculum["thresholds"]["major_total"] == 85
        common_pool = next(
            pool for pool in curriculum["course_pools"].values() if pool["bucket"] == "common_elective"
        )
        professional_pool = next(
            pool for pool in curriculum["course_pools"].values() if pool["bucket"] == "department_professional"
        )
        common_names = {candidate["name"] for candidate in common_pool["candidate_courses"]}
        professional_names = {candidate["name"] for candidate in professional_pool["candidate_courses"]}
        assert common_names <= professional_names
        common_rows = [row for row in curriculum["course_catalog"] if row["bucket"] == "common_elective"]
        if year == "111":
            assert common_pool["required_credits"] == 12
            assert len(common_rows) == 1
        else:
            assert common_pool["required_credits"] is None
            assert common_pool["requirement_minimum_credits"] is None
            assert common_rows == []
            assert professional_pool["required_credits"] == 27


def test_earth_department_candidates_only_claim_science_college_membership():
    """Official Earth department pools carry membership; shared pools do not."""

    department_buckets = {
        "common_compulsory",
        "domain_required",
        "common_elective",
        "domain_elective",
        "department_professional",
        "common_alternative_1",
        "common_alternative_2",
        "common_alternative_3",
    }
    for year in ("111", "112", "113", "114", "115"):
        curriculum = get_curriculum(f"primary:{year}:earth:earth_environment")
        for pool in curriculum["course_pools"].values():
            candidates = pool["candidate_courses"]
            if pool["bucket"] in department_buckets:
                assert candidates, pool["pool_id"]
                assert all(candidate["college"] == "理學院" for candidate in candidates)
                assert all(candidate["membership_ids"] == ("science_college",) for candidate in candidates)
            else:
                assert all("college" not in candidate for candidate in candidates)
                assert all("membership_ids" not in candidate for candidate in candidates)

        ge_or_pe_pools = [
            pool for pool in curriculum["course_pools"].values()
            if pool["selection_rule"] in {"official_category_policy", "semester_count"}
        ]
        assert all(not pool["candidate_courses"] for pool in ge_or_pe_pools)


def test_all_science_primary_department_candidates_claim_membership_only():
    """Four primary science programs keep college membership scoped to departments."""

    program_cases = {
        "earth": (
            "primary:111:earth:earth_environment",
            {
                "common_compulsory",
                "domain_required",
                "common_elective",
                "domain_elective",
                "department_professional",
                "common_alternative_1",
                "common_alternative_2",
                "common_alternative_3",
            },
        ),
        "apc": (
            "primary:115:apc:physics",
            {
                "apc_common_compulsory",
                "apc_cross_track_lab_candidates",
                "apc_track_compulsory",
                "apc_track_elective",
            },
        ),
        "cs": (
            "primary:115:cs:department",
            {"cs_department_required", "cs_elective_alpha", "cs_elective_beta"},
        ),
        "math": (
            "primary:111:math",
            {"math_common_compulsory", "math_domain_required", "math_department_elective"},
        ),
    }
    for program, (curriculum_id, department_buckets) in program_cases.items():
        curriculum = get_curriculum(curriculum_id)
        candidate_pools = [
            pool for pool in curriculum["course_pools"].values() if pool["candidate_courses"]
        ]
        assert any(pool["bucket"] in department_buckets for pool in candidate_pools), program
        for pool in candidate_pools:
            candidates = pool["candidate_courses"]
            if pool["bucket"] in department_buckets:
                assert all(candidate["evidence_state"] == "VERIFIED" for candidate in candidates)
                assert all(candidate["college"] == "理學院" for candidate in candidates)
                if program == "cs" and pool["bucket"] in {"cs_elective_alpha", "cs_elective_beta"}:
                    assert all(candidate["membership_ids"][0] == "science_college" for candidate in candidates)
                    expected_membership = (
                        "cs_elective_alpha:115"
                        if pool["bucket"] == "cs_elective_alpha"
                        else "cs_elective_beta:115"
                    )
                    assert all(expected_membership in candidate["membership_ids"] for candidate in candidates)
                else:
                    assert all(candidate["membership_ids"] == ("science_college",) for candidate in candidates)
                assert all(candidate["source"]["source_type"] == "official_handbook" for candidate in candidates)
            else:
                # University common candidates stay outside the science-college
                # membership; policy-only GE/PE pools must never gain rows here.
                assert all("college" not in candidate for candidate in candidates)
                assert all("membership_ids" not in candidate for candidate in candidates)

        university_pool = next(
            pool for pool in curriculum["course_pools"].values() if pool["bucket"] == "university_compulsory"
        )
        assert university_pool["candidate_courses"]
        assert all("college" not in candidate for candidate in university_pool["candidate_courses"])
        assert all("membership_ids" not in candidate for candidate in university_pool["candidate_courses"])
        ge_or_pe_pools = [
            pool
            for pool in curriculum["course_pools"].values()
            if pool["selection_rule"] in {"official_category_policy", "semester_count"}
        ]
        assert all(not pool["candidate_courses"] for pool in ge_or_pe_pools)


def test_partial_department_candidate_does_not_claim_science_membership():
    """A partial handbook row remains a candidate needing confirmation."""

    from curriculum_registry import _pool_course_entry

    candidate = _pool_course_entry(
        "115",
        "cs",
        "department",
        "primary:115:cs:department:cs_department_required",
        "測試課程",
        3,
        {"source_file": "3-理學院 (115).pdf"},
        evidence_state=PARTIAL,
    )
    assert candidate["evidence_state"] == PARTIAL
    assert "college" not in candidate
    assert "membership_ids" not in candidate


def test_primary_policy_pools_and_pe_gate_have_year_scoped_source_contracts():
    """Policy-only rows carry the selected program/track source contract."""

    program_tracks = {
        "earth": ("earth_environment", "life_science"),
        "apc": ("physics", "chemistry"),
        "cs": ("department",),
        "math": (None,),
    }
    for year in ("111", "112", "113", "114", "115"):
        for program, tracks in program_tracks.items():
            for track in tracks:
                if program == "math" and int(year) >= 113:
                    math_tracks = {
                        "113": ("math_scientific_computing", "data_science", "math_education"),
                        "114": ("math_scientific_computing", "data_science", "math_education"),
                        "115": ("math_scientific_computing", "data_science"),
                    }[year]
                    curriculum_ids = tuple(f"primary:{year}:math:{item}" for item in math_tracks)
                else:
                    curriculum_ids = (f"primary:{year}:{program}" + (f":{track}" if track else ""),)
                for curriculum_id in curriculum_ids:
                    curriculum = get_curriculum(curriculum_id)
                    expected_track = curriculum.get("track_slug") or "department"
                    policy_pools = [
                        pool
                        for pool in curriculum["course_pools"].values()
                        if pool["selection_rule"] in {"official_category_policy", "official_open_elective_policy"}
                    ]
                    assert len(policy_pools) == 6
                    for pool in policy_pools:
                        policy = pool["policy"]
                        assert policy["policy_id"]
                        assert policy["revision"] == f"{year}.1"
                        assert policy["applies_to"]["curriculum_versions"] == (year,)
                        assert policy["applies_to"]["program_slugs"] == (program,)
                        assert policy["applies_to"]["track_slugs"] == (expected_track,)
                        assert policy["applies_to"]["roles"] == ("primary",)
                        assert policy["predicate"]
                        assert policy["evidence_state"] == "VERIFIED"
                        assert policy["coverage_state"] == "COMPLETE"
                        assert isinstance(policy["automatic_decision"], bool)
                        assert policy["source_reference"]
                        assert policy["source_url"].startswith("https://")
                        assert policy["pdf_page"]
                        assert policy["original_clause"]
                        assert policy["policy_source"]["source_reference"] == policy["source_reference"]

                    free_pool = next(
                        pool for pool in policy_pools if pool["selection_rule"] == "official_open_elective_policy"
                    )
                    free_policy = free_pool["policy"]
                    if program == "math":
                        expected_external_cap = (
                            {"non_teacher": 15, "teacher": 11}
                            if year in {"111", "112"}
                            else {"non_teacher": 15, "teacher": 15}
                        )
                        assert free_policy["subset_maxima"]["external_department_or_school_professional"] == expected_external_cap
                        assert free_policy["predicate"]["subset_constraints"]
                        assert all(
                            item["subset_id"] == "external_department_or_school_professional"
                            for item in free_policy["predicate"]["subset_constraints"]
                        )
                        assert "至多" in free_policy["original_clause"]
                        if year in {"111", "112"}:
                            assert free_pool["required_credits"] is None
                            assert free_policy["amount_semantics"] == "MAXIMUM"
                            assert free_policy["predicate"]["amount_semantics"] == "MAXIMUM"
                            assert free_policy["requirement_minimum_credits"] is None
                            assert free_policy["predicate"].get("minimum_credits") is None
                        else:
                            assert free_pool["required_credits"] == 15
                            assert free_policy["amount_semantics"] == "MINIMUM"
                            assert free_policy["predicate"]["amount_semantics"] == "MINIMUM"
                            assert free_policy["requirement_minimum_credits"] == 15
                            assert free_policy["predicate"]["minimum_credits"] == 15
                    else:
                        assert free_pool["required_credits"] == 15
                        assert free_policy["amount_semantics"] == "MINIMUM"
                        assert free_policy["predicate"]["subset_constraints"] == [
                            {
                                "constraint_id": "science_college_minimum",
                                "membership_id": "science_college",
                                "minimum_credits": 3.0,
                            }
                        ]

        earth_curriculum = get_curriculum(f"primary:{year}:earth:earth_environment")
        pe = earth_curriculum["non_credit_requirements"][0]
        assert pe["kind"] == "DISTINCT_TERM_ITEM_COUNT"
        assert pe["required_count"] == 4
        if year in {"111", "112", "113"}:
            assert pe["required_hours"] == 0
            assert pe["hours_per_completion"] == 0
            assert pe["max_completions_per_term"] is None
        else:
            assert pe["required_hours"] == 8
            assert pe["hours_per_completion"] == 2
            assert pe["max_completions_per_term"] == 1
        assert pe["distinct_term_required"] is True
        assert pe["distinct_activity_required"] is True
        assert pe["affects_credit_ledger"] is False
        assert pe["policy_id"] == f"university_common.physical_education.{year}"
        assert pe["policy_source"]["source_reference"]
        assert pe["scope_state"] == "VERIFIED"
        assert pe["source_reference"].startswith(f"handbook:{year}:pdf:4:common:physical_education")

        aliases = earth_curriculum["course_pools"][pe["pool_ids"][0]]["policy"]["official_activity_aliases"]
        for alias_key in ("basketball", "volleyball", "table_tennis", "swimming"):
            assert aliases[alias_key]["applicability_state"] == "LABEL_ONLY"
            assert aliases[alias_key]["source_url"].startswith("https://genedu.utaipei.edu.tw/")


def test_earth_target_has_24_named_and_16_official_elective_credits():
    curriculum = get_curriculum("target:double_major:115:earth:earth_environment")
    assert curriculum["coverage_state"] == COMPLETE
    assert curriculum["pass_eligible"] is True
    named = [row for row in curriculum["course_catalog"] if row["kind"] == "course"]
    quotas = [row for row in curriculum["course_catalog"] if row["kind"] == "quota"]
    assert sum(row["credits"] for row in named) == 24
    assert len(quotas) == 1 and quotas[0]["required_credits"] == 16
    assert quotas[0]["eligible_course_names"]
    assert all(pool["candidate_courses"] for pool in curriculum["course_pools"].values())

def test_old_apc_physics_double_major_does_not_reuse_minor_rows():
    plan = get_apc_target_requirements("114", "物理組", "雙主修")

    assert plan["requirements"][-1]["kind"] == "quota"
    assert not any(row["kind"] == "course" for row in plan["requirements"])
    assert plan["evidence_state"] == "MISSING"
    assert plan["coverage_state"] == PARTIAL
    assert plan["other_required_catalog"] == {}
    assert plan["other_required_candidates"]
    assert plan["automatic_decision"] is False
    assert any("舊式掃描" in warning for warning in plan["warnings"])


def test_115_apc_physics_double_major_registry_keeps_labs_and_provenance():
    curriculum = get_curriculum("target:double_major:115:apc:physics")
    course_rows = [row for row in curriculum["course_catalog"] if row["kind"] == "course"]
    assert [row["name"] for row in course_rows] == [
        "普通物理學(一)", "普通化學(一)", "普通物理實驗(一)", "微積分(一)",
        "普通物理學(二)", "普通化學(二)", "普通物理實驗(二)", "微積分(二)",
    ]
    assert curriculum["coverage_state"] == COMPLETE
    assert curriculum["pass_eligible"] is True
    assert all(
        row["track_slug"] == "physics"
        and row["source_url"].startswith("https://curr.utaipei.edu.tw/")
        and row["pdf_page"]
        and row["printed_page"]
        and row["table_location"]
        and row["original_clause"]
        and row["automatic_decision"] is True
        for row in course_rows
    )
    assert {row["name"] for row in course_rows if row["component"] == "lab"} == {
        "普通物理實驗(一)", "普通物理實驗(二)"
    }


def test_apc_target_registry_exposes_only_the_year_scoped_visible_rows():
    for year in ("111", "112", "113", "114"):
        for track in ("physics", "chemistry"):
            curriculum = get_curriculum(f"target:double_major:{year}:apc:{track}")
            course_rows = [row for row in curriculum["course_catalog"] if row["kind"] == "course"]

            assert curriculum["coverage_state"] == COMPLETE
            assert curriculum["pass_eligible"] is True

            assert len(course_rows) == 8
            assert all(row["curriculum_version"] == year for row in course_rows)
            assert all(row["track_slug"] == track for row in course_rows)
            assert all(row["automatic_decision"] is True for row in course_rows)
            assert curriculum["evidence_state"] == "VERIFIED"
            assert sum(row["credits"] for row in course_rows) == 16
            quota = next(row for row in curriculum["course_catalog"] if row["kind"] == "quota")
            assert quota["required_credits"] == 24
            assert quota["eligible_course_names"]


def test_113_math_minor_current_credit_is_eligible_without_false_conflict():
    curriculum = get_curriculum("minor:113:math:department")
    assert curriculum["evidence_state"] == "VERIFIED"
    assert curriculum["status"] == "VERIFIED"
    assert curriculum["pass_eligible"] is True
    assert not any(item["evidence_state"] == CONFLICTED for item in curriculum["source_assertions"])
    assert curriculum["conflicted_course_names"] == ()
    assert curriculum["credit_revision_history"]["數學導論"] == {
        "current_credits": 3,
        "previous_credits": 4,
        "revision_state": "CURRENT_VALUE_VERIFIED",
        "source_reference": "handbook:113:math:minor:p.74",
    }
    elective_row = next(row for row in curriculum["course_catalog"] if row["name"] == "數學表列選修")
    assert {tuple(sorted(option.items())) for option in elective_row["eligible_course_options"]}.__contains__(
        (("credits", 3.0), ("name", "數學導論"))
    )


def test_every_registry_assertion_and_row_has_the_auditable_evidence_contract():
    """All generated evidence objects remain independently exportable/auditable."""

    required = {
        "curriculum_version",
        "automatic_decision",
        "source_reference",
        "source_url",
        "source_file",
        "pdf_page",
        "printed_page",
        "original_clause",
        "verification_status",
        "evidence_state",
        "coverage_state",
        "automation_sufficiency",
    }
    records = list_curriculum_ids()
    assert len(records) == 90
    for curriculum_id in records:
        curriculum = get_curriculum(curriculum_id)
        evidence_items = [
            *curriculum["source_assertions"],
            *curriculum["course_catalog"],
        ]
        assert evidence_items, curriculum_id
        for item in evidence_items:
            assert required <= item.keys(), (curriculum_id, sorted(required - item.keys()))
            assert item["curriculum_version"] == curriculum["version"]
            assert item["source_url"].startswith("https://curr.utaipei.edu.tw/")
            assert item["source_file"].endswith(".pdf")
            assert item["pdf_page"]
            assert item["printed_page"]
            assert item["source_reference"]
            assert item["original_clause"]
            if not item["automatic_decision"]:
                assert item.get("manual_reason") or item.get("manual_review_reason"), item


def test_all_85_compiled_requirements_keep_auditable_provenance():
    from graduation_service import _compile_requirements

    required = {
        "curriculum_version",
        "source_reference",
        "source_url",
        "source_file",
        "pdf_page",
        "printed_page",
        "original_clause",
        "verification_status",
        "evidence_state",
        "coverage_state",
        "automatic_decision",
    }
    requirement_count = 0
    for curriculum_id in list_curriculum_ids():
        curriculum = get_curriculum(curriculum_id)
        scope = {
            "primary": "primary",
            "minor_target": "minor",
            "double_major_target": "target",
        }[curriculum["kind"]]
        specs, metadata, _ = _compile_requirements(curriculum, scope=scope)
        for spec in specs:
            requirement_count += 1
            provenance = metadata[spec.requirement_id]["source"]
            assert required <= provenance.keys(), (curriculum_id, spec.requirement_id)
            assert provenance["curriculum_version"] == curriculum["version"]
            assert provenance["source_url"].startswith("https://curr.utaipei.edu.tw/")
            assert provenance["source_file"].endswith(".pdf")
            assert provenance["original_clause"]
            if not provenance["automatic_decision"]:
                assert provenance.get("manual_reason"), provenance
    # The registry now emits the exact shared-university rows and explicit
    # department quota rows.  The old 652 count came from the truncated
    # primary catalog and would hide those requirements; keep a lower bound
    # so an accidental return to the candidate-only catalog is caught without
    # coupling this audit to an internal row ordering.
    assert requirement_count >= 1100


def test_automatic_minor_rows_use_official_handbook_row_references():
    for curriculum_id in list_curriculum_ids(kind="minor"):
        curriculum = get_curriculum(curriculum_id)
        for row in curriculum["course_catalog"]:
            if row["automatic_decision"]:
                assert row["source_reference"].startswith(
                    f"handbook:{curriculum['version']}:"
                ), row
                assert re.search(r":p\d[^:]*:.+$", row["source_reference"]), row
                assert row["pdf_page"] and row["original_clause"], row


def test_cs_114_double_major_compiles_named_15_and_elective_25_without_duplicates():
    from graduation_service import _compile_requirements

    record = get_curriculum("target:double_major:114:cs")
    named = [row for row in record["course_catalog"] if row["kind"] == "course"]
    quotas = [row for row in record["course_catalog"] if row["kind"] == "quota"]
    assert {row["name"] for row in named} == {"計算機概論", "C程式設計", "Java程式設計", "資料結構", "演算法"}
    assert all(row["credits"] == 3 for row in named)
    assert len(quotas) == 1 and quotas[0]["required_credits"] == 25
    assert quotas[0]["eligible_course_names"]
    specs, metadata, _ = _compile_requirements(record, scope="target")
    assert len(specs) == 6
    assert sum(item.credits_required for item in specs) == 40
    assert sum(bool(metadata[item.requirement_id]["generic"]) for item in specs) == 1

def test_cs_114_primary_conflict_keeps_both_printed_pages_and_manual_gate():
    record = get_curriculum("primary:114:cs")
    assertions = {
        item["id"]: item for item in record["source_assertions"]
        if item["id"].startswith("cs.primary.114.split")
    }
    assert assertions["cs.primary.114.split10-16-2"]["pdf_page"] == "108"
    assert assertions["cs.primary.114.split10-16-2"]["printed_page"] == "107"
    assert assertions["cs.primary.114.split8-16-4"]["pdf_page"] == "110"
    assert assertions["cs.primary.114.split8-16-4"]["printed_page"] == "109"
    assert record["evidence_state"] == "VERIFIED"
    # The 8/16/4 summary remains a non-blocking conflict assertion; the
    # complete row-level catalogue uses the 10/16/2 source table.
    assert record["pass_eligible"] is True
    assert assertions["cs.primary.114.split10-16-2"]["conflict_group"] is None
    assert assertions["cs.primary.114.split8-16-4"]["conflict_group"] == "cs.primary.114.common-course-split"
    assert assertions["cs.primary.114.split8-16-4"]["manual_reason"]
    assert assertions["cs.primary.114.split8-16-4"]["evidence_state"] == CONFLICTED
    assert assertions["cs.primary.114.split8-16-4"]["blocks_decision"] is False
