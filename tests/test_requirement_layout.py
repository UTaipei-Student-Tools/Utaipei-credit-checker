from copy import deepcopy
from bs4 import BeautifulSoup
from requirement_layout import grouped_requirements_markup, requirement_section, RELIEF_CSS


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
