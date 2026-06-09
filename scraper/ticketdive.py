import re
import urllib.parse
import requests
from bs4 import BeautifulSoup
from scraper.utils import determine_area, parse_date, clean_text
import config

def scrape_ticketdive_event_by_url(url: str) -> dict:
    """
    TicketDiveの個別イベントページ(またはt-dv.comの短縮URL)から情報を取得する。
    """
    if not url:
        return None

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8"
    }
    
    resolved_url = url
    if "t-dv.com" in url or "ticketdive.com" in url:
        try:
            target_url = url
            if not url.startswith("http://") and not url.startswith("https://"):
                target_url = "https://" + url
            res = requests.get(target_url, headers=headers, allow_redirects=True, timeout=10)
            resolved_url = res.url
        except Exception as e:
            print(f"🚨 URL解決エラー: {str(e)}")
            if not url.startswith("http://") and not url.startswith("https://"):
                resolved_url = "https://" + url
    
    if "ticketdive.com/event/" not in resolved_url:
        print(f"⚠️ 個別イベントページではないURLのためスキップ: {resolved_url}")
        return None

    try:
        res = requests.get(resolved_url, headers=headers, timeout=10)
        if res.status_code != 200:
            print(f"🚨 TicketDive取得失敗 (HTTP {res.status_code}): {resolved_url}")
            return None
            
        soup = BeautifulSoup(res.text, "html.parser")
        
        # 1. Title
        page_title = soup.title.string if soup.title else ""
        title = page_title.split("|")[0].strip() if "|" in page_title else page_title.strip()
        title = clean_text(title)
        
        # 2. Date / Times
        date_val = ""
        open_time = ""
        start_time = ""
        
        dt_span = soup.find(string=lambda s: s and "公演日時" in s)
        if dt_span:
            parent_container = dt_span.parent.parent
            info_spans = parent_container.find_all("span")
            if len(info_spans) > 1:
                datetime_text = info_spans[1].get_text(separator=" | ").strip()
                date_match = re.search(r'(\d{4}/\d{1,2}/\d{1,2})', datetime_text)
                if date_match:
                    date_val = parse_date(date_match.group(1))
                
                open_match = re.search(r'開場時刻\s*[:：]?\s*(\d{1,2}:\d{2})', datetime_text)
                if not open_match:
                    open_match = re.search(r'開場時刻.*?(\d{1,2}:\d{2})', datetime_text)
                if open_match:
                    open_time = open_match.group(1)
                    
                start_match = re.search(r'開演時刻\s*[:：]?\s*(\d{1,2}:\d{2})', datetime_text)
                if not start_match:
                    start_match = re.search(r'開演時刻.*?(\d{1,2}:\d{2})', datetime_text)
                if start_match:
                    start_time = start_match.group(1)
        
        if not date_val:
            date_val = parse_date("")
            
        # 3. Venue
        venue = ""
        venue_span = soup.find(string=lambda s: s and "会場" in s)
        if venue_span:
            parent_container = venue_span.parent.parent
            info_spans = parent_container.find_all("span")
            if len(info_spans) > 1:
                venue = info_spans[1].get_text().strip()
        
        # 4. Performers
        performers_list = []
        perf_span = soup.find(string=lambda s: s and "出演" in s)
        if perf_span:
            parent_container = perf_span.parent.parent
            artist_links = parent_container.find_all("a", href=lambda h: h and "/artist/" in h)
            for a in artist_links:
                performers_list.append(a.get_text().strip())
                
        performers_str = ", ".join(performers_list) if performers_list else ""
        from scraper.utils import determine_performers
        performers_str = determine_performers(res.text, default_performers=performers_str)
        
        area = determine_area(f"{title} {venue}")
        
        return {
            "title": f"【TicketDive】{title}" if not title.startswith("【") else title,
            "date": date_val,
            "open_time": open_time,
            "start_time": start_time,
            "venue": venue,
            "performers": performers_str,
            "url": resolved_url,
            "raw_text": res.text,
            "area": area,
            "source": "TicketDive Manual"
        }
        
    except Exception as e:
        print(f"🚨 TicketDive個別ページパースエラー: {str(e)}")
        return None


