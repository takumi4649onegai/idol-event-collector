import os
import sys
import io

# Windowsコンソールでの絵文字表示による UnicodeEncodeError (cp932) 回避用 (リアルタイム出力)
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        # 古いPython環境向けのフォールバック
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', write_through=True)
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', write_through=True)

from datetime import datetime, timezone, timedelta
import requests
import db_manager

LINE_PUSH_API = "https://api.line.me/v2/bot/message/push"

def build_summary_text(today_events: list, tomorrow_events: list, today_str: str, tomorrow_str: str) -> str:
    """今日と明日のイベントリストから、LINEに送信するまとめテキストを作成する"""
    from summary_formatter import format_daily_schedule
    return format_daily_schedule(today_events, today_str, header_prefix="🌅 今日の推し活予定")

def send_summary():
    """朝まとめ通知を実行する"""
    print("🌅 朝まとめ通知処理を開始します...")
    
    # 環境変数の検証
    access_token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
    group_id = os.getenv("LINE_GROUP_ID", "")
    database_url = os.getenv("DATABASE_URL", "")
    
    # 接続情報（DATABASE_URL）がない場合は、エラーログを出して終了（ローカル開発用にSQLite接続を試みる）
    if not database_url:
        print("⚠️ 警告: DATABASE_URL が設定されていません。ローカルの SQLite (events.db) から取得を試みます。")
        
    # LINEトークン類の検証
    missing_secrets = []
    if not access_token:
        missing_secrets.append("LINE_CHANNEL_ACCESS_TOKEN")
    if not group_id:
        missing_secrets.append("LINE_GROUP_ID")
        
    if missing_secrets:
        print(f"❌ エラー: 必要な環境変数が設定されていません: {', '.join(missing_secrets)}")
        print("   通知文の生成テストのみ実行します。")
        
    # JSTでの日付計算
    JST = timezone(timedelta(hours=9))
    now_jst = datetime.now(JST)
    today_str = now_jst.strftime("%Y-%m-%d")
    tomorrow_str = (now_jst + timedelta(days=1)).strftime("%Y-%m-%d")
    
    print(f"📅 対象日付: 本日 {today_str} / 明日 {tomorrow_str}")
    
    # イベントデータの取得
    try:
        today_events = db_manager.query_events(date_str=today_str)
        tomorrow_events = db_manager.query_events(date_str=tomorrow_str)
        print(f"🗄️ 取得結果: 本日 {len(today_events)} 件 / 明日 {len(tomorrow_events)} 件")
    except Exception as e:
        print(f"❌ データベース接続・クエリ実行エラー: {str(e)}")
        sys.exit(1)
        
    # メッセージテキスト構築
    summary_text = build_summary_text(today_events, tomorrow_events, today_str, tomorrow_str)
    
    print("\n--- 送信メッセージプレビュー ---")
    print(summary_text)
    print("--------------------------------\n")
    
    # Secretsが欠落している場合はここで終了
    if missing_secrets:
        print("⚠️ LINE Secretsが不足しているため、LINEへの送信をスキップします（プレビューのみ完了）。")
        return
        
    # LINEへのプッシュ送信
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}"
    }
    
    payload = {
        "to": group_id,
        "messages": [
            {
                "type": "text",
                "text": summary_text
            }
        ]
    }
    
    try:
        response = requests.post(LINE_PUSH_API, headers=headers, json=payload, timeout=15)
        if response.status_code == 200:
            print("✅ LINEまとめ通知の送信に成功しました！")
        else:
            print(f"❌ LINEまとめ通知の送信に失敗しました: HTTP {response.status_code}")
            print(response.text)
            sys.exit(1)
    except Exception as e:
        print(f"❌ LINEへのPOST通信エラー: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    send_summary()
