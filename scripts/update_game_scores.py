#!/usr/bin/env python3
"""Independent matchup score projections from completed ESPN games."""
import csv,datetime as dt,json,requests
from collections import defaultdict
from pathlib import Path
OUT=Path("data");OUT.mkdir(exist_ok=True)
SPORTS={"nba":("basketball","nba"),"nfl":("football","nfl")}
def main():
 for sport,(category,league) in SPORTS.items():
  base=f"https://site.api.espn.com/apis/site/v2/sports/{category}/{league}/scoreboard"
  today=dt.datetime.now(dt.timezone.utc).date()
  season=today.year if sport=="nfl" else today.year
  stats=defaultdict(lambda:{"scored":0,"allowed":0,"games":0})
  upcoming={}
  # Fetch broad date windows with ESPN scoreboard limit; NBA uses rolling season window.
  start=today-dt.timedelta(days=130 if sport=="nba" else 100)
  end=today+dt.timedelta(days=12 if sport=="nba" else 15)
  for day in (start+dt.timedelta(days=i) for i in range((end-start).days+1)):
   try:
    payload=requests.get(base,params={"dates":day.strftime("%Y%m%d"),"limit":100},timeout=15).json()
   except (requests.RequestException,ValueError):continue
   for event in payload.get("events",[]):
    comp=(event.get("competitions") or [{}])[0]
    sides=comp.get("competitors",[])
    if len(sides)!=2:continue
    away=next((x for x in sides if x.get("homeAway")=="away"),None)
    home=next((x for x in sides if x.get("homeAway")=="home"),None)
    if not away or not home:continue
    aid=str(away.get("team",{}).get("id",""));hid=str(home.get("team",{}).get("id",""))
    if not aid or not hid:continue
    status=event.get("status",{}).get("type",{}).get("completed",False)
    if status:
     try:a=float(away["score"]);h=float(home["score"])
     except (KeyError,TypeError,ValueError):continue
     for tid,p,opp in ((aid,a,h),(hid,h,a)):
      stats[tid]["scored"]+=p;stats[tid]["allowed"]+=opp;stats[tid]["games"]+=1
    else:
     when=event.get("date","")
     try:scheduled=dt.datetime.fromisoformat(when.replace("Z","+00:00")).date()
     except ValueError:continue
     if today<=scheduled<=end:
      upcoming[event["id"]]=(when,away,home,aid,hid)
  rows=[]
  for when,away,home,aid,hid in sorted(upcoming.values()):
   a=stats[aid];h=stats[hid]
   if min(a["games"],h["games"])<1:continue
   ap=(a["scored"]/a["games"]+h["allowed"]/h["games"])/2
   hp=(h["scored"]/h["games"]+a["allowed"]/a["games"])/2
   rows.append([when,away["team"]["displayName"],home["team"]["displayName"],round(ap,1),round(hp,1),round(ap+hp,1),a["games"],h["games"],aid,hid])
  with (OUT/f"{sport}_game_scores.csv").open("w",newline="",encoding="utf-8") as file:
   writer=csv.writer(file);writer.writerow(["KICKOFF_UTC","AWAY","HOME","AWAY_PROJ","HOME_PROJ","PROJECTED_TOTAL","AWAY_GP","HOME_GP","AWAY_ID","HOME_ID"]);writer.writerows(rows)
  print(sport,len(rows),"projected matchups")
if __name__=="__main__":main()
