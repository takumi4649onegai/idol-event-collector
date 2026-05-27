import requests
import config

# Notion API エンドポイント
NOTION_BASE_URL = "https://api.notion.com/v1"

def get_headers():
    return {
        "Authorization": f"Bearer {config.NOTION_API_KEY}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }

def get_marking_idols() -> list:
    """
    Notionの「マスターDB（マーキングアイドル用）」からアイドル一覧を取得。
    各アイドルの「アイドル名」と「Xアカウント(ID)」を取得します。
    """
    if not config.NOTION_API_KEY or not config.IDOL_DB_ID:
        print("⚠️ Notion APIキー、またはアイドルマスターDB IDが設定されていません。")
        return []

    url = f"{NOTION_BASE_URL}/databases/{config.IDOL_DB_ID}/query"
    
    # 標準的な初期Xハンドルマッピング（Notion側に列がない・空の場合のフォールバック）
    DEFAULT_X_HANDLES = {
        "東京CuteCute": "tokyo_cutecute",
        "Redradiance": "Redradiance_info"
    }

    idols = []
    try:
        response = requests.post(url, headers=get_headers(), json={})
        if response.status_code != 200:
            print(f"❌ NotionマスターDBの取得に失敗しました: HTTP {response.status_code}")
            print(response.text)
            return []
            
        results = response.json().get("results", [])
        for page in results:
            properties = page.get("properties", {})
            
            # 1. アイドル名の取得 (Title列)
            # Notionのタイトル列の名前は「アイドル名」または「Name」や「Title」である可能性を考慮してフォールバック
            name_prop = properties.get("アイドル名") or properties.get("Name") or properties.get("title")
            if not name_prop:
                continue
                
            title_list = name_prop.get("title", [])
            if not title_list:
                continue
                
            idol_name = title_list[0].get("text", {}).get("content", "").strip()
            if not idol_name:
                continue
            
            # 2. XアカウントIDの取得 (Rich Text列)
            # 「Xアカウント」「X_ID」「X_Account」などの名前の列から探す
            x_id = ""
            x_prop = properties.get("Xアカウント") or properties.get("X_ID") or properties.get("XアカウントID")
            
            if x_prop:
                # テキスト列またはURL列である可能性があるため判定
                prop_type = x_prop.get("type", "")
                if prop_type == "rich_text":
                    rich_text = x_prop.get("rich_text", [])
                    if rich_text:
                        x_id = rich_text[0].get("text", {}).get("content", "").strip()
                elif prop_type == "url":
                    x_url = x_prop.get("url", "")
                    if x_url:
                        # URLからユーザーIDを抽出 (例: https://x.com/tokyo_cutecute -> tokyo_cutecute)
                        x_id = x_url.rstrip("/").split("/")[-1].split("?")[0]
            
            # 先頭の @ を除外
            if x_id:
                x_id = x_id.replace("@", "")
            else:
                # Notion上で未入力の場合は、デフォルトのマッピングから取得
                x_id = DEFAULT_X_HANDLES.get(idol_name, "")
                
            idols.append({
                "name": idol_name,
                "x_id": x_id
            })
            
    except Exception as e:
        print(f"🚨 NotionマスターDB取得中に例外が発生しました: {str(e)}")
        
    print(f"ℹ️ Notionから取得したマーキングアイドル: {idols}")
    return idols

def is_event_duplicate(url_str: str, title: str, date_str: str) -> bool:
    """
    すでにイベントが登録されているか重複チェックを行う。
    1. URLが存在する場合は URL プロパティで一致判定。
    2. URLがない場合は「イベント名」かつ「日付」で一致判定。
    """
    if not config.NOTION_API_KEY or not config.EVENT_DB_ID:
        return False
        
    query_url = f"{NOTION_BASE_URL}/databases/{config.EVENT_DB_ID}/query"
    
    # フィルタ条件の構築
    if url_str:
        # URLによる完全一致検索
        payload = {
            "filter": {
                "property": "URL",
                "url": {
                    "equals": url_str
                }
            }
        }
    else:
        # URLがない場合はタイトルと日付による複合一致検索
        payload = {
            "filter": {
                "and": [
                    {
                        "property": "イベント名",
                        "title": {
                            "equals": title
                        }
                    },
                    {
                        "property": "日付",
                        "date": {
                            "equals": date_str
                        }
                    }
                ]
            }
        }
        
    try:
        response = requests.post(query_url, headers=get_headers(), json=payload)
        if response.status_code == 200:
            results = response.json().get("results", [])
            return len(results) > 0
    except Exception as e:
        print(f"⚠️ 重複チェック中にエラーが発生しました: {str(e)}")
        
    return False

def save_event_to_notion(event: dict) -> bool:
    """
    イベント情報をNotionの「メインDB」へ新規保存する。
    """
    if not config.NOTION_API_KEY or not config.EVENT_DB_ID:
        return False
        
    url = f"{NOTION_BASE_URL}/pages"
    
    # Notionへの保存用ペイロード構築
    payload = {
        "parent": {"database_id": config.EVENT_DB_ID},
        "properties": {
            "イベント名": {
                "title": [
                    {"text": {"content": event["title"]}}
                ]
            },
            "日付": {
                "date": {
                    "start": event["date"]
                }
            },
            "地域": {
                "select": {
                    "name": event["area"]  # "東京", "新潟", "その他"
                }
            },
            "出演者一覧": {
                "rich_text": [
                    {"text": {"content": event["performers"]}}
                ]
            }
        }
    }
    
    # URLがあれば追加
    if event.get("url"):
        payload["properties"]["URL"] = {"url": event["url"]}
        
    try:
        response = requests.post(url, headers=get_headers(), json=payload)
        if response.status_code == 200:
            print(f"💾 Notion保存成功: {event['title']} ({event['date']})")
            return True
        else:
            print(f"❌ Notion保存失敗: HTTP {response.status_code}")
            print(response.text)
            return False
    except Exception as e:
        print(f"🚨 Notion保存中に例外が発生しました: {str(e)}")
        return False

if __name__ == "__main__":
    # 単体テスト用
    import os
    import sys
    import io
    if sys.platform.startswith('win'):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
        
    if config.validate_config():
        print("設定検証: OK")
        idols = get_marking_idols()
        print(f"テスト取得結果: {idols}")
