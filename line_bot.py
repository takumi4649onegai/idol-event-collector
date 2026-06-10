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

import json
import re
import hmac
import hashlib
import base64
from datetime import datetime, timedelta, timezone
JST = timezone(timedelta(hours=9))
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
    today = datetime.now(JST)
    
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
                target_date = datetime(current_year, month, day, tzinfo=JST)
                # もし指定された日付が既に過去であり、かつ今日より大幅に前の場合は翌年とみなす（年越しの境界対策）
                if target_date < today - timedelta(days=30):
                    target_date = datetime(current_year + 1, month, day, tzinfo=JST)
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
        for w in ["今日", "本日", "明日", "あした", "明後日", "あさって", "今週", "こんしゅう", "来週", "らいしゅう", "新潟", "東京", "何かある", "なんかある", "ある", "教えて", "イベント", "ライブ", "の", "で", "に", "が", "を", "は", "？", "?"]:
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

def search_web_free_lives(area: str, date_str: str) -> list:
    """Tavily Web Search 機能を無効化（全面禁止ルール適用）"""
    return []

def search_web_keyword(keyword: str, date_str: str = None) -> list:
    """Tavily Web Search 機能を無効化（全面禁止ルール適用）"""
    return []

from scraper.tiget import scrape_tiget_by_state

