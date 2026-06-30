# 旅行しおり HTML 生成器 — 使い方

`shiori_gen.py` v1.0.0 ／ 指示書_旅行しおりHTML_v0.2 準拠

## できること
- JSON（旅程データ）→ **1枚の自己完結 HTML**（`trip.html`）＋ **`trip.ics`**（カレンダー取込用）
- 地図 / 経路 / 周辺の食事検索は **Google マップ ディープリンク**（APIキー不要・無料・タップで開く）
- `trip.html` は外部依存ゼロ＝**オフラインで開ける／そのまま配布可**（.ics も HTML 内にダウンロードリンク内蔵）
- rule #7: 便名・PNR・予約番号・記号(/ - ;)は**原文そのまま**表示

## 使い方
```bash
python3 shiori_gen.py 入力.json -o 出力先フォルダ
# 例
python3 shiori_gen.py sample_trip.json -o out
```
→ `out/trip.html` と `out/trip.ics` が生成されます。`trip.html` をブラウザで開く／共有する。

## 入力JSONの形
`sample_trip.json` を雛形にコピーして書き換えてください。
キーは trip / flights / hotels / places / dining。任意項目は省略・null 可。
- 場所の指定は `map_query`（地名・店名）か `lat`/`lng`（座標）。座標があれば優先。
- ホテルの `nearby_food_keywords`（例: 居酒屋, イタリアン）→ 周辺検索チップを自動生成。
- 変動情報（料金・営業時間）は入れず、`dining` の `status` を「要直前確認」にしておく運用。

## テスト
```bash
python3 -m pytest -q
```
（境界値8ケース：欠損/原文保持/複数件/順序/リンク/TZ変換/URLエンコード/空配列）
