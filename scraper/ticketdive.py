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
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8"
    }
    
    found_events = []
    seen_urls = set()
    
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code != 200:
            print(f"🚨 TicketDive検索結果取得失敗 (HTTP {res.status_code}): {url}")
            return []
            
        soup = BeautifulSoup(res.text, "html.parser")
        
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
            
            # 各個別イベント詳細を取得してパース
            event_data = scrape_ticketdive_event_by_url(event_url)
            if not event_data:
                continue
                
            # 出演者フィルター： performers または raw_text に対象グループ名が含まれるか判定
            query_clean = query.lower().replace(" ", "")
            performers_clean = event_data.get("performers", "").lower().replace(" ", "")
            raw_text_clean = event_data.get("raw_text", "").lower().replace(" ", "")
            title_clean = event_data.get("title", "").lower().replace(" ", "")
            
            # 1. クエリ自体が、タイトル・出演者・本文のいずれかに含まれているかチェック
            matched = (query_clean in performers_clean) or (query_clean in raw_text_clean) or (query_clean in title_clean)
            
            # 2. もしくは、クエリに対応する本命アイドルのグループ名や検索ワードが含まれているかチェック
            if not matched:
                for idol in config.MARKING_IDOLS:
                    is_target_idol = (query_clean == idol["name"].lower().replace(" ", "")) or \
                                     any(query_clean == q.lower().replace(" ", "") for q in idol.get("search_queries", [])) or \
                                     any(query_clean == q.lower().replace(" ", "") for q in idol.get("ticketdive_search_queries", []))
                    if is_target_idol:
                        group_name_clean = idol["name"].lower().replace(" ", "")
                        if (group_name_clean in performers_clean) or (group_name_clean in raw_text_clean) or (group_name_clean in title_clean):
                            matched = True
                            break
                        for q in idol.get("search_queries", []):
                            q_clean = q.lower().replace(" ", "")
                            if (q_clean in performers_clean) or (q_clean in raw_text_clean) or (q_clean in title_clean):
                                matched = True
                                break
                        if matched:
                            break
                            
            if not matched:
                print(f"⏭️ 出演者フィルターにより除外: {event_data['title']} (出演者・本文に '{query}' 関連の記載なし)")
                continue
                
            # 自動巡回での取得なので、source は TicketDive にする
            event_data["source"] = "TicketDive"
            
            found_events.append(event_data)
            
    except Exception as e:
        print(f"🚨 TicketDive検索エラー: {str(e)}")
        
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
