import sqlite3
import os
import sys
import io
from datetime import datetime, timedelta

DB_FILE = "events.db"

def get_connection():
    """データベースへのコネクションを取得 (PostgreSQL or SQLite)"""
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        import psycopg2
        
        # SSL接続設定 (Neon PostgreSQL に必要)
        if "sslmode" not in database_url:
            if "?" in database_url:
                conn_url = database_url + "&sslmode=require"
            else:
                conn_url = database_url + "?sslmode=require"
        else:
            conn_url = database_url
            
        conn = psycopg2.connect(conn_url)
        return conn
    else:
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row  # 列名でのアクセスを有効にする
        return conn

def get_cursor(conn):
    """接続種別に応じた辞書型アクセス可能なカーソルを取得"""
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        from psycopg2.extras import DictCursor
        return conn.cursor(cursor_factory=DictCursor)
    else:
        return conn.cursor()

def init_db():
    """データベースとテーブルの初期化、及びマイグレーション"""
    conn = get_connection()
    cursor = get_cursor(conn)
    
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        # PostgreSQL用のテーブル作成
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS events (
                url TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                date TEXT NOT NULL,
                area TEXT NOT NULL,
                performers TEXT NOT NULL,
                raw_text TEXT,
                source TEXT DEFAULT 'Unknown',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        
        # 既存DBマイグレーション (source カラム有無チェック)
        try:
            cursor.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'events' AND column_name = 'source'
            """)
            if not cursor.fetchone():
                print("[DB] Migrating PostgreSQL: adding 'source' column...")
                cursor.execute("ALTER TABLE events ADD COLUMN source TEXT DEFAULT 'Unknown'")
                conn.commit()
                print("[DB] Migration completed: 'source' column added successfully.")
            else:
                print("[DB] PostgreSQL database already has 'source' column. Skip migration.")
        except Exception as e:
            print(f"🚨 PostgreSQL 移行中にエラーが発生しました: {str(e)}")
            conn.rollback()
    else:
        # SQLite用のテーブル作成
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS events (
                url TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                date TEXT NOT NULL,
                area TEXT NOT NULL,
                performers TEXT NOT NULL,
                raw_text TEXT,
                source TEXT DEFAULT 'Unknown',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        
        # 既存DBマイグレーション (source カラム有無チェック)
        try:
            cursor.execute("PRAGMA table_info(events)")
            columns = [row[1] for row in cursor.fetchall()]
            if "source" not in columns:
                print("[DB] Migrating SQLite: adding 'source' column...")
                cursor.execute("ALTER TABLE events ADD COLUMN source TEXT DEFAULT 'Unknown'")
                conn.commit()
                print("[DB] Migration completed: 'source' column added successfully.")
            else:
                print("[DB] SQLite database already has 'source' column. Skip migration.")
        except Exception as e:
            print(f"🚨 SQLite 移行中にエラーが発生しました: {str(e)}")
        
    conn.close()
    print("[DB] Database initialized successfully.")

def insert_event(event: dict) -> bool:
    """
    イベント情報を挿入する。
    重複がある場合は無視（スキップ）します。
    戻り値: 新しく挿入された場合は True、重複していてスキップされた場合は False
    """
    from scraper.utils import normalize_event_url
    url = normalize_event_url(event.get("url", ""))
    title = event.get("title", "")
    date = event.get("date", "")
    area = event.get("area", "その他")
    performers = event.get("performers", "")
    raw_text = event.get("raw_text", "")
    source = event.get("source") or "Unknown"
    
    # URLが空の場合は、重複防止のためタイトル・出演者・日付から一意なIDを生成
    if not url:
        url = f"local_id:{performers}:{title}:{date}"
        
    # event辞書側のurlも正規化したものにアップデートしておく
    event["url"] = url
        
    conn = get_connection()
    cursor = get_cursor(conn)
    database_url = os.getenv("DATABASE_URL")
    
    try:
        if database_url:
            # PostgreSQL: ON CONFLICT を用いて主キー重複時は何もしない
            cursor.execute("""
                INSERT INTO events (url, title, date, area, performers, raw_text, source)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (url) DO NOTHING
            """, (url, title, date, area, performers, raw_text, source))
        else:
            # SQLite: INSERT OR IGNORE を使用
            cursor.execute("""
                INSERT OR IGNORE INTO events (url, title, date, area, performers, raw_text, source)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (url, title, date, area, performers, raw_text, source))
            
        conn.commit()
        
        # 実際に挿入された行数を確認
        inserted = cursor.rowcount > 0
        return inserted
    except Exception as e:
        print(f"🚨 データベース保存中にエラーが発生しました: {str(e)}")
        if database_url:
            conn.rollback()
        return False
    finally:
        conn.close()

