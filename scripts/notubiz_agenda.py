#!/usr/bin/env python3
"""Haalt de vergaderagenda van de gemeente Hengelo op via de openbare Notubiz-API
(api.notubiz.nl) en schrijft de vergaderingen naar data.json in het formaat van de app.

Gebruik:
  python3 scripts/notubiz_agenda.py            # data.json bijwerken
  python3 scripts/notubiz_agenda.py --test     # alleen testen: organisatie zoeken en 5 vergaderingen tonen

De organisatie-id van Hengelo wordt opgezocht in de lijst van Notubiz-organisaties en
bewaard in notubiz-org.json, zodat dat maar één keer hoeft.
Let op: de veldnamen van de API zijn (nog) niet getest vanuit deze omgeving; het script
leest daarom ruim en bewaart bij problemen de ruwe API-respons in notubiz-debug.json.
"""
import datetime as dt
import json
import os
import sys
import urllib.parse
import urllib.request

API = "https://api.notubiz.nl"
VERSION = "1.10.8"
GEMEENTE = "Hengelo"
SITE = "https://hengelo.raadsinformatie.nl"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data.json")
ORG_CACHE = os.path.join(ROOT, "notubiz-org.json")
DEBUG = os.path.join(ROOT, "notubiz-debug.json")


def get(path, **params):
    params.setdefault("format", "json")
    params.setdefault("version", VERSION)
    url = f"{API}{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "pvv-hengelo-app/0.1 (fractie-agenda)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def walk(obj):
    """Alle dicts in een geneste JSON-structuur."""
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk(v)


def attr(d, k):
    """Notubiz zet id en andere kenmerken soms onder "@attributes"."""
    v = d.get(k)
    if v is None and isinstance(d.get("@attributes"), dict):
        v = d["@attributes"].get(k)
    return v


def org_id():
    if os.path.exists(ORG_CACHE):
        with open(ORG_CACHE) as f:
            return json.load(f)["id"]
    raw = get("/organisations")
    hits = [d for d in walk(raw) if attr(d, "id") is not None and str(d.get("name", d.get("title", ""))).strip().lower() in
            (GEMEENTE.lower(), f"gemeente {GEMEENTE.lower()}")]
    if not hits:
        with open(DEBUG, "w") as f:
            json.dump(raw, f, ensure_ascii=False, indent=1)
        sys.exit(f"{GEMEENTE} niet gevonden in /organisations; ruwe respons in {DEBUG}")
    org = {"id": attr(hits[0], "id"), "naam": hits[0].get("name") or hits[0].get("title")}
    with open(ORG_CACHE, "w") as f:
        json.dump(org, f, ensure_ascii=False, indent=1)
    return org["id"]


def first(d, *keys):
    for k in keys:
        v = d.get(k)
        if v:
            return v
    return None


GREMIA = {}


def gremium_naam(oid, gid):
    """Naam van het gremium (bijv. Gemeenteraad); per run één keer per gremium opgevraagd."""
    if not gid:
        return ""
    if gid not in GREMIA:
        try:
            raw = get(f"/organisations/{oid}/gremia/{gid}")
            namen = [first(d, "title", "name") for d in walk(raw) if first(d, "title", "name")]
            GREMIA[gid] = str(namen[0]).strip() if namen else ""
        except Exception:
            GREMIA[gid] = ""
    return GREMIA[gid]


def soort(titel):
    t = titel.lower()
    if "commissie" in t or "politieke markt" in t:
        return "beraad"
    if "raad" in t:
        return "raad"
    return "overig"


def events(oid, van, tot):
    out, page = [], 1
    while page <= 20:
        raw = get("/events", organisation_id=oid, page=page,
                  date_from=van.strftime("%Y-%m-%d 00:00:00"), date_to=tot.strftime("%Y-%m-%d 23:59:59"))
        items = raw.get("events") if isinstance(raw, dict) else None
        if isinstance(items, dict):
            items = items.get("event") or list(items.values())
        if items is None:
            with open(DEBUG, "w") as f:
                json.dump(raw, f, ensure_ascii=False, indent=1)
            sys.exit(f"Onverwacht antwoord van /events; ruwe respons in {DEBUG}")
        if not items:
            break
        for e in items:
            if e.get("canceled") or e.get("inactive") or e.get("confidential"):
                continue
            plan = e.get("plannings") or []
            start = first(plan[0], "start_date", "date") if plan else first(e, "start_date", "date")
            if not start:
                continue
            gnaam = gremium_naam(oid, (e.get("gremium") or {}).get("id"))
            # attribuut id 1 is de titel van de vergadering (bijv. "Gemeenteraad (2e Beleidsrapportage ...)")
            attrs = {a.get("id"): a.get("value") for a in e.get("attributes") or [] if isinstance(a, dict)}
            titel = attrs.get(1) or gnaam or ("Bijeenkomst" if e.get("type") == "assembly" else "Vergadering")
            out.append({
                "t": start.replace(" ", "T")[:16],
                "type": soort(f"{titel} {gnaam}"),
                "title": titel,
                "desc": gnaam if gnaam and gnaam not in titel else "",
                "link": f"{SITE}/vergadering/{attr(e, 'id')}" if attr(e, "id") else SITE,
            })
        pag = raw.get("pagination") or {}
        if not pag or page >= int(pag.get("total_pages") or pag.get("last_page") or page):
            break
        page += 1
    return sorted(out, key=lambda x: x["t"])


def main():
    vandaag = dt.date.today()
    oid = org_id()
    lijst = events(oid, vandaag - dt.timedelta(days=14), vandaag + dt.timedelta(days=90))
    if "--test" in sys.argv:
        print(f"Organisatie-id {GEMEENTE}: {oid}; {len(lijst)} vergaderingen gevonden.")
        for e in lijst[:5]:
            print(f"  {e['t']}  {e['title']}  {e['link']}")
        return
    data = {}
    if os.path.exists(DATA):
        with open(DATA) as f:
            data = json.load(f)
    eigen = [e for e in data.get("events", []) if e.get("bron") == "fractie"]  # handmatige items blijven staan
    data["events"] = sorted(lijst + eigen, key=lambda x: x["t"])
    data["bijgewerkt"] = vandaag.isoformat()
    data["bron"] = f"Notubiz-API, organisatie {oid}"
    with open(DATA, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print(f"{len(lijst)} vergaderingen geschreven naar data.json")


if __name__ == "__main__":
    main()
