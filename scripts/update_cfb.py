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
        vals={}
        for item in entry.get("statistics",[]):
            value=item.get("displayValue")
            for key in (item.get("name"),item.get("label"),item.get("abbreviation")):
                if key: vals[str(key).lower().replace(" ","").replace("-","")]=value
        def numeric(*keys):
            for key in keys:
                try:
                    v=vals.get(key.lower().replace(" ","").replace("-",""))
                    if v is not None:return float(str(v).replace(",",""))
                except (ValueError,TypeError):pass
            return None
        plays=numeric("totalPlays","plays","totalOffensivePlays","offensivePlays")
        if plays is None:
            rush=numeric("rushingAttempts","rushAttempts","rushingAtt","rushAtt","Rushing Attempts")
            pas=numeric("passingAttempts","passAttempts","passingAtt","passAtt","Passing Attempts")
            if rush is not None and pas is not None:plays=rush+pas
        # ESPN frequently supplies the combined attempts as a string
        # such as "21-35" under completionAttempts.
        if plays is None:
            rush=numeric("rushingAttempts","rushAttempts","rushingAtt","rushAtt")
            comp=vals.get("completionattempts") or vals.get("completionsattempts")
            if rush is not None and comp and ("/" in str(comp) or "-" in str(comp)):
                try:
                    attempts=float(str(comp).replace("-", "/").split("/")[-1].strip())
                    if attempts >= 0: plays=rush+attempts
                except ValueError:pass
        found[tid]=plays
    return found, list(entries[0].get("statistics",[]))[:15] if entries else []
def write(name,rows,fields):
    with (OUT/name).open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
def main():
    history=[]; future=[]; seen=set(); missing=0; diagnostics=[]
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
                plays,sample=stats(eid)
                try: ap=float(away["score"]);hp=float(home["score"])
                except (KeyError,ValueError,TypeError):continue
                pa=plays.get(pair["AWAY_ID"]);ph=plays.get(pair["HOME_ID"])
                if not pa or not ph or pa<25 or ph<25:
                    missing+=1
                    if len(diagnostics)<3:diagnostics.append({"event_id":eid,"teams":[pair["AWAY"],pair["HOME"]],"plays":plays,"sample_statistics":sample})
                    continue
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
        projections.append({"DATE":g["DATE"],"AWAY":g["AWAY"],"HOME":g["HOME"],"AWAY_PROJ":round(away,1),"HOME_PROJ":round(home,1),"PROJECTED_TOTAL":round(away+home,1),"AWAY_GP":a["games"],"HOME_GP":h["games"],"AWAY_ID":g["AWAY_ID"],"HOME_ID":g["HOME_ID"]})
    fields=["DATE","AWAY","HOME","AWAY_PROJ","HOME_PROJ","PROJECTED_TOTAL","AWAY_GP","HOME_GP","AWAY_ID","HOME_ID"]
    write("cfb_projections.csv",projections,fields)
    (OUT/"cfb_metadata.json").write_text(json.dumps({"season":YEAR,"completed_games_with_verified_plays":len(history),"excluded_games_missing_plays":missing,"upcoming_projected_games":len(projections),"method":"Blend offensive points/play and opposing defensive points allowed/play; multiply by offensive plays/game","source":"ESPN public college football scoreboard and game summary","generated_at":now.isoformat()},indent=2)+"\n")
    print(f"CFB: {len(history)} verified completed games, {missing} missing-play games excluded, {len(projections)} upcoming projections")
    if diagnostics:print("CFB ESPN statistic diagnostics:",json.dumps(diagnostics,default=str)[:9000])
    if not history:raise RuntimeError("No verified completed games: check ESPN data fields")
if __name__=="__main__":main()