def scrape_ticketdive_events(query: str) -> list:
    """
    TicketDive (https://ticketdive.com/search?q=...) から指定されたキーワードでイベント情報を検索・抽出する。
    """
    if not query:
        return []
        
    url = f"https://ticketdive.com/search?q={urllib.parse.quote(query)}"
    print(f"🔍 TicketDive検索中: '{query}' ({url}) ...")
    
    html_content = ""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("⚠️ 警告: playwright がインストールされていないため、TicketDive のスクレイピングをスキップします。")
        return []
        
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 800}
            )
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)
            html_content = page.content()
            browser.close()
    except Exception as e:
        print(f"❌ TicketDive Playwright実行エラー: {str(e)}")
        return []
        
    if not html_content:
        return []
        
    soup = BeautifulSoup(html_content, "html.parser")
    found_events = []
    seen_urls = set()
    
    # 検索結果から本命アイドルの厳格な検証用
    is_marked_idol = False
    target_names = []
    for idol in config.MARKING_IDOLS:
        matches_query = (query.replace(" ", "").lower() == idol["name"].replace(" ", "").lower()) or \
                        any(query.replace(" ", "").lower() == q.replace(" ", "").lower() for q in idol.get("search_queries", []))
        if matches_query:
            is_marked_idol = True
            target_names.append(idol["name"])
            for q in idol.get("search_queries", []):
                target_names.append(q)
            break
            
    # /event/xxxx のリンクを探す
    event_links = soup.find_all("a", href=re.compile(r'/event/[^?#]+'))
    
    for link in event_links:
        href = link.get("href", "")
        if href.startswith("/"):
            event_url = f"https://ticketdive.com{href}"
        else:
            event_url = href
            
        if event_url in seen_urls:
            continue
        seen_urls.add(event_url)
        
        container_text = link.get_text(separator=" | ").strip()
        if not container_text:
            continue
            
        # タイトル、日付、エリアのパース
        # Text: 申込受付中Color Groove2026/06/07シアターマーキュリー新宿
        # 申込受付中 / 販売中 / 終了 などのプレフィックスを取り除く
        clean_text_val = re.sub(r'^(申込受付中|販売中|終了|受付前|完売)', '', container_text).strip()
        
        # 日付パターン (例: 2026/06/07)
        date_match = re.search(r'(\d{4}/\d{1,2}/\d{1,2})', clean_text_val)
        if date_match:
            event_date = parse_date(date_match.group(0))
            # タイトルは日付より前の部分
            title_end = date_match.start()
            title = clean_text_val[:title_end].strip()
        else:
            event_date = parse_date(clean_text_val)
            title = clean_text_val
            
        if not title:
            title = f"{query}出演ライブ"
            
        title = clean_text(title)
        area = determine_area(clean_text_val)
        
        # TicketDiveの検索結果にクエリが含まれているか厳密にチェック（偽陽性・お勧め表示対策）
        query_clean = query.replace(" ", "").lower()
        container_text_clean = container_text.replace(" ", "").lower()
        title_clean = title.replace(" ", "").lower()
        
        if query_clean not in title_clean and query_clean not in container_text_clean:
            # クエリがメンバー名の場合などに備え、タイトルや本文にグループ名が含まれていれば許可
            is_group_match = False
            for group_kw in ["東京CuteCute", "東京Cute", "Red radiance", "Redradiance"]:
                if group_kw.replace(" ", "").lower() in title_clean or group_kw.replace(" ", "").lower() in container_text_clean:
                    is_group_match = True
                    break
            
            if not is_group_match:
                continue
                
        found_events.append({
            "date": event_date,
            "area": area,
            "title": f"【TicketDive】{title}",
            "performers": query,
            "url": event_url
        })
        
    print(f"✅ TicketDiveから {len(found_events)} 件のイベントを抽出しました。")
    return found_events

if __name__ == "__main__":
    import sys
    import io
    if sys.platform.startswith('win'):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
        
    res = scrape_ticketdive_events("東京CuteCute")
    print(res)