PENDING_REGISTRATIONS = {}


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
                
                sender_id = event.get("source", {}).get("groupId") or event.get("source", {}).get("userId")
                
                # addcal コマンドの判定
                addcal_match = re.match(r"^addcal\s+(\S+)", user_text, re.IGNORECASE)
                if addcal_match:
                    target_id = addcal_match.group(1).lower()
                    print(f"💬 LINE addcal コマンド受信: target_id={target_id}")
                    
                    db_events = query_events(date_str=None)
                    from scraper.utils import generate_event_short_id, is_niigata_general_source
                    
                    matched_events = []
                    for ev in db_events:
                        url = ev.get("url", "")
                        if url:
                            ev_id = generate_event_short_id(url)
                            if ev_id == target_id:
                                matched_events.append(ev)
                                
                    if not matched_events:
                        reply_text = (
                            "該当するイベントが見つかりませんでした。\n"
                            "通知または検索結果に表示された addcal のIDを確認してください。"
                        )
                    elif len(matched_events) > 1:
                        reply_text = "同じIDのイベントが複数見つかりました。イベント名を確認してください。"
                    else:
                        target_ev = matched_events[0]
                        source_val = target_ev.get("source")
                        
                        if not is_niigata_general_source(source_val):
                            reply_text = (
                                "このイベントはaddcal対象外です。\n"
                                "本命アイドル予定は通常の自動同期対象です。"
                            )
                        else:
                            from calendar_client import add_to_google_calendar
                            success = add_to_google_calendar(target_ev)
                            
                            if success:
                                date_str = target_ev.get("date", "")
                                start_time = target_ev.get("start_time") or target_ev.get("open_time") or ""
                                
                                from scraper.utils import parse_time_and_venue
                                parsed_time, _ = parse_time_and_venue(target_ev.get("title", ""), target_ev.get("raw_text", "") or "", target_ev.get("area", ""))
                                if parsed_time and parsed_time != "00:00":
                                    time_display = f" {parsed_time}"
                                else:
                                    time_display = f" {start_time}" if start_time else ""
                                
                                date_display = date_str
                                try:
                                    dt = datetime.strptime(date_str, "%Y-%m-%d")
                                    weeks = ["月", "火", "水", "木", "金", "土", "日"]
                                    w_str = weeks[dt.weekday()]
                                    date_display = f"{dt.strftime('%m/%d')}({w_str})"
                                except Exception:
                                    pass
                                
                                clean_title = target_ev.get("title", "")
                                for prefix in ["【LivePocket】", "【TIGET】", "【TicketDive】", "【X告知】", "【HP告知】", "【Web検索】", "【TimeTree】", "【公式カレンダー】"]:
                                    clean_title = clean_title.replace(prefix, "")
                                clean_title = clean_title.strip()
                                
                                reply_text = (
                                    f"Googleカレンダーに追加しました。\n\n"
                                    f"{date_display}{time_display}\n"
                                    f"{clean_title}"
                                )
                            else:
                                reply_text = "❌ Googleカレンダーの追加に失敗しました。設定を確認してください。"
                                
                    send_reply(reply_token, reply_text)
                    continue
                
                # 保留中の登録候補に対する「はい」「登録」の意思確認
                if user_text in ["はい", "登録"] and sender_id and sender_id in PENDING_REGISTRATIONS:
                    pending_event = PENDING_REGISTRATIONS.pop(sender_id)
                    from db_manager import insert_event
                    success = insert_event(pending_event)
                    
                    if success:
                        calendar_synced = False
                        try:
                            from calendar_client import add_to_google_calendar
                            calendar_synced = add_to_google_calendar(pending_event)
                        except Exception as ce:
                            print(f"🚨 Googleカレンダー登録でエラーが発生しました: {ce}")
                            
                        date_display = pending_event['date']
                        try:
                            dt = datetime.strptime(pending_event['date'], "%Y-%m-%d")
                            weeks = ["月", "火", "水", "木", "金", "土", "日"]
                            w_str = weeks[dt.weekday()]
                            date_display = f"{dt.strftime('%m/%d')}({w_str})"
                        except Exception:
                            pass
                            
                        reply_text = (
                            f"✅ イベントをデータベースに登録しました！\n\n"
                            f"・タイトル: {pending_event['title']}\n"
                            f"・日付: {date_display}\n"
                            f"・会場: {pending_event['venue']}\n"
                        )
                        if calendar_synced:
                            reply_text += "📅 Googleカレンダーにも自動同期されました。"
                        else:
                            reply_text += "⚠️ Googleカレンダー同期はスキップされました（設定未完了またはエラー）。"
                    else:
                        reply_text = "⚠️ データベース保存に失敗したか、既に登録されています。"
                        
                    send_reply(reply_token, reply_text)
                    continue
                else:
                    # 「はい」「登録」以外のメッセージを受信した場合は、誤動作防止のために保留中のデータをクリア
                    if sender_id and sender_id in PENDING_REGISTRATIONS:
                        PENDING_REGISTRATIONS.pop(sender_id, None)
                
                # TicketDive URL検出
                url_match = re.search(r'(https?://)?(www\.)?(ticketdive\.com/event/[a-zA-Z0-9_-]+|t-dv\.com/[a-zA-Z0-9_-]+)', user_text)
                if url_match:
                    raw_url = url_match.group(0)
                    full_url = raw_url
                    if not raw_url.startswith("http://") and not raw_url.startswith("https://"):
                        full_url = "https://" + raw_url
                        
                    from scraper.ticketdive import scrape_ticketdive_event_by_url
                    event_data = scrape_ticketdive_event_by_url(full_url)
                    
                    if not event_data:
                        send_reply(reply_token, "⚠️ TicketDive のイベント情報を取得できませんでした。URLが正しいかご確認ください。")
                        continue
                        
                    from db_manager import get_event_by_url
                    existing_event = get_event_by_url(event_data["url"])
                    
                    if existing_event:
                        date_display = existing_event['date']
                        try:
                            dt = datetime.strptime(existing_event['date'], "%Y-%m-%d")
                            weeks = ["月", "火", "水", "木", "金", "土", "日"]
                            w_str = weeks[dt.weekday()]
                            date_display = f"{dt.strftime('%m/%d')}({w_str})"
                        except Exception:
                            pass
                        from scraper.utils import parse_time_and_venue
                        _, venue = parse_time_and_venue(existing_event['title'], existing_event.get('raw_text', ''), existing_event['area'])
                        reply_text = (
                            f"📢 このイベントは既に登録されています。\n\n"
                            f"・タイトル: {existing_event['title']}\n"
                            f"・日付: {date_display}\n"
                            f"・会場: {venue}"
                        )
                        send_reply(reply_token, reply_text)
                        continue
                        
                    if sender_id:
                        PENDING_REGISTRATIONS[sender_id] = event_data
                        
                    date_display = event_data['date']
                    try:
                        dt = datetime.strptime(event_data['date'], "%Y-%m-%d")
                        weeks = ["月", "火", "水", "木", "金", "土", "日"]
                        w_str = weeks[dt.weekday()]
                        date_display = f"{dt.strftime('%m/%d')}({w_str})"
                    except Exception:
                        pass
                        
                    reply_text = (
                        f"📅【TicketDive 登録候補】\n"
                        f"登録候補のイベントが見つかりました！\n\n"
                        f"・タイトル: {event_data['title']}\n"
                        f"・日付: {date_display}\n"
                        f"・開場時間: {event_data['open_time'] or '未設定'}\n"
                        f"・開演時間: {event_data['start_time'] or '未設定'}\n"
                        f"・会場: {event_data['venue'] or '未設定'}\n"
                        f"・出演者: {event_data['performers'] or '未設定'}\n"
                        f"・URL: {event_data['url']}\n"
                        f"・情報源: {event_data['source']}\n\n"
                        f"この内容でデータベースに登録しますか？\n"
                        f"登録する場合は「はい」または「登録」と返信してください。"
                    )
                    send_reply(reply_token, reply_text)
                    continue
                
                # デバッグ診断コマンド
                if user_text.lower() in ["デバッグ", "debug", "診断", "しんだん"]:
                    from calendar_client import run_calendar_diagnostics
                    diagnostics_res = run_calendar_diagnostics()
                    send_reply(reply_token, diagnostics_res)
                    continue

                # カレンダー手動同期コマンド
                if user_text.lower() in ["同期", "sync", "そうき"]:
                    from calendar_client import manually_sync_db_to_calendar
                    sync_res = manually_sync_db_to_calendar()
                    send_reply(reply_token, sync_res)
                    continue

                # ケミカル⇄リアクション スケジュール一括登録コマンド
                if user_text in ["ケミカルスケジュール", "スケジュール登録", "スケジュール", "けみかるすけじゅーる"]:
                    from import_chemical_schedule import import_chemical_schedule
                    report = import_chemical_schedule()
                    reply_text = (
                        f"📅【ケミカル⇄リアクション スケジュール登録】\n"
                        f"公式Xから抽出したライブ予定（5月〜7月）を一括登録・同期しました！\n\n"
                        f"・処理した予定: {report['total']} 件\n"
                        f"・新規カレンダー登録: {report['added']} 件\n"
                        f"・重複スキップ: {report['skipped']} 件\n"
                    )
                    if report['failed'] > 0:
                        reply_text += f"・カレンダー同期失敗: {report['failed']} 件\n"
                        
                    reply_text += (
                        f"\n💡「同期」と送信するか、サーバー起動時に、Googleカレンダーへの自動再同期が試みられます。\n"
                        f"「今日新潟」や「ケミカル」と話しかけて最新の予定を検索することも可能です！🌟"
                    )
                    send_reply(reply_token, reply_text)
                    continue

                # 「追加 NGT48」や「登録 NGT48」といった命令コマンドを判定する
                if user_text.startswith("追加") or user_text.startswith("登録"):
                    # コマンドの後に続く対象名（グループ名等）を切り出す
                    new_idol_name = re.sub(r'^(追加|登録)\s*', '', user_text).strip()
                    if new_idol_name:
                        import config
                        is_added = config.add_custom_idol(new_idol_name)
                        if is_added:
                            reply_text = (
                                f"🎉【登録完了】\n"
                                f"新しい推しグループ「{new_idol_name}」を監視リストに追加しました！\n\n"
                                f"次回以降の自動定期巡回時に、チケット販売サイトや公式Xなどの収集対象として自動追加されます。\n\n"
                                f"💡今すぐ情報が見たい場合は、「{new_idol_name}」と話しかけてください！リアルタイムWeb検索から直近の予定を自動回収して返信します🌟"
                            )
                        else:
                            reply_text = f"💡「{new_idol_name}」はすでに監視リストに登録されています！そのまま「{new_idol_name}」と話しかけていただければ検索可能です。"
                    else:
                        reply_text = "⚠️「追加 NGT48」のように、「追加」の後に半角スペースを空けてグループ名やメンバー名を入力してください。"
                    send_reply(reply_token, reply_text)
                    continue
                
                # 「今日何かある？」「今日の予定」「明日何かある？」「明日の予定」の特別ハンドリング
                normalized_text = re.sub(r'[\s？?]', '', user_text)
                if normalized_text in ["今日何かある", "今日の予定", "明日何かある", "明日の予定"]:
                    if "今日" in normalized_text:
                        target_date_str = datetime.now(JST).strftime("%Y-%m-%d")
                        header = "🌅 今日の推し活予定"
                    else:
                        target_date_str = (datetime.now(JST) + timedelta(days=1)).strftime("%Y-%m-%d")
                        header = "🌅 明日の推し活予定"
                    
                    print(f"💬 LINE予定まとめ質問受信: {user_text} -> 対象日付: {target_date_str}")
                    db_events = query_events(date_str=target_date_str)
                    from summary_formatter import format_daily_schedule
                    reply_text = format_daily_schedule(db_events, target_date_str, header_prefix=header)
                    send_reply(reply_token, reply_text)
                    continue
                
                is_this_week = "今週" in user_text or "こんしゅう" in user_text
                is_next_week = "来週" in user_text or "らいしゅう" in user_text
                
                # メッセージの解析 (日付・地域・キーワードを取り出す)
                target_date, target_area, target_keyword = parse_user_message(user_text)
                
                if is_this_week or is_next_week:
                    target_date = None
                
                # 日付、地域、キーワード、今週/来週のいずれも検出できなかった場合はヘルプメッセージを返す
                if not target_date and not target_area and not target_keyword and not is_this_week and not is_next_week:
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
                
                # リアルタイムスクレイピングは実行しない（全面禁止）
                web_results = []
                
                # データのマージ (SQLite DBの結果のみ)
                merged_results = db_results + web_results
                
                # LINE Bot応答時のコンソールログ出力
                log_date = target_date
                if is_this_week:
                    log_date = "今週"
                elif is_next_week:
                    log_date = "来週"
                elif not target_date:
                    log_date = "指定なし"
                
                print(f"💬 LINE質問受信: {user_text}")
                print(f"📅 判定日付: {log_date}")
                print(f"📍 判定地域: {target_area}")
                print("🗄️ DB検索のみ実行")
                print("🌐 リアルタイムスクレイピングなし")
                print(f"🔎 検索結果: {len(merged_results)}件")

                
                # 具体的な日付が指定されている場合、その日付に完全一致するもの以外を徹底排除 (過去や未来の誤混入防止)
                if target_date:
                    merged_results = [ev for ev in merged_results if ev.get("date", "") == target_date]
                
                # 今週・来週の日付フィルターの適用
                today = datetime.now(JST)
                if is_this_week:
                    start_date = today.strftime("%Y-%m-%d")
                    end_date = (today + timedelta(days=6 - today.weekday())).strftime("%Y-%m-%d")
                    merged_results = [ev for ev in merged_results if start_date <= ev.get("date", "") <= end_date]
                elif is_next_week:
                    start_date = (today + timedelta(days=7 - today.weekday())).strftime("%Y-%m-%d")
                    end_date = (today + timedelta(days=13 - today.weekday())).strftime("%Y-%m-%d")
                    merged_results = [ev for ev in merged_results if start_date <= ev.get("date", "") <= end_date]

                
                # 返信メッセージの組み立て
                if is_this_week:
                    header_date = "今週"
                elif is_next_week:
                    header_date = "来週"
                else:
                    header_date = target_date if target_date else "いつでも"
                
                header_area = target_area if target_area else "全地域"
                header_kw = f" 🔑【{target_keyword}】" if target_keyword else ""
                
                if merged_results:
                    # 時間軸の早い順（開催日の昇順）で並び替え
                    merged_results.sort(key=lambda x: x.get("date", "9999-12-31"))
                    
                    # 1. 表示件数の制限 (画面が埋まらないように最大15件)
                    max_display = 15
                    display_results = merged_results[:max_display]
                    remaining_count = len(merged_results) - max_display
                    
                    # 2. 分類用のリスト作成 (確定チケット販売 vs SNS/HP告知)
                    ticket_list_text = []
                    sns_list_text = []
                    links_footer = []
                    link_idx = 1
                    
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
                        orig_title = ev['title']
                        clean_ev_title = re.sub(r'\s+', ' ', orig_title.replace('\n', ' ').replace('\r', ' ')).strip()
                        
                        # チケットサイトに属するか判定
                        url = ev.get("url", "")
                        is_ticket = any(k in orig_title for k in ["【LivePocket】", "【TIGET】", "【TicketDive】"]) or \
                                    any(k in url for k in ["livepocket.jp", "tiget.net", "ticketdive.com"])
                                    
                        # 表示用にソースタグを取り除く
                        clean_ev_title = clean_ev_title.replace("【LivePocket】", "").replace("【TIGET】", "").replace("【TicketDive】", "").replace("【X告知】", "").replace("【HP告知】", "").replace("【Web検索】", "").strip()
                        
                        # URLの生出しを禁止し、フッター用にインデックス化して退避
                        url_part = ""
                        if url and not url.startswith("local_id:"):
                            url_part = f" [{link_idx}]"
                            links_footer.append(f"[{link_idx}] {clean_ev_title}\n🔗 {url}")
                            link_idx += 1
                            
                        perf_part = f" (👥 {ev['performers']})" if ev['performers'] and not target_keyword else ""
                        source_val = ev.get("source") or "Unknown"
                        
                        from scraper.utils import is_niigata_general_source, generate_event_short_id
                        addcal_part = ""
                        if is_niigata_general_source(source_val):
                            short_id = generate_event_short_id(url)
                            if short_id:
                                addcal_part = f" [addcal: {short_id}]"
                        
                        # 行の作成
                        event_line = f"・{date_display} | {clean_ev_title}{perf_part} (情報源: {source_val}){addcal_part}{url_part}"
                        
                        if is_ticket:
                            ticket_list_text.append(event_line)
                        else:
                            sns_list_text.append(event_line)
                            
                    # カテゴリ別テキストの組み立て
                    events_joined_parts = []
                    if ticket_list_text:
                        events_joined_parts.append("🎫【確定チケット販売サイト】\n" + "\n".join(ticket_list_text))
                    if sns_list_text:
                        events_joined_parts.append("📢【SNS告知・メディア出演情報】\n" + "\n".join(sns_list_text))
                        
                    events_joined = "\n\n".join(events_joined_parts).strip()
                    
                    # 関連リンクフッターの組み立て
                    links_section = ""
                    if links_footer:
                        links_section = "\n\n📲 関連リンク (チケット・告知等):\n" + "\n\n".join(links_footer)
                    
                    # 他にもイベントがある場合のご案内フッター
                    footer_text = ""
                    if remaining_count > 0:
                        footer_text = f"※ほかにも {remaining_count} 件あります。「5/30東京CuteCute」のように日付を絞ると詳しく見られます！\n"
                    
                    reply_text = (
                        f"📅【{header_date}】 📍【{header_area}】{header_kw}\n"
                        f"開催順イベント情報 (全 {len(merged_results)} 件)\n"
                        f"────────────────────\n\n"
                        f"{events_joined}"
                        f"{links_section}\n\n"
                        f"────────────────────\n"
                        f"{footer_text}"
                        f"行きたいイベントは見つかりましたか？🌟"
                    )
                else:
                    # 該当なしの場合（0件時返答の改善）
                    # 日付の表記ラベル決定
                    if is_this_week:
                        date_label = "今週"
                    elif is_next_week:
                        date_label = "来週"
                    else:
                        parsed_date = target_date if target_date else datetime.now(JST).strftime("%Y-%m-%d")
                        if "今日" in user_text or "本日" in user_text or "きょう" in user_text or target_date == datetime.now(JST).strftime("%Y-%m-%d"):
                            date_label = f"本日（{parsed_date}）"
                        elif "明日" in user_text or "あした" in user_text:
                            date_label = f"明日（{parsed_date}）"
                        elif "明後日" in user_text or "あさって" in user_text:
                            date_label = f"明後日（{parsed_date}）"
                        elif target_date:
                            date_label = f"{parsed_date}"
                        else:
                            date_label = "指定期間"

                    # 地域の表記ラベル決定
                    area_label = target_area if target_area else ("新潟" if "新潟" in user_text else ("東京" if "東京" in user_text else "指定地域"))
                    
                    # キーワード表記ラベル決定
                    kw_label = f"「{target_keyword}」の" if target_keyword else ""

                    reply_text = (
                        f"{date_label}、{area_label}で{kw_label}DB登録済みのアイドルイベントは見つかりませんでした。\n\n"
                        f"確認対象：\n"
                        f"・保存済みイベントデータ\n"
                        f"・定期巡回で取得済みのTIGETイベント\n\n"
                        f"注意：\n"
                        f"リアルタイム検索ではないため、公式XやTIGET以外の急な告知は未反映の可能性があります。"
                    )
                
                send_reply(reply_token, reply_text)

                
    except Exception as e:
        print(f"🚨 Webhook処理中に例外が発生しました: {str(e)}")
        
    return "OK", 200

