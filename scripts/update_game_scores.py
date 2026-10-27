#!/usr/bin/env python3
"""Independent matchup score projections from completed ESPN games."""
import csv,datetime as dt,json,requests
from collections import defaultdict
from pathlib import Path
OUT=Path("data");OUT.mkdir(exist_ok=True)
SPORTS={"nba":("basketball","nba"),"nfl":("football","nfl")}
def availability(category,league,team_id):
  url="https://site.api.espn.com/apis/site/v2/sports/{}/{}/teams/{}/injuries".format(category,league,team_id)
  try:
   response=requests.get(url,timeout=10);response.raise_for_status();payload=response.json()
  except (requests.RequestException,ValueError):return []
  entries=payload.get("injuries",[])
  if not isinstance(entries,list):return []
  found=[]
  for item in entries:
   athlete=item.get("athlete") or {}
   status=item.get("status") or item.get("type") or ""
   if isinstance(status,dict):status=status.get("name") or status.get("description") or ""
   name=athlete.get("displayName") or athlete.get("fullName") or ""
   if name and status:found.append({"player":name,"status":str(status),"source":url})
  return found

def main():
 for sport,(category,league) in SPORTS.items():
  base=f"https://site.api.espn.com/apis/site/v2/sports/{category}/{league}/scoreboard"
  now=dt.datetime.now(dt.timezone.utc)
  today=now.date()
  season=today.year if sport=="nfl" else today.year
  stats=defaultdict(lambda:{"scored":0,"allowed":0,"games":0})
  upcoming={}
  completed={}
  archive=OUT/f"{sport}_game_scores.csv"
  old={}
  if archive.exists():
   with archive.open(newline="",encoding="utf-8") as file:
    old={(r["KICKOFF_UTC"],r["AWAY_ID"],r["HOME_ID"]):r for r in csv.DictReader(file)}
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
     completed[(event.get("date",""),aid,hid)]=(int(a),int(h))
     for tid,p,opp in ((aid,a,h),(hid,h,a)):
      stats[tid]["scored"]+=p;stats[tid]["allowed"]+=opp;stats[tid]["games"]+=1
    else:
     when=event.get("date","")
     try:scheduled=dt.datetime.fromisoformat(when.replace("Z","+00:00")).date()
     except ValueError:continue
     if today<=scheduled<=end and dt.datetime.fromisoformat(when.replace("Z","+00:00"))>now:
      upcoming[event["id"]]=(when,away,home,aid,hid)
  injury_cache={}
  rows=[]
  for when,away,home,aid,hid in sorted(upcoming.values(), key=lambda game: (game[0], game[3], game[4])):
   a=stats[aid];h=stats[hid]
   if min(a["games"],h["games"])<1:continue
   ap=(a["scored"]/a["games"]+h["allowed"]/h["games"])/2
   hp=(h["scored"]/h["games"]+a["allowed"]/a["games"])/2
   for tid in (aid,hid):
    if tid not in injury_cache:injury_cache[tid]=availability(category,league,tid)
   notes=json.dumps({"away":injury_cache[aid],"home":injury_cache[hid]},separators=(",",":"))
   rows.append([when,away["team"]["displayName"],home["team"]["displayName"],round(ap,1),round(hp,1),round(ap+hp,1),a["games"],h["games"],aid,hid,notes])
  fields=["KICKOFF_UTC","AWAY","HOME","AWAY_PROJ","HOME_PROJ","PROJECTED_TOTAL","AWAY_GP","HOME_GP","AWAY_ID","HOME_ID","AVAILABILITY","AWAY_FINAL","HOME_FINAL","FINAL_TOTAL","STATUS"]
  fresh=[dict(zip(fields[:11],r)) for r in rows]
  combined={(r["KICKOFF_UTC"],r["AWAY_ID"],r["HOME_ID"]):r for r in fresh}
  for key,prior in old.items():
   kickoff=dt.datetime.fromisoformat(key[0].replace("Z","+00:00"))
   if kickoff<=now or prior.get("STATUS")=="FINAL" or key not in combined:
    combined[key]=prior
  rows=[]
  for key,row in combined.items():
   row=dict(row)
   final=completed.get(key)
   if final:
    row["AWAY_FINAL"],row["HOME_FINAL"]=final
    row["FINAL_TOTAL"]=sum(final)
    row["STATUS"]="FINAL"
   elif row.get("STATUS")!="FINAL":
    row["AWAY_FINAL"]=row["HOME_FINAL"]=row["FINAL_TOTAL"]=""
    row["STATUS"]="SCHEDULED"
   rows.append(row)
  rows.sort(key=lambda r:r["KICKOFF_UTC"])
  with archive.open("w",newline="",encoding="utf-8") as file:
   writer=csv.DictWriter(file,fieldnames=fields);writer.writeheader();writer.writerows(rows)
  print(sport,len(rows),"projected matchups")
if __name__=="__main__":main()
