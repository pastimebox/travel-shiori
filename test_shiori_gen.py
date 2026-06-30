"""pytest 境界値テスト — 指示書_旅行しおりHTML_v0.2 §6（8ケース）。"""
import shiori_gen as sg


def test_01_missing_keys_no_crash():
    """1. 任意キー欠損 / null でクラッシュしない。"""
    data = {"trip": {"trip_title": "最小"},
            "flights": [{"flight_no": "X1"}],
            "hotels": [{"name": "H", "lat": None, "lng": None}],
            "places": [{"name": "P"}],
            "dining": [{"label": "D"}]}
    html = sg.build_html(data)
    ics = sg.build_ics(data)
    assert isinstance(html, str) and "最小" in html
    assert ics.startswith("BEGIN:VCALENDAR")


def test_02_verbatim_preservation():
    """2. 記号(/ - ;)・型番・コードが改変なしで保持（rule #7）。"""
    code = "NH/006-A;Z2"
    pnr = "AB7-熊/9"
    size = "M/L;XL-2"
    data = {"flights": [{"flight_no": code, "pnr": pnr, "note": size}]}
    html = sg.build_html(data)
    assert code in html
    assert pnr in html
    assert size in html


def test_03_multiple_items():
    """3. 複数便・複数ホテル・複数日程。"""
    data = {
        "trip": {"timezone": "Asia/Tokyo"},
        "flights": [{"flight_no": "F1", "dep_datetime": "2026-07-01 10:00"},
                    {"flight_no": "F2", "dep_datetime": "2026-07-05 18:00"}],
        "hotels": [{"name": "HotelA"}, {"name": "HotelB"}],
        "places": [{"name": "PA"}, {"name": "PB"}, {"name": "PC"}],
    }
    html = sg.build_html(data)
    for name in ("F1", "F2", "HotelA", "HotelB", "PA", "PB", "PC"):
        assert name in html
    assert sg.build_ics(data).count("BEGIN:VEVENT") == 2


def test_04_input_order_preserved():
    """4. 入力順＝出力順。"""
    data = {"places": [{"name": "ZZZ"}, {"name": "AAA"}, {"name": "MMM"}]}
    html = sg.build_html(data)
    assert html.index("ZZZ") < html.index("AAA") < html.index("MMM")


def test_05_link_coords_vs_query_vs_none():
    """5. 座標優先 / map_query / どちらも無し。"""
    assert sg.loc_token({"lat": "35.68", "lng": "139.76"}) == "35.68,139.76"
    assert sg.loc_token({"map_query": "東京駅"}) == "東京駅"
    assert sg.loc_token({"map_query": "", "lat": None, "lng": None}) is None
    # 座標優先（query があっても座標を使う）
    assert sg.loc_token({"lat": "1", "lng": "2", "map_query": "x"}) == "1,2"


def test_06_ics_timezone_conversion():
    """6. 現地TZ → UTC 変換（Asia/Tokyo 09:00 = 00:00Z）。"""
    if sg.ZoneInfo is None:
        import pytest
        pytest.skip("zoneinfo 不在")
    data = {"trip": {"timezone": "Asia/Tokyo"},
            "flights": [{"flight_no": "TZ1", "dep_datetime": "2026-07-10 09:00"}]}
    ics = sg.build_ics(data)
    assert "DTSTART:20260710T000000Z" in ics


def test_07_url_encoding():
    """7. URLエンコード（日本語・空白・&）。"""
    link = sg.gmaps_search_link("東京 駅 & 周辺")
    assert "%20" in link            # 空白
    assert "%26" in link            # &
    assert " " not in link and "&周辺" not in link
    dir_link = sg.gmaps_dir_link("A 地点", "B&C")
    assert "origin=A%20" in dir_link and "destination=B%26C" in dir_link


def test_08_empty_arrays():
    """8. 空配列（0件）でクラッシュしない。"""
    data = {"trip": {"trip_title": "空"}, "flights": [], "hotels": [],
            "places": [], "dining": []}
    html = sg.build_html(data)
    ics = sg.build_ics(data)
    assert "空" in html
    assert ics.count("BEGIN:VEVENT") == 0
    assert ics.strip().endswith("END:VCALENDAR")
