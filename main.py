import time
import sys
import io

# Windowsコンソールでの絵文字表示による UnicodeEncodeError (cp932) 回避用
if sys.platform.startswith('win'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

import config
import db_manager
import line_client
from scraper.utils import clean_text
from scraper.tiget import scrape_tiget_events
from scraper.livepocket import scrape_livepocket_events
from scraper.ticketdive import scrape_ticketdive_events
from scraper.x_scraper import fetch_tweets_via_rss

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
        
        # チケットサイト用の検索クエリの決定 (search_queriesが未設定の場合はnameを使う)
        search_words = idol.get("search_queries", [name])
        
        for word in search_words:
            # --- TIGET スクレイピング ---
            if config.ENABLE_TIGET_SCRAPING:
                try:
                    tiget = scrape_tiget_events(word)
                    # 出演者名を統一
                    for ev in tiget:
                        ev["performers"] = name
                    idol_events.extend(tiget)
                except Exception as e:
                    print(f"🚨 TIGET取得中にエラー: {str(e)}")
                    
            # --- LivePocket スクレイピング ---
            if config.ENABLE_LIVEPOCKET_SCRAPING:
                try:
                    lp = scrape_livepocket_events(word)
                    # 出演者名を統一
                    for ev in lp:
                        ev["performers"] = name
                    idol_events.extend(lp)
                except Exception as e:
                    print(f"🚨 LivePocket取得中にエラー: {str(e)}")
                    
            # --- TicketDive スクレイピング ---
            if config.ENABLE_TICKETDIVE_SCRAPING:
                try:
                    td = scrape_ticketdive_events(word)
                    # 出演者名を統一
                    for ev in td:
                        ev["performers"] = name
                    idol_events.extend(td)
                except Exception as e:
                    print(f"🚨 TicketDive取得中にエラー: {str(e)}")
                    
        # --- X RSS スクレイピング ---
        if config.ENABLE_X_SCRAPING and x_id:
            try:
                x_evs = fetch_tweets_via_rss(x_id)
                # 出演者名を統一
                for ev in x_evs:
                    ev["performers"] = name
                idol_events.extend(x_evs)
            except Exception as e:
                print(f"🚨 X(RSS)取得中にエラー: {str(e)}")
                
        total_scraped += len(idol_events)
        
        # セッション内での重複排除
        unique_idol_events = []
        seen_urls = set()
        for ev in idol_events:
            url = ev.get("url", "")
            if url not in seen_urls:
                seen_urls.add(url)
                unique_idol_events.append(ev)
                
        # データベース保存 ＆ 新着プッシュ通知
        for ev in unique_idol_events:
            # データベースへの保存を試みる
            is_new = db_manager.insert_event(ev)
            
            if is_new:
                print(f"🆕 本命マーク新着検知: {ev['title']} ({ev['date']})")
                # 自動プッシュ通知は行わない（手動クエリのみのためコメントアウト）
                # line_client.send_line_push_notification(ev)
                new_notified += 1
                
                # APIレート制限の回避ウェイト
                time.sleep(1.5)
            else:
                print(f"⏭️ 既知（通知スキップ）: {ev['title']} ({ev['date']})")
                
    return total_scraped, new_notified

def run_general_keywords_collection() -> tuple:
    """
    エリア一般イベントの巡回とサイレントDB蓄積の実行
    戻り値: (検出総数, 新規保存数)
    """
    print("\n==================================================")
    print("🔍 モード2: エリア一般（新潟・東京等）イベントの巡回を開始します")
    print("   ※新着通知はされず、対話での引き出し用にDBへ保存されます")
    print("==================================================")
    
    total_scraped = 0
    new_saved = 0
    
    for kw in config.GENERAL_SEARCH_KEYWORDS:
        print(f"\n🔍 検索キーワード: '{kw}'")
        print(f"──────────────────────────────────────────────────")
        
        general_events = []
        
        # --- TIGET スクレイピング ---
        if config.ENABLE_TIGET_SCRAPING:
            try:
                tiget = scrape_tiget_events(kw)
                general_events.extend(tiget)
            except Exception as e:
                print(f"🚨 TIGET取得中にエラー: {str(e)}")
                
        # --- LivePocket スクレイピング ---
        if config.ENABLE_LIVEPOCKET_SCRAPING:
            try:
                lp = scrape_livepocket_events(kw)
                general_events.extend(lp)
            except Exception as e:
                print(f"🚨 LivePocket取得中にエラー: {str(e)}")
                
        # --- TicketDive スクレイピング ---
        if config.ENABLE_TICKETDIVE_SCRAPING:
            try:
                td = scrape_ticketdive_events(kw)
                general_events.extend(td)
            except Exception as e:
                print(f"🚨 TicketDive取得中にエラー: {str(e)}")
                
        total_scraped += len(general_events)
        
        # セッション内での重複排除
        unique_gen_events = []
        seen_urls = set()
        for ev in general_events:
            url = ev.get("url", "")
            if url not in seen_urls:
                seen_urls.add(url)
                unique_gen_events.append(ev)
                
        # データベース保存 (LINE Notify 通知は行わない)
        for ev in unique_gen_events:
            # 検索キーワードが performers に入っているので、少し分かりやすく整形
            ev["performers"] = f"合同/イベント ({kw})"
            
            is_new = db_manager.insert_event(ev)
            if is_new:
                print(f"💾 一般イベント新規蓄積: {ev['title']} ({ev['date']} | {ev['area']})")
                new_saved += 1
            else:
                pass # 一般の重複はログを省略してスッキリさせる
                
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
    
    # モード2: エリア一般の巡回 (通知なし、DB保存のみ)
    gen_total, gen_new = run_general_keywords_collection()
    
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
