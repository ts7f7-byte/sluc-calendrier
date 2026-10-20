#!/usr/bin/env python3
"""Génère sluc-nancy.ics : tous les matchs du SLUC Nancy Basket.

Sources :
  - LNB (Betclic Élite, playoffs, Leaders Cup…) : api-prod.lnb.fr
  - FIBA (Europe Cup / Champions League)        : fiba.basketball

Si une source est indisponible, les matchs de la dernière récupération
réussie (cache.json) sont conservés pour ne jamais vider le calendrier.
Python 3.9+, bibliothèque standard uniquement.
"""
import datetime as dt
import json
import re
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "sluc-nancy.ics"
CACHE = HERE / "cache.json"

LNB_TEAM_ID = 1868  # SLUC Nancy dans l'API LNB
FIBA_TEAM_CODE = "SLUC"
HOME_VENUE = "Palais des Sports Jean Weille, Nancy"
UA = {"User-Agent": "Mozilla/5.0 (sluc-calendrier)"}
MATCH_DURATION = dt.timedelta(hours=2)


def season_start_year(today=None):
    today = today or dt.date.today()
    return today.year if today.month >= 7 else today.year - 1


def http(url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers={**UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8")


def parse_utc(text):
    """'2026-10-25T15:30:00.000Z' ou '2026-10-25T15:30:00' -> datetime UTC."""
    text = text.rstrip("Z").split(".")[0]
    return dt.datetime.fromisoformat(text).replace(tzinfo=dt.timezone.utc)


# --------------------------------------------------------------------------- LNB
def fetch_lnb(year):
    token = json.loads(http("https://lnb.fr/api/token"))["token"]
    body = {
        "year": year, "competition_abbrev": "", "division_external_id": 0,
        "team_external_id": LNB_TEAM_ID, "round_number": 0, "phase_id": 0,
        "tournament_number": 0, "limit": 200,
    }
    raw = http(
        "https://api-prod.lnb.fr/match/v3/getCalendar",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {token}", "language_code": "fr",
                 "device_type": "web", "Content-Type": "application/json"},
    )
    payload = json.loads(raw)
    if not payload.get("status"):
        raise RuntimeError(payload.get("message"))

    events = []
    for day in payload["data"]:
        for m in day["data"]:
            teams = m.get("teams") or []
            if len(teams) != 2:
                continue
            home, away = teams
            is_home = home.get("external_id") == LNB_TEAM_ID
            opponent = (away if is_home else home).get("team_name", "?")
            done = m.get("match_status") == "COMPLETE"
            score = f" {home.get('score_string')}-{away.get('score_string')}" if done else ""
            details = [m.get("competition_name", ""), m.get("round_description") or m.get("phase_name") or ""]
            tv = ", ".join(b["broadcast_provider"]["broadcast_provider"]
                           for b in m.get("broadcast") or [] if b.get("broadcast_provider"))
            if tv:
                details.append(f"Diffusion : {tv}")
            events.append({
                "uid": f"lnb-{m['external_id']}@sluc-nancy-calendrier",
                "start_utc": m.get("match_time_utc"),
                "date": m.get("match_date"),
                "home": is_home,
                "title": f"{home.get('team_name')} - {away.get('team_name')}{score}",
                "competition": short_comp(m.get("competition_name", "")),
                "location": m.get("venue_name") or (HOME_VENUE if is_home else opponent),
                "description": "\n".join(d for d in details if d),
                "url": "https://lnb.fr/fr/calendar/betclicelite",
                "cancelled": m.get("match_status") in ("CANCELLED", "POSTPONED"),
            })
    return events


def short_comp(name):
    n = name.lower()
    if "élite" in n or "elite" in n:
        return "Betclic Élite"
    if "leaders" in n:
        return "Leaders Cup"
    return name


# -------------------------------------------------------------------------- FIBA
def fiba_event_slugs(year):
    yy = f"{year % 100:02d}-{(year + 1) % 100:02d}"
    return [f"fiba-europe-cup-{yy}", f"basketball-champions-league-{yy}"]


def fiba_name(team):
    return "Nancy" if team.get("code") == FIBA_TEAM_CODE else team.get("shortName", "?")


def fetch_fiba(year):
    events, found_page = [], False
    for slug in fiba_event_slugs(year):
        url = f"https://www.fiba.basketball/en/events/{slug}/games"
        try:
            html = http(url)
        except Exception:
            continue
        found_page = True
        # Les matchs sont embarqués dans la page (payload Next.js échappé)
        s = html.replace('\\"', '"').replace("\\\\", "\\")
        dec, games = json.JSONDecoder(), {}
        for mt in re.finditer(r'\{"gameId":', s):
            try:
                g, _ = dec.raw_decode(s, mt.start())
            except ValueError:
                continue
            a, b = g.get("teamA") or {}, g.get("teamB") or {}
            if FIBA_TEAM_CODE in (a.get("code"), b.get("code")):
                games[g["gameId"]] = g
        comp = "FIBA Europe Cup" if "europe-cup" in slug else "Basketball Champions League"
        for g in games.values():
            a, b = g["teamA"], g["teamB"]
            done = g.get("teamAScore") is not None and g.get("gameResultStatusCode") not in (None, "EMPTY")
            score = f" {g['teamAScore']}-{g['teamBScore']}" if done else ""
            has_time = g.get("gameDateTimeUTC") and g.get("hasTimeGameDateTime") is not False
            venue = ", ".join(x for x in (g.get("venueName"), g.get("hostCity")) if x)
            group = g.get("groupPairingCode")
            events.append({
                "uid": f"fiba-{g['gameId']}@sluc-nancy-calendrier",
                "start_utc": g["gameDateTimeUTC"] if has_time else None,
                "date": (g.get("gameDateTime") or "")[:10],
                "home": a.get("code") == FIBA_TEAM_CODE,
                "title": f"{fiba_name(a)} - {fiba_name(b)}{score}",
                "competition": comp,
                "location": venue.replace('"', ""),
                "description": comp + (f" – Groupe {group}" if group else ""),
                "url": url,
                "cancelled": bool(g.get("isPostponed")),
            })
    if not found_page:
        raise RuntimeError("aucune page FIBA trouvée")
    return events


# --------------------------------------------------------------------------- ICS
def esc(text):
    return (text or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def fold(line):
    out, b = [], line.encode("utf-8")
    while len(b) > 75:
        cut = 75 if not out else 74
        while (b[cut] & 0xC0) == 0x80:  # ne pas couper un caractère UTF-8
            cut -= 1
        out.append(b[:cut].decode("utf-8"))
        b = b[cut:]
    out.append(b.decode("utf-8"))
    return "\r\n ".join(out)


def to_ics(events):
    fmt = "%Y%m%dT%H%M%SZ"
    now = dt.datetime.now(dt.timezone.utc).strftime(fmt)
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//sluc-nancy-calendrier//FR",
        "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
        "X-WR-CALNAME:SLUC Nancy Basket", "X-WR-TIMEZONE:Europe/Paris",
        "X-WR-CALDESC:Tous les matchs du SLUC Nancy Basket (mis à jour automatiquement)",
        "REFRESH-INTERVAL;VALUE=DURATION:PT3H", "X-PUBLISHED-TTL:PT3H",
    ]
    for e in sorted(events, key=lambda e: e["start_utc"] or e["date"] or ""):
        icon = "🏠" if e["home"] else "✈️"
        lines += ["BEGIN:VEVENT", f"UID:{e['uid']}", f"DTSTAMP:{now}"]
        if e["start_utc"]:
            start = parse_utc(e["start_utc"])
            lines += [f"DTSTART:{start.strftime(fmt)}", f"DTEND:{(start + MATCH_DURATION).strftime(fmt)}"]
        else:  # horaire pas encore fixé : journée entière
            d = dt.date.fromisoformat(e["date"])
            lines += [f"DTSTART;VALUE=DATE:{d:%Y%m%d}",
                      f"DTEND;VALUE=DATE:{d + dt.timedelta(days=1):%Y%m%d}"]
        summary = f"{icon} {e['title']} ({e['competition']})"
        if not e["start_utc"]:
            summary += " – horaire à confirmer"
        lines += [
            f"SUMMARY:{esc(summary)}",
            f"LOCATION:{esc(e['location'])}",
            f"DESCRIPTION:{esc(e['description'])}",
            f"URL:{e['url']}",
            f"STATUS:{'CANCELLED' if e['cancelled'] else 'CONFIRMED'}",
            "TRANSP:OPAQUE",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(fold(l) for l in lines) + "\r\n"


def main():
    year = season_start_year()
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    errors = []
    for name, fetch in (("lnb", fetch_lnb), ("fiba", fetch_fiba)):
        try:
            evs = fetch(year)
            if evs or name not in cache:
                cache[name] = evs
            print(f"{name}: {len(evs)} matchs")
        except Exception as exc:  # on garde la dernière version connue
            errors.append(f"{name}: {exc}")
            print(f"{name}: ÉCHEC ({exc}) – cache conservé ({len(cache.get(name, []))} matchs)", file=sys.stderr)
    events = [e for evs in cache.values() for e in evs]
    if not events:
        sys.exit("Aucun match récupéré, calendrier non modifié.")
    CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    OUT.write_bytes(to_ics(events).encode("utf-8"))
    print(f"{OUT.name} : {len(events)} matchs")
    if len(errors) == 2:
        sys.exit(1)


if __name__ == "__main__":
    main()
