import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from scraper.utils import parse_date, determine_area, clean_text
import config

def scrape_tokyocutecute_site() -> list:
    """
    東京CuteCute公式サイト (https://tokyocutecute.jp) の「NEWS & SCHEDULE」から
    イベント・ライブ告知情報をクロールし、 unlisted/限定公開 のチケットリンクやイベント情報を抽出する。
    """
    url = "https://tokyocutecute.jp"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    print(f"🔍 東京CuteCute公式サイト巡回中: {url} ...")
    events = []
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code != 200:
            print(f"⚠️ 公式サイトアクセス失敗: HTTP {response.status_code}")
            return []
            
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # /blogs/news/ のパターンを持つリンクを抽出
        blog_links = soup.find_all('a', href=re.compile(r'/blogs/news/'))
        
        seen_urls = set()
        for a in blog_links:
            href = a.get("href", "")
            full_url = f"https://tokyocutecute.jp{href}" if href.startswith("/") else href
            
            if full_url in seen_urls:
                continue
            seen_urls.add(full_url)
            
            # ページネーションやタグリンクを除外
            if any(k in full_url for k in ["page=", "tagged="]):
                continue
                
            title_text = a.get_text().strip()
            if not title_text:
                title_text = a.parent.get_text().strip()
                
            title_text = clean_text(title_text)
            if not title_text or len(title_text) < 4:
                continue
                
            try:
                # 詳細ページの取得
                post_res = requests.get(full_url, headers=headers, timeout=10)
                if post_res.status_code == 200:
                    post_soup = BeautifulSoup(post_res.text, 'html.parser')
                    
                    # 本文コンテナの特定
                    article = post_soup.find('article') or post_soup.find(class_=lambda x: x and any(k in x.lower() for k in ['article', 'post', 'content']))
                    article_text = article.get_text(separator="\n").strip() if article else post_soup.get_text(separator="\n")
                    
                    # チケット予約リンクの探索
                    ticket_url = None
                    for link in post_soup.find_all('a'):
                        lh = link.get("href", "")
                        lt = link.get_text().strip()
                        # 一般的なチケットサイトドメインの検出
                        if any(k in lh for k in ["livepocket.jp/e/", "t.livepocket.jp/e/", "tiget.net/events/", "ticketdive.com/event/"]):
                            ticket_url = lh
                            break
                        if any(k in lt for k in ["チケット", "予約", "購入"]):
                            if any(d in lh for d in ["livepocket.jp", "tiget.net", "ticketdive.com"]):
                                ticket_url = lh
                                break
                                
                    # 開催日のパース (■日時：2026年7月12日(日) 等から抽出)
                    event_date = None
                    date_match = re.search(r'(?:日時|日程|開催日|日付)[\s：:ー〜\-]*(\d{4})年(\d{1,2})月(\d{1,2})日', article_text)
                    if date_match:
                        year = date_match.group(1)
                        month = f"{int(date_match.group(2)):02d}"
                        day = f"{int(date_match.group(3)):02d}"
                        event_date = f"{year}-{month}-{day}"
                    else:
                        # 2026/07/12 や 2026.07.12 等のフォーマット
                        slash_match = re.search(r'(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})', article_text)
                        if slash_match:
                            event_date = f"{slash_match.group(1)}-{int(slash_match.group(2)):02d}-{int(slash_match.group(3)):02d}"
                        else:
                            # M月D日 フォーマット (今年とする)
                            md_match = re.search(r'(\d{1,2})月(\d{1,2})日', article_text)
                            if md_match:
                                year = datetime.today().year
                                event_date = f"{year}-{int(md_match.group(1)):02d}-{int(md_match.group(2)):02d}"
                                
                    # 日付が見つからない場合はフォールバック
                    if not event_date:
                        event_date = parse_date(title_text)
                        if not event_date or event_date == datetime.today().strftime("%Y-%m-%d"):
                            event_date = parse_date(article_text)
                            
                    # 会場のパース (■会場：渋谷DAIA 等から抽出)
                    venue_match = re.search(r'(?:会場|場所|開催場所|ステージ)[\s：:ー〜\-]*([^\n]+)', article_text)
                    venue = venue_match.group(1).strip() if venue_match else ""
                    if venue:
                        # 不要な余白や郵便番号の除去
                        venue = re.sub(r'〒\d+-\d+.*', '', venue).strip()
                        venue = venue.split("（")[0].split("(")[0].strip()
                        
                    # タイトルの組み立て
                    display_title = title_text
                    if venue:
                        display_title = f"{title_text} @ {venue}"
                    display_title = f"【HP告知】{display_title}"
                    
                    # エリア判定
                    area = determine_area(venue + " " + article_text)
                    
                    # 出演者(重複検知と名寄せ)
                    performers_list = ["東京CuteCute"]
                    article_lower = article_text.lower().replace(" ", "")
                    # Red Radianceが共演しているか検証
                    if "redradiance" in article_lower or "red radiance" in article_text.lower():
                        performers_list.append("Red radiance")
                        
                    performers = ", ".join(performers_list)
                    
                    events.append({
                        "date": event_date,
                        "area": area,
                        "title": display_title,
                        "performers": performers,
                        "url": ticket_url if ticket_url else full_url,
                        "raw_text": article_text[:1000]
                    })
                    
            except Exception as pe:
                print(f"⚠️ 詳細ページ {full_url} の取得中にエラー: {str(pe)}")
                
    except Exception as e:
        print(f"🚨 公式サイトスクレイピング中にエラーが発生しました: {str(e)}")
        
    print(f"✅ 公式サイトから {len(events)} 件のイベントを抽出しました。")
    return events

if __name__ == "__main__":
    # テスト実行
    import sys
    import io
    if sys.platform.startswith('win'):
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
        
    res = scrape_tokyocutecute_site()
    for e in res:
        print(f"日付: {e['date']} | エリア: {e['area']} | 出演者: {e['performers']}")
        print(f"タイトル: {e['title']}")
        print(f"URL: {e['url']}")
        print("-" * 40)
