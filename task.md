# タスク: LINE Bot 質問応答の安定化と0件時返答改善

## Phase 1: 同一イベントの重複LINE通知防止 (完了)
- [x] `main.py` の修正
  - [x] `run_marked_idols_collection()` 内の新潟バイパス（既存データ再通知）ロジックの削除・無効化
  - [x] `insert_event(ev)` の戻り値 `is_new` を用いた、新規登録（is_new=True）時のみの通知・カレンダー同期制御
  - [x] 指定されたログ表記（✅, ⏭️, 📩, 🔕）によるコンソール出力の改善
- [x] 動作確認・検証 (Git コミット & デプロイ完了)

## Phase 2: LINE Bot Webhook 安定化と応答改善 (完了)
- [x] `line_bot.py` の調査と修正箇所の特定
- [x] リアルタイムスクレイピングの全面停止
  - [x] Webhook応答処理内での `scrape_tiget_by_state(state_id)` 等の外部呼び出しの無効化
  - [x] 外部アクセスを完全にバイパスし、DB検索結果のみを利用するよう変更
- [x] DB検索結果に基づく応答の構築と0件時返答の改善
  - [x] 日付・地域・キーワードによるDB検索のみの実行確認
  - [x] 0件時の返答表現の改善（「DB登録済みイベントは見つかりませんでした」「リアルタイム検索ではないため急な告知は未反映の可能性がある」等を明記）
- [x] ログ出力の追加
  - [x] 指定の絵文字とフォーマットによるコンソールログ出力機能の追加
- [x] 動作確認・検証 (Git コミット & デプロイ完了)

## Phase 3: 新潟イベント判定の取りこぼしを減らす修正 (完了)
- [x] `scraper/utils.py` の調査と `determine_area()` 修正箇所の特定
- [x] 新潟キーワード辞書の強化
  - [x] 主要ライブ会場、商業施設、リリースイベント会場、表記ゆれの追加（最低限指定されたすべてのキーワード）
  - [x] 全国規模の単一NGワード（イオン、タワレコ、TOWER RECORDS、LOTS）を除外した安全設計の実施
- [x] 判定ロジックのアップデート
  - [x] 小文字化（lower()）を用いたcase-insensitiveな表記ゆれ対応
  - [x] 東京優先ルールを維持しつつ、具体的な新潟会場名が明確に含まれている場合に新潟を優先判定するフォールバックロジックの実装
- [x] 動作確認・検証 (Git コミット & デプロイ完了)

## Phase 4: イベントデータの情報源管理の下準備 (完了)
- [x] `events.db` データベースの事前バックアップ作成 (`events.db.bak`)
- [x] データベース構造の安全なマイグレーション
  - [x] `db_manager.py` の `init_db()` に `PRAGMA table_info` を使用したカラム有無チェックを追加
  - [x] `source` カラムが存在しない場合のみ `ALTER TABLE events ADD COLUMN source TEXT DEFAULT 'Unknown'` を自動実行するロジックを実装
- [x] イベントデータ構築ロジックへの source 付与
  - [x] TIGET スクレイパー (`scraper/tiget.py`) で取得したイベントに `"source": "TIGET"` を設定
  - [x] ケミカルスケジュールインポーター (`import_chemical_schedule.py`) で取得したイベントに `"source": "X"` を設定
  - [x] `db_manager.py` で `source` の指定がない場合、デフォルトで `"Unknown"` にフォールバックするよう変更
- [x] 応答・通知・ログでの情報源（source）の表示
  - [x] LINE プッシュ通知 (`line_client.py`) の文面に `情報源：{source}` を追加
  - [x] LINE Bot 検索結果 (`line_bot.py`) のリスト項目に `(情報源: {source})` を追加
  - [x] クローラー実行ログ (`main.py`) に `/ source={source}` を追加
- [x] 動作確認・検証 (Git コミット & デプロイ完了)

## Phase 5: SQLiteからPostgreSQLへの移行 (完了)
- [x] `requirements.txt` の修正 (`psycopg2-binary` の追加)
- [x] `db_manager.py` の修正 (PostgreSQL/SQLite ハイブリッド接続対応)
  - [x] `DATABASE_URL` の有無による動的なDB切替
  - [x] `init_db()` の PostgreSQL 対応 (情報スキーマチェック & ALTER TABLE)
  - [x] `insert_event()` の PostgreSQL 対応 (`ON CONFLICT (url) DO NOTHING` と `%s` プレースホルダー)
  - [x] `query_events()` の PostgreSQL 対応 (`%s` プレースホルダー)
  - [x] `is_duplicate_by_dedupe_key()` の PostgreSQL 対応
