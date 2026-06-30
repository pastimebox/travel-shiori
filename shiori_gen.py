#!/usr/bin/env python3
"""旅行しおり HTML 生成器 / Travel Itinerary HTML Generator.

Version: 1.0.0
準拠: 指示書_旅行しおりHTML_v0.2（発行版）

- 入力 : JSON（trip / flights / hotels / places / dining）
- 出力 : 自己完結 trip.html（CSS/JS インライン・外部依存ゼロ）＋ trip.ics
- 地図 : Google マップ ディープリンク（APIキー不要・無料）
- rule #7      : 予約番号・便名・型番・記号(/ - ;)は一字一句そのまま（正規化禁止）
- rule #10/#11 : 変動情報は焼き込まず「要直前確認」表示で扱う
"""
from __future__ import annotations

import argparse
import base64
import html
import json
import os
from datetime import datetime, timezone
from urllib.parse import quote

try:
    from zoneinfo import ZoneInfo  # Python 3.9+
except Exception:  # pragma: no cover
    ZoneInfo = None

__version__ = "1.0.0"

_DT_FORMATS = (
    "%Y-%m-%d %H:%M",
    "%Y-%m-%dT%H:%M",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%Y/%m/%d %H:%M",
    "%Y-%m-%d",
)


# ============================== helpers ==============================
def _s(v) -> str:
    """None を '' に。その他は str() で原文保持（正規化しない）。"""
    return "" if v is None else str(v)


def _has(v) -> bool:
    return v is not None and str(v).strip() != ""


def E(v) -> str:
    """HTML 埋め込み用エスケープ（表示テキストは原文と一致する）。"""
    return html.escape(_s(v))


def url_q(value) -> str:
    """URL エンコード（日本語・空白・& を含め全エスケープ）。"""
    return quote(_s(value), safe="")


def loc_token(item: dict):
    """座標があれば 'lat,lng'、無ければ map_query、どちらも無ければ None。"""
    lat, lng = item.get("lat"), item.get("lng")
    if _has(lat) and _has(lng):
        return f"{_s(lat)},{_s(lng)}"
    if _has(item.get("map_query")):
        return _s(item.get("map_query"))
    return None


def gmaps_search_link(query) -> str:
    return "https://www.google.com/maps/search/?api=1&query=" + url_q(query)


def gmaps_dir_link(origin, dest) -> str:
    link = "https://www.google.com/maps/dir/?api=1&destination=" + url_q(dest)
    if _has(origin):
        link += "&origin=" + url_q(origin)
    return link


# ========================= datetime / ICS ===========================
def parse_dt(value):
    s = _s(value).strip()
    if not s:
        return None
    for fmt in _DT_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def ics_dt(value, tzname):
    """ICS の DTSTART 値。tz があれば UTC(Z) へ、無ければフローティング local。"""
    dt = parse_dt(value)
    if dt is None:
        return None
    if _has(tzname) and ZoneInfo is not None:
        try:
            aware = dt.replace(tzinfo=ZoneInfo(_s(tzname)))
            return aware.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        except Exception:
            pass
    return dt.strftime("%Y%m%dT%H%M%S")


def _ics_text(value) -> str:
    s = _s(value).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
    return s.replace("\r\n", "\\n").replace("\n", "\\n").replace("\r", "\\n")


def _now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _vevent(uid, dtstart, summary, location="", description=""):
    out = [
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{_now_stamp()}",
        f"DTSTART:{dtstart}",
        f"SUMMARY:{_ics_text(summary)}",
    ]
    if _has(location):
        out.append(f"LOCATION:{_ics_text(location)}")
    if _has(description):
        out.append(f"DESCRIPTION:{_ics_text(description)}")
    out.append("END:VEVENT")
    return out


