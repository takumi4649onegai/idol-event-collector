import json
import re
import hmac
import hashlib
import base64
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
import requests
import config
from db_manager import query_events

app = Flask(__name__)

def verify_signature(body: str, signature: str) -> bool:
    """LINE Platformからのリクエスト署名を検証する(セキュリティ対策)"""
    if not config.LINE_CHANNEL_SECRET:
        return True # キーが未設定の場合は検証をスキップ
        
    hash = hmac.new(
        config.LINE_CHANNEL_SECRET.encode('utf-8'),
        body.encode('utf-8'),
        hashlib.sha256
    ).digest()
    expected_signature = base64.b64encode(hash).decode('utf-8')
    return hmac.compare_digest(expected_signature, signature)

def parse_user_message(text: str) -> tuple:
    """
    ユーザーのメッセージから「日付 (YYYY-MM-DD)」「地域 (東京/新潟)」「キーワード」を抽出する。
    戻り値: (date_str, area_str, keyword)
    """
    if not text:
        return None, None, None
        
    area = None
    date_str = None
    keyword = None
    
    # 1. 本命アイドルの名前が含まれているかチェック
    # 例：「東京CuteCute」「Red radiance」など
    # もし含まれている場合は、キーワードとして抽出し、名前の中にある「東京」という文字で地域判定が誤作動するのを防ぐために、テキストから一旦名前を除外して地域判定する
    # ※スペースの有無を無視して柔軟にマッチングします
    matched_idol = None
    clean_text_for_area = text
    for idol in config.MARKING_IDOLS:
        name = idol["name"]
        # スペースを除去して比較
        clean_name = name.replace(" ", "").lower()
        clean_user_text = text.replace(" ", "").lower()
        if clean_name in clean_user_text:
            matched_idol = name
            # ユーザー入力からスペースを許容しつつ名前を切り抜く正規表現
            pattern = re.compile(r'\s*'.join(re.escape(char) for char in name), re.IGNORECASE)
            clean_text_for_area = pattern.sub("", text)
            break
            
    # 2. 地域判定 (アイドル名を除外した後のテキストで判定)
    if "新潟" in clean_text_for_area or "niigata" in clean_text_for_area.lower():
        area = "新潟"
    elif "東京" in clean_text_for_area or "tokyo" in clean_text_for_area.lower():
        area = "東京"
        
    # 3. 日付判定
    today = datetime.today()
    
    if "今日" in text or "本日" in text or "きょう" in text:
        date_str = today.strftime("%Y-%m-%d")
    elif "明日" in text or "あした" in text:
        date_str = (today + timedelta(days=1)).strftime("%Y-%m-%d")
    elif "明後日" in text or "あさって" in text:
        date_str = (today + timedelta(days=2)).strftime("%Y-%m-%d")
    else:
        # 正規表現パターンで「M/D」「M月D日」等の具体的な日付表記を検索
        # パターンA: 7/12, 07/12, 7-12
        match_slash = re.search(r'(\d{1,2})[-/](\d{1,2})', text)
        # パターンB: 7月12日
        match_kanji = re.search(r'(\d{1,2})月(\d{1,2})日', text)
        
        month, day = None, None
        if match_slash:
            month = int(match_slash.group(1))
            day = int(match_slash.group(2))
        elif match_kanji:
            month = int(match_kanji.group(1))
            day = int(match_kanji.group(2))
            
        if month and day:
            # 今年を補完して YYYY-MM-DD 形式に成形
            current_year = today.year
            try:
                target_date = datetime(current_year, month, day)
                # もし指定された日付が既に過去であり、かつ今日より大幅に前の場合は翌年とみなす（年越しの境界対策）
                if target_date < today - timedelta(days=30):
                    target_date = datetime(current_year + 1, month, day)
                date_str = target_date.strftime("%Y-%m-%d")
            except ValueError:
                pass # 無効な日付（例: 2月30日など）の場合は無視
                
    # キーワードが検出されたか、あるいは他の言葉が含まれているか
    if matched_idol:
        keyword = matched_idol
    else:
        # 日付や地域以外の特定の単語があればキーワードとする (例: 「対バン」「フリーライブ」など)
        # ただし「何かある」「教えて」などはキーワードから除外する
        clean_kw = text
        # 日付や地域の一般的なフレーズを除去
        for w in ["今日", "本日", "明日", "あした", "明後日", "あさって", "新潟", "東京", "何かある", "なんかある", "ある", "教えて", "イベント", "ライブ", "の", "で", "に", "が", "を", "は"]:
            clean_kw = clean_kw.replace(w, "")
        clean_kw = clean_kw.strip()
        if len(clean_kw) >= 2: # 2文字以上ならキーワードとみなす
            keyword = clean_kw
            
    return date_str, area, keyword

def send_reply(reply_token: str, reply_text: str):
    """LINEの Messaging API を用いてユーザーに返信する"""
    if not config.LINE_CHANNEL_ACCESS_TOKEN:
        print("⚠️ LINE Channel Access Token が設定されていません。返信をスキップします。")
        return
        
    url = "https://api.line.me/v2/bot/message/reply"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {config.LINE_CHANNEL_ACCESS_TOKEN}"
    }
    payload = {
        "replyToken": reply_token,
        "messages": [
            {
                "type": "text",
                "text": reply_text
            }
        ]
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)
        if response.status_code != 200:
            print(f"❌ LINE返信に失敗しました: HTTP {response.status_code}")
            print(response.text)
    except Exception as e:
        print(f"🚨 LINE返信中に例外が発生しました: {str(e)}")

