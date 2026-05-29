import re
import urllib.parse
from bs4 import BeautifulSoup
from scraper.utils import determine_area, parse_date, clean_text
import config

def scrape_livepocket_events(query: str) -> list:
    """
    LivePocket (https://t.livepocket.jp/event/search?search_word=...) から指定されたキーワードでイベント情報を検索・抽出する。
    ※LivePocketはJavaScriptによる動的レンダリングを行うため、Playwrightを使用します。
    """
    if not query:
        return []
        
    url = f"https://t.livepocket.jp/event/search?search_word={urllib.parse.quote(query)}"
    print(f"🔍 LivePocket検索中: '{query}' ({url}) ...")
    
    html_content = ""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("⚠️ 警告: playwright がインストールされていないため、LivePocket のスクレイピングをスキップします。")
        return []
        
    try:
        with sync_playwright() as p:
            import os
            # GitHub Actionsなどのクラウド環境(CI)ではheadless=True、タクミさんのPC(ローカル)ではheadless=Falseにしてアクセスブロックを完全回避！
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
        print(f"❌ LivePocket Playwright実行エラー: {str(e)}")
        return []
        
    if not html_content:
        return []
        
    soup = BeautifulSoup(html_content, "html.parser")
    found_events = []
    seen_urls = set()
    
    # LivePocketのイベント詳細ページへのリンク (例: /event/view/xxxx または /e/xxxx) を探す
    # LivePocketのイベントリンクは href="/event/view/xxxx" などの形をとる
    event_links = soup.find_all("a", href=re.compile(r'/(event/view/|e/)[^?#]+'))
    
    for link in event_links:
        href = link.get("href", "")
        if href.startswith("/"):
            event_url = f"https://t.livepocket.jp{href}"
        else:
            event_url = href
            
        # 重複排除
        if event_url in seen_urls:
            continue
        seen_urls.add(event_url)
        
        # リンクが含まれるイベントカード（コンテナ）を特定する
        # LivePocketのカード構造を遡る
        container = link
        for _ in range(4):
            parent = container.parent
            if parent and (parent.name in ["div", "li", "article"]):
                container = parent
            else:
                break
                
        container_text = container.get_text(separator=" | ")
        
        # タイトルの抽出
        title = link.get_text().strip()
        if not title or len(title) < 3:
            # コンテナ内の見出しタグ等から探す
            headings = [h.get_text().strip() for h in container.find_all(["h2", "h3", "h4", "p", "strong"]) if h.get_text().strip()]
            title = headings[0] if headings else f"{query}出演イベント"
            
        title = clean_text(title)
        
        # 日付の抽出 (正規表現による日付パターンの探索)
        date_match = re.search(r'(\d{4}[-/.]\d{1,2}[-/.]\d{1,2})|(\d{1,2}月\d{1,2}日)', container_text)
        if date_match:
            event_date = parse_date(date_match.group(0))
        else:
            event_date = parse_date(container_text)
            
        # エリア判定
        area = determine_area(container_text)
        
        # クエリでの検索結果を信頼して採用しますが、
        # LivePocketの「ヒットなしの際にお勧めイベントを勝手に表示する仕様」による偽陽性（誤検出）を防ぐため、
        # タイトル、出演者情報、または本文の中に、クエリ（検索語）が本当に含まれているか厳密にチェックします。
        query_clean = query.replace(" ", "").lower()
        container_text_clean = container_text.replace(" ", "").lower()
        title_clean = title.replace(" ", "").lower()
        
        # 検索語がタイトルにも詳細テキストにも含まれていない場合は、LivePocketの偽陽性おすすめイベントとみなして完全に除外します。
        # ※「東京Cute」などのクエリに対する誤マッチ対策
        if query_clean not in title_clean and query_clean not in container_text_clean:
            # ただし、クエリがメンバー名で、タイトルまたは本文に「東京CuteCute」などのグループ名が含まれている場合はメンバーのイベントであるため許可します
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
            "title": f"【LivePocket】{title}",
            "performers": query,
            "url": event_url
        })
        
    print(f"✅ LivePocketから {len(found_events)} 件のイベントを抽出しました。")
    return found_events

if __name__ == "__main__":
    # 単体テスト用
    import sys
    import io
    if sys.platform.startswith('win'):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
        
    events = scrape_livepocket_events("東京CuteCute")
    print("\n--- LivePocket取得結果 ---")
    for e in events:
        print(f"日付: {e['date']} | エリア: {e['area']} | タイトル: {e['title']} | URL: {e['url']}")
