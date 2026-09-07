from workspace_ui import navigation_markup, workspace_css, section_markup


def test_navigation_is_local_and_does_not_replace_form_logic():
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(navigation_markup(),'html.parser')
    links = soup.select('nav a')
    assert links == []
    assert '本學期查課' in section_markup('course-lookup', '本學期查課')
    assert not soup.select('script')


def test_dimension_motion_has_accessible_static_fallback():
    css = workspace_css()
    assert 'animation-timeline:scroll(nearest)' in css
    assert 'prefers-reduced-motion:reduce' in css
    assert 'pointer-events:none' in css
    assert 'height: 254px' not in css
