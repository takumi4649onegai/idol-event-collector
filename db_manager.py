import sqlite3
import os
import sys
import io
from datetime import datetime, timedelta

DB_FILE = "events.db"

def get_connection():
    """SQLite データベースへのコネクションを取得"""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row  # 列名でのアクセスを有効にする
    return conn

def init_db():
    """データベースとテーブルの初期化"""
    conn = get_connection()
    cursor = conn.cursor()
    
    # イベントテーブルの作成
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS events (
            url TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            date TEXT NOT NULL,
            area TEXT NOT NULL,
            performers TEXT NOT NULL,
            raw_text TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()
    print("[DB] SQLite database initialized successfully.")

def insert_event(event: dict) -> bool:
    """
    イベント情報を挿入する。
    重複がある場合は無視（スキップ）します。
    戻り値: 新しく挿入された場合は True、重複していてスキップされた場合は False
    """
    url = event.get("url", "")
    title = event.get("title", "")
    date = event.get("date", "")
    area = event.get("area", "その他")
    performers = event.get("performers", "")
    raw_text = event.get("raw_text", "")
    
    # URLが空の場合は、重複防止のためタイトル・出演者・日付から一意なIDを生成
    if not url:
        url = f"local_id:{performers}:{title}:{date}"
        
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        # INSERT OR IGNORE を用いて、主キー(url)の重複時は何もしない
        cursor.execute("""
            INSERT OR IGNORE INTO events (url, title, date, area, performers, raw_text)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (url, title, date, area, performers, raw_text))
        
        conn.commit()
        
        # 実際に挿入された行数を確認
        inserted = cursor.rowcount > 0
        return inserted
    except Exception as e:
        print(f"🚨 データベース保存中にエラーが発生しました: {str(e)}")
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
    cursor = conn.cursor()
    
    query = "SELECT * FROM events"
    params = []
    conditions = []
    
    # 過去（2025年など）の古い情報を除外するため、
    # 明示的な日付指定がない場合は「昨日以降（昨日を含む）」のイベントのみを対象にする
    yesterday_str = (datetime.today() - timedelta(days=1)).strftime("%Y-%m-%d")
    
    if date_str:
        conditions.append("date = ?")
        params.append(date_str)
    else:
        # 日付の指定がない場合は昨日以降のイベントのみを表示
        conditions.append("date >= ?")
        params.append(yesterday_str)
        
    if area_str:
        conditions.append("area = ?")
        params.append(area_str)
        
    if keyword:
        # タイトルまたは出演者名に部分一致
        conditions.append("(title LIKE ? OR performers LIKE ?)")
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
            events.append({
                "url": row["url"],
                "title": row["title"],
                "date": row["date"],
                "area": row["area"],
                "performers": row["performers"],
                "raw_text": row["raw_text"]
            })
        return events
    except Exception as e:
        print(f"🚨 データベース検索中にエラーが発生しました: {str(e)}")
        return []
    finally:
        conn.close()

def is_duplicate_by_dedupe_key(event: dict) -> bool:
    """
    指定されたイベントが、【日付 ✕ 開始時間 ✕ 会場名(場所)】のキーで
    データベース側に既に存在するか（重複しているか）を判定する。
    """
    from scraper.utils import parse_time_and_venue
    
    # 判定対象イベントのキーを生成
    target_date = event.get("date", "")
    target_title = event.get("title", "")
    target_raw = event.get("raw_text", "")
    target_area = event.get("area", "その他")
    
    target_time, target_venue = parse_time_and_venue(target_title, target_raw, target_area)
    target_key = f"{target_date}_{target_time}_{target_venue}"
    
    # データベースから未来（今日以降）の全イベントを取得
    conn = get_connection()
    cursor = conn.cursor()
    
    today_str = datetime.today().strftime("%Y-%m-%d")
    
    try:
        # 未来のイベントを全取得して走査
        cursor.execute("SELECT title, date, area, raw_text FROM events WHERE date >= ?", (today_str,))
        rows = cursor.fetchall()
        
        for row in rows:
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
