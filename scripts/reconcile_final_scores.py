#!/usr/bin/env python3
"""Reconcile historical scoreboard finals without modifying projected values."""
import csv
import datetime as dt
import os
from pathlib import Path
import requests

ROOT = Path("data")
LEAGUES = {
    "cfb": ("football", "college-football", "cfb_projections.csv"),
    "nfl": ("football", "nfl", "nfl_game_scores.csv"),
}
NOW = dt.datetime.now(dt.timezone.utc)
SESSION = requests.Session()

def parse(value):
    try:
        return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(dt.timezone.utc)
    except (ValueError, TypeError, AttributeError):
        return None

def finals(category, league):
    url = f"https://site.api.espn.com/apis/site/v2/sports/{category}/{league}/scoreboard"
    results = {}
    errors = 0
    for offset in range(-21, 2):
        day = (NOW + dt.timedelta(days=offset)).strftime("%Y%m%d")
        try:
            response = SESSION.get(url, params={"dates": day, "limit": 500, **({"groups": 80} if league == "college-football" else {})}, timeout=18)
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            errors += 1
            print(f"WARNING {league} scoreboard {day}: {exc}")
            continue
        for event in payload.get("events", []):
            if not event.get("status", {}).get("type", {}).get("completed", False):
                continue
            sides = (event.get("competitions") or [{}])[0].get("competitors", [])
            home = next((x for x in sides if x.get("homeAway") == "home"), None)
            away = next((x for x in sides if x.get("homeAway") == "away"), None)
            if not home or not away:
                continue
            try:
                ids = (str(away["team"]["id"]), str(home["team"]["id"]))
                scores = (int(float(away["score"])), int(float(home["score"])))
            except (KeyError, ValueError, TypeError):
                continue
            when = parse(event.get("date"))
            if when:
                results[(str(event.get("id", "")), ids, when)] = scores
    if errors == 23:
        raise RuntimeError(f"All {league} scoreboard requests failed")
    return results

def reconcile(sport, category, league, filename):
    path = ROOT / filename
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open(newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        fields = reader.fieldnames
        rows = list(reader)
    if not fields or not rows:
        raise RuntimeError(f"Empty or invalid {path}")
    fetched = finals(category, league)
    updated = 0
    unmatched = []
    for row in rows:
        when = parse(row.get("KICKOFF_UTC"))
        if not when or when > NOW or row.get("STATUS") == "FINAL":
            continue
        ids = (row.get("AWAY_ID", ""), row.get("HOME_ID", ""))
        candidates = [(abs((event_time - when).total_seconds()), score)
                      for (_, event_ids, event_time), score in fetched.items()
                      if event_ids == ids and abs((event_time - when).total_seconds()) <= 72 * 3600]
        if candidates:
            score = min(candidates, key=lambda x: x[0])[1]
            row["AWAY_FINAL"], row["HOME_FINAL"] = score
            row["FINAL_TOTAL"] = sum(score)
            row["STATUS"] = "FINAL"
            updated += 1
        elif when < NOW - dt.timedelta(hours=36) and when > NOW - dt.timedelta(days=21):
            unmatched.append(f"{row.get('AWAY')} at {row.get('HOME')} ({when.date()})")
    if updated:
        tmp = path.with_suffix(".tmp")
        with tmp.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        os.replace(tmp, path)
    print(f"{sport}: {updated} newly matched finals; {len(unmatched)} older unmatched records; {len(fetched)} ESPN finals examined")
    for item in unmatched[:12]:
        print(f"WARNING unmatched {sport}: {item}")

if __name__ == "__main__":
    for sport, (category, league, filename) in LEAGUES.items():
        reconcile(sport, category, league, filename)