def sync_all_db_events_to_calendar():
    """データベース内の未来の予定をすべてGoogleカレンダーへ強制同期する（重複は自動回避）"""
    import config
    if not config.GOOGLE_CALENDAR_ID or not config.GOOGLE_SERVICE_ACCOUNT_JSON:
        return
        
    print("🔄 [Startup] Googleカレンダーへのデータベース全体同期を開始します...")
    from db_manager import query_events
    from calendar_client import add_to_google_calendar
    from datetime import datetime
    import time
    
    # サーバー起動時に少し待ってから開始（初期化待ち）
    time.sleep(5)
    
    # 今日以降のイベントをすべて取得
    today_str = datetime.now(JST).strftime("%Y-%m-%d")

    events = query_events(date_str=None)
    
    sync_count = 0
    for ev in events:
        if ev.get("date", "") >= today_str:
            from scraper.utils import is_niigata_general_source
            if is_niigata_general_source(ev.get("source")):
                continue
            success = add_to_google_calendar(ev)
            if success:
                sync_count += 1
                time.sleep(1.0) # APIレート制限回避
                
    print(f"📊 [Startup] Googleカレンダー同期完了: {sync_count} 件のイベントを処理しました。")

if __name__ == "__main__":
    # バックグラウンドスレッドでGoogleカレンダー全体同期を走らせる
    import threading
    threading.Thread(target=sync_all_db_events_to_calendar, daemon=True).start()

    print(f"🔌 LINE Webhook サーバーをポート {config.PORT} で起動します...")
    app.run(host="0.0.0.0", port=config.PORT, debug=False)