def build_ics(data: dict) -> str:
    trip = data.get("trip") or {}
    tz = trip.get("timezone")
    out = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//shiori_gen//JP//1.0//EN",
        "CALSCALE:GREGORIAN",
    ]
    n = 0
    for f in data.get("flights") or []:
        for key, label, ap in (
            ("dep_datetime", "出発", "dep_airport"),
            ("arr_datetime", "到着", "arr_airport"),
        ):
            ds = ics_dt(f.get(key), tz)
            if ds:
                n += 1
                summ = (
                    f"✈ {_s(f.get('flight_no'))} {label} "
                    f"{_s(f.get('dep_airport'))}→{_s(f.get('arr_airport'))}"
                ).strip()
                out += _vevent(f"flight-{n}@shiori", ds, summ, location=_s(f.get(ap)))
    for h in data.get("hotels") or []:
        for key, label in (("checkin_datetime", "チェックイン"),
                           ("checkout_datetime", "チェックアウト")):
            ds = ics_dt(h.get(key), tz)
            if ds:
                n += 1
                out += _vevent(f"hotel-{n}@shiori", ds,
                               f"🏨 {_s(h.get('name'))} {label}",
                               location=_s(h.get("address")))
    for p in data.get("places") or []:
        ds = ics_dt(p.get("planned_datetime"), tz)
        if ds:
            n += 1
            out += _vevent(f"place-{n}@shiori", ds, f"📍 {_s(p.get('name'))}",
                           location=_s(p.get("map_query")),
                           description=_s(p.get("note")))
    out.append("END:VCALENDAR")
    return "\r\n".join(out) + "\r\n"


