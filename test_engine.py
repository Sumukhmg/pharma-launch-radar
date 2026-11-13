from engine import build, clean, key, score

assert clean("ELI LILLY AND CO") == "Eli Lilly"
assert clean("Gilead Sciences Inc") == "Gilead Sciences"

assert key("ELI LILLY AND CO") == key("Eli Lilly and Company") == "eli"
assert key("Bristol-Myers Squibb") == key("BRISTOL MYERS SQUIBB CO")
assert key("Gilead Sciences") == key("GILEAD SCIENCES INC")


def ev(sponsor, kind, date="2026-10-01"):
    return {"sponsor": sponsor, "kind": kind, "brand": "Drugx", "class": "", "date": date, "url": ""}


# caps: 5 label changes = 30, not 50
assert score([ev("A", "label change")] * 5) == 30
# approval + label change + news beats three label changes
ranked = build([ev("PFIZER INC", "approval"), ev("Pfizer", "label change"), ev("Pfizer", "news"),
                ev("Acme", "label change"), ev("Acme", "label change"), ev("Acme", "label change")])
assert [a["name"] for a in ranked] == ["Pfizer", "Acme"], ranked
assert ranked[0]["score"] == 55 and ranked[0]["product"] == "Ather"
assert ranked[1]["product"] == "Jarvis"
assert "Oct 1" in ranked[0]["line"]
# untrusted news URLs: only http(s) reaches the dashboard
import engine
engine.get = lambda url: {"articles": [
    {"url": "javascript:alert(1)", "title": "x", "domain": "evil", "seendate": "20261001T000000Z"},
    {"url": "https://ok.example/a", "title": "y", "domain": "ok", "seendate": "20261001T000000Z"}]}
assert [n["url"] for n in engine.news("Pfizer", 30)] == ["https://ok.example/a"]
print("ok")
