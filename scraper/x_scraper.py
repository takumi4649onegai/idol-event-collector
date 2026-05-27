import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from email.utils import parsedate_to_datetime
from scraper.utils import determine_area, parse_date, clean_text
import config

# バックアップ用の Nitter インスタンス一覧
NITTER_INSTANCES = [
    "https://nitter.poast.org",
    "https://nitter.cz",
    "https://nitter.privacydev.net",
    "https://nitter.moomoo.me",
    "https://nitter.perennialte.ch"
]

# イベント判定用キーワード (告知だけでなく、ライブ後のお礼・感謝・セトリ・チェキ報告なども網羅)
EVENT_KEYWORDS = [
    "イベント", "ライブ", "対バン", "フェス", "出演", "開催", "ドンキ", 
    "ドン・キホーテ", "インストア", "特典会", "フリーライブ", "無料", 
    "開場", "開演", "チケット", "予約", "時間", "場所", "物販",
    "ありがとうございました", "ありがとう", "感謝", "セトリ", "セットリスト", "チェキ"
]

def clean_tweet_text(html_content: str) -> str:
    """
    Nitter RSSの description 内にあるHTMLをパースして、純粋なテキストを取り出す。
    """
    if not html_content:
        return ""
    
    # BeautifulSoupでHTMLをパース
    soup = BeautifulSoup(html_content, "html.parser")
    
    # リンクなどのテキストを適切に維持しつつテキスト化
    text = soup.get_text(separator="\n")
    
    # 不要なURLパラメータやNitter特有のリンク表記などをクリーンアップ
    return clean_text(text)

def get_x_url(nitter_url: str, username: str = None) -> str:
    """
    NitterのURLまたは数値のみのTweet IDを、標準の X/Twitter URL (https://x.com/username/status/123456789) に変換する。
    """
    if not nitter_url:
        return ""
    
    # 1. もしguidが数字のみ（Tweet IDのみ）の場合
    nitter_url_str = str(nitter_url).strip()
    if nitter_url_str.isdigit():
        u = username if username else "i" # ユーザー名が不明な場合は一時的に 'i' で補完
        return f"https://x.com/{u}/status/{nitter_url_str}"
        
    # 2. 通常のURL形式の場合
    match = re.search(r'/([^/]+)/status/(\d+)', nitter_url_str)
    if match:
        u = match.group(1)
        tweet_id = match.group(2)
        return f"https://x.com/{u}/status/{tweet_id}"
    
    return nitter_url_str

def fetch_tweets_via_rss(username: str) -> list:
    """
    指定されたユーザー名のX投稿を複数のNitter RSSフィードをフォールバックしながら取得する。
    """
    if not username:
        return []
    
    # ユーザー名の @ などを取り除く
    username = username.strip().replace("@", "")
    
    # 最初は .env で指定された NITTER_BASE_URL を試し、ダメならバックアップを巡回
    instances = [config.NITTER_BASE_URL] + [inst for inst in NITTER_INSTANCES if inst != config.NITTER_BASE_URL]
    
    rss_data = None
    active_instance = None
    
    for instance in instances:
        rss_url = f"{instance}/{username}/rss"
        print(f"🔍 X(RSS)取得中: {rss_url} ...")
        try:
            response = requests.get(rss_url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }, timeout=10)
            
            if response.status_code == 200 and "<rss" in response.text:
                rss_data = response.text
                active_instance = instance
                print(f"✅ X(RSS)取得成功 (インスタンス: {instance})")
                break
            else:
                print(f"⚠️ ステータスコード異常 ({response.status_code}) または無効なRSSレスポンス")
        except Exception as e:
            print(f"❌ エラー発生 ({instance}): {str(e)}")
            
    if not rss_data:
        print(f"🚨 すべてのNitterインスタンスから @{username} のX投稿の取得に失敗しました。")
        return []
    
    found_events = []
    
    try:
        # XMLとしてBeautifulSoupでパース
        soup = BeautifulSoup(rss_data, "xml")
        items = soup.find_all("item")
        
        for item in items:
            title = item.find("title").text if item.find("title") else ""
            description_html = item.find("description").text if item.find("description") else ""
            pub_date_str = item.find("pubDate").text if item.find("pubDate") else ""
            guid = item.find("guid").text if item.find("guid") else ""
            
            # ツイート本文の整形
            tweet_text = clean_tweet_text(description_html)
            if not tweet_text:
                tweet_text = title
            
            # イベントキーワードが含まれているか判定
            tweet_lower = tweet_text.lower()
            is_event = any(kw in tweet_lower for kw in EVENT_KEYWORDS)
            
            if not is_event:
                continue # イベント関連ではないと判断したものはスキップ
                
            # 日付のパース
            try:
                dt = parsedate_to_datetime(pub_date_str)
                event_date = dt.strftime("%Y-%m-%d")
            except Exception:
                # パースできない場合はテキストから日付を探すか、今日にする
                event_date = parse_date(tweet_text)
                
            # エリア判定 (本文やタイトルから抽出)
            area = determine_area(tweet_text)
            
            # 標準X URLへの変換
            tweet_url = get_x_url(guid, username)
            
            # イベントタイトルの整形 (ツイートの最初の1行または30文字)
            first_line = tweet_text.split("\n")[0]
            if len(first_line) > 40:
                event_title = first_line[:40] + "..."
            else:
                event_title = first_line
            
            event_title = f"【X告知】{event_title}"
            
            found_events.append({
                "date": event_date,
                "area": area,
                "title": event_title,
                "performers": username, # 出演者はアカウント名
                "url": tweet_url,
                "raw_text": tweet_text
            })
            
    except Exception as e:
        print(f"🚨 XMLパース中にエラーが発生しました: {str(e)}")
        
    return found_events

if __name__ == "__main__":
    # 単体テスト用
    import sys
    import io
    if sys.platform.startswith('win'):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
        
    test_user = "tokyo_cutecute" if len(sys.argv) < 2 else sys.argv[1]
    events = fetch_tweets_via_rss(test_user)
    print(f"\n--- 取得結果 ({len(events)}件) ---")
    for e in events[:3]:
        print(f"日付: {e['date']} | エリア: {e['area']}")
        print(f"タイトル: {e['title']}")
        print(f"URL: {e['url']}")
        print("-" * 30)
