# SQLiteからNeon PostgreSQLへの移行 (Phase 5)

本プロジェクトのデータベースを SQLite から Neon PostgreSQL に移行し、ローカル開発環境では引き続き SQLite を利用可能なハイブリッド構成を実現します。また、GitHub Actions や Render.com などの本番環境では、環境変数 `DATABASE_URL` を利用して PostgreSQL に自動接続します。

## User Review Required

> [!NOTE]
> **本番データベース (Neon PostgreSQL) 接続の前提**
> ユーザー様側で Neon PostgreSQL 側のプロジェクト作成、および接続用 URL（`DATABASE_URL`）の取得と環境変数・シークレットへの登録（Render.com / GitHub Actions）が完了している前提で動作します。

> [!IMPORTANT]
> **SSL接続の自動付加**
> Neon PostgreSQL は SSL 接続を必須とするため、コード内で `DATABASE_URL` に `sslmode=require` が指定されていない場合は、自動で末尾に付加する処理を追加しています。

---

## Proposed Changes

### Database & Scraper Logic

#### [MODIFY] [db_manager.py](file:///C:/Users/takum/.gemini/antigravity/scratch/idol-event-collector/db_manager.py)
- `get_connection()`: `DATABASE_URL` の有無で接続先を動的切り替え。SSL接続オプションを Neon に適合するよう自動調整。
- `get_cursor()`: PostgreSQL 接続時には `psycopg2.extras.DictCursor` を用いて、SQLite 同様に辞書ライク（カラム名指定）でデータ行にアクセスできるように抽象化。
- `init_db()`: PostgreSQL 用の `CREATE TABLE` スキーマおよび、`information_schema.columns` を使った `source` カラム自動追加マイグレーションに対応。
- `insert_event()`: PostgreSQL の `ON CONFLICT (url) DO NOTHING` と `%s` プレースホルダー、SQLite の `INSERT OR IGNORE` と `?` プレースホルダーを動的切り替え。
- `query_events()`: プレースホルダーを接続タイプにあわせて動的に `%s` または `?` に設定。行アクセスのエラーハンドリング強化。
- `is_duplicate_by_dedupe_key()`: プレースホルダーの動的切り替えを実装。

#### [MODIFY] [requirements.txt](file:///C:/Users/takum/.gemini/antigravity/scratch/idol-event-collector/requirements.txt)
- `psycopg2-binary>=2.9.0` を追加し、Python から PostgreSQL への接続ドライバをインストール。

---

### CI/CD Workflow

#### [MODIFY] [run_collector.yml](file:///C:/Users/takum/.gemini/antigravity/scratch/idol-event-collector/.github/workflows/run_collector.yml)
- クローラー実行時の環境変数に `DATABASE_URL: ${{ secrets.DATABASE_URL }}` を追加。
- 従来行っていた `events.db` ファイルの Git 自動コミットおよびプッシュ処理（Git-pushステップ）を完全に削除。

---

## Verification Plan

### Automated Tests

1. **SQLite 接続の動作検証**
   - 既存のテストスクリプト `test_source_management.py` を実行し、SQLite モードにおいてマイグレーション、データ追加、重複排除、検索、および LINE 通知テキスト生成・Bot 応答生成が正常に動作することを確認します。
   - コマンド: `py C:\Users\takum\.gemini\antigravity\brain\379fd0ad-b37b-4fa3-b2c6-8731c49be4cc\scratch\test_source_management.py`

2. **PostgreSQL 接続（モック経由）の動作検証**
   - 新規テストスクリプト `test_postgres_mode.py` を実行し、`DATABASE_URL` がセットされた PostgreSQL モードにおいてテーブル作成（`init_db`）、データ追加（`insert_event`）、検索（`query_events`）が正しい PostgreSQL 向け SQL 文（`ON CONFLICT`, `%s` プレースホルダーなど）で実行されることをモックを用いて検証します。
   - コマンド: `py C:\Users\takum\.gemini\antigravity\brain\379fd0ad-b37b-4fa3-b2c6-8731c49be4cc\scratch\test_postgres_mode.py`

### Manual Verification
- GitHub にコードをプッシュ後、GitHub Actions および Render.com 上でクローラーと LINE Bot が Neon PostgreSQL の `events` テーブルにアクセスし、正常にデータが登録・検索できることを確認します。
