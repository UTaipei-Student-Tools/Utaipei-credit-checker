import unittest

from application_resolution import (
    FORMAL_AWARD_RECORD,
    get_notice_resolution,
    resolve_application_case,
    resolve_formal_award,
    resolve_formal_qualification,
    resolve_minor_application_case,
    resolve_minor_award,
)


class ApplicationResolutionTests(unittest.TestCase):
    @staticmethod
    def _rule_record(term="114-1", program="cs"):
        return {
            "record_id": f"rule-{term}-{program}",
            "record_type": "RULE_APPLICABILITY_RECORD",
            "evidence_state": "VERIFIED",
            "rule_version": "115.06",
            "curriculum_revision": "115.06",
            "effective_interval": {"start": "114-1", "end": "115-2"},
            "application_term": term,
            "target_program": program,
            "authority": "教務處",
            "evidence_reference": "official:rule-applicability",
        }

    @staticmethod
    def _department_record(term="114-1", program="cs", student_id="S001"):
        return {
            "record_id": f"department-{term}-{program}",
            "record_type": "DEPARTMENT_DECISION_RECORD",
            "evidence_state": "VERIFIED",
            "decision": "APPROVED",
            "application_term": term,
            "target_program": program,
            "authority": "資科系",
            "evidence_reference": "official:department-approval",
            "student_id": student_id,
        }

    @staticmethod
    def _registrar_record(term="114-1", effective_term="114-2", student_id="S001"):
        record = {
            "record_id": f"registrar-{term}",
            "record_type": "REGISTRAR_REGISTRATION_RECORD",
            "evidence_state": "VERIFIED",
            "registration_status": "REGISTERED",
            "application_term": term,
            "target_program": "cs",
            "authority": "教務處",
            "evidence_reference": "official:registrar-registration",
            "student_id": student_id,
        }
        if effective_term is not None:
            record["effective_term"] = effective_term
        return record

    def test_verified_university_notice_exposes_window_and_provenance(self):
        result = get_notice_resolution("114-1", target_program="資科")

        self.assertEqual(result["application_term"], "114-1")
        self.assertEqual(result["university_window"]["status"], "PASS")
        self.assertEqual(result["university_window"]["window"]["start"], "114-03-10")
        self.assertEqual(result["university_window"]["window"]["end"], "114-03-14")
        self.assertTrue(result["university_window"]["evidence_ids"])
        self.assertTrue(result["university_window"]["provenance"])

    def test_self_reported_approval_without_official_decision_is_unknown(self):
        result = resolve_application_case(
            {
                "application_term": "114-1",
                "target_program": "資科",
                "submitted_at": "2025-03-10T10:00:00",
                "department_approved": True,
            }
        )

        self.assertEqual(result["department_decision"]["status"], "UNKNOWN")
        self.assertEqual(result["status"], "UNKNOWN")

    def test_notice_conflicts_and_missing_terms_never_infer_from_adjacent_terms(self):
        conflict = get_notice_resolution("114-2", target_program="資科")
        self.assertEqual(conflict["university_window"]["state"], "CONFLICTED")
        self.assertEqual(conflict["university_window"]["status"], "UNKNOWN")

        missing = get_notice_resolution("115-2", target_program="資科")
        self.assertEqual(missing["university_window"]["state"], "MISSING")
        self.assertEqual(missing["university_window"]["status"], "UNKNOWN")
        self.assertIsNone(missing["university_window"]["window"])

    def test_113_2_cs_department_window_is_scoped_but_university_gate_unknown(self):
        result = get_notice_resolution("113-2", target_program="資科")

        self.assertEqual(result["university_window"]["status"], "UNKNOWN")
        self.assertEqual(result["department_window"]["status"], "PASS")
        self.assertEqual(result["department_window"]["state"], "VERIFIED")
        self.assertEqual(result["status"], "UNKNOWN")

    def test_non_cs_cannot_use_cs_department_notice(self):
        result = get_notice_resolution("113-2", target_program="數學")

        self.assertEqual(result["department_window"]["status"], "NOT_APPLICABLE")
        self.assertEqual(result["status"], "UNKNOWN")

    def test_111_1_eligibility_wording_conflict_stays_unknown(self):
        result = get_notice_resolution("111-1", target_program="資科")

        self.assertEqual(result["university_window"]["status"], "PASS")
        self.assertEqual(result["eligibility"]["status"], "UNKNOWN")
        self.assertGreaterEqual(len(result["eligibility"]["evidence_ids"]), 2)
        self.assertEqual(result["status"], "UNKNOWN")

    def test_self_reported_registrar_and_effective_term_never_become_active(self):
        result = resolve_application_case(
            {
                "application_term": "114-1",
                "target_program": "資科",
                "submitted_at": "2025-03-10T10:00:00",
                "registrar_registered": True,
                "effective_term": "114-2",
            }
        )

        self.assertNotEqual(result["activity"]["state"], "ACTIVE")
        self.assertNotEqual(result["activity"]["status"], "PASS")

    def test_verified_department_approval_without_registrar_is_unknown(self):
        department = self._department_record()
        result = resolve_application_case(
            {
                "application_term": "114-1",
                "target_program": "資科",
                "student_id": "S001",
                "submitted_at": "2025-03-10T10:00:00",
            },
            department_decision=department["record_id"],
            evidence_resolver=lambda record_id: department if record_id == department["record_id"] else None,
        )

        self.assertEqual(result["department_decision"]["status"], "PASS")
        self.assertEqual(result["registration"]["status"], "UNKNOWN")
        self.assertEqual(result["status"], "UNKNOWN")

    def test_verified_registration_without_effective_term_cannot_be_active(self):
        registrar = self._registrar_record(effective_term=None)
        result = resolve_application_case(
            {
                "application_term": "114-1",
                "target_program": "資科",
                "student_id": "S001",
                "submitted_at": "2025-03-10T10:00:00",
            },
            registrar_registration=registrar["record_id"],
            evidence_resolver=lambda record_id: registrar if record_id == registrar["record_id"] else None,
        )

        self.assertEqual(result["registration"]["status"], "PASS")
        self.assertEqual(result["activity"]["status"], "UNKNOWN")
        self.assertEqual(result["activity"]["code"], "EFFECTIVE_TERM_UNKNOWN")
        self.assertNotEqual(result["activity"]["state"], "ACTIVE")
        self.assertEqual(result["status"], "UNKNOWN")

    def test_113_2_cs_submission_can_use_department_window_but_case_stays_unknown(self):
        result = resolve_application_case(
            {
                "application_term": "113-2",
                "target_program": "資科",
                "submitted_at": "2024-10-07T10:00:00",
            }
        )

        self.assertEqual(result["university_window"]["status"], "UNKNOWN")
        self.assertEqual(result["department_window"]["status"], "PASS")
        self.assertEqual(result["submission"]["status"], "PASS")
        self.assertEqual(result["status"], "UNKNOWN")

    def test_non_cs_does_not_use_cs_department_window_for_submission(self):
        result = resolve_application_case(
            {
                "application_term": "113-2",
                "target_program": "數學",
                "submitted_at": "2024-10-07T10:00:00",
            }
        )

        self.assertEqual(result["department_window"]["status"], "NOT_APPLICABLE")
        self.assertEqual(result["submission"]["status"], "UNKNOWN")

    def test_missing_or_conflicted_university_notice_stays_unknown(self):
        for term in ("114-2", "115-2"):
            with self.subTest(term=term):
                result = resolve_application_case(
                    {
                        "application_term": term,
                        "target_program": "資科",
                        "submitted_at": "2026-01-01T10:00:00",
                    }
                )
                self.assertEqual(result["university_window"]["status"], "UNKNOWN")
                self.assertEqual(result["submission"]["status"], "UNKNOWN")
                self.assertEqual(result["status"], "UNKNOWN")

    def test_missing_rule_applicability_is_explicitly_unknown(self):
        result = resolve_application_case(
            {
                "application_term": "114-1",
                "target_program": "資科",
                "submitted_at": "2025-03-10T10:00:00",
            }
        )

        self.assertEqual(result["rule_version"]["status"], "UNKNOWN")
        self.assertEqual(result["rule_version"]["code"], "RULE_VERSION_UNKNOWN")
        self.assertEqual(result["gates"]["rule_version"], "UNKNOWN")

    def test_rule_version_display_alone_cannot_prove_curriculum_applicability(self):
        record = self._rule_record()
        record.pop("curriculum_revision")
        record.pop("effective_interval")
        result = resolve_application_case(
            {
                "application_term": "114-1",
                "target_program": "資科",
                "submitted_at": "2025-03-10T10:00:00",
            },
            rule_applicability=record["record_id"],
            evidence_resolver=lambda record_id: record if record_id == record["record_id"] else None,
        )

        self.assertEqual(result["rule_version"]["status"], "UNKNOWN")
        self.assertEqual(result["rule_version"]["code"], "RULE_VERSION_UNKNOWN")
        self.assertIn("revision", result["rule_version"]["reason"])

    def test_subject_bound_active_qualification_can_prove_current_status_without_history_date(self):
        record = {
            "record_id": "qualification-current",
            "record_type": "FORMAL_QUALIFICATION_RECORD",
            "evidence_state": "VERIFIED",
            "qualification_state": "ACTIVE",
            "subject_ref": "subject-current",
            "target_program": "cs",
            "authority": "教務處",
            "evidence_reference": "official:qualification-current",
        }

        result = resolve_formal_qualification(
            record["record_id"],
            subject_ref="subject-current",
            target_program="資科",
            evidence_resolver=lambda record_id: record if record_id == record["record_id"] else None,
        )

        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["qualification_state"], "ACTIVE")
        self.assertTrue(result["is_official"])

    def test_application_event_is_separate_from_submission_date_evidence(self):
        record = {
            "record_id": "application-event-114-1",
            "record_type": "APPLICATION_EVENT_RECORD",
            "evidence_state": "VERIFIED",
            "subject_ref": "subject-current",
            "application_term": "114-1",
            "target_program": "cs",
            "curriculum_revision": "115.06",
            "effective_interval": {"start": "114-1", "end": "115-2"},
            "authority": "教務處",
            "evidence_reference": "official:application-event",
        }

        result = resolve_application_case(
            {
                "application_term": "114-1",
                "target_program": "資科",
                "subject_ref": "subject-current",
                "curriculum_revision": "115.06",
            },
            application_event_evidence_id=record["record_id"],
            evidence_resolver=lambda record_id: record if record_id == record["record_id"] else None,
        )

        self.assertEqual(result["application_event"]["status"], "PASS")
        self.assertEqual(result["submission"]["code"], "SUBMISSION_UNKNOWN")
        self.assertEqual(result["status"], "UNKNOWN")

    def test_submission_outside_verified_window_is_fail(self):
        result = resolve_application_case(
            {
                "application_term": "114-1",
                "target_program": "資科",
                "submitted_at": "2025-03-20T10:00:00",
            }
        )

        self.assertEqual(result["submission"]["status"], "FAIL")
        self.assertEqual(result["submission"]["code"], "SUBMISSION_OUTSIDE_WINDOW")
        self.assertEqual(result["status"], "FAIL")

    def test_missing_submitted_at_is_submission_unknown(self):
        result = resolve_application_case(
            {"application_term": "114-1", "target_program": "資科"}
        )

        self.assertEqual(result["submission"]["status"], "UNKNOWN")
        self.assertEqual(result["submission"]["code"], "SUBMISSION_UNKNOWN")

    def test_verified_application_path_can_pass_but_does_not_grant_formal_award(self):
        rule = self._rule_record()
        department = self._department_record()
        registrar = self._registrar_record()
        records = {record["record_id"]: record for record in (rule, department, registrar)}
        result = resolve_application_case(
            {
                "application_term": "114-1",
                "target_program": "資科",
                "student_id": "S001",
                "submitted_at": "2025-03-10T10:00:00",
                "graduation_verdict": "PASS",
            },
            rule_applicability=rule["record_id"],
            department_decision=department["record_id"],
            registrar_registration=registrar["record_id"],
            evidence_resolver=lambda record_id: records.get(record_id),
        )

        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["gates"]["rule_version"], "PASS")
        self.assertEqual(result["gates"]["department_decision"], "PASS")
        self.assertEqual(result["gates"]["registration"], "PASS")
        self.assertNotEqual(result["formal_award"]["award_state"], "GRANTED")
        self.assertEqual(result["formal_award"]["status"], "UNKNOWN")

    def test_exact_official_formal_award_record_can_grant_independently(self):
        award = {
            "record_id": "award-114-cs-001",
            "record_type": FORMAL_AWARD_RECORD,
            "evidence_state": "VERIFIED",
            "award_state": "GRANTED",
            "student_id": "S001",
            "target_program": "cs",
            "application_term": "114-1",
            "effective_term": "114-2",
            "authority": "教務處",
            "evidence_reference": "official:formal-award:114-2",
        }
        result = resolve_formal_award(
            "award-114-cs-001",
            evidence_resolver=lambda record_id: award if record_id == "award-114-cs-001" else None,
            student_id="S001",
            target_program="資科",
        )

        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["award_state"], "GRANTED")
        self.assertTrue(result["is_official"])
        self.assertIn("award-114-cs-001", result["evidence_ids"])

    def test_unverified_or_wrong_formal_award_record_cannot_grant(self):
        for record in (
            {
                "record_id": "self-report",
                "record_type": FORMAL_AWARD_RECORD,
                "award_state": "GRANTED",
            },
            {
                "record_id": "wrong-type",
                "record_type": "GRADUATION_VERDICT",
                "evidence_state": "VERIFIED",
                "award_state": "GRANTED",
                "authority": "教務處",
                "evidence_reference": "official:wrong-type",
            },
            {
                "record_id": "not-granted",
                "record_type": FORMAL_AWARD_RECORD,
                "evidence_state": "VERIFIED",
                "award_state": "PENDING",
                "authority": "教務處",
                "evidence_reference": "official:pending",
            },
        ):
            with self.subTest(record=record["record_id"]):
                result = resolve_formal_award(record)
                self.assertNotEqual(result["award_state"], "GRANTED")
                self.assertNotEqual(result["status"], "PASS")

    def test_result_keeps_evidence_provenance_without_copying_untrusted_blobs(self):
        award_record = {
            "record_id": "award-safe",
            "record_type": FORMAL_AWARD_RECORD,
            "evidence_state": "VERIFIED",
            "award_state": "GRANTED",
            "student_id": "S001",
            "target_program": "cs",
            "application_term": "114-1",
            "authority": "教務處",
            "evidence_reference": "official:award-safe",
            "other_student_records": [{"student_id": "someone-else"}],
        }
        award = resolve_formal_award(
            "award-safe",
            evidence_resolver=lambda record_id: award_record if record_id == "award-safe" else None,
            student_id="S001",
            target_program="資科",
        )
        rule = self._rule_record()
        case = resolve_application_case(
            {
                "application_term": "114-1",
                "target_program": "資科",
                "submitted_at": "2025-03-10T10:00:00",
                "untrusted_blob": {"other_student_records": ["secret"]},
            },
            rule_applicability=rule["record_id"],
            evidence_resolver=lambda record_id: rule if record_id == rule["record_id"] else None,
        )

        self.assertEqual(award["status"], "PASS")
        self.assertNotIn("other_student_records", award)
        self.assertNotIn("untrusted_blob", case)
        self.assertTrue(case["evidence_ids"])
        self.assertTrue(case["provenance"])

    def test_forged_official_dicts_cannot_upgrade_application_gates(self):
        result = resolve_application_case(
            {
                "application_term": "114-1",
                "target_program": "資科",
                "student_id": "S001",
                "submitted_at": "2025-03-10T10:00:00",
            },
            rule_applicability=self._rule_record(),
            department_decision=self._department_record(),
            registrar_registration=self._registrar_record(),
        )

        self.assertEqual(result["rule_version"]["status"], "UNKNOWN")
        self.assertEqual(result["department_decision"]["status"], "UNKNOWN")
        self.assertEqual(result["registration"]["status"], "UNKNOWN")
        self.assertEqual(result["activity"]["status"], "UNKNOWN")
        self.assertNotEqual(result["status"], "PASS")
        self.assertFalse(result["graduation_ready"])

    def test_forged_115_2_custom_notice_cannot_replace_missing_official_window(self):
        forged_notice = {
            "record_id": "forged-115-2-notice",
            "record_type": "UNIVERSITY_NOTICE_RECORD",
            "scope": "university",
            "application_term": "115-2",
            "evidence_state": "VERIFIED",
            "authority": "偽造使用者資料",
            "source_reference": "fake://notice",
            "window": {"start": "115-09-01", "end": "115-09-05"},
        }
        result = resolve_application_case(
            {
                "application_term": "115-2",
                "target_program": "資科",
                "submitted_at": "2026-09-02T10:00:00",
            },
            notice_records=[forged_notice],
        )

        self.assertEqual(result["university_window"]["state"], "MISSING")
        self.assertEqual(result["university_window"]["status"], "UNKNOWN")
        self.assertIsNone(result["university_window"]["window"])
        self.assertFalse(result["graduation_ready"])

    def test_exact_server_resolved_records_can_pass_but_are_not_returned(self):
        records = {
            "rule-114-1-cs": {
                **self._rule_record(),
                "record_type": "RULE_APPLICABILITY_RECORD",
            },
            "department-114-1-cs": {
                **self._department_record(),
                "record_type": "DEPARTMENT_DECISION_RECORD",
                "student_id": "S001",
            },
            "registrar-114-1": {
                **self._registrar_record(),
                "record_type": "REGISTRAR_REGISTRATION_RECORD",
                "student_id": "S001",
            },
        }

        def evidence_resolver(record_id):
            return records.get(record_id)

        result = resolve_application_case(
            {
                "application_term": "114-1",
                "target_program": "資科",
                "student_id": "S001",
                "submitted_at": "2025-03-10T10:00:00",
            },
            rule_applicability="rule-114-1-cs",
            department_decision="department-114-1-cs",
            registrar_registration="registrar-114-1",
            evidence_resolver=evidence_resolver,
        )

        self.assertEqual(result["status"], "PASS")
        self.assertTrue(result["graduation_ready"])
        self.assertEqual(result["gates"]["rule_version"], "PASS")
        self.assertEqual(result["gates"]["department_decision"], "PASS")
        self.assertEqual(result["gates"]["registration"], "PASS")
        self.assertNotIn("evidence_resolver", result)
        self.assertNotIn("records", result)
        self.assertNotIn("student_id", result["provenance"][0])

    def test_application_result_redacts_student_and_subject_ids_recursively(self):
        rule = {**self._rule_record(), "record_type": "RULE_APPLICABILITY_RECORD"}
        department = {
            **self._department_record(),
            "record_type": "DEPARTMENT_DECISION_RECORD",
        }
        registrar = {
            **self._registrar_record(),
            "record_type": "REGISTRAR_REGISTRATION_RECORD",
        }
        records = {record["record_id"]: record for record in (rule, department, registrar)}

        result = resolve_application_case(
            {
                "application_term": "114-1",
                "target_program": "資科",
                "student_id": "S001",
                "subject_id": "S001",
                "submitted_at": "2025-03-10T10:00:00",
            },
            rule_applicability=rule["record_id"],
            department_decision=department["record_id"],
            registrar_registration=registrar["record_id"],
            evidence_resolver=lambda record_id: records.get(record_id),
        )

        self.assertEqual(result["status"], "PASS")

        def assert_no_identity_keys(value):
            if isinstance(value, dict):
                self.assertNotIn("student_id", value)
                self.assertNotIn("subject_id", value)
                for child in value.values():
                    assert_no_identity_keys(child)
            elif isinstance(value, (list, tuple)):
                for child in value:
                    assert_no_identity_keys(child)

        assert_no_identity_keys(result)

    def test_resolver_mismatch_by_id_student_term_program_track_or_type_is_unknown(self):
        base = {
            "record_id": "rule-114-1-cs",
            "record_type": "RULE_APPLICABILITY_RECORD",
            "evidence_state": "VERIFIED",
            "rule_version": "115.06",
            "application_term": "114-1",
            "target_program": "cs",
            "authority": "教務處",
            "evidence_reference": "official:rule",
        }
        variants = {
            "id": {**base, "record_id": "different-id"},
            "term": {**base, "application_term": "114-2"},
            "program": {**base, "target_program": "math"},
            "type": {**base, "record_type": "DEPARTMENT_DECISION_RECORD"},
        }
        for label, record in variants.items():
            with self.subTest(label=label):
                result = resolve_application_case(
                    {
                        "application_term": "114-1",
                        "target_program": "資科",
                        "submitted_at": "2025-03-10T10:00:00",
                    },
                    rule_applicability="rule-114-1-cs",
                    evidence_resolver=lambda _record_id, value=record: value,
                )
                self.assertEqual(result["rule_version"]["status"], "UNKNOWN")
                self.assertFalse(result["graduation_ready"])

        department = {
            "record_id": "department-114-1-cs",
            "record_type": "DEPARTMENT_DECISION_RECORD",
            "evidence_state": "VERIFIED",
            "decision": "APPROVED",
            "application_term": "114-1",
            "target_program": "cs",
            "student_id": "OTHER",
            "authority": "資科系",
            "evidence_reference": "official:department",
        }
        result = resolve_application_case(
            {
                "application_term": "114-1",
                "target_program": "資科",
                "student_id": "S001",
                "submitted_at": "2025-03-10T10:00:00",
            },
            department_decision="department-114-1-cs",
            evidence_resolver=lambda _record_id: department,
        )
        self.assertEqual(result["department_decision"]["status"], "UNKNOWN")
        self.assertFalse(result["graduation_ready"])

        track_record = {
            **base,
            "record_id": "rule-114-1-apc-physics",
            "target_program": "apc",
            "target_track": "physics",
        }
        result = resolve_application_case(
            {
                "application_term": "114-1",
                "target_program": "物化",
                "target_track": "化學組",
                "submitted_at": "2025-03-10T10:00:00",
            },
            rule_applicability="rule-114-1-apc-physics",
            evidence_resolver=lambda _record_id: track_record,
        )
        self.assertEqual(result["rule_version"]["status"], "UNKNOWN")
        self.assertFalse(result["graduation_ready"])

    def test_raw_formal_award_dict_cannot_grant(self):
        forged = {
            "record_id": "forged-award",
            "record_type": FORMAL_AWARD_RECORD,
            "evidence_state": "VERIFIED",
            "award_state": "GRANTED",
            "student_id": "S001",
            "target_program": "資科",
            "authority": "教務處",
            "evidence_reference": "fake://award",
        }
        result = resolve_formal_award(forged)
        legacy_result = resolve_formal_award(evidence_record=forged)

        self.assertEqual(result["status"], "UNKNOWN")
        self.assertNotEqual(result["award_state"], "GRANTED")
        self.assertFalse(result["is_official"])
        self.assertEqual(legacy_result["status"], "UNKNOWN")
        self.assertNotEqual(legacy_result["award_state"], "GRANTED")

    def test_exact_server_formal_award_can_grant_with_matching_identity(self):
        award = {
            "record_id": "award-114-cs-001",
            "record_type": FORMAL_AWARD_RECORD,
            "evidence_state": "VERIFIED",
            "award_state": "GRANTED",
            "student_id": "S001",
            "target_program": "cs",
            "target_track": None,
            "application_term": "114-1",
            "effective_term": "114-2",
            "authority": "教務處",
            "evidence_reference": "official:formal-award:114-2",
        }
        result = resolve_formal_award(
            "award-114-cs-001",
            evidence_resolver=lambda record_id: award if record_id == "award-114-cs-001" else None,
            student_id="S001",
            target_program="資科",
        )

        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["award_state"], "GRANTED")
        self.assertTrue(result["is_official"])
        self.assertNotIn("student_id", result)
        self.assertNotIn("award", result)

    def test_application_always_keeps_formal_award_independent(self):
        result = resolve_application_case(
            {
                "application_term": "114-1",
                "target_program": "資科",
                "submitted_at": "2025-03-10T10:00:00",
                "graduation_verdict": "PASS",
            }
        )

        self.assertEqual(result["formal_award"]["status"], "UNKNOWN")
        self.assertNotEqual(result["formal_award"]["award_state"], "GRANTED")

    def test_minor_evidence_must_bind_the_request_subject_ref(self):
        base = {
            "evidence_state": "VERIFIED",
            "authority": "教務處",
            "evidence_reference": "official:minor-evidence",
            "record_type": "MINOR_APPROVAL",
            "application_term": "114-1",
            "target_program": "cs",
            "decision": "APPROVED",
        }
        records = {
            "missing-subject": {"record_id": "missing-subject", **base},
            "wrong-subject": {"record_id": "wrong-subject", **base, "subject_ref": "subject-other"},
        }

        for record_id in records:
            with self.subTest(record_id=record_id):
                result = resolve_minor_application_case(
                    {
                        "application_term": "114-1",
                        "target_program": "cs",
                        "subject_ref": "subject-current",
                    },
                    department_approval=record_id,
                    evidence_resolver=lambda requested, values=records: values.get(requested),
                )

                self.assertEqual(result["department_decision"]["status"], "UNKNOWN")
                self.assertFalse(result["can_pass"])

    def test_minor_evidence_without_request_subject_ref_is_unknown(self):
        record = {
            "record_id": "bound-approval",
            "record_type": "MINOR_APPROVAL",
            "evidence_state": "VERIFIED",
            "authority": "教務處",
            "evidence_reference": "official:minor-approval",
            "application_term": "114-1",
            "target_program": "cs",
            "subject_ref": "subject-current",
            "decision": "APPROVED",
        }
        result = resolve_minor_application_case(
            {"application_term": "114-1", "target_program": "cs"},
            department_approval="bound-approval",
            evidence_resolver=lambda requested: record if requested == "bound-approval" else None,
        )

        self.assertEqual(result["department_decision"]["status"], "UNKNOWN")
        self.assertFalse(result["can_pass"])

    def test_minor_evidence_requires_request_term_and_target_program(self):
        record = {
            "record_id": "bound-approval-context",
            "record_type": "MINOR_APPROVAL",
            "evidence_state": "VERIFIED",
            "authority": "系所",
            "evidence_reference": "official:minor-approval-context",
            "application_term": "114-1",
            "target_program": "cs",
            "subject_ref": "subject-current",
            "decision": "APPROVED",
        }
        def resolver(requested):
            return record if requested == "bound-approval-context" else None

        for context in (
            {"target_program": "cs", "subject_ref": "subject-current"},
            {"application_term": "114-1", "subject_ref": "subject-current"},
        ):
            with self.subTest(context=context):
                result = resolve_minor_application_case(
                    context,
                    department_approval="bound-approval-context",
                    evidence_resolver=resolver,
                )

                self.assertEqual(result["department_decision"]["status"], "UNKNOWN")
                self.assertFalse(result["can_pass"])

    def test_minor_missing_explicit_decision_does_not_infer_approval_from_record_type(self):
        record = {
            "record_id": "implicit-approval",
            "record_type": "MINOR_APPROVAL",
            "evidence_state": "VERIFIED",
            "authority": "教務處",
            "evidence_reference": "official:minor-approval",
            "application_term": "114-1",
            "target_program": "cs",
            "subject_ref": "subject-current",
        }
        result = resolve_minor_application_case(
            {
                "application_term": "114-1",
                "target_program": "cs",
                "subject_ref": "subject-current",
            },
            department_approval="implicit-approval",
            evidence_resolver=lambda requested: record if requested == "implicit-approval" else None,
        )

        self.assertEqual(result["department_decision"]["status"], "UNKNOWN")
        self.assertFalse(result["can_pass"])

    def test_minor_award_requires_subject_term_and_explicit_granted_decision(self):
        base = {
            "evidence_state": "VERIFIED",
            "authority": "教務處",
            "evidence_reference": "official:minor-award",
            "record_type": "MINOR_AWARD",
            "target_program": "cs",
        }
        records = {
            "missing-subject": {"record_id": "missing-subject", **base, "application_term": "114-1", "award_state": "GRANTED"},
            "wrong-subject": {"record_id": "wrong-subject", **base, "application_term": "114-1", "subject_ref": "subject-other", "award_state": "GRANTED"},
            "missing-term": {"record_id": "missing-term", **base, "subject_ref": "subject-current", "award_state": "GRANTED"},
            "implicit-grant": {"record_id": "implicit-grant", **base, "application_term": "114-1", "subject_ref": "subject-current"},
        }

        for record_id in records:
            with self.subTest(record_id=record_id):
                result = resolve_minor_award(
                    record_id,
                    evidence_resolver=lambda requested, values=records: values.get(requested),
                    target_program="cs",
                    application_term="114-1",
                    subject_ref="subject-current",
                )

                self.assertEqual(result["status"], "UNKNOWN")
                self.assertNotEqual(result["award_state"], "GRANTED")

    def test_bound_minor_application_and_award_with_explicit_states_still_pass(self):
        records = {
            "approval": {
                "record_id": "approval",
                "record_type": "MINOR_APPROVAL",
                "evidence_state": "VERIFIED",
                "authority": "系所",
                "evidence_reference": "official:minor-approval",
                "application_term": "114-1",
                "target_program": "cs",
                "subject_ref": "subject-current",
                "decision": "APPROVED",
            },
            "registration": {
                "record_id": "registration",
                "record_type": "MINOR_REGISTRATION",
                "evidence_state": "VERIFIED",
                "authority": "教務處",
                "evidence_reference": "official:minor-registration",
                "application_term": "114-1",
                "target_program": "cs",
                "subject_ref": "subject-current",
                "registration_status": "REGISTERED",
            },
            "award": {
                "record_id": "award",
                "record_type": "MINOR_AWARD",
                "evidence_state": "VERIFIED",
                "authority": "教務處",
                "evidence_reference": "official:minor-award",
                "application_term": "114-1",
                "target_program": "cs",
                "subject_ref": "subject-current",
                "award_state": "GRANTED",
            },
        }
        def resolver(requested):
            return records.get(requested)

        application = resolve_minor_application_case(
            {
                "application_term": "114-1",
                "target_program": "cs",
                "subject_ref": "subject-current",
            },
            department_approval="approval",
            registrar_registration="registration",
            evidence_resolver=resolver,
        )
        award = resolve_minor_award(
            "award",
            evidence_resolver=resolver,
            target_program="cs",
            application_term="114-1",
            subject_ref="subject-current",
        )

        self.assertEqual(application["status"], "PASS")
        self.assertEqual(award["status"], "PASS")
        self.assertEqual(award["award_state"], "GRANTED")

    def test_minor_gate_states_are_specific_to_their_application_event(self):
        base = {
            "record_id": "minor-event-state",
            "evidence_state": "VERIFIED",
            "authority": "官方單位",
            "source_reference": "official:minor-event-state",
            "application_term": "114-1",
            "target_program": "cs",
            "subject_ref": "subject-current",
        }
        cases = (
            (
                "department",
                "department_approval",
                {"record_type": "MINOR_APPROVAL", "decision": "QUALIFIED"},
            ),
            (
                "registrar",
                "registrar_registration",
                {"record_type": "MINOR_REGISTRATION", "decision": "APPROVED"},
            ),
            (
                "registrar_active",
                "registrar_registration",
                {"record_type": "MINOR_REGISTRATION", "registration_status": "ACTIVE"},
            ),
            (
                "qualification",
                "formal_qualification",
                {"record_type": "MINOR_QUALIFICATION", "qualification_status": "APPROVED"},
            ),
            (
                "qualification_granted",
                "formal_qualification",
                {"record_type": "MINOR_QUALIFICATION", "qualification_state": "GRANTED"},
            ),
        )

        for record_id, gate_name, state in cases:
            with self.subTest(record_id=record_id):
                record = {**base, "record_id": record_id, **state}
                result = resolve_minor_application_case(
                    {
                        "application_term": "114-1",
                        "target_program": "cs",
                        "subject_ref": "subject-current",
                    },
                    department_approval=record_id if gate_name == "department_approval" else None,
                    registrar_registration=record_id if gate_name == "registrar_registration" else None,
                    formal_qualification=record_id if gate_name == "formal_qualification" else None,
                    evidence_resolver=lambda requested, current=record: current if requested == record_id else None,
                )

                self.assertEqual(result["gates"][gate_name], "UNKNOWN")
                result_key = "department_decision" if gate_name == "department_approval" else gate_name
                self.assertNotEqual(result[result_key]["status"], "PASS")


if __name__ == "__main__":
    unittest.main()
