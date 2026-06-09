import re
import requests
from bs4 import BeautifulSoup
from scraper.utils import determine_area, parse_date, clean_text, determine_performers
import config

def scrape_tiget_event_by_url(url: str) -> dict:
    """
    TIGET個別イベントページから情報を取得してパースする。
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8"
    }
    
    print(f"🔍 TIGET個別イベント取得中: {url} ...")
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code != 200:
            print(f"⚠️ TIGET個別アクセス失敗: HTTP {response.status_code}")
            return None
    except Exception as e:
        print(f"❌ TIGET個別リクエストエラー: {str(e)}")
        return None

    soup = BeautifulSoup(response.text, "html.parser")
    
    # 1. Title
    title_el = soup.find("h1", class_="pg-event__header__title")
    title = title_el.get_text().strip() if title_el else ""
    if not title:
        page_title = soup.title.string if soup.title else ""
        if page_title:
            title = page_title.split("のチケット")[0].strip()
    title = clean_text(title)
    
    # 2. DL metadata (Date, Venue, etc.)
    detail_section = soup.find("section", class_="pg-event__detail")
    raw_text = detail_section.get_text(separator=" \n ").strip() if detail_section else soup.get_text(separator=" \n ")
    
    event_date = ""
    venue = ""
    default_performers = ""
    
    if detail_section:
        dls = detail_section.find_all("dl")
        for dl in dls:
            dt = dl.find("dt")
            dd = dl.find("dd")
            if dt and dd:
                dt_text = dt.get_text().strip()
                dd_text = dd.get_text().strip()
                
                if dt_text == "開催日":
                    event_date = parse_date(dd_text)
                elif dt_text == "会場":
                    venue = dd_text
                elif dt_text == "出演者":
                    default_performers = dd_text

    # 3. Fallback for Date if not found via DL
    if not event_date:
        date_match = re.search(r'(\d{4}[-/.]\d{1,2}[-/.]\d{1,2})|(\d{1,2}月\d{1,2}日)', raw_text)
        if date_match:
            event_date = parse_date(date_match.group(0))
        else:
            event_date = parse_date("")

    # 4. Open Time and Start Time
    open_time = ""
    start_time = ""
    
    entire_text = soup.get_text(separator=" \n ")
    time_match = re.search(r'開場\s*(\d{1,2}:\d{2})\s*/\s*開演\s*(\d{1,2}:\d{2})', entire_text)
    if time_match:
        open_time = time_match.group(1)
        start_time = time_match.group(2)
    else:
        open_m = re.search(r'(?:OPEN|開場)[\s：:ー]*(\d{1,2}:\d{2})', entire_text, re.IGNORECASE)
        start_m = re.search(r'(?:START|開演)[\s：:ー]*(\d{1,2}:\d{2})', entire_text, re.IGNORECASE)
        if open_m:
            open_time = open_m.group(1)
        if start_m:
            start_time = start_m.group(1)

    # 5. Area
    area = determine_area(venue + " " + raw_text)
    
    # 6. Performers
    performers = determine_performers(title + " " + raw_text, default_performers)
    
    return {
        "title": f"【TIGET】{title}",
        "date": event_date,
        "open_time": open_time,
        "start_time": start_time,
        "venue": venue,
        "performers": performers,
        "url": url,
        "area": area,
        "raw_text": raw_text,
        "source": "TIGET"
    }

def scrape_tiget_events(query: str) -> list:
    """
    TIGET (https://tiget.net/events?q[words]=...) から指定されたキーワードでイベント情報を検索・抽出する。
    """
    if not query:
        return []
    
    url = "https://tiget.net/events"
    payload = {"q[words]": query}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8"
    }
    
    print(f"🔍 TIGET検索中: '{query}' ({url} with {payload}) ...")
    try:
        response = requests.get(url, headers=headers, params=payload, timeout=15)
        if response.status_code != 200:
            print(f"⚠️ TIGET検索アクセス失敗: HTTP {response.status_code}")
            return []
    except Exception as e:
        print(f"❌ TIGET検索リクエストエラー: {str(e)}")
        return []
        
    soup = BeautifulSoup(response.text, "html.parser")
    found_events = []
    seen_urls = set()
    
    event_links = soup.find_all("a", href=re.compile(r'^/events/\d+'))
    
    for link in event_links:
        href = link.get("href", "")
        event_url = f"https://tiget.net{href}" if href.startswith("/") else href
        
        if event_url in seen_urls:
            continue
        seen_urls.add(event_url)
        
        event_data = scrape_tiget_event_by_url(event_url)
        if not event_data:
            continue
            
        # 出演者フィルター (記号やスペースを無視して部分一致判定)
        def normalize_filter_text(t: str) -> str:
            return re.sub(r'[^a-zA-Z0-9\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff]', '', t).lower()
            
        norm_query = normalize_filter_text(query)
        norm_title = normalize_filter_text(event_data["title"])
        norm_perf = normalize_filter_text(event_data["performers"])
        norm_text = normalize_filter_text(event_data["raw_text"])
        
        if norm_query in norm_title or norm_query in norm_perf or norm_query in norm_text:
            found_events.append(event_data)
        else:
            print(f"⏭️ 関連キーワード不足のためTIGETイベントを除外: {event_data['title']}")
            
    print(f"✅ TIGET検索から {len(found_events)} 件のイベントを抽出しました。")
    return found_events

def scrape_tiget_performer(performer_id: str, default_performers: str = "") -> list:
    """
    TIGETのパフォーマー（アーティスト）ページ (https://tiget.net/performers/{performer_id}) から
    出演イベント情報をPlaywrightを使用してスクレイピング・抽出する。
    """
    if not performer_id:
        return []
        
    url = f"https://tiget.net/performers/{performer_id}"
    print(f"🔍 TIGETパフォーマーページ検索中(Playwright): ID {performer_id} ({url}) ...")
    
    html_content = ""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("⚠️ 警告: playwright がインストールされていないため、TIGETパフォーマーのスクレイピングをスキップします。")
        return []
        
    try:
        with sync_playwright() as p:
            import os
            is_ci = os.getenv("CI", "false").lower() == "true" or os.getenv("GITHUB_ACTIONS", "false").lower() == "true"
            
            browser = p.chromium.launch(headless=is_ci)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 800}
            )
            page = context.new_page()
            
            # ページ遷移と読み込み待機
            page.goto(url, wait_until="networkidle", timeout=30000)
            
            # JSのレンダリング完了を少し待つ
            page.wait_for_timeout(3000)
            
            # HTMLソースを取得
            html_content = page.content()
            browser.close()
    except Exception as e:
        print(f"❌ TIGETパフォーマー Playwright実行エラー: {str(e)}")
        return []
        
    if not html_content:
        return []
        
    soup = BeautifulSoup(html_content, "html.parser")
    event_divs = soup.find_all(class_=re.compile(r"pg-performer-events--wrap--event"))
    
    found_events = []
    for div in event_divs:
        # タイトル
        title_el = div.find(class_=re.compile(r"pg-performer-events--label__bold"))
        title = title_el.get_text().strip() if title_el else "無題のイベント"
        title = clean_text(title)
        
        # 日付と出演者
        date_str = ""
        performers = default_performers
        
        info_els = div.find_all(class_=re.compile(r"pg-performer-events--label__nomal"))
        for el in info_els:
            text = el.get_text().strip()
            if text.startswith("開催"):
                date_clean = text.replace("開催", "").replace("：", "").strip()
                date_str = parse_date(date_clean)
            elif text.startswith("出演"):
                performers = text.replace("出演", "").replace("：", "").strip()
                performers = clean_text(performers)
                
        if not date_str:
            print(f"⚠️ 開催日の明記がないためイベントをスキップします: {title}")
            continue
            
        area = determine_area(div.get_text())
        
        # 個別イベントURLの抽出
        event_url = ""
        if div.name == "a" and div.get("href") and re.search(r'/events/\d+', div.get("href")):
            href = div.get("href")
            event_url = "https://tiget.net" + href if href.startswith("/") else href
        else:
            link_el = div.find("a", href=re.compile(r'/events/\d+'))
            if link_el:
                href = link_el.get("href", "")
                event_url = "https://tiget.net" + href if href.startswith("/") else href
                
        # フォールバック: 個別URLが取得できない場合は一意のlocal_idを生成
        if not event_url:
            event_url = f"local_id:TIGET:{performer_id}:{date_str}:{title}"
            
        found_events.append({
            "date": date_str,
            "area": area,
            "title": f"【TIGET】{title}",
            "performers": performers if performers else default_performers,
            "url": event_url,
            "raw_text": div.get_text(separator=" | "),
            "source": "TIGET"
        })
        
    print(f"✅ TIGETパフォーマーページから {len(found_events)} 件 of イベントを抽出しました。")
    return found_events

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
        from scraper.utils import parse_date, clean_text, determine_area, is_generic_list_url, determine_performers
        
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            
            # 各イベントカード（div.event-box）を基準にパース処理を行う
            event_boxes = soup.find_all(class_=re.compile(r'event-box'))
            seen_urls = set()
            
            for box in event_boxes:
                # a) URLの抽出 (event-title div 内の a タグを優先)
                title_a = None
                title_div = box.find(class_=re.compile(r'event-title'))
                if title_div:
                    title_a = title_div.find("a")
                if not title_a:
                    title_a = box.find("a", href=re.compile(r'^/events/\d+'))
                    
                if not title_a:
                    continue
                    
                href = title_a.get("href", "")
                event_url = f"https://tiget.net{href}" if href.startswith("/") else href
                
                # 重複排除
                if event_url in seen_urls:
                    continue
                seen_urls.add(event_url)
                
                # 一覧ページURLは除外
                if is_generic_list_url(event_url):
                    continue
                    
                container_text = box.get_text(separator=" | ")
                
                # b) タイトルの抽出
                title = ""
                if title_div:
                    title = title_div.get_text().strip()
                if not title:
                    title = title_a.get_text().strip()
                if not title:
                    title = "無題のイベント"
                title = clean_text(title)
                
                # c) 日付の抽出 (play-date div を優先)
                date_div = box.find(class_=re.compile(r'play-date'))
                date_text = date_div.get_text().strip() if date_div else ""
                
                event_date = None
                if date_text:
                    date_clean = re.sub(r'^(開催|日程)\s*[:：]\s*', '', date_text).strip()
                    # 複数日にまたがる場合は開始日を優先
                    first_date_part = re.split(r'[〜~-]', date_clean)[0].strip()
                    event_date = parse_date(first_date_part)
                    
                # 取得できなかった、または今日にフォールバックしてしまった場合は全体テキストから抽出
                if not event_date or event_date == parse_date(""):
                    date_match = re.search(r'(\d{4}[-/.]\d{1,2}[-/.]\d{1,2})|(\d{1,2}月\d{1,2}日)', container_text)
                    if date_match:
                        event_date = parse_date(date_match.group(0))
                    else:
                        event_date = parse_date(container_text)
                
                # d) 会場・エリア判定
                area_div = box.find(class_=re.compile(r'event-area'))
                area_text = area_div.get_text().strip() if area_div else ""
                
                area = "新潟"
                if area_text:
                    area_clean = re.sub(r'^(場所|会場)\s*[:：]\s*', '', area_text).strip()
                    area = determine_area(area_clean + " " + container_text)
                else:
                    area = determine_area(container_text)
                
                # e) 出演者の判定 (本文からお気に入りアイドルを自動判定)
                perf = determine_performers(container_text + " " + title, "")
                
                found_events.append({
                    "date": event_date,
                    "area": area,
                    "title": f"【TIGET】{title}",
                    "performers": perf,
                    "url": event_url,
                    "raw_text": container_text,
                    "source": "TIGET"
                })
    except Exception as e:
        print(f"🚨 TIGETエリアスクレイピング中にエラー: {str(e)}")
    return found_events

if __name__ == "__main__":
    # 単体テスト用
    import sys
    import io
    if sys.platform.startswith('win'):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
        
    events = scrape_tiget_events("東京CuteCute")
    print("\n--- TIGET取得結果 ---")
    for e in events:
        print(f"日付: {e['date']} | エリア: {e['area']} | タイトル: {e['title']} | URL: {e['url']}")
