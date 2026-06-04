import re
from datetime import datetime

# 地域判定用のキーワード辞書 (すべて小文字で判定)
NIIGATA_KEYWORDS = [
    "新潟", "niigata", "長岡", "三条", "上越", "朱鷺メッセ", "新潟lott", "nexus", 
    "万代", "古町", "golds", "riverst", "nexs", "新潟駅", "柳都"
]

TOKYO_KEYWORDS = [
    "東京", "tokyo", "渋谷", "新宿", "池袋", "秋葉原", "アキバ", "品川", "六本木", 
    "恵比寿", "お台場", "豊洲", "赤坂", "原宿", "上野", "中野", "吉祥寺", "立川", 
    "八王子", "蒲田", "浅草", "目黒", "五反田", "新木場", "Zepp", "ドーム", "ホール",
    "下北沢", "代々木", "銀座", "有楽町", "大手町"
]

def determine_area(text: str) -> str:
    """
    イベントのタイトルや本文、会場名から「東京」「新潟」「その他」を判別する。
    """
    if not text:
        return "その他"
    
    text_lower = text.lower()
    
    # 新潟判定
    if any(keyword in text_lower for keyword in NIIGATA_KEYWORDS):
        return "新潟"
    
    # 東京判定
    if any(keyword in text_lower for keyword in TOKYO_KEYWORDS):
        return "東京"
    
    return "その他"

def parse_date(date_str: str) -> str:
    """
    様々な日付表記を YYYY-MM-DD 形式に統一する。
    郵便番号（150-0043）、時間（19:35-19:55）、番地（5-51-12）等に対する
    誤検知（月日が範囲外になるマッチ）を防ぐため、日本語表記を優先し、月日の妥当性を厳密に検証します。
    """
    if not date_str:
        return datetime.today().strftime("%Y-%m-%d")
    
    # 余分な空白や改行をクリーンアップ
    date_clean = re.sub(r'\s+', '', date_str)
    current_year = datetime.today().year
    
    # --- 最優先: 日本語表記パターン (誤マッチが極めて少ないため) ---
    
    # パターン1: YYYY年MM月DD日
    match = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日', date_clean)
    if match:
        y, m, d = int(match.group(1)), int(match.group(2)), int(match.group(3))
        if 1 <= m <= 12 and 1 <= d <= 31:
            return f"{y}-{m:02d}-{d:02d}"
    
    # パターン2: MM月DD日
    match = re.search(r'(\d{1,2})月(\d{1,2})日', date_clean)
    if match:
        m, d = int(match.group(1)), int(match.group(2))
        if 1 <= m <= 12 and 1 <= d <= 31:
            return f"{current_year}-{m:02d}-{d:02d}"
            
    # --- 次点: スラッシュ・ハイフン表記パターン (範囲チェック付きで郵便番号や時間範囲を完全排除) ---
    
    # パターン3: YYYY-MM-DD
    # findall でマッチを全列挙し、有効な最初の日付を採用（郵便番号などの部分ノイズを迂回するため）
    matches = re.findall(r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})', date_clean)
    for y_str, m_str, d_str in matches:
        y, m, d = int(y_str), int(m_str), int(d_str)
        if 1 <= m <= 12 and 1 <= d <= 31:
            return f"{y}-{m:02d}-{d:02d}"
            
    # パターン4: MM-DD または MM/DD (例: 05/27, 5/27)
    # タイムスケジュール 19:35-19:55 等に含まれる部分文字列（35-19 等）や郵便番号（50-00 等）を回避するため、
    # 有効な月日（1-12月、1-31日）に合致する最初の組み合わせのみを厳密に探す
    matches = re.findall(r'(\d{1,2})[-/](\d{1,2})', date_clean)
    for m_str, d_str in matches:
        m, d = int(m_str), int(d_str)
        if 1 <= m <= 12 and 1 <= d <= 31:
            return f"{current_year}-{m:02d}-{d:02d}"
    
    # フォールバック: パースできなかった場合は今日の年月日を返す
    try:
        # '20260527' のような単純数値
        parsed = datetime.strptime(date_clean, "%Y%m%d")
        return parsed.strftime("%Y-%m-%d")
    except ValueError:
        pass
        
    return datetime.today().strftime("%Y-%m-%d")

