import json
from datetime import datetime, timedelta
import config

def build_calendar_event_body(event: dict) -> dict:
    """
    Google Calendar API登録用のリソースボディを構築する。
    """
    date_str = event.get("date", "")
    if not date_str:
        return {}

    summary = (
        event.get("title", "アイドルイベント")
        .replace("【LivePocket】", "")
        .replace("【TIGET】", "")
        .replace("【TicketDive】", "")
        .replace("【X告知】", "")
        .replace("【HP告知】", "")
        .replace("【Web検索】", "")
        .replace("【公式カレンダー】", "")
        .strip()
    )

    url = event.get("url", "")
    if url.startswith("local_id:"):
        if "WIX_OFFICIAL" in url:
            url_display = "なし（公式カレンダー掲載）\n🔗 公式スケジュール: https://chemicarinet.wixsite.com/official/live-schedule"
        else:
            url_display = "なし"
    else:
        url_display = url

    description = f"👥 出演者: {event.get('performers', '')}\n🔗 チケットURL: {url_display}\n（Idol Event Collectorより自動同期）"

    # 時間情報の取得と解析
    start_time_str = event.get("start_time") or event.get("open_time") or ""
    has_time = False
    start_dt = None
    end_dt = None

    if start_time_str:
        import re
        time_match = re.match(r'^(\d{1,2}):(\d{2})', start_time_str.strip())
        if time_match:
            try:
                hour = int(time_match.group(1))
                minute = int(time_match.group(2))
                dt = datetime.strptime(date_str, "%Y-%m-%d")
                start_dt = dt.replace(hour=hour, minute=minute)
                end_dt = start_dt + timedelta(hours=2)
                has_time = True
            except Exception:
                pass

    if has_time and start_dt and end_dt:
        # dateTime形式 (JST)
        start_iso = start_dt.strftime("%Y-%m-%dT%H:%M:%S+09:00")
        end_iso = end_dt.strftime("%Y-%m-%dT%H:%M:%S+09:00")
        start_payload = {
            'dateTime': start_iso,
            'timeZone': 'Asia/Tokyo',
        }
        end_payload = {
            'dateTime': end_iso,
            'timeZone': 'Asia/Tokyo',
        }
    else:
        # 従来通りの終日予定 (date形式)
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            next_day_str = (dt + timedelta(days=1)).strftime("%Y-%m-%d")
        except ValueError:
            return {}
        start_payload = {
            'date': date_str,
            'timeZone': 'Asia/Tokyo',
        }
        end_payload = {
            'date': next_day_str,
            'timeZone': 'Asia/Tokyo',
        }

    return {
        'summary': summary,
        'location': event.get("area", "その他"),
        'description': description,
        'start': start_payload,
        'end': end_payload
    }

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

        calendar_event = build_calendar_event_body(event)
        if not calendar_event:
            return False

        date_str = event.get("date", "")

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

