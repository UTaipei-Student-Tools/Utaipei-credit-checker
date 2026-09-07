from copy import deepcopy
from decimal import Decimal
import pytest
from confirmed_rules import validate_confirmed_rules, verify_sources, route_confirmed_attempts
from curriculum_registry import get_curriculum, _RULES
from allocation_engine import CourseAttempt, RequirementSpec, _direct_match


def test_confirmed_contract_and_source_integrity():
    assert verify_sources()
    for cid in ('primary:113:earth:earth_environment', 'primary:113:earth:life_science', 'target:double_major:114:cs'):
        row = get_curriculum(cid)
        assert row['user_confirmation']['locked']
        assert '已確認資料' in row['user_confirmation']['label']
        if ':earth:' in cid:
            assert not any('service_learning' in r['requirement_id'] for r in row['non_credit_requirements'])
            assert any('life_guidance' in r['requirement_id'] for r in row['non_credit_requirements'])


def test_changed_confirmed_rule_fails_closed():
    rules = deepcopy(_RULES)
    rules['handbooks']['113']['earth_life_major']['total_req'] = 999
    with pytest.raises(ValueError, match='已確認'):
        validate_confirmed_rules(rules, get_curriculum('primary:113:earth:earth_environment'))


def test_specific_classification_cannot_be_spent_as_free_or_other():
    reqs = (RequirementSpec('domain', bucket='domain_elective', eligible_pool_ids=('domain',), credits_required=20),
            RequirementSpec('other', bucket='department_professional', eligible_pool_ids=('other',), credits_required=27),
            RequirementSpec('free', bucket='free_elective', eligible_pool_ids=('free',), credits_required=15))
    a = CourseAttempt('a','a','地球物理通論',3,3,pool_ids=('domain','other','free'))
    routed, = route_confirmed_attempts('primary:113:earth:earth_environment', (a,), reqs)
    assert routed.pool_ids == ('domain',)
    assert routed.earned_credits == Decimal(3)
    assert route_confirmed_attempts('primary:114:earth:earth_environment', (a,), reqs) == (a,)


def test_unrelated_unknown_component_does_not_block_other_requirements():
    a = CourseAttempt('a','a','無關課程',3,3,course_kind='UNKNOWN')
    req = RequirementSpec('other', eligible_course_ids=('b',), allowed_course_kinds=('LECTURE',))
    assert _direct_match(a,req) is False


def test_confirmed_physics_alias_keeps_department_membership():
    from graduation_service import _compile_attempts, _compile_requirements
    from input_confirmation import start_confirmation
    reqs, metadata, _ = _compile_requirements(get_curriculum('primary:113:earth:earth_environment'), scope='primary')
    rows = start_confirmation([dict(course_name='普通物理(含實驗)', credits=3, earned_credits=3,
                                  status='已修', term='113-1', course_type='選修')]).rows
    attempts, _ = _compile_attempts(rows, metadata)
    assert attempts[0].identity_status == 'VERIFIED'
    assert any(p.endswith(':department_professional') for p in attempts[0].pool_ids)
    routed = route_confirmed_attempts('primary:113:earth:earth_environment', attempts, reqs)
    assert not any(p.endswith(':free_elective') for p in routed[0].pool_ids)
