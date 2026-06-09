import os
import sys
import json
from datetime import datetime
import db_manager

def run_select():
    print("Connecting to database...")
    conn = db_manager.get_connection()
    cursor = db_manager.get_cursor(conn)
    
    query = """
        SELECT url, title, date, area, performers, source, created_at 
        FROM events 
        WHERE source = %s AND area = %s AND title = %s
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

def run_delete():
    print("Connecting to database...")
    conn = db_manager.get_connection()
    cursor = db_manager.get_cursor(conn)
    
    # Double check count first
    select_query = """
        SELECT COUNT(*) as cnt 
        FROM events 
        WHERE source = %s AND area = %s AND title = %s
    """
    params = ("TIGET", "新潟", "【TIGET】無題のイベント")
    cursor.execute(select_query, params)
    cnt = cursor.fetchone()["cnt"]
    
    if cnt == 0:
        print("No target records found to delete.")
        conn.close()
        return
        
    print(f"Confirming deletion of {cnt} target records...")
    
    delete_query = """
        DELETE FROM events 
        WHERE source = %s AND area = %s AND title = %s
    """
    cursor.execute(delete_query, params)
    conn.commit()
    print(f"Successfully deleted {cnt} records!")
    
    # Verify count after delete
    cursor.execute(select_query, params)
    verify_cnt = cursor.fetchone()["cnt"]
    print(f"Verified count of target records after deletion: {verify_cnt}")
    conn.close()

def main():
    action = os.getenv("MAINTENANCE_ACTION", "SELECT").upper()
    print(f"=== Database Maintenance action={action} ===")
    
    if action == "SELECT":
        run_select()
    elif action == "DELETE":
        run_delete()
    else:
        print(f"Unknown action: {action}")
        sys.exit(1)

if __name__ == "__main__":
    main()
