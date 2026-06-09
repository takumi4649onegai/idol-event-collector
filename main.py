import time
import sys
import io

# Windowsコンソールでの絵文字表示による UnicodeEncodeError (cp932) 回避用 (リアルタイム出力)
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        # 古いPython環境向けのフォールバック (バッファ自動フラッシュ有効)
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', write_through=True)
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', write_through=True)

import config
import db_manager
import line_client
from scraper.utils import clean_text
from scraper.tiget import scrape_tiget_performer
from datetime import datetime, timezone, timedelta
JST = timezone(timedelta(hours=9))

def run_marked_idols_collection() -> tuple:
    """
    本命マークアイドルの巡回と新着プッシュ通知の実行
    戻り値: (検出総数, 新規保存＆通知数)
    """
    print("\n==================================================")
    print("🎯 モード1: 本命マークアイドルの巡回を開始します")
    print("==================================================")
    
    total_scraped = 0
    new_notified = 0
    
    for idol in config.MARKING_IDOLS:
        name = idol["name"]
        x_id = idol["x_id"]
        
        print(f"\n──────────────────────────────────────────────────")
        print(f"🎤 監視対象: {name} (X: @{x_id if x_id else '未設定'})")
        print(f"──────────────────────────────────────────────────")
        
        idol_events = []
        
        # LivePocket用の検索ワードの組み立て
        group_queries = idol.get("livepocket_search_queries", [name])
        
        # メンバー名による検索ワード（生誕祭用）
        member_queries = []
        for q in idol.get("search_queries", []):
            q_clean = q.replace(" ", "").lower()
            is_group_name = q_clean == name.replace(" ", "").lower() or any(q_clean == g.replace(" ", "").lower() for g in group_queries)
            if not is_group_name:
                clean_q = q.replace(" ", "").strip()
                if clean_q and clean_q not in member_queries:
                    member_queries.append(clean_q)
        
        # --- LivePocket スクレイピング ---
        if config.ENABLE_LIVEPOCKET_SCRAPING:
            from scraper.livepocket import scrape_livepocket_events
            
            # 1. グループ検索の実行
            for word in group_queries:
                print(f"🔍 LivePocketグループ検索開始: {word}")
                try:
                    lp_events = scrape_livepocket_events(word)
                    print(f"✅ LivePocket取得件数: {len(lp_events)}件")
                    for ev in lp_events:
                        ev["is_member_search"] = False
                        ev["searched_word"] = word
                    idol_events.extend(lp_events)
                except Exception as e:
                    print(f"🚨 LivePocket取得中にエラー ({word}): {str(e)}")
                    
            # 2. メンバー検索の実行 (生誕祭・個人イベント用)
            for word in member_queries:
                print(f"🔍 LivePocketメンバー検索開始: {word}")
                try:
                    lp_events = scrape_livepocket_events(word)
                    print(f"✅ LivePocket取得件数: {len(lp_events)}件")
                    for ev in lp_events:
                        ev["is_member_search"] = True
                        ev["searched_word"] = word
                    idol_events.extend(lp_events)
                except Exception as e:
                    print(f"🚨 LivePocket取得中にエラー ({word}): {str(e)}")

        # --- TIGET パフォーマーページ スクレイピング (最優先情報源) ---
        tiget_perf_id = idol.get("tiget_performer_id", "")
        if config.ENABLE_TIGET_SCRAPING and tiget_perf_id:
            try:
                tiget_perf = scrape_tiget_performer(tiget_perf_id, name)
                idol_events.extend(tiget_perf)
            except Exception as e:
                print(f"🚨 TIGETパフォーマーページ取得中にエラー: {str(e)}")
                
        # --- TicketDive 巡回・検索スクレイピング ---
        if config.ENABLE_TICKETDIVE_SCRAPING:
            from scraper.ticketdive import scrape_ticketdive_events
            td_queries = idol.get("ticketdive_search_queries", idol.get("livepocket_search_queries", [name]))
            for word in td_queries:
                print(f"🔍 TicketDive検索開始: {word}")
                try:
                    td_events = scrape_ticketdive_events(word)
                    print(f"✅ TicketDive取得件数: {len(td_events)}件")
                    idol_events.extend(td_events)
                except Exception as e:
                    print(f"🚨 TicketDive取得中にエラー ({word}): {str(e)}")
                
        total_scraped += len(idol_events)
        
        # セッション内での重複排除 と 取得後フィルタリング
        unique_idol_events = []
        seen_urls = set()
        for ev in idol_events:
            url = ev.get("url", "")
            if url in seen_urls:
                continue
                
            # LivePocket用の取得後ノイズフィルター
            if ev.get("source") == "LivePocket":
                title = ev.get("title", "")
                performers = ev.get("performers", "")
                raw_text = ev.get("raw_text", "")
                combined_text = (title + " " + performers + " " + raw_text).lower().replace(" ", "")
                
                # 対象グループ関連キーワードまたはメンバー名が含まれるか確認
                group_kws_clean = [g.replace(" ", "").lower() for g in group_queries]
                member_kws_clean = [m.replace(" ", "").lower() for m in member_queries]
                all_kws_clean = group_kws_clean + member_kws_clean
                
                # 「レドラ」の厳密な判定用の正規表現
                import re
                has_redra = False
                if "レドラ" in raw_text or "レドラ" in title:
                    if re.search(r'(?<![ぁ-んァ-ヶ一-龠a-zA-Z0-9])レドラ(?![ぁ-んァ-ヶ一-龠a-zA-Z0-9])', raw_text + " " + title):
                        has_redra = True
                
                # いずれかのキーワードが含まれているか判定
                matched_kw = any(kw in combined_text for kw in all_kws_clean if kw != "レドラ") or has_redra
                
                if not matched_kw:
                    # 関連キーワードが一切含まれていない無関係なイベントはスキップ
                    print(f"⏭️ 関連キーワード不足のためLivePocketイベントを除外: {title}")
                    continue
                    
                # メンバー検索（生誕祭など）の場合の追加フィルタ条件
                if ev.get("is_member_search", False):
                    # タイトルに生誕・Birthday等の文字があるか、または本文・出演者に対象グループ名があるか
                    has_birthday_kw = any(x in title.lower() for x in ["生誕", "生誕祭", "birthday"])
                    has_group_mention = any(g.replace(" ", "").lower() in combined_text for g in group_kws_clean)
                    
                    if not (has_birthday_kw or has_group_mention):
                        # メンバー名ではヒットしたものの、生誕祭でもグループ公式イベントでもないものは除外
                        print(f"⏭️ メンバー名検索の対象外(生誕/グループ名なし)のため除外: {title}")
                        continue
            
            from scraper.utils import determine_performers
            ev["performers"] = determine_performers(ev.get("raw_text", "") + " " + ev.get("title", ""), ev.get("performers", name))
            seen_urls.add(url)
            unique_idol_events.append(ev)
                
        # データベース保存 ＆ 新着プッシュ通知
        for ev in unique_idol_events:
            # 過去（今日より前）のイベントはデータベースに保存しない (JST基準)
            today_str = datetime.now(JST).strftime("%Y-%m-%d")
            if ev.get("date", "") < today_str:
                print(f"⏭️ 過去イベント（保存スキップ）: {ev['title']} ({ev['date']})")
                continue
                
            # 一覧ページURLはイベント特定ができないため除外 (全面禁止ルール適用)
            from scraper.utils import is_generic_list_url
            if is_generic_list_url(ev.get("url", "")):
                print(f"⏭️ 一覧ページURLのためスキップ: {ev['title']} ({ev['url']})")
                continue
                
            # データベースへの保存を試みる (URL重複は自動スキップ)
            is_new = db_manager.insert_event(ev)
            
            # 新潟ローカルシグナル判定の厳密化 (会場名ベースでの新潟判定)
            from scraper.utils import determine_area
            combined_text = f"{ev.get('title', '')} {ev.get('raw_text', '')}"
            is_niigata_local = determine_area(combined_text) == "新潟"

            
            source_val = ev.get("source") or "Unknown"
            if is_new:
                print(f"✅ 新規イベント登録: {ev['title']} ({ev['date']}) / source={source_val}")
                
                # 重複排除チェック（新潟エリア含めすべての地域で共通実行）
                from db_manager import is_duplicate_by_dedupe_key
                if not is_duplicate_by_dedupe_key(ev):
                    print(f"📩 LINE通知送信: {ev['title']} ({ev['date']}) / source={source_val}")
                    line_client.send_line_push_notification(ev)
                    from calendar_client import add_to_google_calendar
                    add_to_google_calendar(ev)
                    new_notified += 1
                else:
                    print(f"🔕 重複または既存イベントのためLINE通知なし: {ev['title']} ({ev['date']}) / source={source_val}")
                
                # APIレート制限の回避ウェイト
                time.sleep(1.5)
            else:
                print(f"⏭️ 重複イベントのためスキップ: {ev['title']} ({ev['date']}) / source={source_val}")
                print(f"🔕 重複または既存イベントのためLINE通知なし: {ev['title']} ({ev['date']}) / source={source_val}")
                
    return total_scraped, new_notified


