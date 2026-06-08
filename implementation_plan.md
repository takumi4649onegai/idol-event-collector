# LivePocketスクレイパーの復活と重複通知の防止 (Phase 6)

本フェーズでは、停止中だった LivePocket スクレイパーを安全に復活させます。また、TIGETとLivePocketの双方に同一のイベントが登録された際に、LINE通知が重複して配信されるスパム問題を防ぐため、重複排除（デデュープ）処理を強化し、新潟イベントであっても重複時は通知をスキップするように動作を厳密化します。

## User Review Required

> [!IMPORTANT]
> **新潟イベント重複通知バイパスの廃止**
> 従来、新潟エリアのイベント（`is_niigata_local = True`）は重複排除判定（`is_duplicate_by_dedupe_key`）をバイパスして即座に通知する仕様になっていました。しかし、LivePocket を有効化すると、TIGETとLivePocketの両方で販売される同じ新潟イベントで二重通知（スパム）が発生するため、**新潟イベントであっても重複している場合は通知をスキップする**よう `main.py` の条件分岐を統一します。

> [!WARNING]
> **is_duplicate_by_dedupe_key の論理バグ修正**
> 既存の `is_duplicate_by_dedupe_key` は、自身（今回挿入されたばかりの新規イベント）もクエリ結果に含んでしまい、自身と日時・会場が一致することから**常に重複（True）と判定されるバグ**を抱えていました。
> 本計画で、同一URLを持つレコード（自身）を判定ループから除外するよう修正します。これにより、通常イベント（東京等）の通知が正しく配信されるようになります。

---

## Proposed Changes

### Configuration

#### [MODIFY] [config.py](file:///C:/Users/takum/.gemini/antigravity/scratch/idol-event-collector/config.py)
- `ENABLE_LIVEPOCKET_SCRAPING = True` に変更し、LivePocketの巡回機能を有効化します。

---

### Scraper Logic

#### [MODIFY] [livepocket.py](file:///C:/Users/takum/.gemini/antigravity/scratch/idol-event-collector/scraper/livepocket.py)
- `scrape_livepocket_events(query)` にて、返却するイベント情報辞書に `"source": "LivePocket"` および `"raw_text": container_text` を追加します。

---

### Database Manager

#### [MODIFY] [db_manager.py](file:///C:/Users/takum/.gemini/antigravity/scratch/idol-event-collector/db_manager.py)
- `is_duplicate_by_dedupe_key(event)` を修正：
  - `SELECT` 文で `url` カラムもあわせて取得。
  - ループ内で `row["url"] == target_url` の場合は `continue` でスキップするようにし、自身とのマッチングによる誤判定を回避します。

---

### Main Loop & Duplication Check

#### [MODIFY] [main.py](file:///C:/Users/takum/.gemini/antigravity/scratch/idol-event-collector/main.py)
- `run_marked_idols_collection()` 内のLivePocketスクレイピング呼び出し部を有効化。
  - エラー発生時もクローラー全体を巻き込んで停止しないよう、`try-except` で保護しエラーログを出力。
- 巡回時のコンソール出力ログに、指定された以下のフォーマットを追加・適用：
  - `🔍 LivePocket検索開始: {name}`
  - `✅ LivePocket取得件数: {count}件`
- 新着イベントの通知判定ロジックを修正：
  - `is_niigata_local` による通知バイパス処理を廃止し、すべての地域において `is_duplicate_by_dedupe_key(ev)` を適用して、未通知の新規イベントのみLINE通知 & Googleカレンダー同期を行います。

---

## Verification Plan

### Automated Tests

1. **重複排除ロジックの修正検証**
   - 新たに `test_livepocket_resurrection.py` を作成し、以下を検証します。
     - `is_duplicate_by_dedupe_key` が自身を除外して正しく新規イベントを検知できること。
     - 異なるURLだが同一日時・会場のイベントが来た場合、2枚目は `is_duplicate_by_dedupe_key` で重複と判定されること。
     - 新潟イベントであっても重複時は通知フラグが立たないこと。
   - コマンド: `py C:\Users\takum\.gemini\antigravity\brain\379fd0ad-b37b-4fa3-b2c6-8731c49be4cc\scratch\test_livepocket_resurrection.py`

2. **LivePocket スクレイパーの単体検証**
   - `scraper/livepocket.py` を直接実行し、LivePocket から正常に `"source": "LivePocket"` および `"raw_text"` を含むイベントリストが返されることを確認します。
   - コマンド: `py scraper/livepocket.py`
