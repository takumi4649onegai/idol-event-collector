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
