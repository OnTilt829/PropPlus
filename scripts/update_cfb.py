#!/usr/bin/env python3
"""College football points-per-play analytics using ESPN public game summaries.
Incomplete games or missing plays are excluded, never converted to zero.
"""
import csv, datetime as dt, json, os, time
from collections import defaultdict
from pathlib import Path
import requests

YEAR=int(os.getenv("CFB_SEASON",dt.date.today().year))
BASE="https://site.api.espn.com/apis/site/v2/sports/football/college-football"
OUT=Path("data"); OUT.mkdir(exist_ok=True)
S=requests.Session(); S.headers["User-Agent"]="PropPlus-CFB-Analytics/1.0"
def get(path,params):
    for attempt in range(3):
        try:
            r=S.get(BASE+path,params=params,timeout=22);r.raise_for_status();return r.json()
        except requests.RequestException:
            if attempt==2: return {}
            time.sleep(2*(attempt+1))
def teams(event):
    c=event.get("competitions",[{}])[0]
    return c.get("competitors",[])
def stats(event_id):
    data=get("/summary",{"event":event_id})
    entries=data.get("boxscore",{}).get("teams",[])
    found={}
    for entry in entries:
        tid=str(entry.get("team",{}).get("id",""))
        vals={x.get("name"):x.get("displayValue") for x in entry.get("statistics",[])}
        def numeric(k):
            try:return float(str(vals.get(k,"")).replace(",",""))
            except (ValueError,TypeError):return None
        plays=numeric("totalPlays")
        if plays is None:
            rush=numeric("rushingAttempts");pas=numeric("passingAttempts")
            if rush is not None and pas is not None:plays=rush+pas
        found[tid]=plays
    return found
def write(name,rows,fields):
    with (OUT/name).open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
def main():
    history=[]; future=[]; seen=set(); missing=0
    now=dt.datetime.now(dt.timezone.utc)
    for week in range(1,18):
        payload=get("/scoreboard",{"dates":YEAR,"week":week,"seasontype":2,"groups":80,"limit":500})
        for e in payload.get("events",[]):
            eid=e.get("id")
            if not eid or eid in seen:continue
            seen.add(eid)
            c=teams(e)
            if len(c)!=2:continue
            home=next((x for x in c if x.get("homeAway")=="home"),None)
            away=next((x for x in c if x.get("homeAway")=="away"),None)
            if not home or not away:continue
            # Restrict to FBS-vs-FBS matchups.
            if any(x.get("team",{}).get("isActive") is False for x in (home,away)):continue
            date=e.get("date","")[:10]
            status=e.get("status",{}).get("type",{}).get("name","")
            pair={"DATE":date,"AWAY":away["team"].get("displayName",""),"HOME":home["team"].get("displayName",""),"AWAY_ID":str(away["team"].get("id","")),"HOME_ID":str(home["team"].get("id",""))}
            if status=="STATUS_FINAL":
                plays=stats(eid)
                try: ap=float(away["score"]);hp=float(home["score"])
                except (KeyError,ValueError,TypeError):continue
                pa=plays.get(pair["AWAY_ID"]);ph=plays.get(pair["HOME_ID"])
                if not pa or not ph or pa<25 or ph<25:
                    missing+=1;continue
                history.append({**pair,"AWAY_PTS":ap,"HOME_PTS":hp,"AWAY_PLAYS":pa,"HOME_PLAYS":ph})
            elif date>=now.date().isoformat():
                future.append(pair)
    # Use verified FBS teams appearing in completed FBS scoreboard games.
    teamlog=defaultdict(lambda:{"points":0.,"plays":0.,"allowed":0.,"defplays":0.,"games":0})
    for g in history:
        a=teamlog[g["AWAY_ID"]];h=teamlog[g["HOME_ID"]]
        a["points"]+=g["AWAY_PTS"];a["plays"]+=g["AWAY_PLAYS"];a["allowed"]+=g["HOME_PTS"];a["defplays"]+=g["HOME_PLAYS"];a["games"]+=1
        h["points"]+=g["HOME_PTS"];h["plays"]+=g["HOME_PLAYS"];h["allowed"]+=g["AWAY_PTS"];h["defplays"]+=g["AWAY_PLAYS"];h["games"]+=1
    projections=[]
    for g in sorted(future,key=lambda x:x["DATE"]):
        a=teamlog.get(g["AWAY_ID"]);h=teamlog.get(g["HOME_ID"])
        if not a or not h or min(a["games"],h["games"])<3:continue
        # Original model: blended offense/defense points per play times offense plays/game.
        away=((a["points"]/a["plays"]+h["allowed"]/h["defplays"])/2)*(a["plays"]/a["games"])
        home=((h["points"]/h["plays"]+a["allowed"]/a["defplays"])/2)*(h["plays"]/h["games"])
        projections.append({"DATE":g["DATE"],"AWAY":g["AWAY"],"HOME":g["HOME"],"AWAY_PROJ":round(away,1),"HOME_PROJ":round(home,1),"PROJECTED_TOTAL":round(away+home,1),"AWAY_GP":a["games"],"HOME_GP":h["games"]})
    fields=["DATE","AWAY","HOME","AWAY_PROJ","HOME_PROJ","PROJECTED_TOTAL","AWAY_GP","HOME_GP"]
    write("cfb_projections.csv",projections,fields)
    (OUT/"cfb_metadata.json").write_text(json.dumps({"season":YEAR,"completed_games_with_verified_plays":len(history),"excluded_games_missing_plays":missing,"upcoming_projected_games":len(projections),"method":"Blend offensive points/play and opposing defensive points allowed/play; multiply by offensive plays/game","source":"ESPN public college football scoreboard and game summary","generated_at":now.isoformat()},indent=2)+"\n")
    print(f"CFB: {len(history)} verified completed games, {missing} missing-play games excluded, {len(projections)} upcoming projections")
    if not history:raise RuntimeError("No verified completed games: check ESPN data fields")
if __name__=="__main__":main()
