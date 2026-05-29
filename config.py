import os
from dotenv import load_dotenv

# .env ファイルの読み込み (ローカル開発用)
load_dotenv()

# ==================================================
# 1. 監視対象の「本命マークアイドル」リスト
# ==================================================
# アイドル名とXのユーザーIDを定義します。
# 新しく追跡したいグループがあれば、この配列に要素を追加するだけでOKです！
# 公式Xのタイムラインとチケットサイトを優先監視し、新着は即座にプッシュ通知されます。
MARKING_IDOLS = [
    {
        "name": "東京CuteCute",
        "search_queries": [
            "東京CuteCute",
            "東京Cute",
            "西萌葉", "西 萌葉",
            "小見山沙空", "小見山 沙空",
            "白瀬みれい", "白瀬 みれい",
            "桃宮唯花", "桃宮 唯花",
            "柴田理名", "柴田 理名",
            "桜ゆな", "桜 ゆな",
            "柚谷双葉", "柚谷 双葉",
            "有栖れる", "有栖 れる"
        ],
        "x_id": "TOKYO_Cute2"
    },
    {
        "name": "Red radiance",
        "search_queries": [
            "Red radiance",
            "Redradiance",
            "神城朱里", "神城 朱里",
            "恋水凛", "恋水 凛",
            "Chara", "ちゃら",
            "星宮ほのか", "星宮 ほのか",
            "茉音華", "まおか"
        ],
        "x_id": "gce_rr"
    }
]

# ==================================================
# 2. エリア一般イベントの収集用検索キーワード
# ==================================================
# チケットサイトで一般収集するためのキーワードです。
# ここに登録されたワードでの検索結果はすべてデータベースに保存されます。
# 自動プッシュ通知はされず、LINEで「今日新潟で何かある？」等と聞いた時に引き出すことができます。
GENERAL_SEARCH_KEYWORDS = [
    "新潟 アイドル",
    "新潟 ライブ",
    "アイドル 対バン",
    "フリーライブ アイドル",
    "インストアライブ アイドル"
]

# ==================================================
# 3. システム環境設定 (環境変数から取得)
# ==================================================

# LINE Messaging API 設定 (対話応答 ＆ 自動プッシュ配信用)
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET", "")

# Webサーバーポート
PORT = int(os.getenv("PORT", "5000"))

# スクレイピング機能制御 (True / False)
ENABLE_X_SCRAPING = True
ENABLE_TIGET_SCRAPING = os.getenv("ENABLE_TIGET_SCRAPING", "True").lower() == "true"
ENABLE_LIVEPOCKET_SCRAPING = os.getenv("ENABLE_LIVEPOCKET_SCRAPING", "True").lower() == "true"
ENABLE_TICKETDIVE_SCRAPING = os.getenv("ENABLE_TICKETDIVE_SCRAPING", "True").lower() == "true"

# Nitter RSS base url
NITTER_BASE_URL = os.getenv("NITTER_BASE_URL", "https://nitter.poast.org").rstrip("/")

# Googleカレンダー & Web検索 API 設定
GOOGLE_CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID", "")
GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")

def validate_config():
    """設定の入力状況を確認"""
    missing = []
    if not LINE_CHANNEL_ACCESS_TOKEN:
        missing.append("LINE_CHANNEL_ACCESS_TOKEN")
    if not LINE_CHANNEL_SECRET:
        missing.append("LINE_CHANNEL_SECRET")
        
    if missing:
        print(f"⚠️ 警告: 以下の環境変数が設定されていません: {', '.join(missing)}")
        print("対話型ボットの完全な動作にはこれらが必須です。")
        print(".env ファイルを作成するか、サーバーの設定を確認してください。")
        return False
    return True