def clean_text(text: str) -> str:
    """
    余分な改行や半角/全角スペースを整形する
    """
    if not text:
        return ""
    text = text.replace("\r", "")
    text = re.sub(r'\n{3,}', '\n\n', text) # 3つ以上の連続改行は2つにする
    return text.strip()

def determine_performers(text: str, default_performers: str = "") -> str:
    """
    テキスト本文（ツイートや公式サイト記事）から、出演しているアイドルグループを動的に名寄せ・判定する。
    兼任メンバー（小見山沙空、柚谷双葉、西萌葉）が関わる場合は、自動的に両グループを出演者として設定する。
    ただし、名前が「除く」「不参加」といったキーワードと共に用いられている場合は、そのメンバーの出演をカウントしない。
    """
    if not text:
        return default_performers
        
    text_clean = text.lower().replace(" ", "").replace("\n", "").replace("\r", "")
    
    concurrent_members = ["小見山沙空", "小宮山さら", "柚谷双葉", "西萌葉"]
    exclude_keywords = ["除く", "不参加", "欠席", "お休み", "休演", "出演はございません", "出演なし", "出演いたしません", "出演致しません"]
    
    matched_groups = set()
    
    # グループ名や個々のメンバーのキーワード検出
    import config
    for idol in config.MARKING_IDOLS:
        group_name = idol["name"]
        for query in idol["search_queries"]:
            q_clean = query.lower().replace(" ", "")
            if q_clean in text_clean:
                # 兼任メンバーの名前がマッチした場合のみ除外判定を行う
                is_concurrent = any(c.lower() in q_clean or q_clean in c.lower() for c in concurrent_members)
                if is_concurrent:
                    pos = text_clean.find(q_clean)
                    context = text_clean[pos:pos+25]
                    is_excluded = any(kw in context for kw in exclude_keywords)
                    if is_excluded:
                        continue # 除外されている場合はこのキーワードでのマッチを無視
                        
                    # 除外されていない場合は、兼任メンバーなので両グループを追加
                    matched_groups.add("東京CuteCute")
                    matched_groups.add("Red radiance")
                else:
                    # 通常メンバーまたはグループ名自体のマッチ
                    matched_groups.add(group_name)
                    
    if not matched_groups:
        return default_performers
        
    # 元のデフォルト出演者も確実に入れる
    if default_performers:
        for p in default_performers.split(", "):
            if p.strip() and p.strip() != "i":
                matched_groups.add(p.strip())
                
    # MARKING_IDOLSの順番でソートして綺麗な文字列にする
    ordered_groups = []
    for idol in config.MARKING_IDOLS:
        if idol["name"] in matched_groups:
            ordered_groups.append(idol["name"])
            
    for g in matched_groups:
        if g not in ordered_groups:
            ordered_groups.append(g)
            
    return ", ".join(ordered_groups)

def parse_time_and_venue(title: str, raw_text: str, default_area: str = "その他") -> tuple:
    """
    イベントのタイトルや本文から、開始時間(HH:MM)と会場名(場所)を抽出する。
    重複排除(デデュープ)のキー作成用に使用します。
    """
    combined = f"{title} {raw_text or ''}"
    
    # 1. 開始時間の抽出 (例: 18:30, 19:00 など)
    time_match = re.search(r'\b(\d{1,2}:\d{2})\b', combined)
    start_time = time_match.group(1) if time_match else "00:00"
    
    # 2. 会場名(場所)の抽出
    # 会場らしきキーワードの後に続く文字列を抽出する
    venue = default_area
    venue_match = re.search(r'(?:会場|場所|place|Place|＠|@|スタジオ|シアター|ホール|ライブハウス)[\s：:ー]*([^\s|｜(（【]+)', combined)
    if venue_match:
        venue = venue_match.group(1).strip()
        # 余分な括弧や記号を削除
        venue = re.sub(r'[\(\)（）\-\[\]\{\}]', '', venue).strip()
        
    return start_time, venue
