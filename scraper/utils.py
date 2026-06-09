import re
from datetime import datetime

# 新潟の具体的なライブ会場・商業施設・リリイベ会場など (誤判定しにくい特定キーワード)
NIIGATA_SPECIFIC_KEYWORDS = [
    "riverst",
    "club riverst",
    "golden pigs",
    "goldenpigs",
    "新潟golden pigs",
    "新潟riverst",
    "新潟club riverst",
    "柳都showcase",
    "柳都show!case!!",
    "柳都オレンジスタジアム",
    "niigata lots",
    "新潟lots",
    "nexs niigata",
    "nexs",
    "ジョイアミーア",
    "gioiamia",
    "gioia mia",
    "朱鷺メッセ",
    "新潟県民会館",
    "新潟市民芸術文化会館",
    "りゅーとぴあ",
    "新潟日報メディアシップ",
    "万代島多目的広場",
    "イオンモール新潟亀田インター",
    "イオン新潟亀田",
    "新潟亀田インター",
    "亀田インター",
    "タワーレコード新潟店",
    "タワレコ新潟",
    "tower records 新潟",
    "tower records niigata",
    "イオンモール新発田",
    "イオン新発田",
    "イオンモール新潟南",
    "新潟南",
    "万代シテイ",
    "万代シティ",
    "万代シテイビルボードプレイス",
    "ビルボードプレイス",
    "bp2",
    "ラブラ万代",
    "ラブラ2",
    "古町ルフル",
    "cocolo新潟"
]

# 新潟の広域・地域名系キーワード (他県との併記時に誤判定しやすいもの)
NIIGATA_GENERAL_KEYWORDS = [
    "新潟市",
    "長岡市",
    "三条市",
    "上越市",
    "新発田市",
    "燕市",
    "柏崎市",
    "古町",
    "万代",
    "新潟駅",
    "新潟駅南口",
    "新潟駅前",
    "新潟", "niigata", "長岡", "三条", "上越", "nexus", "柳都"
]

# 全新潟キーワード統合
NIIGATA_KEYWORDS = NIIGATA_SPECIFIC_KEYWORDS + NIIGATA_GENERAL_KEYWORDS

TOKYO_KEYWORDS = [
    "東京", "tokyo", "渋谷", "新宿", "池袋", "秋葉原", "アキバ", "品川", "六本木", 
    "恵比寿", "お台場", "豊洲", "赤坂", "原宿", "上野", "中野", "吉祥寺", "立川", 
    "八王子", "蒲田", "浅草", "目黒", "五反田", "新木場", "zepp", "ドーム", "ホール",
    "下北沢", "代々木", "銀座", "有楽町", "大手町"
]

def determine_area(text: str) -> str:
    """
    イベントのタイトルや本文から会場名（場所）を抽出し、
    その会場名に新潟または東京の要素があるかを厳密に判定してエリアを割り当てる。
    """
    if not text:
        return "その他"
        
    text_lower = text.lower()
    
    # 1. 会場名（場所）の抽出を試みる
    venue = ""
    venue_match = re.search(r'(?:会場|場所|place|Place|＠|@|スタジオ|シアター|ホール|ライブハウス)[\s：:ー]*([^\s|｜(（【\n]+)', text)
    if venue_match:
        venue = venue_match.group(1).strip().lower()
        # 会場名の後にありがちな余分なテキスト（出演、開場、開演、チケットなど）を切り落とす
        venue = re.split(r'(?:出演|開場|開演|チケット|予約|主催|企画|料金|・|\|)', venue)[0].strip()
        venue = re.sub(r'[\(\)（）\-\[\]\{\}！!？?]', '', venue).strip()
    
    # 新潟・東京のキーワード判定
    # A. 抽出された会場名での判定
    if venue:
        is_niigata_venue = any(kw.lower() in venue for kw in NIIGATA_KEYWORDS)
        is_tokyo_venue = any(kw.lower() in venue for kw in TOKYO_KEYWORDS)
        
        # 新潟会場名が明確に含まれている場合は、新潟優先
        if is_niigata_venue and not is_tokyo_venue:
            return "新潟"
        if is_tokyo_venue:
            return "東京"
            
    # B. 会場名が明示されていない、または判定が曖昧な場合のフォールバック（本文全体の解析）
    has_specific_niigata = any(kw.lower() in text_lower for kw in NIIGATA_SPECIFIC_KEYWORDS)
    has_general_niigata = any(kw.lower() in text_lower for kw in NIIGATA_GENERAL_KEYWORDS)
    has_tokyo_signal = any(kw.lower() in text_lower for kw in TOKYO_KEYWORDS)
    
    # 本文中に新潟の特定会場が明確に含まれている場合は新潟優先
    if has_specific_niigata:
        return "新潟"
        
    if has_tokyo_signal:
        return "東京"
        
    if has_general_niigata:
        return "新潟"
        
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
        venue = re.sub(r'[\(\)（）\-\[\]\{\}【】]', '', venue).strip()
        
    return start_time, venue


def is_generic_list_url(url: str) -> bool:
    """
    URLが個別イベントではなく、雑多な予定が並ぶ一覧・まとめページであるかを判定する。
    """
    if not url:
        return False
    
    url_lower = url.lower()
    
    # 汎用一覧ページを表すパスパターン
    list_patterns = [
        r'/events$', r'/events\?.*',
        r'/schedule$', r'/schedule\?.*',
        r'/performers/\d+$', r'/performers/\d+\?.*',
        r'/artist/\d+$', r'/artist/\d+\?.*',
        r'/news$', r'/news\?.*',
        r'/blog$', r'/blog\?.*',
        r'event/search', r'event/list'
    ]
    
    for pattern in list_patterns:
        if re.search(pattern, url_lower):
            return True
            
    return False

def normalize_event_url(url: str) -> str:
    """
    イベントURLから不要なトラッキングパラメータやフラグメント（アンカー）を削除し、一意に正規化する。
    ただし、通常の http:// または https:// URLのみを対象とし、それ以外（local_id: など）はそのまま維持する。
    """
    if not url:
        return ""
    
    url = url.strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        return url
        
    # 1. フラグメント (#以降) を完全に削除
    url_no_frag = url.split("#")[0].strip()
    
    # 2. クエリパラメータ (?) を解析し、トラッキングパラメータのみを除去
    if "?" in url_no_frag:
        base, query_str = url_no_frag.split("?", 1)
        tracking_keys = {
            "_gl", "utm_source", "utm_medium", "utm_campaign",
            "utm_term", "utm_content", "fbclid", "gclid",
            "yclid", "igshid", "xclid"
        }
        
        parts = query_str.split("&")
        new_parts = []
        for part in parts:
            if not part:
                continue
            # キー部を取得（例: name=value の name）
            key = part.split("=")[0].strip()
            if key.lower() not in tracking_keys:
                new_parts.append(part)
                
        if new_parts:
            return f"{base}?{'&'.join(new_parts)}"
        else:
            return base
    else:
        return url_no_frag
