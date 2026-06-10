import os
import sys
import io

# Windowsコンソールでのcp932エラー回避
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', write_through=True)
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', write_through=True)

from datetime import datetime, timezone, timedelta
import requests
import db_manager

LINE_PUSH_API = "https://api.line.me/v2/bot/message/push"
JST = timezone(timedelta(hours=9))

def is_niigata_related_event(ev: dict) -> bool:
    """
    イベントが「新潟一般系」または「本命アイドルの新潟開催」であるか判定する。
    """
    from scraper.utils import is_niigata_general_source
    from main import is_niigata_event_refined
    
    # 他県判定があれば除外
    if not is_niigata_event_refined(ev):
        return False
        
    source_val = ev.get("source") or "Unknown"
    
    # 新潟一般系イベントまたは新潟開催の本命アイドルイベント
    # (新潟開催判定をパスしており、DB内のデータは一般系か本命系のみのためTrueを返してOKです)
    return True

def format_niigata_reminder(events: list, is_today: bool) -> str:
    """
    新潟イベントリマインド通知の文面を構築する。
    """
    from scraper.utils import parse_time_and_venue, is_niigata_general_source, generate_event_short_id
    from summary_formatter import clean_event_title
    
    # 時間でソート
    def get_sort_key(ev):
        start_time, _ = parse_time_and_venue(ev.get("title", ""), ev.get("raw_text", "") or "", ev.get("area", ""))
        return start_time if (start_time and start_time != "00:00") else "23:59:59"
        
    events.sort(key=get_sort_key)
    
    lines = ["【新潟イベントリマインド】", ""]
    
    count = len(events)
    if is_today:
        if count == 1:
            lines.append("本日は以下のイベントがあります。")
        else:
            lines.append(f"本日は新潟絡みのイベントが{count}件あります。")
    else:
        if count == 1:
            lines.append("明日は以下のイベントがあります。")
        else:
            lines.append(f"明日は新潟絡みのイベントが{count}件あります。")
    lines.append("")
    
    for idx, ev in enumerate(events, 1):
        title = ev.get("title", "")
        raw_text = ev.get("raw_text", "") or ""
        area = ev.get("area", "その他")
        url = ev.get("url", "")
        source_val = ev.get("source") or "Unknown"
        
        # 開始時間と会場の取得
        start_time, venue = parse_time_and_venue(title, raw_text, area)
        time_part = f"{start_time} " if (start_time and start_time != "00:00") else ""
        
        clean_title = clean_event_title(title)
        lines.append(f"{idx}. {time_part}{clean_title}")
        lines.append(f"会場：{venue}")
        
        # 出演者
        performers = ev.get("performers", "")
        if performers:
            lines.append(f"出演：{performers}")
            
        # 新潟一般系イベントのみ addcal を表示
        if is_niigata_general_source(source_val) and url:
            short_id = generate_event_short_id(url)
            if short_id:
                lines.append(f"addcal {short_id}")
        
        lines.append("")
        
    return "\n".join(lines).strip()

def send_niigata_reminder(target_day_arg: str = "auto"):
    """リマインド通知を実行する"""
    print(f"🔔 新潟イベントリマインド通知処理を開始します... (指定対象日: {target_day_arg})")
    
    # 環境変数の検証
    access_token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
    group_id = os.getenv("LINE_GROUP_ID", "")
    database_url = os.getenv("DATABASE_URL", "")
    
    if not database_url:
        print("⚠️ 警告: DATABASE_URL が設定されていません。ローカルの SQLite (events.db) から取得を試みます。")
        
    missing_secrets = []
    if not access_token:
        missing_secrets.append("LINE_CHANNEL_ACCESS_TOKEN")
    if not group_id:
        missing_secrets.append("LINE_GROUP_ID")
        
    if missing_secrets:
        print(f"❌ エラー: 必要な環境変数が設定されていません: {', '.join(missing_secrets)}")
        print("   通知文の生成テストのみ実行します。")
        
    # 現在時刻 (JST)
    now_jst = datetime.now(JST)
    
    # 対象日の決定
    target_day = target_day_arg.lower().strip()
    if target_day not in ["today", "tomorrow"]:
        # 時間帯による自動判定: 12:00前なら本日(today)、12:00以降なら明日(tomorrow)
        if now_jst.hour < 12:
            target_day = "today"
        else:
            target_day = "tomorrow"
            
    if target_day == "today":
        target_date_str = now_jst.strftime("%Y-%m-%d")
        is_today = True
    else:
        target_date_str = (now_jst + timedelta(days=1)).strftime("%Y-%m-%d")
        is_today = False
        
    print(f"📅 対象日付: {target_date_str} (当日判定: {is_today})")
    
    # イベント取得
    try:
        all_events = db_manager.query_events(date_str=target_date_str)
        # 新潟絡みのイベントのみフィルタリング
        niigata_events = [ev for ev in all_events if is_niigata_related_event(ev)]
        print(f"🗄️ 取得結果: 対象日付のイベント総数={len(all_events)}件 / 新潟絡み={len(niigata_events)}件")
    except Exception as e:
        print(f"❌ データベースクエリ実行エラー: {str(e)}")
        sys.exit(1)
        
    # リマインド対象がない場合は通知を送らない
    if not niigata_events:
        print(f"⏭️ 対象日付 {target_date_str} の新潟絡みイベントは 0 件のため、LINE送信をスキップします。")
        return
        
    # 通知文の構築
    reminder_text = format_niigata_reminder(niigata_events, is_today)
    
    print("\n--- 送信メッセージプレビュー ---")
    print(reminder_text)
    print("--------------------------------\n")
    
    if missing_secrets:
        print("⚠️ LINE Secretsが不足しているため、LINEへの送信をスキップします（プレビューのみ完了）。")
        return
        
    # LINE送信
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}"
    }
    
    payload = {
        "to": group_id,
        "messages": [
            {
                "type": "text",
                "text": reminder_text
            }
        ]
    }
    
    try:
        response = requests.post(LINE_PUSH_API, headers=headers, json=payload, timeout=15)
        if response.status_code == 200:
            print("✅ LINEリマインド通知の送信に成功しました！")
        else:
            print(f"❌ LINEリマインド通知の送信に失敗しました: HTTP {response.status_code}")
            sys.exit(1)
    except Exception as e:
        print(f"🚨 LINE送信中に例外が発生しました: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "auto"
    send_niigata_reminder(arg)
