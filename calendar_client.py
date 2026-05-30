import json
from datetime import datetime, timedelta
import config

def add_to_google_calendar(event: dict) -> bool:
    """
    Google Calendar APIを使用して、指定されたイベントをカレンダーへ自動登録する。
    """
    if not config.GOOGLE_CALENDAR_ID or not config.GOOGLE_SERVICE_ACCOUNT_JSON:
        # 設定が不足している場合はスキップ
        return False

    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
    except ImportError:
        print("⚠️ 警告: google-api-python-client または google-auth がインストールされていないため、Googleカレンダー登録をスキップします。")
        return False

    try:
        # 環境変数からサービスアカウントのJSON文字列をパースして認証情報を生成
        service_account_info = json.loads(config.GOOGLE_SERVICE_ACCOUNT_JSON)
        credentials = service_account.Credentials.from_service_account_info(service_account_info)
        service = build('calendar', 'v3', credentials=credentials)

        # 終日イベントの場合、終了日は翌日の日付である必要がある
        date_str = event.get("date", "")
        if not date_str:
            return False

        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            next_day_str = (dt + timedelta(days=1)).strftime("%Y-%m-%d")
        except ValueError:
            return False

        # カレンダーイベントの作成
        calendar_event = {
            'summary': event.get("title", "アイドルイベント").replace("【LivePocket】", "").replace("【TIGET】", "").replace("【TicketDive】", "").strip(),
            'location': event.get("area", "その他"),
            'description': f"👥 出演者: {event.get('performers', '')}\n🔗 チケットURL: {event.get('url', '')}\n（Idol Event Collectorより自動同期）",
            'start': {
                'date': date_str,
                'timeZone': 'Asia/Tokyo',
            },
            'end': {
                'date': next_day_str,
                'timeZone': 'Asia/Tokyo',
            }
        }

        # 重複登録を避けるため、同一日かつ同一タイトルのイベントが既に存在するか確認する
        time_min = f"{date_str}T00:00:00Z"
        time_max = f"{date_str}T23:59:59Z"
        
        events_result = service.events().list(
            calendarId=config.GOOGLE_CALENDAR_ID,
            timeMin=time_min,
            timeMax=time_max,
            q=calendar_event['summary']
        ).execute()
        
        existing_events = events_result.get('items', [])
        if existing_events:
            print(f"⏭️ Googleカレンダー登録スキップ（既に存在します）: {calendar_event['summary']} ({date_str})")
            return True

        # API呼び出し
        inserted_event = service.events().insert(
            calendarId=config.GOOGLE_CALENDAR_ID,
            body=calendar_event
        ).execute()

        print(f"📅 Googleカレンダーに登録完了: {calendar_event['summary']} ({date_str}) -> ID: {inserted_event.get('id')}")
        return True

    except Exception as e:
        print(f"❌ Googleカレンダー自動登録中にエラーが発生しました: {str(e)}")
        return False
