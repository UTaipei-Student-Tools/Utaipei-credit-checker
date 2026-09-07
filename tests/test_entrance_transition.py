from welcome import _scroll_transition_script


def test_entry_scroll_is_one_shot_cancellable_and_reduced_motion_safe():
    script = _scroll_transition_script('workspace', 'test-token')
    assert '.st-key-dimension_toolbar' in script
    assert '__utaipeiEntranceScroll === token' in script
    assert '850' in script
    assert 'const begin = host.performance.now()' in script
    assert 'prefers-reduced-motion: reduce' in script
    assert "['wheel', 'touchstart', 'keydown']" in script
    assert 'scrollTop' in script
    assert 'session_state' not in script
    assert "root.classList.add('utaipei-cover-away')" in script
    assert "root.classList.remove('utaipei-cover-away')" in script


def test_return_scroll_targets_preserved_cover():
    script = _scroll_transition_script('cover', 'return-token')
    assert '.st-key-dimension_cover' in script
    assert 'return-token' in script


def test_cover_keeps_full_width_in_both_states():
    from welcome import _stylesheet
    css = _stylesheet()
    assert 'width: 100cqw' in css
    assert 'min-height: 100svh' in css
    assert '.dimension-intro { max-width: 760px' in css
    opened = css.split('.stApp:has(.st-key-dimension_toolbar) .st-key-dimension_cover {')[1].split('}')[0]
    assert 'width' not in opened
    assert 'border-radius' not in opened
