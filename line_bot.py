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

def scrape_tiget_by_state(state_id: int) -> list:
    """TIGETの都道府県ID指定のイベント一覧から情報をリアルタイムに抽出する"""
    if not state_id:
        return []
    url = f"https://tiget.net/events?q%5Bstate_id_eq%5D={state_id}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8"
    }
    found_events = []
    try:
        from bs4 import BeautifulSoup
        from scraper.utils import parse_date, clean_text, determine_area, is_generic_list_url
        import urllib.parse
        
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            links = soup.find_all("a", href=re.compile(r'^/events/\d+'))
            seen_urls = set()
            for link in links:
                href = link.get("href", "")
                event_url = f"https://tiget.net{href}"
                if event_url in seen_urls:
                    continue
                seen_urls.add(event_url)
                
                # 一覧ページURLは除外
                if is_generic_list_url(event_url):
                    continue
                    
                # カード親要素の特定
                container = link
                for _ in range(4):
                    parent = container.parent
                    if parent and parent.name in ["div", "article", "li"]:
                        container = parent
                        break
                
                container_text = container.get_text(separator=" | ")
                
                # タイトルの抽出
                title = link.get_text().strip()
                if not title:
                    heading = container.find(["h2", "h3", "h4", "strong"])
                    title = heading.get_text().strip() if heading else "無題のイベント"
                title = clean_text(title)
                
                # 日付の抽出
                date_match = re.search(r'(\d{4}[-/.]\d{1,2}[-/.]\d{1,2})|(\d{1,2}月\d{1,2}日)', container_text)
                event_date = parse_date(date_match.group(0)) if date_match else parse_date(container_text)
                
                # エリア判定
                area = determine_area(container_text)
                
                found_events.append({
                    "date": event_date,
                    "area": area,
                    "title": f"【TIGET】{title}",
                    "performers": "東京CuteCute",  # デフォルト
                    "url": event_url,
                    "raw_text": container_text
                })
    except Exception as e:
        print(f"🚨 TIGETエリアスクレイピング中にエラー: {str(e)}")
    return found_events

    return []

    
    # 検索用クエリの作成 (例: "2026-05-30 新潟 アイドル フリーライブ リリイベ インストア")
    query = f"{date_str} {area} アイドル フリーライブ リリイベ インストア"
    url = "https://api.tavily.com/search"
    payload = {
        "api_key": config.TAVILY_API_KEY,
        "query": query,
        "search_depth": "advanced",
        "include_answer": False,
        "max_results": 5
    }
    
    found_events = []
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            results = response.json().get("results", [])
            for res in results:
                title = res.get("title", "")
                link = res.get("url", "")
                snippet = res.get("content", "")
                
                if not title or not link:
                    continue
                
                # 汎用イベント一覧ページや、他地域ノイズのフィルタリング
                url_lower = link.lower()
                title_lower = title.lower()
                snippet_lower = snippet.lower()
                
                # A. 汎用の「全国店舗イベント一覧」ページ（個別イベント名がないもの）はノイズになるためスキップ
                if "store/event" in url_lower or "store/list" in url_lower or "event/index" in url_lower:
                    if not any(k in title_lower or k in snippet_lower for k in ["発売記念", "ミニライブ", "特典会", "フリーライブ", "リリイベ"]):
                        continue
                
                # B. 地域間のクロスノイズ判定（例：新潟検索時に東京の地名が入っていて新潟の文字がないものを弾く）
                tokyo_keywords = ["東京", "tokyo", "shibuya", "渋谷", "shinjuku", "新宿", "harajuku", "原宿", "ikebukuro", "池袋", "akihabara", "秋葉原"]
                niigata_keywords = ["新潟", "niigata", "bandai", "万代", "furumachi", "古町"]
                
                if area == "新潟":
                    if any(k in url_lower or k in title_lower for k in tokyo_keywords) and not any(k in title_lower or k in snippet_lower for k in niigata_keywords):
                        continue
                elif area == "東京":
                    if any(k in url_lower or k in title_lower for k in niigata_keywords) and not any(k in title_lower or k in snippet_lower for k in tokyo_keywords):
                        continue

                # タイトルを少し綺麗に整形し、Web検索由来であることがわかるようにマーク
                clean_title = f"【Web検索】{title.strip()}"
                
                # スニペットやタイトルから日付を抽出
                event_date = None
                # スニペットからシステムメンテナンスや規約・お知らせのノイズを除去して誤判定を防ぐ
                clean_snippet = snippet
                for noise_word in ["メンテナンス", "システム", "ログイン", "利用規約", "お知らせ", "会員登録", "アンケート"]:
                    clean_snippet = re.sub(r'[^.!?。\n]*' + re.escape(noise_word) + r'[^.!?。\n]*', '', clean_snippet)

                # まずタイトルから日付抽出を試みる (タイトルの方がノイズが少ないため)
                date_match = re.search(r'(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})', title)
                if not date_match:
                    date_match = re.search(r'(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})', clean_snippet)

                if date_match:
                    event_date = f"{date_match.group(1)}-{int(date_match.group(2)):02d}-{int(date_match.group(3)):02d}"
                else:
                    md_match = re.search(r'(\d{1,2})月(\d{1,2})日', title)
                    if not md_match:
                        md_match = re.search(r'(\d{1,2})月(\d{1,2})日', clean_snippet)

                    if md_match:
                        year = datetime.today().year
                        event_date = f"{year}-{int(md_match.group(1)):02d}-{int(md_match.group(2)):02d}"
                    else:
                        slash_match = re.search(r'(\d{1,2})/(\d{1,2})', title)
                        if not slash_match:
                            slash_match = re.search(r'(\d{1,2})/(\d{1,2})', clean_snippet)

                        if slash_match:
                            year = datetime.today().year
                            event_date = f"{year}-{int(slash_match.group(1)):02d}-{int(slash_match.group(2)):02d}"

                if not event_date:
                    if re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
                        event_date = date_str
                    else:
                        event_date = datetime.today().strftime("%Y-%m-%d")

                found_events.append({
                    "url": link,
                    "title": clean_title,
                    "date": event_date,
                    "area": area,
                    "performers": "街のフリーライブ/リリイベ",
                    "raw_text": snippet
                })
        else:
            print(f"❌ Tavily API エラー: HTTP {response.status_code}")
    except Exception as e:
        print(f"🚨 Tavily Web検索中に例外が発生しました: {str(e)}")
        
    return found_events