def run_calendar_diagnostics() -> str:
    """Googleカレンダー連携のデバッグ用診断を実行する（読み書き両方の権限をチェック）"""
    if not config.GOOGLE_CALENDAR_ID:
        return "❌ GOOGLE_CALENDAR_ID が環境変数に設定されていません。"
    if not config.GOOGLE_SERVICE_ACCOUNT_JSON:
        return "❌ GOOGLE_SERVICE_ACCOUNT_JSON が環境変数に設定されていません。"

    try:
        service_account_info = json.loads(config.GOOGLE_SERVICE_ACCOUNT_JSON)
    except Exception as e:
        return f"❌ GOOGLE_SERVICE_ACCOUNT_JSON のJSONパースに失敗しました: {str(e)}"

    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
    except ImportError:
        return "❌ google-api-python-client または google-auth がインストールされていません。"

    try:
        credentials = service_account.Credentials.from_service_account_info(service_account_info)
        service = build('calendar', 'v3', credentials=credentials)
        
        # 1. 読み込みテスト
        service.events().list(
            calendarId=config.GOOGLE_CALENDAR_ID,
            maxResults=1
        ).execute()
        read_status = "✅ 読み込み権限: あり"
    except Exception as e:
        return (
            f"❌ Googleカレンダー疎通テスト失敗（読み込み失敗）:\n{str(e)}\n\n"
            f"💡対策: カレンダーID（{config.GOOGLE_CALENDAR_ID}）が正しいこと、およびGoogle Cloud Consoleで「Google Calendar API」が有効化されていることを確認してください。"
        )

    # 2. 書き込みテスト (ダミー予定の挿入と削除)
    try:
        dummy_event = {
            'summary': '🔍 疎通確認用テストイベント',
            'start': {'date': '2099-12-31', 'timeZone': 'Asia/Tokyo'},
            'end': {'date': '2100-01-01', 'timeZone': 'Asia/Tokyo'}
        }
        inserted = service.events().insert(
            calendarId=config.GOOGLE_CALENDAR_ID,
            body=dummy_event
        ).execute()
        
        # 挿入できたらすぐに削除する
        event_id = inserted.get('id')
        if event_id:
            service.events().delete(
                calendarId=config.GOOGLE_CALENDAR_ID,
                eventId=event_id
            ).execute()
        write_status = "✅ 書き込み権限: あり（予定の作成・削除に成功しました）"
    except Exception as e:
        write_status = (
            f"❌ 書き込み権限: なし（エラー: {str(e)}）\n"
            f"💡対策: Googleカレンダーの設定画面（マイカレンダーの設定 ➡ 特定のユーザーまたはグループとの共有）で、サービスアカウント（{credentials.service_account_email}）に対する権限が「予定の変更」または「変更および共有の管理」になっているか確認してください。「予定の表示（すべての予定の詳細）」のままだと書き込み（同期）ができません。"
        )

    tavily_status = "✅ Web検索機能 (Tavily API): 有効" if config.TAVILY_API_KEY else "⚠️ Web検索機能 (Tavily API): 未設定（💡対策: リアルタイムWeb検索を利用するには、Renderの環境変数に TAVILY_API_KEY を設定してください）"

    return (
        f"📋 システム診断レポート:\n"
        f"・カレンダーID: {config.GOOGLE_CALENDAR_ID}\n"
        f"・接続アカウント: {credentials.service_account_email}\n"
        f"・{read_status}\n"
        f"・{write_status}\n"
        f"・{tavily_status}"
    )

def manually_sync_db_to_calendar() -> str:
    """データベース内の未来の予定をすべてGoogleカレンダーへ手動同期し、詳細レポートを返す"""
    import config
    if not config.GOOGLE_CALENDAR_ID or not config.GOOGLE_SERVICE_ACCOUNT_JSON:
        return "❌ Googleカレンダーの設定（IDまたはサービスアカウントキー）が不足しています。"
        
    from db_manager import query_events
    import time
    
    today_str = datetime.today().strftime("%Y-%m-%d")
    events = query_events(date_str=None)
    
    processed = 0
    added = 0
    skipped = 0
    failed = 0
    errors = []
    
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        service_account_info = json.loads(config.GOOGLE_SERVICE_ACCOUNT_JSON)
        credentials = service_account.Credentials.from_service_account_info(service_account_info)
        service = build('calendar', 'v3', credentials=credentials)
    except Exception as e:
        return f"❌ Google Calendar API クライアント初期化失敗: {str(e)}"
    
    for ev in events:
        date_str = ev.get("date", "")
        if date_str >= today_str:
            processed += 1
            try:
                calendar_event = build_calendar_event_body(ev)
                if not calendar_event:
                    failed += 1
                    continue
                
                # 重複チェック
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
                    skipped += 1
                else:
                    service.events().insert(
                        calendarId=config.GOOGLE_CALENDAR_ID,
                        body=calendar_event
                    ).execute()
                    added += 1
                    time.sleep(0.5) # レート制限対策
            except Exception as e:
                failed += 1
                err_msg = str(e)
                if err_msg not in errors:
                    errors.append(err_msg)
                    
    err_report = ""
    if errors:
        err_report = "\n⚠️ 発生したエラー:\n" + "\n".join([f"・{err}" for err in errors[:3]])
        
    return (
        f"📊 カレンダー手動同期結果:\n"
        f"・未来の対象イベント: {processed} 件\n"
        f"・新規登録: {added} 件\n"
        f"・重複スキップ: {skipped} 件\n"
        f"・失敗: {failed} 件"
        f"{err_report}"
    )