def is_actual_niigata_event(ev: dict) -> bool:
    """
    イベントが実際に新潟で開催されるものであるかを、
    会場情報(event-area)、タイトル、本文(raw_text)から厳密に判定する。
    """
    import re
    title = ev.get("title", "") or ""
    raw_text = ev.get("raw_text", "") or ""
    
    # 1. 会場・場所情報の抽出
    venue = ""
    venue_match = re.search(r'(?:会場|場所|place|Place|＠|@)[\s：:ー]*([^\s|｜(（【\n]+)', title + " " + raw_text)
    if venue_match:
        venue = venue_match.group(1).strip()
        # 余分なテキストの切り落とし
        venue = re.split(r'(?:出演|開場|開演|チケット|予約|主催|料金|・|\|)', venue)[0].strip()
        venue = re.sub(r'[\(\)（）\-\[\]\{\}！!？?]', '', venue).strip()
        
    title_lower = title.lower()
    raw_text_lower = raw_text.lower()
    venue_lower = venue.lower()

    # 新潟関連キーワード (新潟市、万代、柳都、主要ライブハウスや商業施設など)
    niigata_keywords = [
        "新潟", "新潟市", "新潟県", "nexs niigata", "nexs", "club riverst", "riverst",
        "golden pigs", "goldenpigs", "柳都showcase", "柳都show!case!!", "柳都オレンジスタジアム",
        "niigata lots", "新潟lots", "lots", "イオンモール新潟", "イオンモール新発田",
        "タワーレコード新潟店", "タワレコ新潟", "ラブラ万代", "ラブラ2", "cocolo新潟", "朱鷺メッセ",
        "万代シテイ", "万代シティ", "古町ルフル", "新潟県民会館", "りゅーとぴあ", "ジョイアミーア"
    ]
    
    # 他地域除外キーワード
    exclude_keywords = [
        "東京", "tokyo", "京都", "kyoto", "広島", "hiroshima", "大阪", "osaka",
        "名古屋", "nagoya", "福岡", "fukuoka", "横浜", "yokohama", "千葉", "chiba",
        "埼玉", "saitama"
    ]

    # "場所：[住所]" のようなパターンもチェック
    place_match = re.search(r'(?:場所|会場)[\s：:ー]*([^\s|｜\n]+)', raw_text)
    place_text = place_match.group(1).strip() if place_match else ""
    place_text_lower = place_text.lower()

    # A. 会場・開催地に新潟のキーワードがあるか
    is_niigata_in_venue = False
    if venue:
        is_niigata_in_venue = any(kw in venue_lower for kw in niigata_keywords)
    if not is_niigata_in_venue and place_text:
        is_niigata_in_venue = any(kw in place_text_lower for kw in niigata_keywords)

    # B. 会場・開催地に他地域のキーワードがあるか
    is_other_in_venue = False
    if venue:
        is_other_in_venue = any(kw in venue_lower for kw in exclude_keywords)
    if not is_other_in_venue and place_text:
        is_other_in_venue = any(kw in place_text_lower for kw in exclude_keywords)

    # 優先順位 1: 会場・開催地に新潟がある → 保存
    if is_niigata_in_venue:
        return True

    # 優先順位 2: 会場・開催地に明確な他県がある → 除外
    if is_other_in_venue:
        return False

    # 優先順位 3: 会場情報が曖昧な場合 → raw_text と title を確認
    has_niigata_in_text = any(kw in raw_text_lower or kw in title_lower for kw in niigata_keywords)
    # タイトル内の他地域キーワードはイベント名の可能性があるので除外しない (例: TOKYO GIRLS GIRLS)
    # そのため他地域キーワードは本文 (raw_text_lower) のみに対してチェックする
    has_other_in_text = any(kw in raw_text_lower for kw in exclude_keywords)

    if has_niigata_in_text:
        if has_other_in_text:
            # 本文に新潟と他地域が混在していて会場が曖昧な場合は「判定不能」とする
            # ただし、特定の新潟会場名が明確に入っている場合は救う
            niigata_specific = [
                "nexs", "riverst", "golden pigs", "goldenpigs", "lots", "朱鷺メッセ", 
                "新潟県民会館", "りゅーとぴあ", "万代", "ラブラ", "cocolo新潟"
            ]
            if any(kw in raw_text_lower or kw in title_lower for kw in niigata_specific):
                return True
            print(f"⚠️ 判定不能 (会場曖昧かつ本文に新潟・他地域併記): {title}")
            return False
        return True

    # 優先順位 4: それでも不明 → 保存せず、ログに「判定不能」として出す
    print(f"⚠️ 判定不能 (新潟キーワードなし): {title}")
    return False


