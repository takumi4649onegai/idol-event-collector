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
                
        # --- TIGET 検索巡回 (ゲスト出演・紐付け漏れ対策) ---
        tiget_queries = idol.get("tiget_search_queries", [])
        if config.ENABLE_TIGET_SCRAPING and tiget_queries:
            from scraper.tiget import scrape_tiget_events
            for word in tiget_queries:
                print(f"🔍 TIGET検索開始: {word}")
                try:
                    tiget_search_evs = scrape_tiget_events(word)
                    print(f"✅ TIGET検索取得件数: {len(tiget_search_evs)}件")
                    idol_events.extend(tiget_search_evs)
                except Exception as e:
                    print(f"🚨 TIGET検索取得中にエラー ({word}): {str(e)}")
                
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
                
        # --- Wix 公式カレンダー巡回 ---
        wix_url = idol.get("wix_schedule_url", "")
        if config.ENABLE_WIX_OFFICIAL_SCRAPING and wix_url:
            from scraper.wix_official import scrape_wix_official_schedule
            print(f"🔍 Wix公式カレンダー巡回開始: {name} ({wix_url})")
            try:
                wix_events = scrape_wix_official_schedule(wix_url, name)
                print(f"✅ Wix公式カレンダー取得件数: {len(wix_events)}件")
                idol_events.extend(wix_events)
            except Exception as e:
                print(f"🚨 Wix公式カレンダー取得中にエラー ({name}): {str(e)}")
                
        # --- 東京CuteCute公式サイト巡回 ---
        official_url = idol.get("official_site_url", "")
        if config.ENABLE_TOKYOCUTECUTE_OFFICIAL_SCRAPING and official_url:
            from scraper.tokyocutecute_official import scrape_tokyocutecute_site
            print(f"🔍 東京CuteCute公式サイト巡回開始: {name} ({official_url})")
            try:
                tcc_events = scrape_tokyocutecute_site(official_url, name)
                print(f"✅ 東京CuteCute公式サイト取得件数: {len(tcc_events)}件")
                idol_events.extend(tcc_events)
            except Exception as e:
                print(f"🚨 東京CuteCute公式サイト取得中にエラー ({name}): {str(e)}")
                
        # --- Red Radiance TimeTree巡回 ---
        timetree_url = idol.get("timetree_url", "")
        if config.ENABLE_REDRADIANCE_TIMETREE_SCRAPING and timetree_url:
            from scraper.redradiance_timetree import scrape_redradiance_timetree
            print(f"🔍 Red Radiance TimeTree巡回開始: {name} ({timetree_url})")
            try:
                tt_events = scrape_redradiance_timetree(timetree_url, name)
                print(f"✅ Red Radiance TimeTree取得件数: {len(tt_events)}件")
                idol_events.extend(tt_events)
            except Exception as e:
                print(f"🚨 Red Radiance TimeTree取得中にエラー ({name}): {str(e)}")
                
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
                    # Googleカレンダーへの同期は常に実行
                    from calendar_client import add_to_google_calendar
                    add_to_google_calendar(ev)
                    
                    # 即時LINE通知を送るべきかどうかの判定
                    should_notify = config.ENABLE_REALTIME_LINE_NOTIFICATIONS
                    
                    if not should_notify:
                        # 例外条件のチェック
                        # 1. 新潟開催
                        if is_niigata_local:
                            should_notify = True
                            
                        # 2. 今日または明日の予定 (JST基準)
                        today_str = datetime.now(JST).strftime("%Y-%m-%d")
                        tomorrow_str = (datetime.now(JST) + timedelta(days=1)).strftime("%Y-%m-%d")
                        if ev.get("date", "") in [today_str, tomorrow_str]:
                            should_notify = True
                            
                        # 3. 無銭LIVEっぽい予定
                        free_keywords = ["無料", "無銭", "フリーライブ", "フリー", "観覧無料", "入場無料", "観覧フリー", "リリイベ", "インストアライブ"]
                        combined_lower = combined_text.lower()
                        if any(kw in combined_lower for kw in free_keywords):
                            should_notify = True
                            
                        # 4. チケット発売/受付開始/先行/一般販売
                        ticket_keywords = ["発売", "販売開始", "受付開始", "抽選", "先行", "一般販売"]
                        if any(kw in combined_lower for kw in ticket_keywords):
                            should_notify = True
                            
                        # 5. 重要イベント
                        important_keywords = ["ワンマン", "生誕", "卒業", "解散", "デビュー", "重要"]
                        if any(kw in combined_lower for kw in important_keywords):
                            should_notify = True
                            
                    if should_notify:
                        print(f"📩 LINE通知送信: {ev['title']} ({ev['date']}) / source={source_val}")
                        line_client.send_line_push_notification(ev)
                    else:
                        print(f"⏭️ LINE通知スキップ（即時通知OFFかつ例外条件非該当）: {ev['title']} ({ev['date']})")
                        
                    new_notified += 1
                else:
                    print(f"🔕 重複または既存イベントのためLINE通知なし: {ev['title']} ({ev['date']}) / source={source_val}")
                
                # APIレート制限の回避ウェイト
                time.sleep(1.5)
            else:
                print(f"⏭️ 重複イベントのためスキップ: {ev['title']} ({ev['date']}) / source={source_val}")
                print(f"🔕 重複または既存イベントのためLINE通知なし: {ev['title']} ({ev['date']}) / source={source_val}")
                
    return total_scraped, new_notified


