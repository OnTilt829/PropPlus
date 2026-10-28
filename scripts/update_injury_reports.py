#!/usr/bin/env python3
"""Standalone informational injury report; not used in projections."""
import csv
import datetime as dt
import json
from pathlib import Path
import requests

LEAGUES={"nba":("basketball","nba"),"nfl":("football","nfl"),"cfb":("football","college-football")}
FIELDS=["SPORT","TEAM_ID","TEAM","PLAYER_ID","PLAYER","STATUS","DETAIL","REPORTED_AT","SOURCE"]
OUT=Path("data/injury_reports.csv")
HEALTH=Path("data/injury_sources.json")

def parse_report(sport,payload,url):
    if not isinstance(payload,dict) or not isinstance(payload.get("injuries"),list):
        raise ValueError("Unexpected league injury response")
    rows=[]
    for group in payload["injuries"]:
        team=group.get("team") or group
        entries=group.get("injuries") or ([group] if group.get("athlete") else [])
        if not isinstance(entries,list):continue
        for entry in entries:
            athlete=entry.get("athlete") or entry.get("player") or {}
            pid=str(athlete.get("id") or "")
            name=athlete.get("displayName") or athlete.get("fullName") or ""
            if not name:continue
            status=entry.get("status") or entry.get("type") or ""
            if isinstance(status,dict):status=status.get("name") or status.get("description") or ""
            kind=entry.get("type") or {}
            detail=entry.get("detail") or (kind.get("description") if isinstance(kind,dict) else "") or ""
            rows.append({"SPORT":sport,"TEAM_ID":str(team.get("id") or ""),
                         "TEAM":team.get("displayName") or team.get("name") or "",
                         "PLAYER_ID":pid,"PLAYER":name,"STATUS":str(status),
                         "DETAIL":str(detail),"REPORTED_AT":entry.get("date") or payload.get("timestamp") or "",
                         "SOURCE":url})
    return rows

def collect(session=requests):
    report=[];health={};stamp=dt.datetime.now(dt.timezone.utc).isoformat()
    for sport,(category,league) in LEAGUES.items():
        url=f"https://site.api.espn.com/apis/site/v2/sports/{category}/{league}/injuries"
        try:
            response=session.get(url,timeout=20)
            response.raise_for_status()
            payload=response.json()
            rows=parse_report(sport,payload,url)
            health[sport]={"state":"ok" if rows else "empty_unverified","records":len(rows),"checked_at":stamp,"source":url,"response_keys":sorted(payload.keys()),"groups":len(payload.get("injuries",[])),"first_group_keys":sorted(payload["injuries"][0].keys()) if payload.get("injuries") and isinstance(payload["injuries"][0],dict) else [], "first_entry_keys":sorted(payload["injuries"][0]["injuries"][0].keys()) if payload.get("injuries") and isinstance(payload["injuries"][0],dict) and isinstance(payload["injuries"][0].get("injuries"),list) and payload["injuries"][0]["injuries"] and isinstance(payload["injuries"][0]["injuries"][0],dict) else [], "first_entry_athlete_keys":sorted(payload["injuries"][0]["injuries"][0].get("athlete",{}).keys()) if payload.get("injuries") and isinstance(payload["injuries"][0],dict) and isinstance(payload["injuries"][0].get("injuries"),list) and payload["injuries"][0]["injuries"] and isinstance(payload["injuries"][0]["injuries"][0].get("athlete"),dict) else []}
            report.extend(rows)
        except (requests.RequestException,ValueError,TypeError,KeyError) as exc:
            health[sport]={"state":"unavailable","error":str(exc)[:200],"checked_at":stamp,"source":url}
    return report,health

def main():
    OUT.parent.mkdir(parents=True,exist_ok=True)
    rows,health=collect()
    # Preserve the most recent successful report if a league source fails.
    if OUT.exists():
        with OUT.open(newline="",encoding="utf-8") as stream:
            previous=list(csv.DictReader(stream))
        failed={sport for sport,h in health.items() if h["state"]!="ok"}
        rows.extend(r for r in previous if r.get("SPORT") in failed)
    rows.sort(key=lambda r:(r["SPORT"],r["TEAM"],r["PLAYER"]))
    with OUT.open("w",newline="",encoding="utf-8") as stream:
        writer=csv.DictWriter(stream,fieldnames=FIELDS)
        writer.writeheader();writer.writerows(rows)
    HEALTH.write_text(json.dumps(health,indent=2)+"\n",encoding="utf-8")
    for sport,h in health.items():print(f"{sport}: {h['state']} ({h.get('records','unknown')} records)")
    print("Report rows:",len(rows))

if __name__=="__main__":main()
