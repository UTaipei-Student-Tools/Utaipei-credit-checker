from __future__ import annotations

from curriculum_registry import COMPLETE, get_curriculum
from graduation_service import _compile_requirements
from handbook_rules import get_handbook_config

YEARS = ("111", "112", "113", "114", "115")


def _pool(record: dict, bucket: str) -> dict:
    return next(pool for pool in record["course_pools"].values() if pool["bucket"] == bucket)


def test_cs_primary_catalogues_are_year_scoped_complete_and_sum_to_128():
    for year in YEARS:
        record = get_curriculum(f"primary:{year}:cs")
        specs, _metadata, _provenance = _compile_requirements(record, scope="primary")

        assert record["coverage_state"] == COMPLETE
        assert record["pass_eligible"] is True
        assert sum(spec.credits_required for spec in specs) == 128

        required_rows = [row for row in record["course_catalog"] if row["bucket"] == "cs_required"]
        alpha_rows = [row for row in record["course_catalog"] if row["bucket"] == "cs_alpha_required"]
        beta_rows = [row for row in record["course_catalog"] if row["bucket"] == "cs_elective_beta"]
        assert len(required_rows) == 11
        assert sum(row["credits"] for row in required_rows) == 31
        assert len(alpha_rows) == 12
        assert sum(row["credits"] for row in alpha_rows) == 32
        assert all(row["requirement_type"] == "named_course" for row in alpha_rows)
        assert all(row["membership_ids"] == (f"cs_elective_alpha:{year}",) for row in alpha_rows)
        assert all(row["excluded_from_free"] is True for row in alpha_rows)
        assert len(beta_rows) == 1
        assert beta_rows[0]["credits"] == 22
        assert not any(pool["bucket"] == "cs_department_elective" for pool in record["course_pools"].values())
        assert not any("cs_department_elective" in spec.requirement_id for spec in specs)

        catalog = get_handbook_config(year)["cs_rules"]["primary_catalog"]
        assert catalog["alpha_required_credits"] == 32
        assert catalog["beta_required_credits"] == 22
        assert catalog["rollup_group_id"] == "cs_primary_elective_54"
        assert catalog["rollup_required_credits"] == 54
        assert len(catalog["alpha"]) == 12
        assert catalog["source_pdf_sha256"]


def test_cs_beta_domains_have_year_scoped_minimum_course_gates_and_dual_witnesses():
    for year in YEARS:
        record = get_curriculum(f"primary:{year}:cs")
        specs, _metadata, _provenance = _compile_requirements(record, scope="primary")
        beta = _pool(record, "cs_elective_beta")
        expected_domains = {"common", "software", "network"} if year in {"111", "112", "113"} else {"software", "network"}
        constraints = beta["policy"]["predicate"]["subset_constraints"]
        beta_requirement_id = f"primary:primary:{year}:cs:cs.primary.{year}.beta_remainder"
        beta_spec = next(spec for spec in specs if spec.requirement_id == beta_requirement_id)

        assert beta["membership_id"] == f"cs_elective_beta:{year}"
        assert beta["minimum_course_count"] == 1
        assert len(beta_spec.subset_constraints) == len(constraints)
        for compiled, raw in zip(beta_spec.subset_constraints, constraints):
            assert {
                key: compiled[key]
                for key in raw
                if key in compiled and key != "observed_requirement_ids"
            } == {
                key: value
                for key, value in raw.items()
                if key in compiled and key != "observed_requirement_ids"
            }
            assert tuple(compiled["observed_requirement_ids"]) == (beta_spec.requirement_id,)
        assert {item["membership_id"] for item in constraints} == {
            f"cs_beta_domain:{year}:{domain}" for domain in expected_domains
        }
        assert all(item["minimum_course_count"] == 1 for item in constraints)
        assert all(
            tuple(item["observed_requirement_ids"]) == (beta_spec.requirement_id,)
            for item in beta_spec.subset_constraints
        )
        for candidate in beta["candidate_courses"]:
            assert f"cs_elective_beta:{year}" in candidate["membership_ids"]
            assert candidate["pool_membership_evidence"]
            assert all(item["state"] == "VERIFIED" for item in candidate["pool_membership_evidence"])

        dual_domain_candidates = [
            candidate
            for candidate in beta["candidate_courses"]
            if len([item for item in candidate["membership_ids"] if item.startswith("cs_beta_domain:")]) == 2
        ]
        if year in {"114", "115"}:
            assert dual_domain_candidates
            assert all(
                {item for item in candidate["membership_ids"] if item.startswith("cs_beta_domain:")}
                == {f"cs_beta_domain:{year}:software", f"cs_beta_domain:{year}:network"}
                for candidate in dual_domain_candidates
            )


def test_cs_primary_free_policy_excludes_alpha_and_115_uses_current_ai_name():
    for year in YEARS:
        record = get_curriculum(f"primary:{year}:cs")
        free = _pool(record, "free_elective")
        alpha_pool_id = _pool(record, "cs_elective_alpha")["id"]
        predicate = free["policy"]["predicate"]
        assert f"cs_elective_alpha:{year}" in predicate["excluded_membership_ids"]
        assert alpha_pool_id in predicate["exclude_pool_ids"]

    alpha_names = {
        row["name"]
        for row in get_curriculum("primary:115:cs")["course_catalog"]
        if row["bucket"] == "cs_alpha_required"
    }
    assert "人工智慧" in alpha_names
    assert "人工智慧概論" not in alpha_names
