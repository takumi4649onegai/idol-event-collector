import os
import requests
import sys
import io
import config

GROUP_ID_FILE = "group_id.txt"
LINE_PUSH_API = "https://api.line.me/v2/bot/message/push"

def get_group_id() -> str:
    """自動保存されたLINEグループIDを読み込む"""
    # 1. まず環境変数から取得を試みる (GitHub Actions などのクラウド用)
    env_group_id = os.getenv("LINE_GROUP_ID", "")
    if env_group_id:
        return env_group_id.strip()
        
    # 2. 次にローカルのファイルから読み込む
    if os.path.exists(GROUP_ID_FILE):
        try:
            with open(GROUP_ID_FILE, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception as e:
            print(f"⚠️ グループIDファイルの読み込みに失敗しました: {str(e)}")
    return ""

def send_line_push_notification(event: dict) -> bool:
    """
    収集した新着イベント情報を、LINE Messaging APIを通じてLINEグループへプッシュ送信する。
    """
    if not config.LINE_CHANNEL_ACCESS_TOKEN:
        print("⚠️ LINE Channel Access Token が設定されていないため、プッシュ通知をスキップします。")
        return False
        
    group_id = get_group_id()
    if not group_id:
        print("⚠️ LINEグループID(groupId)がまだ保存されていません。")
        print("   ボットアカウントをLINEグループに追加し、何か一言（例:「テスト」）発言して自動取得させてください。")
        return False
        
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {config.LINE_CHANNEL_ACCESS_TOKEN}"
    }
    
    from scraper.utils import parse_time_and_venue
    from datetime import datetime
    
    title = event.get("title", "")
    raw_text = event.get("raw_text", "")
    area = event.get("area", "その他")
    date_str = event.get("date", "")
    
    # 時間と会場の抽出
    start_time, venue = parse_time_and_venue(title, raw_text, area)
    
    # 曜日のパースと日付整形
    weekday_str = ""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        weeks = ["月", "火", "水", "木", "金", "土", "日"]
        weekday_str = f"({weeks[dt.weekday()]})"
        display_date = f"{dt.strftime('%Y/%m/%d')}{weekday_str}"
    except Exception:
        display_date = date_str
        
    time_display = f" {start_time}" if start_time and start_time != "00:00" else ""
    
    # タイトルからソース表示を除去してクリーンに
    clean_title = title.replace("【LivePocket】", "").replace("【TIGET】", "").replace("【TicketDive】", "").replace("【X告知】", "").replace("【HP告知】", "").replace("【Web検索】", "").strip()
    
    # 新潟ローカルシグナルの検出
    combined_text = f"{title} {raw_text}"
    is_niigata_local = any(kw in combined_text for kw in ["新潟", "ガタ", "古町", "苗場"])
    
    header = "🚨【見逃し厳禁速報】新潟ローカルシグナル検知！" if is_niigata_local else "🌟【本命マークアイドル新着情報】🌟"
    
    # URLの生出しを禁止し、メッセージ最下部に格納する形式に変更
    url_section = ""
    event_url = event.get('url')
    if event_url and not event_url.startswith("local_id:"):
        url_section = f"\n📲 公式チケット・告知詳細:\n🔗 {event_url}"
        
    source_name = event.get("source") or "Unknown"
    
    if source_name in ["TicketDive", "TicketDive Manual"]:
        message_text = (
            f"【新着イベント｜TicketDive】\n"
            f"・タイトル：{clean_title}\n"
            f"・日付：{display_date}{time_display}\n"
            f"・会場：{venue}\n"
            f"・出演：{event.get('performers', '')}\n"
            f"・URL：{event_url or 'なし'}"
        )
    else:
        message_text = (
            f"{header}\n"
            f"🗓️ 日時：{display_date}{time_display}\n"
            f"🎵 イベント名：{clean_title}\n"
            f"📍 会場：{venue}\n"
            f"情報源：{source_name}\n"
            f"────────────────────"
            f"{url_section}"
        )
    
    payload = {
        "to": group_id,
        "messages": [
            {
                "type": "text",
                "text": message_text
            }
        ]
    }
    
    try:
        response = requests.post(LINE_PUSH_API, headers=headers, json=payload, timeout=15)
        if response.status_code == 200:
            print(f"🔔 LINEプッシュ通知送信成功: {event['title']}")
            return True
        else:
            print(f"❌ LINEプッシュ通知送信失敗: HTTP {response.status_code}")
            print(response.text)
            return False
    except Exception as e:
        print(f"🚨 LINEプッシュ通知送信中に例外が発生しました: {str(e)}")
        return False

if __name__ == "__main__":
    # 単体テスト用
    import sys
    import io
    if sys.platform.startswith('win'):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
        
    print("LINE Client (Messaging API) Test Run")
    sample_event = {
        "date": "2026-07-12",
        "area": "東京",
        "title": "【テスト】真夏のアイドル対バンLIVE 2026",
        "performers": "東京CuteCute",
        "url": "https://tiget.net/events/sample",
        "raw_text": "【急告！】\n本日18:00より秋葉原ドンキホーテ店頭にてフリーライブを行います！\n観覧無料です！ぜひお越しください！"
    }
    send_line_push_notification(sample_event)
