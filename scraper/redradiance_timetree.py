import re
import os
from datetime import datetime, timezone, timedelta
from playwright.sync_api import sync_playwright
from scraper.utils import determine_area, normalize_event_url

def scrape_redradiance_timetree(calendar_url: str, group_name: str = "Red Radiance") -> list:
    """
    Red Radianceの公式TimeTreeカレンダーから予定情報を取得する。
    """
    events = []
    
    is_ci = os.getenv("CI", "false").lower() == "true" or os.getenv("GITHUB_ACTIONS", "false").lower() == "true"
    
    print(f"🔍 Red Radiance TimeTreeカレンダー取得中(Playwright): {calendar_url} ...")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=is_ci)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 800}
            )
            page = context.new_page()
            
            api_data = []
            
            def handle_response(response):
                # TimeTreeのpublic_eventsエンドポイントを監視
                if "/public_events" in response.url and response.status == 200:
                    try:
                        res_json = response.json()
                        events_list = res_json.get("public_events", [])
                        if events_list:
                            api_data.extend(events_list)
                    except Exception as e:
                        print(f"⚠️ Response parsing error: {e}")
                        
            page.on("response", handle_response)
            
            # ページ遷移とAPI発火待ち
            page.goto(calendar_url, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(10000)
            browser.close()
            
            # APIから取得できたデータを処理
            jst = timezone(timedelta(hours=9))
            
            for item in api_data:
                title = item.get("title", "")
                if not title:
                    continue
                    
                note = item.get("note", "") or ""
                
                # 1. 日付の取得 (UTC millisecond timestamp -> JST date)
                start_at_ms = item.get("start_at")
                if start_at_ms:
                    try:
                        start_dt = datetime.fromtimestamp(start_at_ms / 1000, tz=jst)
                        event_date = start_dt.strftime("%Y-%m-%d")
                    except Exception as e:
                        print(f"⚠️ Date parse error: {e}")
                        continue
                else:
                    continue
                    
                # 2. 時間の取得
                open_time = ""
                start_time = ""
                
                # note本文から優先的に開場・開演時間を探す
                match1 = re.search(r'(?:open|開場)[\s：:ー/]*(\d{1,2}:\d{2})\s*(?:/|｜|\||&)?\s*(?:start|開演)[\s：:ー]*(\d{1,2}:\d{2})', note, re.IGNORECASE)
                if match1:
                    open_time = match1.group(1)
                    start_time = match1.group(2)
                else:
                    open_m = re.search(r'(?:open|開場)[\s：:ー]*(\d{1,2}:\d{2})', note, re.IGNORECASE)
                    start_m = re.search(r'(?:start|開演)[\s：:ー]*(\d{1,2}:\d{2})', note, re.IGNORECASE)
                    if open_m:
                        open_time = open_m.group(1)
                    if start_m:
                        start_time = start_m.group(1)
                        
                if not start_time:
                    time_m = re.search(r'時間[\s：:ー]*(\d{1,2}:\d{2})', note)
                    if time_m:
                        start_time = time_m.group(1)
                        
                all_day = item.get("all_day", False)
                if not start_time and not all_day:
                    try:
                        start_time = start_dt.strftime("%H:%M")
                        if start_time == "00:00":
                            start_time = ""
                    except Exception:
                        pass
                        
                # 3. チケットURLの抽出
                ticket_url = ""
                urls_in_note = re.findall(r'https?://[^\s\n\r<>"]+', note)
                if urls_in_note:
                    # ① 優先的にお知らせの日付 (MMDD または MM-DD) が含まれるURLを探す
                    md_formats = [event_date.replace("-", "")[4:], event_date[5:]]
                    for link in urls_in_note:
                        if any(fmt in link for fmt in md_formats):
                            # チケットサイトまたは外部URLであれば採用
                            if not any(k in link for k in ["timetree", "timetr.ee"]):
                                ticket_url = link
                                break
                    
                    if not ticket_url:
                        # ② チケット購入サイト優先で抽出
                        for link in urls_in_note:
                            if any(k in link for k in ["livepocket.jp", "tiget.net", "ticketdive.com", "t-dv.com"]):
                                ticket_url = link
                                break
                                
                    if not ticket_url:
                        # ③ その他の外部URL（TimeTree以外）の最初を採用
                        external_links = [l for l in urls_in_note if "timetree" not in l and "timetr.ee" not in l]
                        if external_links:
                            ticket_url = external_links[0]
                            
                if not ticket_url:
                    ticket_url = item.get("url", "")
                    
                # 4. 会場とエリア判定
                venue = item.get("location_name", "") or ""
                if not venue:
                    venue_match = re.search(r'(?:会場|場所|place|Place|＠|@|📍|🎉)[\s：:ー]*(?:会場|場所|開場)?[\s：:ー]*([^\n\r|｜(（【]+)', note)
                    if venue_match:
                        venue = venue_match.group(1).strip()
                        venue = re.sub(r'^(?:会場|場所|開場)[\s：:ー]*', '', venue)
                        venue = re.split(r'(?:出演|開場|開演|チケット|予約|主催|料金|・|\|)', venue)[0].strip()
                        venue = re.sub(r'[\(\)（）\-\[\]\{\}！!？?]', '', venue).strip()
                        
                if not venue:
                    venue = "未設定"
                    
                area = determine_area(venue + " " + note)
                
                # 5. 一意URL (チケットURLがある場合はそれを正規化、ない場合はTimeTreeのurlを正規化)
                normalized_url = normalize_event_url(ticket_url)
                if not normalized_url:
                    normalized_url = f"local_id:REDRADIANCE_TIMETREE:{event_date}:{title}"
                    
                events.append({
                    "title": f"【TimeTree】{title}",
                    "date": event_date,
                    "open_time": open_time,
                    "start_time": start_time,
                    "venue": venue,
                    "performers": group_name,
                    "url": normalized_url,
                    "area": area,
                    "raw_text": note,
                    "source": "Red Radiance TimeTree"
                })
                
    except Exception as e:
        print(f"🚨 Red Radiance TimeTreeカレンダー取得中に例外エラー: {str(e)}")
        
    print(f"✅ Red Radiance TimeTreeカレンダーから {len(events)} 件のイベントを抽出しました。")
    return events
