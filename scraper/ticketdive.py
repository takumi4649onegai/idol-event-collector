import re
import urllib.parse
from bs4 import BeautifulSoup
from scraper.utils import determine_area, parse_date, clean_text
import config

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
        
        # TicketDiveの検索エンジンは正確なため、検証なしでそのまま採用します
                
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
