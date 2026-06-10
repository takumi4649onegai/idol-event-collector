import re
from scraper.utils import parse_time_and_venue
import config

def clean_event_title(title: str) -> str:
    """タイトルの表示用クリーンアップ"""
    if not title:
        return ""
    # 不要なプレフィックスを取り除く
    for prefix in ["【LivePocket】", "【TIGET】", "【TicketDive】", "【X告知】", "【HP告知】", "【Web検索】", "【TimeTree】", "【公式カレンダー】"]:
        title = title.replace(prefix, "")
    return title.strip()

def format_daily_schedule(events: list, target_date_str: str, header_prefix: str = "🌅 今日の推し活予定") -> str:
    """
    指定された日付のイベント一覧をグループ別・時間順に成形したテキストを作成する。
    """
    from datetime import datetime
    
    # 曜日表記の取得
    weekday_str = ""
    try:
        dt = datetime.strptime(target_date_str, "%Y-%m-%d")
        weeks = ["月", "火", "水", "木", "金", "土", "日"]
        weekday_str = f"({weeks[dt.weekday()]})"
        display_date = f"{dt.strftime('%m/%d')}{weekday_str}"
    except Exception:
        display_date = target_date_str

    # 1. 各イベントに対して、開始時間と会場を動的パースして格納
    parsed_events = []
    for ev in events:
        title = ev.get("title", "")
        raw_text = ev.get("raw_text", "") or ""
        area = ev.get("area", "その他")
        
        start_time, venue = parse_time_and_venue(title, raw_text, area)
        
        # ソート用の時間キー（時間がない場合は "23:59:59" にして最後に並べる）
        sort_time = start_time if (start_time and start_time != "00:00") else "23:59:59"
        
        parsed_events.append({
            "event": ev,
            "start_time": start_time,
            "venue": venue,
            "sort_time": sort_time,
            "performers": ev.get("performers", "")
        })

    # 2. グループごとに振り分け
    # Marking Idols の順序を維持する
    group_schedules = {}
    for idol in config.MARKING_IDOLS:
        group_schedules[idol["name"]] = []
        
    other_events = []
    
    for pev in parsed_events:
        matched = False
        performers_str = pev["performers"].lower().replace(" ", "")
        
        for idol in config.MARKING_IDOLS:
            name = idol["name"]
            # Performersフィールドにアイドル名が含まれるか、またはアイドル名のsearch_queriesが含まれるかチェック
            if name.lower().replace(" ", "") in performers_str or any(q.lower().replace(" ", "") in performers_str for q in idol.get("search_queries", [])):
                group_schedules[name].append(pev)
                matched = True
                
        if not matched:
            other_events.append(pev)

    # 3. 各グループのイベントを時間順にソートしてテキスト構築
    lines = [f"{header_prefix} ({display_date})", ""]
    
    # 本命グループの予定
    for idol in config.MARKING_IDOLS:
        name = idol["name"]
        pevs = group_schedules[name]
        lines.append(f"【{name}】")
        
        if not pevs:
            lines.append("予定なし")
            lines.append("")
            continue
            
        # 時間順ソート
        pevs.sort(key=lambda x: x["sort_time"])
        
        for pev in pevs:
            ev = pev["event"]
            time_str = pev["start_time"]
            time_display = time_str if (time_str and time_str != "00:00") else "終日/時間未定"
            
            clean_title = clean_event_title(ev["title"])
            lines.append(f"{time_display} {clean_title}")
            lines.append(f"会場/形式：{pev['venue']}")
            
            url = ev.get("url", "")
            if url and not url.startswith("local_id:"):
                lines.append(f"URL: {url}")
            
            from scraper.utils import is_niigata_general_source, generate_event_short_id
            if is_niigata_general_source(ev.get("source")):
                short_id = generate_event_short_id(url)
                if short_id:
                    lines.append(f"addcal {short_id}")
            lines.append("")

    # その他の予定 (本命以外)
    if other_events:
        lines.append("【その他】")
        other_events.sort(key=lambda x: x["sort_time"])
        
        for pev in other_events:
            ev = pev["event"]
            time_str = pev["start_time"]
            time_display = time_str if (time_str and time_str != "00:00") else "終日/時間未定"
            
            clean_title = clean_event_title(ev["title"])
            lines.append(f"{time_display} {clean_title}")
            lines.append(f"会場/形式：{pev['venue']}")
            
            url = ev.get("url", "")
            if url and not url.startswith("local_id:"):
                lines.append(f"URL: {url}")
            
            from scraper.utils import is_niigata_general_source, generate_event_short_id
            if is_niigata_general_source(ev.get("source")):
                short_id = generate_event_short_id(url)
                if short_id:
                    lines.append(f"addcal {short_id}")
            lines.append("")

    return "\n".join(lines).strip()
