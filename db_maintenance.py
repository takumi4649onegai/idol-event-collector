import os
import sys
import json
from datetime import datetime
import db_manager

def run_select():
    print("Connecting to database...")
    conn = db_manager.get_connection()
    cursor = db_manager.get_cursor(conn)
    
    database_url = os.getenv("DATABASE_URL")
    placeholder = "%s" if database_url else "?"
    
    query = f"""
        SELECT url, title, date, area, performers, source, created_at 
        FROM events 
        WHERE source = {placeholder} AND area = {placeholder} AND title = {placeholder}
    """
    params = ("TIGET", "新潟", "【TIGET】無題のイベント")
    
    print(f"Executing query with params: {params}")
    cursor.execute(query, params)
    rows = cursor.fetchall()
    
    print(f"\nFound {len(rows)} target records.")
    
    backup_data = []
    for row in rows:
        # row can be accessed as dict due to DictCursor
        item = {
            "url": row["url"],
            "title": row["title"],
            "date": row["date"],
            "area": row["area"],
            "performers": row["performers"],
            "source": row["source"],
            "created_at": str(row["created_at"]) if row["created_at"] else None
        }
        backup_data.append(item)
    
    # Print list to stdout
    print("\n--- Target Records List ---")
    for idx, item in enumerate(backup_data):
        print(f"[{idx+1}] Title: {item['title']} | Date: {item['date']} | Area: {item['area']} | Source: {item['source']} | URL: {item['url']}")
    
    # Save backup as JSON
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"db_backup_untitled_events_{timestamp}.json"
    with open(backup_filename, "w", encoding="utf-8") as f:
        json.dump(backup_data, f, ensure_ascii=False, indent=4)
    
    print(f"\nBackup successfully saved to {backup_filename}")
    conn.close()
    return len(rows)

# run_delete has been removed for safety

def is_wrong_niigata(item: dict) -> bool:
    title = item.get("title", "") or ""
    raw_text = item.get("raw_text", "") or ""
    combined = (title + " " + raw_text).lower()
    
    # 1. 新潟の超特定キーワードが含まれているか
    niigata_specific = [
        "nexs niigata", "nexs", "club riverst", "riverst", "golden pigs", "goldenpigs",
        "柳都showcase", "柳都show!case!!", "柳都オレンジスタジアム", "新潟lots", "lots",
        "朱鷺メッセ", "新潟県民会館", "りゅーとぴあ", "ラブラ万代", "cocolo新潟", "ジョイアミーア"
    ]
    has_niigata_place = "場所：新潟" in raw_text or "会場：新潟" in raw_text or "場所 : 新潟" in raw_text or "場所：新潟県" in raw_text
    
    if has_niigata_place or any(kw in combined for kw in niigata_specific):
        return False  # This is a valid Niigata event
        
    # 2. 他地域のキーワードが含まれているか
    exclude_keywords = [
        "東京", "tokyo", "京都", "kyoto", "広島", "hiroshima", "大阪", "osaka", "名古屋", "nagoya",
        "福岡", "fukuoka", "横浜", "yokohama", "千葉", "chiba", "埼玉", "saitama"
    ]
    for kw in exclude_keywords:
        if kw in combined:
            return True  # This is an incorrect event (contains other region)
            
    # 3. 一般的な新潟ワードが一切含まれていない場合も他地域とみなす
    niigata_general = ["新潟", "niigata", "長岡", "三条", "上越", "新発田", "燕", "柏崎", "佐渡"]
    if not any(kw in combined for kw in niigata_general):
        return True  # Incorrect event (no Niigata keyword at all)
        
    return False

def run_select_wrong_niigata():
    print("Connecting to database...")
    conn = db_manager.get_connection()
    cursor = db_manager.get_cursor(conn)
    
    database_url = os.getenv("DATABASE_URL")
    placeholder = "%s" if database_url else "?"
    
    query = f"""
        SELECT url, title, date, area, performers, source, raw_text
        FROM events 
        WHERE area = {placeholder} AND source = {placeholder}
    """
    params = ("新潟", "TIGET")
    cursor.execute(query, params)
    rows = cursor.fetchall()
    
    wrong_records = []
    for row in rows:
        item = {
            "url": row["url"],
            "title": row["title"],
            "date": row["date"],
            "area": row["area"],
            "performers": row["performers"],
            "source": row["source"],
            "raw_text": row["raw_text"] or ""
        }
        if is_wrong_niigata(item):
            wrong_records.append(item)
            
    print(f"\nFound {len(wrong_records)} incorrect Niigata TIGET events in DB (out of {len(rows)} total Niigata TIGET events).")
    
    print("\n--- Target Records List ---")
    for idx, item in enumerate(wrong_records):
        print(f"[{idx+1}] Title: {item['title']} | Date: {item['date']} | Area: {item['area']} | Source: {item['source']} | URL: {item['url']}")
        
    # Save backup as JSON (without raw_text to keep it cleaner)
    backup_data = []
    for r in wrong_records:
        backup_data.append({
            "url": r["url"],
            "title": r["title"],
            "date": r["date"],
            "area": r["area"],
            "performers": r["performers"],
            "source": r["source"]
        })
        
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"db_backup_wrong_niigata_{timestamp}.json"
    with open(backup_filename, "w", encoding="utf-8") as f:
        json.dump(backup_data, f, ensure_ascii=False, indent=4)
        
    print(f"\nBackup successfully saved to {backup_filename}")
    conn.close()
    return len(wrong_records)

# run_delete_wrong_niigata has been removed for safety

def main():
    action = os.getenv("MAINTENANCE_ACTION", "SELECT").upper()
    print(f"=== Database Maintenance action={action} ===")
    
    if action == "SELECT":
        run_select()
    elif action == "SELECT_WRONG_NIIGATA":
        run_select_wrong_niigata()
    else:
        print(f"Unknown action: {action} (DELETE actions have been deactivated for safety)")
        sys.exit(1)

if __name__ == "__main__":
    main()
