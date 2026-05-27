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
    
    # メッセージの作成
    raw_text_section = ""
    if "raw_text" in event and event["raw_text"]:
        indented_text = "\n".join(f"  {line}" for line in event["raw_text"].split("\n")[:10])
        if len(event["raw_text"].split("\n")) > 10:
            indented_text += "\n  ..."
        raw_text_section = f"\n\n📝 【告知本文】:\n{indented_text}"
        
    message_text = (
        f"🌟【本命アイドル新着情報】🌟\n"
        f"📅 日付: {event['date']}\n"
        f"📍 エリア: {event['area']}\n"
        f"🎤 ライブ名: {event['title']}\n"
        f"👥 出演: {event['performers']}\n"
        f"🔗 詳細URL: {event['url'] or 'なし'}"
        f"{raw_text_section}\n"
        f"────────────────────"
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
