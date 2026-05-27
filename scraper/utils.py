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
    例: '2026年5月27日' -> '2026-05-27'
        '2026/05/27' -> '2026-05-27'
        '5/27(水)' -> 今年('2026')を補完して '2026-05-27'
    """
    if not date_str:
        return datetime.today().strftime("%Y-%m-%d")
    
    # 余分な空白や改行をクリーンアップ
    date_clean = re.sub(r'\s+', '', date_str)
    
    current_year = datetime.today().year
    
    # パターン1: YYYY-MM-DD
    match = re.search(r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})', date_clean)
    if match:
        return f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
    
    # パターン2: MM-DD または MM/DD (例: 05/27, 5/27)
    match = re.search(r'(\d{1,2})[-/](\d{1,2})', date_clean)
    if match:
        return f"{current_year}-{int(match.group(1)):02d}-{int(match.group(2)):02d}"
    
    # パターン3: YYYY年MM月DD日
    match = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日', date_clean)
    if match:
        return f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
    
    # パターン4: MM月DD日
    match = re.search(r'(\d{1,2})月(\d{1,2})日', date_clean)
    if match:
        return f"{current_year}-{int(match.group(1)):02d}-{int(match.group(2)):02d}"
    
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
