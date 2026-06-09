import re
import requests
from bs4 import BeautifulSoup
from scraper.utils import determine_area, parse_date, clean_text

def scrape_wix_official_schedule(url: str, group_name: str = "ケミカル⇄リアクション") -> list:
    """
    ケミカル⇄リアクションのWix公式ホームページのLIVE SCHEDULEカレンダーから予定情報を取得する。
    """
    events = []
    
    from playwright.sync_api import sync_playwright
    import os
    
    is_ci = os.getenv("CI", "false").lower() == "true" or os.getenv("GITHUB_ACTIONS", "false").lower() == "true"
    
    print(f"🔍 Wix公式カレンダー取得中(Playwright): {url} ...")
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
                if "_api/cloud-data/v2/items/query" in response.url and response.status == 200:
                    try:
                        res_json = response.json()
                        items = res_json.get("dataItems", [])
                        if items:
                            api_data.extend(items)
                    except Exception:
                        pass
                        
            page.on("response", handle_response)
            
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            
            # Wix APIデータ通信が終了するのを10秒待つ
            page.wait_for_timeout(10000)
            browser.close()
            
            # APIから取得できたデータを処理
            for item in api_data:
                data = item.get("data", {})
                title = data.get("title", "")
                if not title:
                    continue
                    
                # 1. 日付の取得 (UTC -> JST)
                wix_date_dict = data.get("date", {})
                wix_date_str = ""
                if isinstance(wix_date_dict, dict):
                    wix_date_str = wix_date_dict.get("$date", "")
                else:
                    wix_date_str = str(wix_date_dict)
                    
                jst_date = ""
                if wix_date_str:
                    try:
                        from datetime import datetime, timedelta
                        # "2026-06-03T15:00:00Z" -> JST
                        utc_dt = datetime.strptime(wix_date_str.replace("Z", ""), "%Y-%m-%dT%H:%M:%S")
                        jst_dt = utc_dt + timedelta(hours=9)
                        jst_date = jst_dt.strftime("%Y-%m-%d")
                    except Exception:
                        jst_date = parse_date(wix_date_str)
                else:
                    jst_date = parse_date("")
                    
                # 2. 時間の取得
                start_time = ""
                open_time = ""
                wix_start_time = data.get("startTime", "") # 例: "19:00:00.000"
                if wix_start_time:
                    try:
                        start_time = ":".join(wix_start_time.split(":")[:2])
                    except Exception:
                        pass
                        
                desc = data.get("description", "")
                
                # startTime が 00:00 等だった場合や未設定の場合は本文からパースを試みる
                if not start_time or start_time == "00:00":
                    time_match = re.search(r'開場\s*(\d{1,2}:\d{2})\s*/\s*開演\s*(\d{1,2}:\d{2})', desc)
                    if time_match:
                        open_time = time_match.group(1)
                        start_time = time_match.group(2)
                    else:
                        open_m = re.search(r'(?:OPEN|開場)[\s：:ー]*(\d{1,2}:\d{2})', desc, re.IGNORECASE)
                        start_m = re.search(r'(?:START|開演)[\s：:ー]*(\d{1,2}:\d{2})', desc, re.IGNORECASE)
                        if open_m:
                            open_time = open_m.group(1)
                        if start_m:
                            start_time = start_m.group(1)
                else:
                    # 開始時間が設定されていれば、開場時間だけ本文から探す
                    open_m = re.search(r'(?:OPEN|開場)[\s：:ー]*(\d{1,2}:\d{2})', desc, re.IGNORECASE)
                    if open_m:
                        open_time = open_m.group(1)
                        
                # 3. チケットURLの抽出
                ticket_urls = re.findall(r'https?://[^\s\n\r<>"]+', desc)
                ticket_url = ""
                if ticket_urls:
                    # チケット購入サイト優先で抽出
                    for link in ticket_urls:
                        if any(k in link for k in ["livepocket.jp", "tiget.net", "ticketdive.com", "t-dv.com"]):
                            ticket_url = link
                            break
                    if not ticket_url:
                        ticket_url = ticket_urls[0]
                        
                # 4. 無料LIVE判定
                is_free = False
                for free_kw in ["観覧無料", "入場無料", "無料", "フリー"]:
                    if free_kw in desc or free_kw in title:
                        is_free = True
                        break
                        
                # 5. 会場とエリア判定
                venue = ""
                venue_match = re.search(r'(?:会場|場所|place|Place|＠|@)[\s：:ー]*([^\s|｜(（【\n]+)', desc)
                if venue_match:
                    venue = venue_match.group(1).strip()
                    venue = re.split(r'(?:出演|開場|開演|チケット|予約|主催|料金|・|\|)', venue)[0].strip()
                    venue = re.sub(r'[\(\)（）\-\[\]\{\}！!？?]', '', venue).strip()
                    
                if not venue:
                    if "】" in title:
                        venue = title.split("】")[-1].strip()
                    else:
                        venue = title
                
                venue = venue.strip("【】 ")
                        
                area = determine_area(venue + " " + desc)
                
                # 6. 一意URL（local_id）の作成
                event_url = ticket_url
                if not event_url:
                    # チケットURLのない無料LIVE等は、日付とタイトルから一意な local_id URL を作成
                    event_url = f"local_id:WIX_OFFICIAL:{jst_date}:{title}"
                    
                events.append({
                    "title": f"【公式カレンダー】{title}",
                    "date": jst_date,
                    "open_time": open_time,
                    "start_time": start_time,
                    "venue": venue,
                    "performers": group_name,
                    "url": event_url,
                    "area": area,
                    "raw_text": desc,
                    "source": "Wix Official"
                })
                
    except Exception as e:
        print(f"🚨 Wix公式カレンダー取得中に例外エラー: {str(e)}")
        
    print(f"✅ Wix公式カレンダーから {len(events)} 件のイベントを抽出しました。")
    return events