def run_niigata_area_collection() -> tuple:
    """
    新潟エリアのイベント収集 (LINE即通知なし、DB保存のみ)
    戻り値: (検出総数, 新規保存数)
    """
    if not getattr(config, "ENABLE_NIIGATA_AREA_COLLECTION", False):
        print("\n==================================================")
        print("⏭️ 新潟地域イベント収集は無効化されています。")
        print("==================================================")
        return 0, 0
        
    print("\n==================================================")
    print("🌾 新潟地域イベントの一般収集を開始します (通知なし)")
    print("==================================================")
    
    state_id = getattr(config, "NIIGATA_TIGET_STATE_ID", 15)
    from scraper.tiget import scrape_tiget_by_state
    
    try:
        events = scrape_tiget_by_state(state_id)
    except Exception as e:
        print(f"🚨 新潟地域イベント取得中にエラー: {str(e)}")
        return 0, 0
        
    total_scraped = len(events)
    new_saved = 0
    
    # セッション内での重複排除
    unique_events = []
    seen_urls = set()
    for ev in events:
        url = ev.get("url", "")
        if url in seen_urls:
            continue
        seen_urls.add(url)
        unique_events.append(ev)
        
    for ev in unique_events:
        # 過去のイベントはスキップ (JST基準)
        today_str = datetime.now(JST).strftime("%Y-%m-%d")
        if ev.get("date", "") < today_str:
            print(f"⏭️ 過去イベント（保存スキップ）: {ev['title']} ({ev['date']})")
            continue
            
        # 一覧ページURLは除外
        from scraper.utils import is_generic_list_url
        if is_generic_list_url(ev.get("url", "")):
            print(f"⏭️ 一覧ページURLのためスキップ: {ev['title']} ({ev['url']})")
            continue
            
        # 新潟開催のイベントか確認し、違えば保存スキップ
        if not is_actual_niigata_event(ev):
            continue
            
        # エリアを強制的に "新潟" に設定
        ev["area"] = "新潟"
        
        # ソースを "TIGET" に設定
        ev["source"] = "TIGET"
        
        # データベース保存を試みる (重複時は False が返る)
        is_new = db_manager.insert_event(ev)
        source_val = ev.get("source") or "Unknown"
        
        if is_new:
            print(f"✅ 新規新潟地域イベント登録: {ev['title']} ({ev['date']}) / source={source_val}")
            new_saved += 1
        else:
            print(f"⏭️ 重複イベントのためスキップ: {ev['title']} ({ev['date']}) / source={source_val}")
            
    return total_scraped, new_saved


def main():
    print("==================================================")
    print("🚀 女性地下アイドル対話型収集システム コレクター起動")
    print(f"⏰ 実行日時: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("==================================================")

    # 1. 設定の検証
    config.validate_config()
    
    # 2. SQLiteデータベースの確保
    db_manager.init_db()
    
    start_time = time.time()
    
    # モード1: 本命マークアイドルの巡回 (通知あり)
    marked_total, marked_new = run_marked_idols_collection()
    
    # 新潟地域一般イベントの巡回 (通知なし、DB保存のみ)
    gen_total, gen_new = run_niigata_area_collection()
    
    end_time = time.time()
    duration = end_time - start_time
    
    print("\n==================================================")
    print("📊 巡回コレクター 実行処理レポート")
    print(f"⏱️ 処理時間: {duration:.1f} 秒")
    print(f"🎯 本命マーク: 検出 {marked_total} 件 | 新着通知 {marked_new} 件")
    print(f"🔍 一般イベント: 検出 {gen_total} 件 | 新規蓄積 {gen_new} 件")
    print("==================================================")

if __name__ == "__main__":
    main()
