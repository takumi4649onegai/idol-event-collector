import re
import requests
from bs4 import BeautifulSoup
from scraper.utils import determine_area, parse_date, clean_text
import config

def scrape_tiget_events(query: str) -> list:
    """
    TIGET (https://tiget.net/events?q=...) から指定されたキーワードでイベント情報を検索・抽出する。
    """
    if not query:
        return []
    
    url = f"https://tiget.net/events?q={requests.utils.quote(query)}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8"
    }
    
    print(f"🔍 TIGET検索中: '{query}' ({url}) ...")
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code != 200:
            print(f"⚠️ TIGETアクセス失敗: HTTP {response.status_code}")
            return []
    except Exception as e:
        print(f"❌ TIGETリクエストエラー: {str(e)}")
        return []
        
    soup = BeautifulSoup(response.text, "html.parser")
    found_events = []
    seen_urls = set()
    
    # TIGETのイベントページへのリンク (例: /events/123456) を探す
    event_links = soup.find_all("a", href=re.compile(r'^/events/\d+'))
    
    for link in event_links:
        href = link.get("href", "")
        event_url = f"https://tiget.net{href}"
        
        # 重複排除
        if event_url in seen_urls:
            continue
        seen_urls.add(event_url)
        
        # リンクが含まれるコンテナ（親要素など）から情報を取得
        # TIGETのレイアウト変更に耐えるため、親を遡ってテキストを解析するヘリスティック（経験則）な手法を採用
        container = link
        for _ in range(4): # 最大4階層上まで探索
            parent = container.parent
            if parent and (parent.name in ["div", "article", "li"]):
                container = parent
            else:
                break
                
        container_text = container.get_text(separator=" | ")
        
        # イベントタイトルの抽出: リンクタグ自体のテキスト、またはコンテナ内の最初の太字/見出し要素
        title = link.get_text().strip()
        if not title:
            # 代替としてコンテナ内の見出しなどを探す
            heading = container.find(["h2", "h3", "h4", "strong"])
            title = heading.get_text().strip() if heading else "無題のイベント"
            
        title = clean_text(title)
        if title == "チケット" or title == "詳細" or not title:
            # 汎用的な文言だった場合はより上位のテキストを探索
            headings = [h.get_text().strip() for h in container.find_all(["h2", "h3", "h4", "strong"]) if h.get_text().strip()]
            if headings:
                title = headings[0]
            else:
                title = f"{query}出演イベント"
        
        # 日付の抽出: コンテナのテキストから日付パターンを探す
        # 例: 2026/05/27, 2026.05.27, 5月27日
        date_match = re.search(r'(\d{4}[-/.]\d{1,2}[-/.]\d{1,2})|(\d{1,2}月\d{1,2}日)', container_text)
        if date_match:
            event_date = parse_date(date_match.group(0))
        else:
            event_date = parse_date(container_text) # フォールバック判定
            
        # エリア判定
        area = determine_area(container_text)
        
        # クエリでの検索結果をすべて信頼して採用します (生誕祭など表記の異なるイベントを漏れなく拾うため)
        
        found_events.append({
            "date": event_date,
            "area": area,
            "title": f"【TIGET】{title}",
            "performers": query,
            "url": event_url,
            "source": "TIGET"
        })
        
    print(f"✅ TIGETから {len(found_events)} 件のイベントを抽出しました。")
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
        
        found_events.append({
            "date": date_str,
            "area": area,
            "title": f"【TIGET】{title}",
            "performers": performers if performers else default_performers,
            "url": url,
            "raw_text": div.get_text(separator=" | "),
            "source": "TIGET"
        })
        
    print(f"✅ TIGETパフォーマーページから {len(found_events)} 件 of イベントを抽出しました。")
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
