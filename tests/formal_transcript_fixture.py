"""Synthetic completed transcript using public Earth111 handbook/catalog courses."""
from __future__ import annotations

from curriculum_registry import get_curriculum
from public_course_catalog import load_public_course_catalog, resolve_public_evidence


def build_rows():
    record = get_curriculum('primary:111:earth:earth_environment')
    catalog = load_public_course_catalog()
    rows = []
    used = set()

    def add(name, credits, *, term='111-1', code='', kind=''):
        if credits and name in used:
            raise AssertionError(('duplicate synthetic course', name))
        if credits:
            used.add(name)
        rows.append(dict(course_code=code, course_name=name, credits=float(credits),
                         earned_credits=float(credits), status='COMPLETED', term=term, course_type=kind))

    def take(candidates, target):
        unique = {}
        for candidate in candidates:
            name = candidate.get('name') or candidate.get('course_name')
            if name in used or not float(candidate['credits']):
                continue
            unique.setdefault(name, candidate)
        dp = {0: []}
        for c in unique.values():
            credits = round(float(c['credits']) * 10)
            for total, choices in list(dp.items())[::-1]:
                if total + credits <= target * 10:
                    dp.setdefault(total + credits, choices + [c])
        assert target * 10 in dp, ('cannot select exact synthetic sum', target)
        return dp[target * 10]

    # Real named compulsory requirements, excluding the quota descriptors.
    for c in record['course_catalog']:
        if float(c.get('credits') or 0) > 0 and c.get('component') != 'quota':
            add(c['name'], c['credits'], kind=c.get('component', ''))

    pools = record['course_pools']
    for bucket in ('common_alternative_1', 'common_alternative_2', 'common_elective',
                   'domain_elective', 'department_professional'):
        pool = next(p for p in pools.values() if p['bucket'] == bucket)
        for c in take(pool['candidate_courses'], int(pool['required_credits'])):
            add(c['name'], c['credits'], kind=c.get('component', ''))

    # Remaining actual Earth electives can fill free credit with college evidence.
    candidates = [c for p in pools.values() if p['bucket'] in ('common_elective', 'domain_elective', 'department_professional')
                  for c in p['candidate_courses']]
    for c in take(candidates, 15):
        add(c['name'], c['credits'], kind=c.get('component', ''))

    # Select exact public GE offerings, including one official IT-listed course.
    public = [dict(c) for c in catalog.courses if c.get('active') and c.get('official_category')]
    it_candidates = [c for c in public if c['term'] == '112-1' and float(c['credits']) >= 2
                     and 'university_it_direct_completion' in resolve_public_evidence(
                         {'term': c['term'], 'course_name': c['course_name'], 'credits': c['credits']}, catalog=catalog
                     ).verified_memberships]
    it = next(c for c in it_candidates if c['official_category'] in ('共同選修', '自然、生命與科技領域'))
    add(it['course_name'], it['credits'], term=it['term'])
    category_targets = {'藝術與美感': 4, '人文與文化思考': 4, '公民素養與社會探索': 4,
                        '自然、生命與科技': 4, '共同選修類': 4}
    for category, target in category_targets.items():
        def own(c):
            return c['official_category'].removesuffix('類').removesuffix('領域') == category.removesuffix('類')
        target -= int(it['credits']) if own(it) else 0
        candidates = [c for c in public if c['term'] in ('111-1', '111-2', '112-1') and own(c)]
        for c in take(candidates, target):
            add(c['course_name'], c['credits'], term=c['term'])

    pe_codes = set()
    terms = ['111-1', '111-2', '112-1', '112-2', '113-1', '113-2', '114-1', '114-2']
    for term in terms[:4]:
        c = next(c for c in public if c['term'] == term and c['official_category'] == '體育類'
                 and c['official_course_code'] not in pe_codes and float(c['credits']) == 0)
        pe_codes.add(c['official_course_code'])
        add(c['course_name'], 0, term=term)
    for code, eligible_terms in [('28030', terms), ('07140', terms[:2])]:
        for term in eligible_terms:
            c = next(c for c in catalog.courses if c['term'] == term and c['official_course_code'] == code and c.get('active'))
            add(c['course_name'], 0, term=term)
    return rows