# ============================== HTML ================================
_CSS = """
:root{
  --ink:#5b4a54; --ink-soft:#9a8690; --paper:#fff6f4; --card:#ffffff;
  --line:#f6e2e2; --pink:#ff8fab; --pink-d:#e76a8d; --peach:#ffb39a;
  --mint:#7fd1bd; --mint-d:#3aa48f; --lav:#b9a7e6; --lav-d:#8a73c9; --gold:#ffcf5e;
  --shadow:0 2px 0 rgba(231,106,141,.05),0 16px 32px -20px rgba(231,106,141,.55);
}
*{box-sizing:border-box}
body{margin:0;background:
  radial-gradient(1200px 420px at 80% -120px, #ffe3ec 0%, transparent 60%),
  var(--paper);
  color:var(--ink);
  font-family:"Hiragino Maru Gothic ProN","ヒラギノ丸ゴ ProN",system-ui,-apple-system,
    "Segoe UI",Roboto,"Hiragino Sans","Noto Sans JP",sans-serif;
  line-height:1.7;-webkit-text-size-adjust:100%}
.wrap{max-width:740px;margin:0 auto;padding:0 18px 72px}
a{color:inherit}
code,.mono{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}

/* hero */
.hero{background:linear-gradient(135deg,#ffd9e2 0%,#ffc8d6 42%,#e9cdf7 100%);
  color:var(--ink);margin:0 -18px 26px;padding:46px 28px 36px;position:relative;overflow:hidden;
  border-radius:0 0 30px 30px;box-shadow:0 18px 36px -26px rgba(231,106,141,.7)}
.hero::after{content:"";position:absolute;right:-50px;top:-50px;width:190px;height:190px;
  border-radius:50%;background:radial-gradient(circle,rgba(255,255,255,.75),transparent 70%)}
.hero::before{content:"";position:absolute;left:-30px;bottom:-40px;width:130px;height:130px;
  border-radius:50%;background:radial-gradient(circle,rgba(185,167,230,.55),transparent 70%)}
.hero .eyebrow{font-size:12px;letter-spacing:.22em;color:var(--pink-d);margin:0 0 8px;font-weight:700}
.hero h1{font-weight:800;font-size:33px;line-height:1.2;margin:0 0 14px;letter-spacing:.01em;
  text-shadow:0 1px 0 rgba(255,255,255,.6)}
.hero .meta{display:flex;flex-wrap:wrap;gap:8px}
.hero .meta span{background:rgba(255,255,255,.7);border:1px solid rgba(255,255,255,.9);
  border-radius:999px;padding:4px 12px;font-size:13px;font-weight:600;backdrop-filter:blur(2px)}
.hero .meta b{font-weight:800}

/* section */
.sec{margin:34px 0 0}
.sec > h2{display:flex;align-items:center;gap:9px;font-size:17px;color:var(--ink);
  margin:0 0 14px;font-weight:800;letter-spacing:.02em}
.sec > h2::before{content:"";width:10px;height:10px;border-radius:50%;background:var(--pink);
  box-shadow:0 0 0 4px rgba(255,143,171,.22)}

/* cards */
.card{background:var(--card);border:1.5px solid var(--line);border-radius:20px;
  box-shadow:var(--shadow);padding:16px 18px 16px 20px;margin:0 0 14px;position:relative;overflow:hidden}
.card::before{content:"";position:absolute;left:0;top:0;bottom:0;width:6px;
  background:linear-gradient(var(--pink),var(--peach))}
.card.hotel::before{background:linear-gradient(var(--mint),#bfeede)}
.card.place::before{background:linear-gradient(var(--lav),#d9ccf6)}
.card .title{font-weight:800;font-size:17.5px;margin:0 0 2px;padding-left:6px}
.card .sub{color:var(--ink-soft);font-size:13.5px;margin:0 0 10px;padding-left:6px}
.row{display:flex;flex-wrap:wrap;gap:2px 14px;font-size:14px;padding-left:6px;margin:3px 0}
.row .k{color:var(--ink-soft);min-width:80px}
.row .v{font-weight:600}
.code{display:inline-block;background:#fff0f4;border:1px solid #ffd6e2;color:var(--pink-d);
  border-radius:8px;padding:1px 8px;font-size:13px;font-weight:700}

/* chips */
.chips{display:flex;flex-wrap:wrap;gap:8px;margin:13px 0 2px;padding-left:6px}
.chip{display:inline-flex;align-items:center;gap:6px;text-decoration:none;
  border:1.5px solid var(--pink);color:var(--pink-d);background:#fff5f8;
  border-radius:999px;padding:7px 14px;font-size:13px;font-weight:700;
  transition:transform .12s,background .15s,color .15s}
.chip:hover,.chip:focus-visible{background:var(--pink);color:#fff;transform:translateY(-1px)}
.chip.teal{border-color:var(--mint);color:var(--mint-d);background:#f1fbf7}
.chip.teal:hover,.chip.teal:focus-visible{background:var(--mint);color:#fff}
.chip.ink{border-color:var(--lav);color:var(--lav-d);background:#f6f2fd}
.chip.ink:hover,.chip.ink:focus-visible{background:var(--lav);color:#fff}

.badge{display:inline-block;background:#fff0c6;color:#b6892b;border:1px solid #ffe39a;
  border-radius:999px;padding:1px 10px;font-size:12px;font-weight:800;margin-left:8px}
.note{color:var(--ink-soft);font-size:13px;padding-left:6px;margin-top:8px;
  background:#fffaf6;border-radius:10px;padding:7px 10px;display:inline-block}
.empty{color:var(--ink-soft);font-size:14px;padding-left:6px}
.foot{margin-top:42px;padding-top:18px;border-top:1.5px dashed var(--line);
  color:var(--ink-soft);font-size:12.5px;display:flex;flex-wrap:wrap;gap:6px 14px;justify-content:space-between}
a:focus-visible,.chip:focus-visible{outline:2px solid var(--lav-d);outline-offset:2px}
@media (max-width:480px){.hero h1{font-size:27px}.wrap{padding:0 14px 60px}.hero{padding:36px 18px 30px;margin:0 -14px 22px}}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}
"""


def _kv(label, value, mono=False):
    if not _has(value):
        return ""
    cls = "v code mono" if mono else "v"
    return f'<div class="row"><span class="k">{E(label)}</span><span class="{cls}">{E(value)}</span></div>'


