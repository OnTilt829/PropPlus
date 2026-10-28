#!/usr/bin/env python3
"""Read-only quality audit for historical CFB and NFL scoreboard archives."""
import csv
import datetime as dt
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path("data")
NOW = dt.datetime.now(dt.timezone.utc)
SOURCES = {"cfb": ROOT / "cfb_projections.csv", "nfl": ROOT / "nfl_game_scores.csv"}
GRACE = dt.timedelta(hours=36)

def parse(value):
    try:
        result = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return result if result.tzinfo else result.replace(tzinfo=dt.timezone.utc)
    except (TypeError, ValueError):
        return None

def audit(sport, path):
    if not path.exists():
        raise FileNotFoundError(f"Missing {path}")
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise RuntimeError(f"No CSV headers: {path}")
        rows = list(reader)
    problems = defaultdict(list)
    seen = {}
    counts = defaultdict(int)
    for index, row in enumerate(rows, start=2):
        when = parse(row.get("KICKOFF_UTC"))
        away_id, home_id = row.get("AWAY_ID", ""), row.get("HOME_ID", "")
        label = f"line {index}: {row.get('AWAY', '?')} at {row.get('HOME', '?')} ({row.get('KICKOFF_UTC', '')})"
        if not when or not away_id or not home_id:
            problems["invalid_identity"].append(label)
            continue
        # Team IDs plus a 24-hour UTC window identify the same scheduled fixture
        # even when one archive row uses a slightly different kickoff time.
        key = (away_id, home_id, when.date().isoformat())
        if key in seen:
            problems["duplicate_games"].append(f"{label}; first seen on line {seen[key]}")
        else:
            seen[key] = index
        status = (row.get("STATUS") or "").upper()
        score_fields = [row.get(k, "").strip() for k in ("AWAY_FINAL", "HOME_FINAL", "FINAL_TOTAL")]
        has_any = any(score_fields)
        has_all = all(score_fields)
        counts[status or "MISSING_STATUS"] += 1
        if status == "FINAL":
            if not has_all:
                problems["final_missing_scores"].append(label)
            else:
                try:
                    away, home, total = (int(float(x)) for x in score_fields)
                    if away < 0 or home < 0 or total != away + home:
                        problems["invalid_final_scores"].append(label)
                except (ValueError, TypeError):
                    problems["invalid_final_scores"].append(label)
        elif has_any:
            problems["scores_without_final_status"].append(label)
        if when < NOW - GRACE and status != "FINAL":
            problems["stale_scheduled_games"].append(label)
    return {"sport": sport, "file": str(path), "rows": len(rows),
            "status_counts": dict(counts),
            "issues": {name: {"count": len(items), "examples": items[:20]}
                       for name, items in problems.items()}}

def main():
    report = {"generated_at": NOW.isoformat(), "grace_hours": 36, "sports": {}}
    for sport, path in SOURCES.items():
        result = audit(sport, path)
        report["sports"][sport] = result
        summary = ", ".join(f"{name}={info['count']}" for name, info in result["issues"].items()) or "no issues"
        print(f"AUDIT {sport.upper()}: {result['rows']} records; {summary}")
        for name, info in result["issues"].items():
            for item in info["examples"][:5]:
                print(f"WARNING {sport} {name}: {item}")
    output = ROOT / "score_archive_audit.json"
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Audit report saved: {output}")

if __name__ == "__main__":
    main()
