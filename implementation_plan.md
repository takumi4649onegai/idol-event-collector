# 朝まとめ通知機能の導入 (Phase 8)

本フェーズでは、毎日朝9:00（日本時間）に、Neon PostgreSQL から今日および明日のイベント情報を取得し、エリアごとの集計および本日の主なイベント（最大5件、新潟優先）をまとめてLINEグループに1通で通知する「朝まとめ通知」機能を実装します。

## User Review Required

> [!IMPORTANT]
> **独立した構成**
> 既存の即時通知ロジック（`main.py` などのクローラー部分）や LINE Bot 応答部分（`line_bot.py`）には影響を与えないよう、完全に独立した実行ファイル `daily_summary.py` およびワークフロー `daily_summary.yml` として追加します。データベース設計や新規テーブルの追加もありません。

> [!WARNING]
> **手動実行時の注意**
> GitHub Actions 上で手動実行（`workflow_dispatch`）を行った場合にも通知が送信されます。テストや臨時の確認目的以外での過度な手動実行にはご注意ください。

---

## Proposed Changes

### 1. 新規ファイルの作成

#### [NEW] [daily_summary.py](file:///C:/Users/takum/./.gemini/antigravity/scratch/idol-event-collector/daily_summary.py)
- JST（日本標準時）の今日と明日の日付を算出して `db_manager.query_events()` で対象日付のイベントを取得。
- 新潟・東京・その他の地域別件数を集計。
- 本日のイベント一覧から、新潟を優先的にソートした上位5件（出演、会場、情報源）の詳細テキストを生成。
- 6件以上ある場合は「ほか〇件あります。」を表示。
- 今日・明日ともにイベントがない場合は、簡潔な0件時の案内メッセージを生成。
- `LINE_CHANNEL_ACCESS_TOKEN` 和 `LINE_GROUP_ID` を用いて、LINEプッシュAPI経由で1通のまとめメッセージを送信。
- Windows環境での絵文字表示（cp932）によるエラー防止のため、標準出力のエンコーディング変更処理を冒頭に導入。

#### [NEW] [daily_summary.yml](file:///C:/Users/takum/./.gemini/antigravity/scratch/idol-event-collector/.github/workflows/daily_summary.yml)
- 毎日 UTC 0:00 (JST 9:00) に自動起動する cron 設定を追加。
- Web UI からいつでも手動実行できる `workflow_dispatch` トリガーを設定。
- 実行時に必要なシークレット（`DATABASE_URL`, `LINE_CHANNEL_ACCESS_TOKEN`, `LINE_GROUP_ID`）を環境変数として渡す。

---

## Verification Plan

### Automated Tests
1. **テキスト生成ロジックの単体テスト**
   - 0件時のフォーマット検証、複数イベント時の集計、新潟優先ソート、最大5件表示、ほか〇件表示、sourceの表示の検証。
   - 環境変数が不足している場合に、LINE送信をスキップしてプレビューのみを表示する動作の検証。
   - コマンド: `py C:\Users\takum\.gemini\antigravity\brain\379fd0ad-b37b-4fa3-b2c6-8731c49be4cc\scratch\test_daily_summary.py`

### Manual Verification
- ローカル環境で環境変数を指定せずに `daily_summary.py` を実行し、プレビューされるテキストが要件を満たしていること。
- GitHub にプッシュ後、GitHub Actions で `daily_summary.yml` を手動実行し、正しく成功終了することを確認します。
