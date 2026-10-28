"""Incrementally collect verified player participation from ESPN final box scores.

Only explicit DNP designations are used for absences; missing box-score rows
are never interpreted as DNP. The dataset is an evidence cache, not a roster.
"""
import csv,datetime as dt,requests
from pathlib import Path
OUT=Path("data/player_game_logs.csv")
FIELDS=["SPORT","TEAM_ID","PLAYER_ID","PLAYER","DATE","PLAYED","POINTS","TEAM_POINTS"]
SPORTS={"nba":("basketball","nba",45),"nfl":("football","nfl",100),"cfb":("football","college-football",100)}
SESSION=requests.Session()
SESSION.headers["User-Agent"]="PropPlus-Research/1.0"

def fetch(url,params=None):
    try:
        r=SESSION.get(url,params=params,timeout=12)
        r.raise_for_status()
        return r.json()
    except (requests.RequestException,ValueError):return {}

def main():
    OUT.parent.mkdir(exist_ok=True)
    old={}
    if OUT.exists():
        with OUT.open(newline="",encoding="utf-8") as f:
            for r in csv.DictReader(f):
                old[(r["SPORT"],r["TEAM_ID"],r["PLAYER_ID"],r["DATE"])]=r
    now=dt.datetime.now(dt.timezone.utc).date()
    additions=0
    for sport,(category,league,lookback) in SPORTS.items():
        root=f"https://site.api.espn.com/apis/site/v2/sports/{category}/{league}"
        events={}
        # Only recently completed games; old rows persist indefinitely.
        for offset in range(lookback):
            day=now-dt.timedelta(days=offset)
            data=fetch(root+"/scoreboard",{"dates":day.strftime("%Y%m%d"),"limit":200})
            for e in data.get("events",[]):
                if e.get("status",{}).get("type",{}).get("completed") and e.get("id"):
                    events[str(e["id"])]=(e.get("date","")[:10],e)
        for event_id,(day,event) in events.items():
            # Avoid repeated box-score fetches once this event has been recorded.
            # Some games have no explicit DNP information and are retried later.
            if any(r.get("EVENT_ID")==event_id for r in old.values()):continue
            payload=fetch(root+"/summary",{"event":event_id})
            box=payload.get("boxscore",{})
            competitors=(event.get("competitions") or [{}])[0].get("competitors",[])
            totals={str(c.get("team",{}).get("id")):c.get("score") for c in competitors}
            for group in box.get("players",[]):
                team_id=str(group.get("team",{}).get("id") or "")
                try:team_points=float(totals[team_id])
                except (KeyError,ValueError,TypeError):continue
                for statgroup in group.get("statistics",[]):
                    labels=[str(x).lower() for x in statgroup.get("labels",[])]
                    pts_index=next((i for i,x in enumerate(labels) if x in ("pts","points")),None)
                    for athlete in statgroup.get("athletes",[]):
                        player=athlete.get("athlete") or {}
                        pid=str(player.get("id") or "")
                        if not pid:continue
                        # A boxscore listing alone does not prove participation.
                        explicit_dnp=athlete.get("didNotPlay") is True
                        stats=athlete.get("stats") or []
                        played=not explicit_dnp and bool(stats)
                        if not (explicit_dnp or played):continue
                        points=""
                        if played and pts_index is not None and len(stats)>pts_index:
                            try:points=float(stats[pts_index])
                            except (ValueError,TypeError):pass
                        row={"SPORT":sport,"TEAM_ID":team_id,"PLAYER_ID":pid,
                             "PLAYER":player.get("displayName",""),"DATE":day,
                             "PLAYED":"1" if played else "0","POINTS":points,
                             "TEAM_POINTS":team_points,"EVENT_ID":event_id}
                        old[(sport,team_id,pid,day)]=row
                        additions+=1
    fields=FIELDS+["EVENT_ID"]
    with OUT.open("w",newline="",encoding="utf-8") as f:
        writer=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore")
        writer.writeheader()
        writer.writerows(sorted(old.values(),key=lambda r:(r["DATE"],r["SPORT"],r["TEAM_ID"],r["PLAYER_ID"])))
    print(f"Player participation: {len(old)} records; {additions} new records")

if __name__=="__main__":main()
