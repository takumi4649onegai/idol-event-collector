# TIGETパフォーマーページ個別URL抽出バグ修正 (Phase 7)

本フェーズでは、[scraper/tiget.py](file:///C:/Users/takum/.gemini/antigravity/scratch/idol-event-collector/scraper/tiget.py) の `scrape_tiget_performer()` において、取得されたすべてのイベントの `url` にアーティストページ自体のURLが設定され、2件目以降のイベントが重複SeenチェックやデータベースのURL主キー制約によってすべて破棄されていたバグを修正します。

## User Review Required

> [!NOTE]
> **個別イベントURL取得のフォールバック**
> 各イベントカードのHTMLタグ（リンクと周囲のコンテナ要素）から個別イベントリンク（`/events/\d+`）の抽出を試みますが、万が一抽出できない場合であっても、同一URLによる破棄を防ぐため、`local_id:TIGET:{performer_id}:{date}:{title}` の一意なローカルIDにフォールバックさせる安全設計を導入します。

---

## Proposed Changes

### Scraper Logic

#### [MODIFY] [tiget.py](file:///C:/Users/takum/.gemini/antigravity/scratch/idol-event-collector/scraper/tiget.py)
- `scrape_tiget_performer(performer_id, default_performers)` を修正：
  - 各 `div` (イベントカード) 内の `a` タグまたは自身が `a` タグの場合の `href` から、`/events/` パスにマッチする個別URLを抽出。
  - 相対パスの場合は `https://tiget.net` をプレフィックスとして結合し、絶対URLに正規化。
  - 個別URLが取得できなかった場合は、`local_id:TIGET:{performer_id}:{date_str}:{title}` 形式で一意のフォールバックIDを生成。

---

## Verification Plan

### Automated Tests

1. **個別URL抽出とフォールバックの検証**
   - 既存のテストスクリプト `test_livepocket_resurrection.py` に `test_scrape_tiget_performer_individual_urls` テストケースを追加して検証します。
     - HTML内に個別リンクが含まれるイベントは、`https://tiget.net/events/111222` のように絶対URLが返ること。
     - リンクが欠落しているイベントは、`local_id:TIGET:4483:...` の一意なIDにフォールバックされること。
     - 返されるイベントリスト内に重複URLが発生せず、`main.py` の Seen チェックや PostgreSQL の URL 主キー制約で破棄されないことを担保。
   - コマンド: `py C:\Users\takum\.gemini\antigravity\brain\379fd0ad-b37b-4fa3-b2c6-8731c49be4cc\scratch\test_livepocket_resurrection.py`

### Manual Verification
- GitHub にプッシュ後、GitHub Actions で手動実行（またはスケジュール起動）された際に、TIGETパフォーマーページから10件のイベントが検出され、過去イベント以外の未来のイベントについて、DBへの新規登録または既存スキップ（重複チェック）のログがイベント名ごとに個別に1件ずつ表示されることを確認します。
