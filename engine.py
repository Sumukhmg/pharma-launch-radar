"""Pharma launch signal engine: which pharma accounts are in buying mode this week, and why.

Sources (all free, no keys): openFDA approvals + label changes, ClinicalTrials.gov Phase 3
completions, GDELT news. Writes signals.js, which index.html renders.

    python3 engine.py            # last 90 days
    python3 engine.py 60         # last 60 days
"""
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta

WEIGHT = {"approval": 40, "new indication": 25, "label change": 10, "phase 3 readout": 10, "news": 5}
CAP = {"approval": 80, "new indication": 50, "label change": 30, "phase 3 readout": 30, "news": 15}
NEWS_FOR_TOP = 15  # GDELT allows 1 request / 5s, so only enrich the leaders

SUFFIX = re.compile(r"\b(inc|llc|ltd|limited|corp|corporation|co|company|and|plc|ag|sa|se|gmbh|nv|bv|us|usa|"
                    r"holdings?|pharmaceuticals?|pharma|therapeutics|biosciences?|sciences?|laboratories|labs|"
                    r"biopharma|biotech|the|of|international|global)\b")


LEGAL = re.compile(r"(,?\s+(inc|llc|ltd|co|corp|plc|usa|us|lp|and co|and company)\.?)+$", re.I)


def clean(name):
    """'ELI LILLY AND CO' -> 'Eli Lilly'; keeps mixed-case names as written."""
    name = LEGAL.sub("", name.strip())
    return name.title() if name == name.upper() else name


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "pharma-signal-engine/0.1"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def key(name):
    # ponytail: company = first meaningful word ("ELI LILLY AND CO" == "Eli Lilly"). Merges/collides
    # on rare generic first words; add an alias dict when a wrong merge shows up.
    words = SUFFIX.sub(" ", re.sub(r"[^a-z0-9 ]", " ", name.lower())).split()
    return words[0] if words else name.lower().strip()


def fda(since, today):
    """Branded (NDA/BLA) approvals, new indications and label changes in the window."""
    q = urllib.parse.quote(f"submissions.submission_status_date:[{since:%Y%m%d} TO {today:%Y%m%d}]")
    events, skip = [], 0
    while True:
        try:
            page = get(f"https://api.fda.gov/drug/drugsfda.json?search={q}&limit=1000&skip={skip}")
        except urllib.error.HTTPError as e:
            if e.code == 404:  # openFDA's way of saying "no more results"
                break
            raise
        for app in page["results"]:
            if app.get("application_number", "").startswith("ANDA"):  # generics don't launch brands
                continue
            ofda = app.get("openfda", {})
            brand = ((app.get("products") or [{}])[0].get("brand_name") or (ofda.get("brand_name") or [""])[0]
                     or (ofda.get("generic_name") or [""])[0]).title() or "a new product"
            cls = (app.get("openfda", {}).get("pharm_class_epc") or [""])[0].split(" [")[0]
            appl = re.sub(r"\D", "", app["application_number"])
            for s in app.get("submissions", []):
                d = s.get("submission_status_date", "")
                if s.get("submission_status") != "AP" or d < f"{since:%Y%m%d}":
                    continue
                kind = ("approval" if s["submission_type"] == "ORIG" else
                        {"EFFICACY": "new indication", "LABELING": "label change"}.get(s.get("submission_class_code")))
                if kind:
                    events.append({"sponsor": app["sponsor_name"], "kind": kind, "brand": brand, "class": cls,
                                   "date": f"{d[:4]}-{d[4:6]}-{d[6:]}",
                                   "url": f"https://www.accessdata.fda.gov/scripts/cder/daf/index.cfm?event=overview.process&ApplNo={appl}"})
        skip += 1000
        if skip >= page["meta"]["results"]["total"]:
            break
    return events


def trials(since):
    """Industry-sponsored Phase 3 studies that completed in the window (next year's launches)."""
    params = {"filter.overallStatus": "COMPLETED",
              "filter.advanced": f"AREA[Phase]PHASE3 AND AREA[LeadSponsorClass]INDUSTRY "
                                 f"AND AREA[PrimaryCompletionDate]RANGE[{since},MAX]",
              "fields": "NCTId,BriefTitle,LeadSponsorName,PrimaryCompletionDate,Condition", "pageSize": 1000}
    events, token = [], None
    while True:
        page = get("https://clinicaltrials.gov/api/v2/studies?" + urllib.parse.urlencode({**params, **({"pageToken": token} if token else {})}))
        for st in page["studies"]:
            p = st["protocolSection"]
            nct = p["identificationModule"]["nctId"]
            events.append({"sponsor": p["sponsorCollaboratorsModule"]["leadSponsor"]["name"], "kind": "phase 3 readout",
                           "brand": p["identificationModule"]["briefTitle"],
                           "class": ", ".join(p.get("conditionsModule", {}).get("conditions", [])[:2]),
                           "date": p["statusModule"]["primaryCompletionDateStruct"]["date"],
                           "url": f"https://clinicaltrials.gov/study/{nct}"})
        token = page.get("nextPageToken")
        if not token:
            return events