@app.route("/callback", methods=["POST"])
def callback():
    """LINEのWebhookコールバック受付"""
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)
    
    # 署名検証
    if not verify_signature(body, signature):
        return "Invalid Signature", 400
        
    try:
        events = json.loads(body).get("events", [])
        for event in events:
            # 1. グループID(groupId)の自動抽出と保存
            # LINE Notify廃止に伴い、Messaging APIでの自動プッシュ配信先としてグループIDを動的にキャッチします。
            source = event.get("source", {})
            if source.get("type") == "group":
                group_id = source.get("groupId")
                if group_id:
                    current_stored = ""
                    import os
                    if os.path.exists("group_id.txt"):
                        try:
                            with open("group_id.txt", "r", encoding="utf-8") as f:
                                current_stored = f.read().strip()
                        except Exception:
                            pass
                    
                    if current_stored != group_id:
                        try:
                            with open("group_id.txt", "w", encoding="utf-8") as f:
                                f.write(group_id)
                            print(f"📁 [LINE] グループIDが自動保存されました: {group_id}")
                        except Exception as e:
                            print(f"🚨 [LINE] グループIDの書き込みに失敗しました: {str(e)}")

            # 2. メッセージイベントかつテキストメッセージのみ処理
            if event.get("type") == "message" and event.get("message", {}).get("type") == "text":
                reply_token = event.get("replyToken")
                user_text = event.get("message", {}).get("text", "").strip()
                
                # メッセージの解析 (日付・地域・キーワードを取り出す)
                target_date, target_area, target_keyword = parse_user_message(user_text)
                
                # 日付、地域、キーワードのいずれも検出できなかった場合はヘルプメッセージを返す
                if not target_date and not target_area and not target_keyword:
                    reply_text = (
                        "🌟【地下アイドルイベント案内ボット】🌟\n\n"
                        "探したい「日付」や「地域」または「グループ名」を入れて話しかけてください！\n"
                        "（例：「今日新潟でなんかある？」「東京CuteCuteある？」「5/30東京」など）\n\n"
                        "※自動的にチケットサイトや公式Xを巡回して、該当するライブ情報を探してその場でお答えします！"
                    )
                    send_reply(reply_token, reply_text)
                    continue
                
                # データベースから条件に合うイベントを検索
                db_results = query_events(date_str=target_date, area_str=target_area, keyword=target_keyword)
                
                # 返信メッセージの組み立て
                header_date = target_date if target_date else "いつでも"
                header_area = target_area if target_area else "全地域"
                header_kw = f" 🔑【{target_keyword}】" if target_keyword else ""
                
                if db_results:
                    # 1. 表示件数の制限 (画面が埋まらないように最大15件)
                    max_display = 15
                    display_results = db_results[:max_display]
                    remaining_count = len(db_results) - max_display
                    
                    # 2. フラットなリスト形式の組み立て (何月何日 | イベント名 🔗 URL)
                    event_list_text = []
                    for ev in display_results:
                        date_display = ev["date"]
                        try:
                            dt = datetime.strptime(ev["date"], "%Y-%m-%d")
                            weeks = ["月", "火", "水", "木", "金", "土", "日"]
                            w_str = weeks[dt.weekday()]
                            date_display = f"{dt.strftime('%m/%d')}({w_str})"
                        except Exception:
                            pass
                            
                        # 改行や複数スペースを綺麗に整形
                        clean_ev_title = re.sub(r'\s+', ' ', ev['title'].replace('\n', ' ').replace('\r', ' ')).strip()
                        # チケットサイトのタグを取り除く
                        clean_ev_title = clean_ev_title.replace("【LivePocket】", "").replace("【TIGET】", "").replace("【TicketDive】", "").strip()
                        
                        url_part = f" 🔗 {ev['url']}" if ev['url'] and not ev['url'].startswith("local_id:") else ""
                        perf_part = f" (👥 {ev['performers']})" if ev['performers'] and not target_keyword else ""
                        
                        # 『何月何日 | イベント名 🔗 URL』のフラットなリスト形式
                        event_list_text.append(f"・{date_display} | {clean_ev_title}{perf_part}{url_part}")
                        
                    events_joined = "\n".join(event_list_text).strip()
                    
                    # 他にもイベントがある場合のご案内フッター
                    footer_text = ""
                    if remaining_count > 0:
                        footer_text = f"※ほかにも {remaining_count} 件あります。「5/30東京CuteCute」のように日付を絞ると詳しく見られます！\n"
                    
                    reply_text = (
                        f"📅【{header_date}】 📍【{header_area}】{header_kw}\n"
                        f"新着順イベント情報 (全 {len(db_results)} 件)\n"
                        f"────────────────────\n\n"
                        f"{events_joined}\n\n"
                        f"────────────────────\n"
                        f"{footer_text}"
                        f"行きたいイベントは見つかりましたか？🌟"
                    )
                else:
                    # 該当なしの場合
                    reply_text = (
                        f"📅【{header_date}】 📍【{header_area}】{header_kw}\n"
                        f"のアイドルイベントは見つかりませんでした😢\n\n"
                        f"新しくチケットサイトに登録されたら、自動的に検索してお答えします！"
                    )
                
                send_reply(reply_token, reply_text)
                
    except Exception as e:
        print(f"🚨 Webhook処理中に例外が発生しました: {str(e)}")
        
    return "OK", 200

if __name__ == "__main__":
    import sys
    import io
    # Windowsコンソールでのcp932エラー回避 (リアルタイム出力)
    if sys.platform.startswith('win'):
        try:
            sys.stdout.reconfigure(encoding='utf-8')
            sys.stderr.reconfigure(encoding='utf-8')
        except AttributeError:
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', write_through=True)
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', write_through=True)
        
    print(f"🔌 LINE Webhook サーバーをポート {config.PORT} で起動します...")
    app.run(host="0.0.0.0", port=config.PORT, debug=False)
