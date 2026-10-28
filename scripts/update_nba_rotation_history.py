"""Collect actual NBA minutes and team rotation changes in completed games.

Historical evidence only; does not estimate future minutes or player statistics.
"""
import csv
import datetime as dt
from collections import defaultdict
from pathlib import Path
import requests

OUT = Path("data/nba_rotation_history.csv")
FIELDS = ["DATE", "EVENT_ID", "TEAM_ID", "PLAYER_ID", "PLAYER", "MINUTES",
          "STARTER", "PLAYED", "TEAM_MINUTES", "TEAM_PLAYERS_RECORDED"]
S = requests.Session()
S.headers["User-Agent"] = "PropPlus-Research/1.0"

def get(url, params):
    try:
        r = S.get(url, params=params, timeout=18)
        r.raise_for_status()
        return r.json()
    except (requests.RequestException, ValueError) as e:
        print(f"WARNING NBA rotation fetch: {e}")
        return {}

def minutes(raw):
    try:
        if ":" in str(raw):
            a, b = str(raw).split(":", 1)
            return round(int(a) + int(b) / 60, 2)
        return round(float(raw), 2)
    except (ValueError, TypeError):
        return None

def main():
    old = {}
    if OUT.exists():
        with OUT.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                old[(row["EVENT_ID"], row["TEAM_ID"], row["PLAYER_ID"])] = row
    root = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
    today = dt.datetime.now(dt.timezone.utc).date()
    events = {}
    for offset in range(15):
        date = today - dt.timedelta(days=offset)
        data = get(root + "/scoreboard", {"dates": date.strftime("%Y%m%d"), "limit": 100})
        for e in data.get("events", []):
            if e.get("id") and e.get("status", {}).get("type", {}).get("completed"):
                events[str(e["id"])] = e.get("date", "")[:10]
    known = {key[0] for key in old}
    added = 0
    for event_id, date in sorted(events.items(), key=lambda x: x[1], reverse=True):
        if event_id in known:
            continue
        data = get(root + "/summary", {"event": event_id})
        team_rows = defaultdict(list)
        for group in data.get("boxscore", {}).get("players", []):
            team_id = str(group.get("team", {}).get("id", ""))
            for section in group.get("statistics", []):
                labels = [str(x).upper() for x in section.get("labels", [])]
                idx = next((i for i, x in enumerate(labels) if x in ("MIN", "MINUTES")), None)
                if idx is None:
                    continue
                for entry in section.get("athletes", []):
                    athlete = entry.get("athlete") or {}
                    pid = str(athlete.get("id", ""))
                    stats = entry.get("stats") or []
                    if not pid or idx >= len(stats) or entry.get("didNotPlay") is True:
                        continue
                    value = minutes(stats[idx])
                    if value is None:
                        continue
                    team_rows[team_id].append({
                        "DATE": date, "EVENT_ID": event_id, "TEAM_ID": team_id,
                        "PLAYER_ID": pid, "PLAYER": athlete.get("displayName", ""),
                        "MINUTES": value, "STARTER": "1" if entry.get("starter") is True else "0",
                        "PLAYED": "1",
                    })
        for team_id, rows in team_rows.items():
            total = round(sum(float(x["MINUTES"]) for x in rows), 2)
            for row in rows:
                row["TEAM_MINUTES"] = total
                row["TEAM_PLAYERS_RECORDED"] = len(rows)
                old[(event_id, team_id, row["PLAYER_ID"])] = row
                added += 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(sorted(old.values(), key=lambda r: (r["DATE"], r["EVENT_ID"], r["TEAM_ID"], r["PLAYER_ID"])))
    print(f"NBA historical rotation: {len(old)} player-game records, {added} new; {len(events)} recent completed games examined")

if __name__ == "__main__":
    main()