- [x] `.github/workflows/run_collector.yml` の修正
  - [x] `env` に `DATABASE_URL: ${{ secrets.DATABASE_URL }}` を追加
  - [x] `events.db` の自動コミット・プッシュステップの削除
- [x] 動作確認・検証
  - [x] ローカル環境での SQLite モード動作確認
  - [x] ローカル環境での PostgreSQL モード動作確認 (テストスクリプト作成 & テスト用DBへの接続検証)
  - [x] Git コミット & プッシュ (Render.com へのデプロイ)

## Phase 6: LivePocketスクレイパー復活と重複通知防止 (完了)
- [x] `db_manager.py` の `is_duplicate_by_dedupe_key()` の論理バグ修正
  - [x] `SELECT` 項目に `url` を追加し、同一URLの自分自身を重複判定から除外
- [x] `main.py` の重複通知判定ロジックの修正
  - [x] 新潟エリア判定による通知バイパスの廃止
  - [x] すべての地域において `is_duplicate_by_dedupe_key()` を適用して通知を制御
- [x] `scraper/livepocket.py` の修正
  - [x] 返却辞書に `"source": "LivePocket"` と `"raw_text": container_text` を追加
- [x] `config.py` の修正
  - [x] `ENABLE_LIVEPOCKET_SCRAPING = True` に設定
- [x] `main.py` への巡回ロジックの追加
  - [x] `ENABLE_LIVEPOCKET_SCRAPING` によるLivePocket巡回を追加
  - [x] `try-except` による安全なエラーハンドリングと指定ログ出力の追加
- [x] 動作確認・検証
  - [x] 新たに `test_livepocket_resurrection.py` を作成し、重複排除とLivePocket連携の動作を検証
  - [x] テスト結果確認（SQLiteモードおよびPostgreSQLモード）
- [x] Git コミット & プッシュ (Render.com へのデプロイ)

## Phase 7: TIGETパフォーマーページ個別URL抽出バグ修正 (完了)
- [x] `scraper/tiget.py` の `scrape_tiget_performer()` 修正
  - [x] 各イベントカードの `a` 要素から個別イベントの `/events/数字` の取得処理の実装
  - [x] 相対パス時の絶対URLへの変換処理の実装
  - [x] 個別URLが取得できない場合に `local_id:TIGET:...` での一意のフォールバックID生成処理の実装
- [x] テストコードによる動作確認
  - [x] `test_livepocket_resurrection.py` 内に `test_scrape_tiget_performer_individual_urls` テストケースを追加
  - [x] 個別URLの正しいパース、およびlocal_idフォールバックの動作検証クリア
- [x] Git コミット & プッシュ (Render.com へのデプロイ)

## Phase 8: 朝まとめ通知機能の導入 (完了)
- [x] `daily_summary.py` の新規作成
  - [x] JSTの今日・明日の日付計算処理の実装
  - [x] `db_manager.query_events()` による今日・明日のイベントデータ取得
  - [x] エリア別（新潟・東京・その他）件数の集計処理
  - [x] 表示制限（最大5件）および「新潟優先」表示ロジックの実装
  - [x] 0件時の簡潔な案内メッセージ生成処理
  - [x] LINE_GROUP_ID へのプッシュ通知送信処理（LINE_CHANNEL_ACCESS_TOKEN 認証）
- [x] `.github/workflows/daily_summary.yml` の新規作成
  - [x] スケジュール（cron: JST 9:00 / UTC 0:00）の設定
  - [x] `workflow_dispatch` (手動実行) の追加
  - [x] `DATABASE_URL`, `LINE_CHANNEL_ACCESS_TOKEN`, `LINE_GROUP_ID` のシークレット渡し設定
- [x] 動作確認・検証
  - [x] `test_daily_summary.py` を作成し、0件時/イベントあり時の通知テキスト生成ロジックの動作検証
  - [x] 環境変数が不足している際のエラーログハンドリング動作検証
  - [x] GitHub Actions ワークフローの YAML シンタックス検証
- [x] Git コミット & プッシュ