def search_web_keyword(keyword: str, date_str: str = None) -> list:
    """Tavily Web Search 機能を無効化（全面禁止ルール適用）"""
    return []

    return []

        
    query_parts = [keyword]
    if date_str:
        query_parts.append(date_str)
    query_parts.append("(ライブ OR イベント OR 告知 OR 出演 OR ラジオ OR 水着)")
    
    query = " ".join(query_parts) + " -site:youtube.com"
    url = "https://api.tavily.com/search"
    payload = {
        "api_key": config.TAVILY_API_KEY,
        "query": query,
        "search_depth": "advanced",
        "include_answer": False,
        "max_results": 10
    }
    
    found_events = []
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            results = response.json().get("results", [])
            for res in results:
                title = res.get("title", "")
                link = res.get("url", "")
                snippet = res.get("content", "")
                
                if not title or not link:
                    continue
                    
                # スニペットやタイトルから日付を抽出
                event_date = date_str
                if not event_date:
                    # スニペットからシステムメンテナンスや規約・お知らせのノイズを除去して誤判定を防ぐ
                    clean_snippet = snippet
                    for noise_word in ["メンテナンス", "システム", "ログイン", "利用規約", "お知らせ", "会員登録", "アンケート"]:
                        clean_snippet = re.sub(r'[^.!?。\n]*' + re.escape(noise_word) + r'[^.!?。\n]*', '', clean_snippet)

                    # まずタイトルから日付抽出を試みる (タイトルの方がノイズが少ないため)
                    date_match = re.search(r'(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})', title)
                    if not date_match:
                        date_match = re.search(r'(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})', clean_snippet)

                    if date_match:
                        event_date = f"{date_match.group(1)}-{int(date_match.group(2)):02d}-{int(date_match.group(3)):02d}"
                    else:
                        md_match = re.search(r'(\d{1,2})月(\d{1,2})日', title)
                        if not md_match:
                            md_match = re.search(r'(\d{1,2})月(\d{1,2})日', clean_snippet)

                        if md_match:
                            year = datetime.today().year
                            event_date = f"{year}-{int(md_match.group(1)):02d}-{int(md_match.group(2)):02d}"
                        else:
                            slash_match = re.search(r'(\d{1,2})/(\d{1,2})', title)
                            if not slash_match:
                                slash_match = re.search(r'(\d{1,2})/(\d{1,2})', clean_snippet)

                            if slash_match:
                                year = datetime.today().year
                                event_date = f"{year}-{int(slash_match.group(1)):02d}-{int(slash_match.group(2)):02d}"
                                
                if not event_date:
                    # 日付が抽出できない公式サイトやチケット一覧等は、今日の案内（情報サイト直リンク）として残す
                    event_date = datetime.today().strftime("%Y-%m-%d")
                            
                # 今日以降の日付、または指定日のイベントのみを採用
                today_str = datetime.today().strftime("%Y-%m-%d")
                target_cmp_date = date_str if date_str else today_str
                
                if event_date and event_date >= target_cmp_date:
                    # タイトルのクリーンアップ
                    clean_title = title.replace("\n", " ").replace("\r", "").strip()
                    if len(clean_title) > 60:
                        clean_title = clean_title[:60] + "..."
                        
                    found_events.append({
                        "url": link,
                        "title": f"【Web検索】{clean_title}",
                        "date": event_date,
                        "area": "東京" if "東京" in title + snippet else ("新潟" if "新潟" in title + snippet else "その他"),
                        "performers": keyword,
                        "raw_text": snippet
                    })
        else:
            print(f"❌ Tavily API エラー: HTTP {response.status_code}")
    except Exception as e:
        print(f"🚨 Tavily Web検索中に例外が発生しました: {str(e)}")
        
    return found_events

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
                        
                        # 行の作成
                        event_line = f"・{date_display} | {clean_ev_title}{perf_part} (情報源: {source_val}){url_part}"
                        
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
