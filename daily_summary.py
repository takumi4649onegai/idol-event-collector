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
    
    # 日付のフォーマット (例: 06/09)
    try:
        t_dt = datetime.strptime(today_str, "%Y-%m-%d")
        t_display = t_dt.strftime("%m/%d")
    except Exception:
        t_display = today_str
        
    try:
        tm_dt = datetime.strptime(tomorrow_str, "%Y-%m-%d")
        tm_display = tm_dt.strftime("%m/%d")
    except Exception:
        tm_display = tomorrow_str
        
    # エリア件数のカウント
    def count_by_area(events):
        counts = {"新潟": 0, "東京": 0, "その他": 0}
        for ev in events:
            area = ev.get("area", "その他")
            if area in counts:
                counts[area] += 1
            else:
                counts["その他"] += 1
        return counts
        
    t_counts = count_by_area(today_events)
    tm_counts = count_by_area(tomorrow_events)
    
    # タイトル部分の作成
    lines = [
        "【朝まとめ｜アイドルイベント】",
        "",
        f"本日（{t_display}）",
        f"・新潟：{t_counts['新潟']}件",
        f"・東京：{t_counts['東京']}件",
        f"・その他：{t_counts['その他']}件",
        "",
        f"明日（{tm_display}）",
        f"・新潟：{tm_counts['新潟']}件",
        f"・東京：{tm_counts['東京']}件",
        f"・その他：{tm_counts['その他']}件",
        ""
    ]
    
    # 今日も明日もイベントが0件の場合
    if len(today_events) == 0 and len(tomorrow_events) == 0:
        lines.extend([
            "DB登録済みのイベントは見つかりませんでした。",
            "急な告知は未反映の可能性があります。"
        ])
        return "\n".join(lines)
        
    # 本日の主なイベントの作成 (今日にイベントがある場合のみ詳細表示)
    if len(today_events) > 0:
        lines.append("【本日の主なイベント】")
        
        # 新潟イベントを優先して並び替える
        sorted_today = sorted(
            today_events,
            key=lambda x: 0 if x.get("area") == "新潟" else (1 if x.get("area") == "東京" else 2)
        )
        
        max_details = 5
        details_to_show = sorted_today[:max_details]
        
        for idx, ev in enumerate(details_to_show, 1):
            title = ev.get("title", "")
            # タイトルからソース表示を除去してクリーンに
            clean_title = title.replace("【LivePocket】", "").replace("【TIGET】", "").replace("【TicketDive】", "").replace("【X告知】", "").replace("【HP告知】", "").replace("【Web検索】", "").strip()
            
            # 日付の月日フォーマット
            ev_date = ev.get("date", "")
            try:
                dt_obj = datetime.strptime(ev_date, "%Y-%m-%d")
                date_formatted = dt_obj.strftime("%m/%d")
            except Exception:
                date_formatted = ev_date
                
            area = ev.get("area", "その他")
            performers = ev.get("performers", "未設定")
            source = ev.get("source", "Unknown")
            
            # 会場情報の抽出
            from scraper.utils import parse_time_and_venue
            _, venue = parse_time_and_venue(title, ev.get("raw_text", ""), area)
            
            lines.append(f"{idx}. {date_formatted} {area}｜{clean_title}")
            lines.append(f"出演：{performers}")
            lines.append(f"会場：{venue}")
            lines.append(f"情報源：{source}")
            lines.append("")
            
        # 6件以上ある場合
        if len(today_events) > max_details:
            extra_count = len(today_events) - max_details
            lines.append(f"ほか{extra_count}件あります。")
            lines.append("")
            
    lines.append("詳細はLINEで「今日新潟」「明日東京」などと送って確認できます。")
    
    return "\n".join(lines).strip()

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
