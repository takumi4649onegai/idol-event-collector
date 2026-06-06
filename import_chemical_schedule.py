import re
import sys
import io
from datetime import datetime
import db_manager
from calendar_client import add_to_google_calendar

if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', write_through=True)
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', write_through=True)

SCHEDULE_TEXT = """
【 5月 】
31新潟 ※野外

【 6月 】
4宮城
5福島
6新潟 ※野外・無料
7新潟
12東京
13静岡
14新潟 ※野外・無料
20福島
21新潟 ※野外・無料
22東京
27愛知
28愛知

【 7月 】
3大阪
6島根
7島根
"""

def import_chemical_schedule() -> dict:
    """
    ケミカル⇄リアクションのX上のスケジュールテキストを解析し、
    データベース(events.db)およびGoogleカレンダーに一括登録・同期します。
    """
    lines = SCHEDULE_TEXT.strip().split("\n")
    current_month = None
    events = []

    # 1. テキスト解析
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # 月ヘッダーの検出
        month_match = re.match(r'【\s*(\d+)月\s*】', line)
        if month_match:
            current_month = int(month_match.group(1))
            continue
        
        if current_month is None:
            continue
            
        # スケジュール行の検出 (例: "31新潟 ※野外", "4宮城", "6新潟 ※野外・無料")
        line_match = re.match(r'^(\d+)([^※\s\d]+)(.*)$', line)
        if line_match:
            day = int(line_match.group(1))
            area_name = line_match.group(2).strip()
            notes = line_match.group(3).strip()
            
            # 日付文字列 (YYYY-MM-DD) の構築 (2026年想定)
            date_str = f"2026-{current_month:02d}-{day:02d}"
            
            # DBの地域(area)判定
            area = "その他"
            if "新潟" in area_name:
                area = "新潟"
            elif "東京" in area_name:
                area = "東京"
                
            # タイトルの組み立て
            notes_str = f" {notes}" if notes else ""
            title = f"ケミカル⇄リアクション ライブ（{area_name}{notes_str}）"
            
            event = {
                # 重複登録防止のユニークID（XのポストID + 日付）
                "url": f"https://x.com/michiproject/status/205922010436194721#{current_month:02d}-{day:02d}",
                "title": title,
                "date": date_str,
                "area": area,
                "performers": "ケミカル⇄リアクション",
                "raw_text": f"ケミカル⇄リアクション 公式Xスケジュール\n日付: {current_month}月{day}日\n場所: {area_name}\n備考: {notes}",
                "source": "X"
            }
            events.append(event)

    # 2. データベース保存 ＆ Googleカレンダー同期
    db_manager.init_db()
    today_str = datetime.today().strftime("%Y-%m-%d")
    
    added_count = 0
    skipped_count = 0
    failed_count = 0
    results_list = []

    for ev in events:
        # 過去のイベントはスキップ
        if ev["date"] < today_str:
            skipped_count += 1
            results_list.append({"title": ev["title"], "date": ev["date"], "status": "skipped (past)"})
            continue

        # DBへインサート (主キーURL重複で自動スキップ)
        is_new = db_manager.insert_event(ev)
        
        # すでにDBにあろうと無かろうと、Googleカレンダーへの登録（重複チェック付き）は常に呼び出す
        success = add_to_google_calendar(ev)
        if success:
            if is_new:
                added_count += 1
                results_list.append({"title": ev["title"], "date": ev["date"], "status": "synced (new)"})
            else:
                skipped_count += 1
                results_list.append({"title": ev["title"], "date": ev["date"], "status": "synced (exists in DB)"})
        else:
            failed_count += 1
            results_list.append({"title": ev["title"], "date": ev["date"], "status": "calendar_failed"})

    return {
        "total": len(events),
        "added": added_count,
        "skipped": skipped_count,
        "failed": failed_count,
        "results": results_list
    }

if __name__ == "__main__":
    print("==================================================")
    print("🎯 Importing Chemical Reaction schedule from X...")
    report = import_chemical_schedule()
    print(f"Total processed: {report['total']} events")
    print(f"🆕 Added and synced: {report['added']} events")
    print(f"⏭️ Skipped (past or duplicate): {report['skipped']} events")
    print(f"❌ Failed to sync: {report['failed']} events")
    
    print("\nDetailed results:")
    for res in report["results"]:
        print(f" - {res['date']}: {res['title']} -> {res['status']}")
    print("==================================================")