def _chip(href, text, cls="") -> str:
    return f'<a class="chip {cls}" href="{E(href)}" target="_blank" rel="noopener">{E(text)}</a>'


def _flight_card(f: dict) -> str:
    title = _s(f.get("flight_no")) or "フライト"
    sub_bits = [b for b in (_s(f.get("airline")),) if b]
    route = " → ".join([b for b in (_s(f.get("dep_airport")), _s(f.get("arr_airport"))) if b])
    h = [f'<div class="card flight">',
         f'<div class="title"><span class="code mono">{E(title)}</span></div>']
    if sub_bits:
        h.append(f'<div class="sub">{E(" / ".join(sub_bits))}</div>')
    if route:
        h.append(_kv("区間", route))
    h.append(_kv("出発", f.get("dep_datetime")))
    h.append(_kv("到着", f.get("arr_datetime")))
    h.append(_kv("PNR", f.get("pnr"), mono=True))
    h.append(_kv("座席", f.get("seat")))
    h.append(_kv("ターミナル", f.get("terminal_gate")))
    if _has(f.get("note")):
        h.append(f'<div class="note">{E(f.get("note"))}</div>')
    h.append("</div>")
    return "".join(h)


def _hotel_card(h_: dict) -> str:
    h = [f'<div class="card hotel">',
         f'<div class="title">{E(h_.get("name") or "宿泊")}</div>']
    if _has(h_.get("address")):
        h.append(f'<div class="sub">{E(h_.get("address"))}</div>')
    h.append(_kv("IN", h_.get("checkin_datetime")))
    h.append(_kv("OUT", h_.get("checkout_datetime")))
    h.append(_kv("予約番号", h_.get("booking_no"), mono=True))
    h.append(_kv("電話", h_.get("phone")))
    if _has(h_.get("note")):
        h.append(f'<div class="note">{E(h_.get("note"))}</div>')
    chips = []
    tok = loc_token(h_)
    if tok:
        chips.append(_chip(gmaps_search_link(tok), "地図", "teal"))
    name = _s(h_.get("name"))
    for kw in (h_.get("nearby_food_keywords") or []):
        if _has(kw):
            q = f"{name} {kw}".strip()
            chips.append(_chip(gmaps_search_link(q), f"周辺の{_s(kw)}", "ink"))
    if chips:
        h.append('<div class="chips">' + "".join(chips) + "</div>")
    h.append("</div>")
    return "".join(h)


def _place_card(p: dict) -> str:
    h = [f'<div class="card place">',
         f'<div class="title">{E(p.get("name") or "行き先")}</div>']
    subbits = [b for b in (_s(p.get("category")),) if b]
    if subbits:
        h.append(f'<div class="sub">{E(" / ".join(subbits))}</div>')
    h.append(_kv("予定", p.get("planned_datetime")))
    h.append(_kv("滞在(分)", p.get("stay_minutes")))
    if _has(p.get("note")):
        h.append(f'<div class="note">{E(p.get("note"))}</div>')
    chips = []
    tok = loc_token(p)
    if tok:
        if _has(p.get("route_from")):
            chips.append(_chip(gmaps_dir_link(p.get("route_from"), tok), "経路"))
        chips.append(_chip(gmaps_search_link(tok), "地図", "teal"))
    if chips:
        h.append('<div class="chips">' + "".join(chips) + "</div>")
    h.append("</div>")
    return "".join(h)


def _dining_card(d: dict) -> str:
    title = _s(d.get("label")) or "食事候補"
    badge = f'<span class="badge">{E(d.get("status"))}</span>' if _has(d.get("status")) else ""
    h = [f'<div class="card">',
         f'<div class="title">{E(title)}{badge}</div>']
    if _has(d.get("genre")):
        h.append(f'<div class="sub">{E(d.get("genre"))}</div>')
    chips = []
    tok = loc_token(d) or _s(d.get("map_query"))
    if _has(tok):
        chips.append(_chip(gmaps_search_link(tok), "地図検索", "teal"))
    if _has(d.get("url")):
        chips.append(_chip(d.get("url"), "リンク", "ink"))
    if chips:
        h.append('<div class="chips">' + "".join(chips) + "</div>")
    h.append("</div>")
    return "".join(h)


