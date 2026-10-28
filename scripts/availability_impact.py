"""Conservative, auditable player-availability adjustment engine.

Input player_game_logs.csv columns:
SPORT,TEAM_ID,PLAYER_ID,PLAYER,DATE,PLAYED,POINTS,TEAM_POINTS
Each row must represent a completed team game, including DNP rows. Team points
are the actual team total for that game. No inferred missing games.
"""
import csv
import datetime as dt
from collections import defaultdict
from pathlib import Path

CONFIRMED_OUT={"out","inactive","ruled out","injured reserve","ir","suspended"}
CONFIRMED_IN={"active","available","will play"}
def normalize(status):
    return str(status or "").strip().lower().replace("_"," ")

def load_logs(path="data/player_game_logs.csv"):
    rows=defaultdict(list)
    if not Path(path).exists():return rows
    with open(path,newline="",encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            try:
                if not all(row.get(k) for k in ("SPORT","TEAM_ID","PLAYER_ID","DATE","PLAYED","TEAM_POINTS")):continue
                dt.date.fromisoformat(row["DATE"])
                row["POINTS"]=float(row.get("POINTS") or 0)
                row["TEAM_POINTS"]=float(row["TEAM_POINTS"])
                row["PLAYED"]=str(row["PLAYED"]).lower() in ("1","true","yes")
                rows[(row["SPORT"].lower(),row["TEAM_ID"],row["PLAYER_ID"])].append(row)
            except (ValueError,TypeError):continue
    return rows

def adjustment(sport,team_id,injuries,logs):
    """Return adjustment and evidence. Do not infer absence from uncertain status.

    Uses observed team scoring with vs without player; requires >=3 games in
    each group and <= 20 point NBA or 10 point football adjustment per team.
    Because multiple absences are correlated, only the single most material
    supported absence is applied, avoiding double counting.
    """
    candidates=[]
    for injury in injuries:
        if normalize(injury.get("status")) not in CONFIRMED_OUT:continue
        player_id=str(injury.get("player_id") or "")
        if not player_id:continue
        games=logs.get((sport,team_id,player_id),[])
        with_player=[r["TEAM_POINTS"] for r in games if r["PLAYED"]]
        without=[r["TEAM_POINTS"] for r in games if not r["PLAYED"]]
        if min(len(with_player),len(without))<3:continue
        # Baseline already contains historical absences: adjust only the
        # difference from the historical team scoring average.
        full=(sum(with_player)/len(with_player))
        absent=(sum(without)/len(without))
        baseline=sum(r["TEAM_POINTS"] for r in games)/len(games)
        raw=absent-baseline
        limit=20 if sport=="nba" else 10
        value=max(-limit,min(limit,raw))
        candidates.append({"player":injury.get("player"),"player_id":player_id,
                           "status":injury.get("status"),"adjustment":round(value,2),
                           "with_games":len(with_player),"without_games":len(without),
                           "with_avg":round(full,2),"without_avg":round(absent,2),
                           "source":injury.get("source","")})
    if not candidates:return 0.0,{"applied":False,"reason":"insufficient confirmed availability and matched historical participation"}
    chosen=max(candidates,key=lambda x:abs(x["adjustment"]))
    return chosen["adjustment"],{"applied":True,"method":"observed team scoring with/without player","evidence":chosen}
