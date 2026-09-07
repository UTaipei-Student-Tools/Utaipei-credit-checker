from copy import deepcopy
from bs4 import BeautifulSoup
from requirement_layout import grouped_requirements_markup, requirement_section, RELIEF_CSS
from requirement_layout import deficit_markup


def test_separates_secondary_without_recounting_or_changing_rows():
    items = [dict(requirement_id="target:114:cs:C", name="C程式設計", effective_credits="3"),
             dict(requirement_id="primary:113:earth:satellite", name="衛星遙測學", effective_credits="2"),
             dict(requirement_id="target:114:cs:Java", name="Java程式設計", effective_credits="0")]
    view = {"requirements": items, "context": "unchanged"}
    before = deepcopy(view)
    seen = []
    def render(subset):
        seen.extend(subset["requirements"])
        return "".join(f'<p>{x["name"]}:{x["effective_credits"]}</p>' for x in subset["requirements"])
    soup = BeautifulSoup(grouped_requirements_markup(view, render), "html.parser")
    primary = soup.select_one('.snapshot-requirement-section--primary')
    secondary = soup.select_one('.snapshot-requirement-section--secondary')
    assert "衛星遙測學:2" in primary.text and "C程式" not in primary.text
    assert "C程式設計:3" in secondary.text and "Java程式設計:0" in secondary.text
    assert view == before and len(seen) == len(items)


def test_empty_secondary_is_not_shown_and_minor_is_not_mislabeled():
    assert requirement_section({"requirement_id": "minor:113:cs:course"}) == "minor"
    assert "<h3" not in grouped_requirements_markup({"requirements": []}, lambda _: "")
    assert "height: auto" in RELIEF_CSS
    assert "190px" not in RELIEF_CSS and "254px" not in RELIEF_CSS


def test_real_requirement_renderer_preserves_expanders_in_separate_sections():
    from snapshot_renderer import _requirements_markup
    view = {"requirements": [
        {"requirement_id": "primary:113:earth:course", "name": "主修課程"},
        {"requirement_id": "target:114:cs:course", "name": "雙主修課程"}]}
    soup = BeautifulSoup(_requirements_markup(view), "html.parser")
    assert len(soup.select('.snapshot-requirement-expander')) == 2
    assert soup.select_one('.snapshot-requirement-section--secondary details > summary')


def test_each_category_has_card_and_red_footer_uses_given_deficit():
    items = [dict(requirement_id='p1', name='共同選修', bucket='ge_common_elective', deficit='2', status='FAIL'),
             dict(requirement_id='p2', name='地質學', bucket='地球環境:compulsory', deficit='0', status='PASS'),
             dict(requirement_id='p3', name='自由選修', bucket='free_elective', deficit='15', status='FAIL')]
    soup = BeautifulSoup(grouped_requirements_markup({'requirements':items},lambda _: ''),'html.parser')
    assert [h.text for h in soup.select('.snapshot-category > h4')] == ['通識課程','地球環境領域必修','自由選修']
    footers = soup.select('.snapshot-category-deficit')
    assert len(footers) == 2
    assert '尚缺 2 學分' in footers[0].text
    assert '尚缺 15 學分' in footers[1].text
    assert 'background: #a52232; color: #fff' in RELIEF_CSS


def test_deficit_disclosure_threshold_and_pending_not_counted():
    courses = [dict(course_id=str(i),course_name=f'課程{i}',status='NOT_ATTEMPTED') for i in range(3)]
    item = dict(name='領域選修',bucket='domain_elective',deficit='6',status='FAIL',courses=courses)
    before = deepcopy(item)
    soup = BeautifulSoup(deficit_markup([item]),'html.parser')
    assert soup.select_one('details.snapshot-category-deficit > summary')
    assert '查看未修課程（3 門）' in soup.text
    assert '可選課程，非全部必修' in soup.text
    assert item == before
    item['courses'] = courses[:2] + [dict(course_name='在修課',status='IN_PROGRESS')]
    output = deficit_markup([item])
    assert '<details' not in output and '在修課' not in output
    assert '課程0' in output and '課程1' in output


def test_deficit_courses_are_unique_and_escaped():
    item = dict(name='必修',deficit='3',status='FAIL',courses=[dict(course_name='<script>bad</script>',status='NOT_ATTEMPTED')]*3)
    output = deficit_markup([item])
    assert '<details' not in output and '<script>' not in output
    assert '&lt;script&gt;' in output


def test_completed_alternative_does_not_inflate_missing_course_count():
    passed = dict(name='完成擇一', bucket='common_alternative_1', status='PASS', deficit='0',
                  courses=[dict(course_name=n,status='NOT_ATTEMPTED') for n in ('未選甲','未選乙')])
    missing = dict(name='必修',status='FAIL',deficit='3',courses=[dict(course_name='尚缺科目',status='NOT_ATTEMPTED')])
    output = deficit_markup([passed,missing])
    assert '<details' not in output
    assert '未選甲' not in output and '未選乙' not in output
    assert '尚缺科目' in output
