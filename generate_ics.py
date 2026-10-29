#!/usr/bin/env python3
"""Genera un calendario .ics con los partidos de lolesports.com (solo librería estándar)."""
import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

API = "https://esports-api.lolesports.com/persisted/gw"
# Clave pública que usa la propia web de lolesports.com
API_KEY = "0TvQnueqKa5mxJntVWt0w4LpLfEkrV1Ta8rQBb9Z"

# Ligas a incluir (slugs de la URL de lolesports.com). Edita esta lista a tu gusto:
# lck, lpl, lcs, lcp, cblol-brazil, lta_n, lta_s, esports_world_cup...
LEAGUE_SLUGS = ["first_stand", "lec", "msi", "worlds"]

HL = "es-ES"
MAX_PAGES = 8  # páginas a recorrer hacia el pasado y hacia el futuro
OUTPUT = os.path.join("site", "lol.ics")
CAL_NAME = "LoL Esports"


def api_get(endpoint, **params):
    url = f"{API}/{endpoint}?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(
        url, headers={"x-api-key": API_KEY, "User-Agent": "lol-calendar/1.0"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def get_league_ids():
    leagues = api_get("getLeagues", hl=HL)["data"]["leagues"]
    found = {l["slug"]: l["id"] for l in leagues if l["slug"] in LEAGUE_SLUGS}
    missing = set(LEAGUE_SLUGS) - set(found)
    if missing:
        print(f"Aviso: ligas no encontradas: {', '.join(sorted(missing))}")
    return list(found.values())


def fetch_events(league_ids):
    """Recorre las páginas de la API hacia atrás y hacia delante."""
    ids = ",".join(league_ids)
    events = {}

    def collect(data):
        for ev in data["data"]["schedule"]["events"]:
            if ev.get("type") == "match" and ev.get("match"):
                events[ev["match"]["id"]] = ev

    first = api_get("getSchedule", hl=HL, leagueId=ids)
    collect(first)
    pages = first["data"]["schedule"]["pages"]

    for direction in ("newer", "older"):
        token = pages.get(direction)
        for _ in range(MAX_PAGES):
            if not token:
                break
            data = api_get("getSchedule", hl=HL, leagueId=ids, pageToken=token)
            collect(data)
            token = data["data"]["schedule"]["pages"].get(direction)
    return list(events.values())


# ---------- Generación del ICS ----------

def esc(text):
    return (
        str(text).replace("\\", "\\\\").replace(";", "\\;")
        .replace(",", "\\,").replace("\n", "\\n")
    )


def fold(line):
    """Pliega líneas a 75 octetos como exige el RFC 5545."""
    raw = line.encode("utf-8")
    if len(raw) <= 75:
        return line
    out, cur, size = [], "", 0
    for ch in line:
        n = len(ch.encode("utf-8"))
        limit = 75 if not out else 74
        if size + n > limit:
            out.append(cur)
            cur, size = "", 0
        cur += ch
        size += n
    out.append(cur)
    return "\r\n ".join(out)


def duration_for(ev):
    count = (ev["match"].get("strategy") or {}).get("count", 0)
    return {1: 60, 3: 150, 5: 240}.get(count, 120)


def build_event(ev, stamp):
    match = ev["match"]
    start = datetime.fromisoformat(ev["startTime"].replace("Z", "+00:00")).astimezone(timezone.utc)
    end = start + timedelta(minutes=duration_for(ev))
    teams = [t.get("code") or t.get("name") or "TBD" for t in match.get("teams", [])]
    while len(teams) < 2:
        teams.append("TBD")
    league = ev["league"]["name"]
    count = (match.get("strategy") or {}).get("count")
    desc = [f"{league} - {ev.get('blockName', '')}".strip(" -")]
    if count:
        desc.append(f"Bo{count}")
    desc.append(f"https://lolesports.com/{HL}/leagues/{ev['league']['slug']}")
    fmt = "%Y%m%dT%H%M%SZ"
    lines = [
        "BEGIN:VEVENT",
        f"UID:{match['id']}@lol-calendar",
        f"DTSTAMP:{stamp}",
        f"DTSTART:{start.strftime(fmt)}",
        f"DTEND:{end.strftime(fmt)}",
        f"SUMMARY:{esc(f'{league}: {teams[0]} vs {teams[1]}')}",
        f"DESCRIPTION:{esc(chr(10).join(desc))}",
        "END:VEVENT",
    ]
    return [fold(l) for l in lines]


def build_ics(events):
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//lol-calendar//ES",
        "CALSCALE:GREGORIAN",
        f"X-WR-CALNAME:{CAL_NAME}",
        "REFRESH-INTERVAL;VALUE=DURATION:PT3H",
        "X-PUBLISHED-TTL:PT3H",
    ]
    for ev in sorted(events, key=lambda e: e["startTime"]):
        lines += build_event(ev, stamp)
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def main():
    league_ids = get_league_ids()
    events = fetch_events(league_ids)
    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8", newline="") as f:
        f.write(build_ics(events))
    print(f"{len(events)} partidos escritos en {OUTPUT}")


if __name__ == "__main__":
    main()