def news(name, days):
    """Recent launch / medical-affairs / field-medical coverage of one company (GDELT, free)."""
    q = (f'"{name}" ("FDA approval" OR launch OR "medical affairs" OR "medical science liaison" '
         f'OR "field medical" OR "medical information")')
    url = ("https://api.gdeltproject.org/api/v2/doc/doc?mode=artlist&format=json&maxrecords=10&sort=datedesc"
           f"&timespan={min(days, 90)}d&query=" + urllib.parse.quote(q))
    for wait in (0, 20, 45):  # GDELT throttles hard (429 / plain-text notices); back off, then give up
        time.sleep(wait)
        try:
            arts = get(url).get("articles", [])
            break
        except Exception:
            arts = None
    if arts is None:  # news is a bonus signal, not a blocker
        print(f"  news skipped for {name} (GDELT throttled)")
        return []
    return [{"sponsor": name, "kind": "news", "brand": a["title"].strip(), "class": a["domain"],
             "date": f"{a['seendate'][:4]}-{a['seendate'][4:6]}-{a['seendate'][6:8]}", "url": a["url"]} for a in arts
            if a.get("url", "").lower().startswith(("https://", "http://"))]  # no javascript:/data: hrefs in the dashboard


def score(events):
    counts = {}
    for e in events:
        counts[e["kind"]] = counts.get(e["kind"], 0) + 1
    return sum(min(CAP[k], WEIGHT[k] * n) for k, n in counts.items())


def pitch(events):
    """Pick the product that fits the strongest signal and write the opener."""
    by = {k: sorted((e for e in events if e["kind"] == k), key=lambda e: e["date"], reverse=True) for k in WEIGHT}
    fmt = lambda e: datetime.strptime(e["date"], "%Y-%m-%d").strftime("%b %d").replace(" 0", " ")
    if by["approval"]:
        e = by["approval"][0]
        return "Ather", (f"Congrats on the FDA approval of {e['brand']} on {fmt(e)}. The first months of a launch are "
                         "when HCP questions spike, and Ather answers them 24/7, checked against your approved label.")
    if by["new indication"]:
        e = by["new indication"][0]
        return "Ather", (f"Saw {e['brand']} picked up a new indication on {fmt(e)}. New indications bring a fresh wave "
                         "of dosing and safety questions; Ather handles them around the clock against the updated label.")
    if by["label change"]:
        e = by["label change"][0]
        return "Jarvis", (f"Noticed the {e['brand']} label was updated on {fmt(e)}. Jarvis gets your field team "
                          "up to speed on the change before their next HCP call.")
    e = by["phase 3 readout"][0] if by["phase 3 readout"] else events[0]
    return "Simulation Studio", (f"Congrats on wrapping up a Phase 3 study ({e['class'] or e['brand'][:60]}). Before launch, "
                                 "Simulation Studio lets you test messaging with AI HCP twins in days instead of months.")


def build(events):
    accounts = {}
    for e in events:
        a = accounts.setdefault(key(e["sponsor"]), {"names": [], "events": []})
        a["names"].append(e["sponsor"])
        a["events"].append(e)
    out = []
    for a in accounts.values():
        # prefer the mixed-case spelling (ClinicalTrials.gov) over openFDA's ALL CAPS
        name = max(a["names"], key=lambda n: (n != n.upper(), -len(n)))
        product, line = pitch(a["events"])
        out.append({"name": clean(name), "score": score(a["events"]),
                    "product": product, "line": line,
                    "events": sorted(a["events"], key=lambda e: (WEIGHT[e["kind"]], e["date"]), reverse=True)})
    return sorted(out, key=lambda a: a["score"], reverse=True)


def main():
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 90
    today = date.today()
    since = today - timedelta(days=days)
    print(f"window {since} -> {today}")
    events = fda(since, today)
    print(f"openFDA: {len(events)} branded approvals / label events")
    events += trials(since)
    print(f"total with ClinicalTrials.gov: {len(events)}")
    ranked = build(events)
    for a in ranked[:NEWS_FOR_TOP]:
        time.sleep(8)
        hits = news(a["name"], days)
        a["events"] += hits
        print(f"news {a['name']}: {len(hits)}")
    ranked = build([e for a in ranked for e in a["events"]])
    data = {"generated": today.isoformat(), "since": since.isoformat(), "days": days,
            "counts": {k: sum(e["kind"] == k for a in ranked for e in a["events"]) for k in WEIGHT},
            "accounts": ranked[:60]}
    with open("signals.js", "w") as f:
        f.write("window.SIGNALS = " + json.dumps(data, indent=1) + ";\n")
    print("top 10:", ", ".join(f"{a['name']} ({a['score']})" for a in ranked[:10]))


if __name__ == "__main__":
    main()
