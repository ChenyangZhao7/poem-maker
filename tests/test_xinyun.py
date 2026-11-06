from eh_poem_style.xinyun import resolve_rhyme, rhyme_groups


def test_guang_huang_same_group():
    assert "十唐" in rhyme_groups("光")
    assert resolve_rhyme(["光", "黄"]).group == "十唐"


def test_han_dan_same_group():
    assert resolve_rhyme(["寒", "淡"]).group == "八寒"


def test_deng_sheng_same_group():
    assert resolve_rhyme(["灯", "生"]).group == "十一庚"


def test_qi_xi_di_same_group():
    assert resolve_rhyme(["齐", "袭", "敌"]).group == "十二齐"


def test_shuo_mei_no_common_group():
    assert resolve_rhyme(["说", "没"]).group is None


def test_zhi_is_zhisan_zhi():
    assert rhyme_groups("知") == frozenset({"十三支"})
    assert "十二齐" not in rhyme_groups("知")


def test_er_and_yu_are_qier():
    assert "十二齐" in rhyme_groups("儿")
    assert "十二齐" in rhyme_groups("鱼")


def test_preferred_group_wins():
    resolution = resolve_rhyme(["说", "没"], preferred="二波")
    assert resolution.group == "二波"


def test_candidates_filters_by_group():
    from eh_poem_style.xinyun import candidates

    result = candidates("十唐", ["光", "黄", "寒", "山"])
    assert result == ["光", "黄"]