def _section(title, cards):
    inner = "".join(cards) if cards else '<div class="empty">（データなし）</div>'
    return f'<section class="sec"><h2>{E(title)}</h2>{inner}</section>'


def build_html(data: dict) -> str:
    trip = data.get("trip") or {}
    title = _s(trip.get("trip_title")) or "旅のしおり"
    dates = " – ".join([d for d in (_s(trip.get("start_date")), _s(trip.get("end_date"))) if d])

    meta = []
    if dates:
        meta.append(f'<span><b>{E(dates)}</b></span>')
    if _has(trip.get("travelers")):
        meta.append(f'<span>{E(trip.get("travelers"))}</span>')
    if _has(trip.get("timezone")):
        meta.append(f'<span>TZ {E(trip.get("timezone"))}</span>')
    if _has(trip.get("currency")):
        meta.append(f'<span>{E(trip.get("currency"))}</span>')

    sections = [
        _section("Flights ✈", [_flight_card(f) for f in (data.get("flights") or [])]),
        _section("Hotels 🏨", [_hotel_card(h) for h in (data.get("hotels") or [])]),
        _section("Places 📍", [_place_card(p) for p in (data.get("places") or [])]),
        _section("Dining 🍶", [_dining_card(d) for d in (data.get("dining") or [])]),
    ]

    # .ics を data URI として埋め込み（自己完結・オフライン取込可）
    ics = build_ics(data)
    ics_b64 = base64.b64encode(ics.encode("utf-8")).decode("ascii")
    ics_link = (f'<a class="chip" download="trip.ics" '
                f'href="data:text/calendar;base64,{ics_b64}">カレンダーに追加 (.ics)</a>')

    emergency = ""
    if _has(trip.get("emergency_contact")):
        emergency = f'<span>緊急連絡先: {E(trip.get("emergency_contact"))}</span>'

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{E(title)}</title>
<style>{_CSS}</style>
</head>
<body>
<header class="hero">
  <p class="eyebrow">Travel Itinerary</p>
  <h1>{E(title)}</h1>
  <div class="meta">{''.join(meta)}</div>
  <div class="chips" style="padding-left:0;margin-top:16px">{ics_link}</div>
</header>
<main class="wrap">
{''.join(sections)}
<div class="foot"><span>変動情報（料金・営業時間等）は要直前確認</span>{emergency}<span>generated by shiori_gen v{__version__}</span></div>
</main>
</body>
</html>
"""


# ============================== I/O =================================
def load_data(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fp:
        return json.load(fp)


def generate(data: dict, out_dir: str) -> dict:
    os.makedirs(out_dir, exist_ok=True)
    html_path = os.path.join(out_dir, "trip.html")
    ics_path = os.path.join(out_dir, "trip.ics")
    with open(html_path, "w", encoding="utf-8") as fp:
        fp.write(build_html(data))
    with open(ics_path, "w", encoding="utf-8", newline="") as fp:
        fp.write(build_ics(data))
    return {"html": html_path, "ics": ics_path}


def main(argv=None):
    ap = argparse.ArgumentParser(description="旅行しおり HTML/ICS 生成器")
    ap.add_argument("input", help="入力 JSON ファイル")
    ap.add_argument("-o", "--out", default=".", help="出力ディレクトリ（既定: カレント）")
    ap.add_argument("--version", action="version", version=f"shiori_gen {__version__}")
    args = ap.parse_args(argv)
    paths = generate(load_data(args.input), args.out)
    print(f"OK: {paths['html']} / {paths['ics']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