def is_niigata_event_refined(ev: dict) -> bool:
    """
    新潟開催判定の強化版。人名「長岡」による誤爆を防ぎつつ、
    会場・住所・場所行などの地域ワードから判定する。
    """
    import re
    from scraper.utils import determine_area
    
    title = ev.get("title", "") or ""
    raw_text = ev.get("raw_text", "") or ""
    venue = ev.get("venue", "") or ""
    performers = ev.get("performers", "") or ""
    address = ev.get("address", "") or ""
    location = ev.get("location", "") or ""
    
    title_lower = title.lower()
    venue_lower = venue.lower()
    
    # === 新潟一般イベント他県除外ルール ===
    # 47都道府県から新潟県を除いた46都道府県のリスト
    other_prefectures = [
        "北海道", "青森", "岩手", "宮城", "秋田", "山形", "福島", 
        "茨城", "栃木", "群馬", "埼玉", "千葉", "東京", "神奈川", 
        "富山", "石川", "福井", "山梨", "長野", "岐阜", "静岡", 
        "愛知", "三重", "滋賀", "京都", "大阪", "兵庫", "奈良", 
        "和歌山", "鳥取", "島根", "岡山", "広島", "山口", 
        "徳島", "香川", "愛媛", "高知", "福岡", "佐賀", "長崎", 
        "熊本", "大分", "宮崎", "鹿児島", "沖縄"
    ]
    # 他県の主要都市/スポット名（さらに除外を確実にするため）
    other_cities = [
        "渋谷", "新宿", "池袋", "秋葉原", "品川", "上野", "六本木", "原宿", 
        "横浜", "川崎", "幕張", "大宮", "梅田", "難波", "心斎橋", "なんば", 
        "名古屋", "栄", "博多", "天神"
    ]
    other_locations = other_prefectures + other_cities
    
    # 新潟の地域ワードが含まれる安全な会場情報がある場合は、他県ツアーの記載による誤除外を防ぐために除外ルールをスキップする
    region_kws_venue = ["新潟", "万代", "古町", "柳都", "亀田", "新潟駅", "ラブラ", "lots", "アオーレ", "長岡"]
    is_explicit_niigata_venue = any(kw in venue_lower for kw in region_kws_venue)
    
    if not is_explicit_niigata_venue:
        # A. タイトル内の明確な「他県大会」「他県公演」などを検出
        for pref in other_locations:
            if pref in title_lower:
                if re.search(rf"{pref}(?:県|府|都)?(?:公演|大会|ツアー|フェス|ライブ|ワンマン|gig|ギグ|シリーズ|遠征)", title_lower):
                    print(f"⏭️ 他県タイトルパターンのため除外: {title} (検知: {pref})")
                    return False
                if re.search(rf"\b(?:in|at)\s*{pref}", title_lower):
                    print(f"⏭️ 他県(in/at)表記のため除外: {title} (検知: {pref})")
                    return False

        # B. venue, address, location フィールドのチェック
        for pref in other_locations:
            pref_pat = rf"{pref}(?:県|府|都)?"
            if venue and re.search(pref_pat, venue_lower):
                print(f"⏭️ 他県会場名のため除外: {title} (会場: {venue})")
                return False
            if address and re.search(pref_pat, address.lower()):
                print(f"⏭️ 他県住所のため除外: {title} (住所: {address})")
                return False
            if location and re.search(pref_pat, location.lower()):
                print(f"⏭️ 他県開催地のため除外: {title} (開催地: {location})")
                return False

        # C. 本文中の場所指定行のチェック
        lines = raw_text.split("\n")
        for line in lines:
            line_lower = line.lower().strip()
            # 出演者行やキャスト行はスルー
            if any(w in line_lower for w in ["出演", "cast", "キャスト", "ゲスト", "メンバー", "出演者", "performer"]):
                continue
            
            # 場所関連キーが含まれる行
            if any(w in line_lower for w in ["会場", "場所", "住所", "開催地", "place", "location", "address", "@", "＠"]):
                for pref in other_locations:
                    pref_pat = rf"{pref}(?:県|府|都)?"
                    if re.search(pref_pat, line_lower):
                        print(f"⏭️ 本文場所行に他県検知のため除外: {title} (行: {line_lower})")
                        return False
                        
    combined_text = f"{title} {raw_text}"
    
    # 1. determine_area による初期判定
    area_determined = determine_area(combined_text)
    
    # 2. 会場・ロケーション情報の精査
    # 出演者名によらない安全な新潟地域ワード
    region_kws = ["新潟", "万代", "古町", "柳都", "亀田", "新潟駅", "ラブラ", "cocolo"]
    longoka_kws = ["長岡市", "長岡駅", "長岡リリック", "長岡市内", "長岡インター", "長岡アオーレ", "アオーレ長岡"]
    
    has_safe_location = False
    
    # A. venueフィールドのチェック
    venue_lower = venue.lower()
    if venue_lower:
        if any(kw in venue_lower for kw in region_kws):
            has_safe_location = True
        if any(kw in venue_lower for kw in longoka_kws) or "長岡" in venue_lower:
            has_safe_location = True
            
    # B. タイトル内の明確な場所表現のチェック
    title_lower = title.lower()
    if any(tok in title_lower for tok in ["東京", "渋谷", "新宿", "池袋", "秋葉原", "大阪", "名古屋"]) and not any(kw in title_lower for kw in ["新潟駅", "万代シテイ", "古町ルフル", "新潟lots", "新潟県民会館"]):
        # 「東京遠征」などのタイトルかつ明確な新潟会場名がない場合は除外
        pass
    else:
        if any(kw in title_lower for kw in region_kws):
            has_safe_location = True
        if any(kw in title_lower for kw in longoka_kws):
            has_safe_location = True
        if "長岡" in title_lower:
            # タイトルで地名として使われているか (市、駅、ホール、ライブ、lots等の文脈)
            if any(w in title_lower for w in ["市", "駅", "ホール", "ライブ", "フェス", "lots", "柳都", "万代"]):
                has_safe_location = True
            
    # C. 本文内の会場・住所・場所行のチェック (出演者行は除外)
    lines = raw_text.split("\n")
    for line in lines:
        line_lower = line.lower().strip()
        # 出演者名が含まれる行は場所判定からは除外
        if any(w in line_lower for w in ["出演", "cast", "キャスト", "ゲスト", "メンバー", "出演者", "performer"]):
            continue
        if any(w in line_lower for w in ["会場", "場所", "place", "＠", "@", "開催地", "住所", "アクセス"]):
            # 他地域の明示的な記載がある場合はスキップ
            if any(tok in line_lower for tok in ["東京", "渋谷", "新宿", "池袋", "大阪", "名古屋"]):
                continue
            if any(kw in line_lower for kw in region_kws):
                has_safe_location = True
                break
            if any(kw in line_lower for kw in longoka_kws) or "長岡" in line_lower:
                has_safe_location = True
                break

    # 3. 判定ロジックの統合
    # 出演者名（performers）や、出演者行に「長岡」が含まれる場合
    # (raw_textの出演者リスト内に「長岡」がある場合を含む)
    has_nagaoka_performer = False
    if "長岡" in performers.lower():
        has_nagaoka_performer = True
    else:
        # 本文中の出演者行に「長岡」が含まれるかチェック
        for line in lines:
            line_lower = line.lower().strip()
            if any(w in line_lower for w in ["出演", "cast", "キャスト", "ゲスト", "メンバー", "出演者", "performer"]):
                if "長岡" in line_lower:
                    has_nagaoka_performer = True
                    break

    if has_nagaoka_performer:
        # 「長岡」という出演者がいる場合は、determine_area や大雑把な判定は信頼せず、
        # venue や住所行に明確な新潟の地名表現がある場合のみOKとする
        return has_safe_location

    if area_determined == "新潟":
        return True
        
    return has_safe_location

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
    新潟エリアの一般アイドルイベント収集 (LINE即時通知・カレンダー同期あり)
    戻り値: (検出総数, 新規保存数)
    """
    if not getattr(config, "ENABLE_NIIGATA_AREA_COLLECTION", False):
        print("\n==================================================")
        print("⏭️ 新潟地域イベント収集は無効化されています。")
        print("==================================================")
        return 0, 0
        
    print("\n==================================================")
    print("🌾 新潟地域イベントの一般収集を開始します")
    print("==================================================")
    
    state_id = getattr(config, "NIIGATA_TIGET_STATE_ID", 15)
    from scraper.tiget import scrape_tiget_by_state
    
    general_events = []
    
    # 1. TIGET 県別検索 (新潟県: state_id=15)
    try:
        tiget_evs = scrape_tiget_by_state(state_id)
        for ev in tiget_evs:
            ev["source"] = "Niigata TIGET"
        general_events.extend(tiget_evs)
    except Exception as e:
        print(f"🚨 新潟地域TIGET一般取得エラー: {str(e)}")
        
    # 2. LivePocket & TicketDive の新潟キーワード検索 (有効化されている場合)
    if getattr(config, "ENABLE_NIIGATA_GENERAL_IDOL_COLLECTION", False):
        # アクセス制限と速度低下を避けるため、主要な地域ワードに絞る
        search_keywords = ["新潟", "万代", "古町", "柳都", "長岡"]
        
        # LivePocket キーワード検索
        if config.ENABLE_LIVEPOCKET_SCRAPING:
            from scraper.livepocket import scrape_livepocket_events
            for kw in search_keywords:
                try:
                    lp_evs = scrape_livepocket_events(kw)
                    for ev in lp_evs:
                        ev["source"] = "Niigata LivePocket"
                    general_events.extend(lp_evs)
                except Exception as e:
                    print(f"🚨 LivePocket一般検索エラー ({kw}): {e}")
                    
        # TicketDive キーワード検索
        if config.ENABLE_TICKETDIVE_SCRAPING:
            from scraper.ticketdive import scrape_ticketdive_events
            for kw in search_keywords:
                try:
                    td_evs = scrape_ticketdive_events(kw)
                    for ev in td_evs:
                        ev["source"] = "Niigata TicketDive"
                    general_events.extend(td_evs)
                except Exception as e:
                    print(f"🚨 TicketDive一般検索エラー ({kw}): {e}")
                    
    total_scraped = len(general_events)
    new_saved = 0
    
    # セッション内での重複排除
    unique_events = []
    seen_urls = set()
    from scraper.utils import normalize_event_url
    for ev in general_events:
        url = ev.get("url", "")
        norm_url = normalize_event_url(url)
        ev["url"] = norm_url
        if norm_url in seen_urls:
            continue
        seen_urls.add(norm_url)
        unique_events.append(ev)
        
    # フィルタ用のキーワード定義
    region_kws = [kw.lower() for kw in getattr(config, "NIIGATA_GENERAL_REGION_KEYWORDS", [])]
    idol_kws = [kw.lower() for kw in getattr(config, "NIIGATA_GENERAL_IDOL_KEYWORDS", [])]
    
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
            
        combined_text = f"{ev.get('title', '')} {ev.get('raw_text', '')}"
        
        # 1. 新潟開催判定
        is_niigata = is_niigata_event_refined(ev)
        if not is_niigata:
            print(f"⏭️ 新潟以外のイベントのためスキップ: {ev['title']}")
            continue
            
        # 2. アイドル系イベント判定
        is_idol = any(kw in combined_text.lower() for kw in idol_kws)
        if not is_idol:
            print(f"⏭️ 非アイドルイベントのためスキップ: {ev['title']}")
            continue
            
        # エリアを強制的に "新潟" に設定
        ev["area"] = "新潟"
        
        # 出演者の動的判定
        from scraper.utils import determine_performers
        ev["performers"] = determine_performers(combined_text, ev.get("performers", "新潟アイドル"))
        
        # データベース保存を試みる (重複時は False が返る)
        is_new = db_manager.insert_event(ev)
        source_val = ev.get("source") or "Unknown"
        
        if is_new:
            print(f"✅ 新規新潟一般イベント登録: {ev['title']} ({ev['date']}) / source={source_val}")
            
            # 重複排除チェック（新潟エリア含めすべての地域で共通実行）
            from db_manager import is_duplicate_by_dedupe_key
            if not is_duplicate_by_dedupe_key(ev):
                # 新潟一般ソースの場合は自動同期をスキップ、それ以外は同期
                from scraper.utils import is_niigata_general_source
                if not is_niigata_general_source(source_val):
                    from calendar_client import add_to_google_calendar
                    add_to_google_calendar(ev)
                else:
                    print(f"⏭️ Googleカレンダー自動登録スキップ（新潟一般）: {ev['title']}")
                
                # LINEプッシュ通知（新潟開催は例外即時通知対象なので常に通知）
                print(f"📩 LINE通知送信: {ev['title']} ({ev['date']}) / source={source_val}")
                line_client.send_line_push_notification(ev)
                
                new_saved += 1
            else:
                print(f"🔕 重複または既存イベントのためLINE通知なし: {ev['title']} ({ev['date']}) / source={source_val}")
            
            # APIレート制限の回避ウェイト
            time.sleep(1.5)
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