def query_events(date_str: str = None, area_str: str = None, keyword: str = None) -> list:
    """
    日付、地域、またはキーワードに基づいてイベントを検索する。
    日付は 'YYYY-MM-DD' 形式を想定。
    地域は '東京', '新潟', 'その他'。
    """
    conn = get_connection()
    cursor = get_cursor(conn)
    database_url = os.getenv("DATABASE_URL")
    
    query = "SELECT * FROM events"
    params = []
    conditions = []
    
    placeholder = "%s" if database_url else "?"
    
    # 過去（2025年など）の古い情報を除外するため、
    # 明示的な日付指定がない場合は「昨日以降（昨日を含む）」のイベントのみを対象にする
    yesterday_str = (datetime.today() - timedelta(days=1)).strftime("%Y-%m-%d")
    
    if date_str:
        conditions.append(f"date = {placeholder}")
        params.append(date_str)
    else:
        # 日付の指定がない場合は昨日以降のイベントのみを表示
        conditions.append(f"date >= {placeholder}")
        params.append(yesterday_str)
        
    if area_str:
        conditions.append(f"area = {placeholder}")
        params.append(area_str)
        
    if keyword:
        # タイトルまたは出演者名に部分一致
        conditions.append(f"(title LIKE {placeholder} OR performers LIKE {placeholder})")
        params.append(f"%{keyword}%")
        params.append(f"%{keyword}%")
        
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
        
    # 日付の古い順（これから開催される順）でソート
    query += " ORDER BY date ASC, created_at DESC"
    
    try:
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        events = []
        for row in rows:
            source_val = "Unknown"
            try:
                source_val = row["source"] or "Unknown"
            except (KeyError, IndexError, sqlite3.OperationalError, Exception):
                pass
                
            events.append({
                "url": row["url"],
                "title": row["title"],
                "date": row["date"],
                "area": row["area"],
                "performers": row["performers"],
                "raw_text": row["raw_text"],
                "source": source_val
            })
        return events
    except Exception as e:
        print(f"🚨 データベース検索中にエラーが発生しました: {str(e)}")
        return []
    finally:
        conn.close()

def get_event_by_url(url: str) -> dict:
    """
    URLを指定してイベントを取得する。
    重複判定用に使用します。
    """
    if not url:
        return None
        
    from scraper.utils import normalize_event_url
    url = normalize_event_url(url)
    
    conn = get_connection()
    cursor = get_cursor(conn)
    import os
    database_url = os.getenv("DATABASE_URL")
    
    placeholder = "%s" if database_url else "?"
    query = f"SELECT * FROM events WHERE url = {placeholder}"
    
    try:
        cursor.execute(query, (url,))
        row = cursor.fetchone()
        if row:
            source_val = "Unknown"
            try:
                source_val = row["source"] or "Unknown"
            except Exception:
                pass
            return {
                "url": row["url"],
                "title": row["title"],
                "date": row["date"],
                "area": row["area"],
                "performers": row["performers"],
                "raw_text": row["raw_text"],
                "source": source_val
            }
        return None
    except Exception as e:
        print(f"🚨 URLでの検索中にエラーが発生しました: {str(e)}")
        return None
    finally:
        conn.close()

def is_duplicate_by_dedupe_key(event: dict) -> bool:
    """
    指定されたイベントが、【日付 ✕ 開始時間 ✕ 会場名(場所)】のキーで
    データベース側に既に存在するか（重複しているか）を判定する。
    """
    from scraper.utils import parse_time_and_venue, normalize_event_url
    
    # 判定対象イベントのキーを生成
    target_url = normalize_event_url(event.get("url", ""))
    target_date = event.get("date", "")
    target_title = event.get("title", "")
    target_raw = event.get("raw_text", "")
    target_area = event.get("area", "その他")
    
    # URLが空の場合に db_manager.insert_event 内で行うキー生成と同じロジックでフォールバック
    if not target_url:
        performers = event.get("performers", "")
        target_url = f"local_id:{performers}:{target_title}:{target_date}"
        
    target_time, target_venue = parse_time_and_venue(target_title, target_raw, target_area)
    target_key = f"{target_date}_{target_time}_{target_venue}"
    
    # データベースから未来（今日以降）の全イベントを取得
    conn = get_connection()
    cursor = get_cursor(conn)
    database_url = os.getenv("DATABASE_URL")
    
    today_str = datetime.today().strftime("%Y-%m-%d")
    placeholder = "%s" if database_url else "?"
    
    try:
        # 未来のイベントを全取得して走査 (URLも取得して重複判定の除外に使用)
        cursor.execute(f"SELECT url, title, date, area, raw_text FROM events WHERE date >= {placeholder}", (today_str,))
        rows = cursor.fetchall()
        
        for row in rows:
            r_url = normalize_event_url(row["url"])
            # 自分自身（同一URLのレコード）は重複排除の対象外とする
            if r_url == target_url:
                continue
                
            r_title = row["title"]
            r_raw = row["raw_text"]
            r_area = row["area"]
            r_date = row["date"]
            
            r_time, r_venue = parse_time_and_venue(r_title, r_raw, r_area)
            r_key = f"{r_date}_{r_time}_{r_venue}"
            
            if r_key == target_key:
                return True
        return False
    except Exception as e:
        print(f"🚨 重複排除キーチェック中にエラーが発生しました: {str(e)}")
        return False
    finally:
        conn.close()

# 起動時に必ずデータベース構造を確保する
init_db()

if __name__ == "__main__":
    # 単体テスト用
    print("Database manager test run")
    test_event = {
        "url": "https://test.com/events/123",
        "title": "テストイベント新潟",
        "date": "2026-07-12",
        "area": "新潟",
        "performers": "テストアイドル",
        "raw_text": "新潟駅南口広場でミニライブ開催！"
    }
    
    # 挿入テスト
    is_new = insert_event(test_event)
    print(f"新規挿入成否 (1回目): {is_new} (期待値: True)")
    
    is_new_again = insert_event(test_event)
    print(f"新規挿入成否 (2回目): {is_new_again} (期待値: False / 重複スキップ)")
    
    # 検索テスト
    results = query_events(date_str="2026-07-12", area_str="新潟")
    print(f"検索結果件数: {len(results)} 件")
    for r in results:
        print(f"- {r['title']} ({r['date']} - {r['area']})")
