"""Tests af repo-versionen med falske svar. Kør: python3 test_repo.py <repo-mappe>"""
import asyncio
import copy
import json
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace as N

repo = Path(sys.argv[1])
work = Path(tempfile.mkdtemp())
for f in ("agent.py", "regler.md"):
    shutil.copy(repo / f, work / f)
cfg = json.loads((repo / "config.example.json").read_text(encoding="utf-8"))
cfg["parent"]["name"] = "Testforælder"
(work / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
(work / "manuelle_aftaler.json").write_text("[]", encoding="utf-8")
sys.path.insert(0, str(work))
import agent  # noqa: E402

TZ = agent.TZ
fails = 0


def check(name, cond):
    global fails
    print(("OK   " if cond else "FEJL ") + name)
    fails += not cond


# 1. Skiftende UID
class G:
    def __init__(s):
        s.n, s.log, s.mails = 0, [], []
    def create_event(s, cal, b):
        s.n += 1; s.log.append(("create", b["subject"])); return f"id{s.n}"
    def update_event(s, i, b): s.log.append(("update", b["subject"]))
    def delete_event(s, i): s.log.append(("delete", i))
    def calendar_id(s, n): return "cal"
    def list_events(s, *a): return []
    def send_mail(s, to, subj, html): s.mails.append((subj, html))


def items(uid, extra=True):
    d = {f"feed:{uid}": dict(title="Skole-hjem-samtale", date="2030-11-17", end_date=None, start="14:00",
                             end="14:20", location="", notes="", source="Aula", children=["Emma"])}
    if extra:
        d["feed:x"] = dict(title="Aflyst ting", date="2030-12-01", end_date=None, start=None, end=None,
                           location="", notes="", source="Aula", children=["Emma"])
    return d


orig_fetch_feed = agent.fetch_feed_items
state, g = {"events": {}}, G()
for uid, extra in [("A", True), ("B", True), ("C", False)]:
    agent.fetch_feed_items = lambda c, u=uid, e=extra: items(u, e)
    agent.sync_feeds(g, "cal", state, cfg, False)
check("UID: én oprettelse, ingen slet/opret ved nyt UID", [x[0] for x in g.log] == ["create", "create", "delete"])
check("UID: nøgle flyttet til nyeste UID", sorted(state["events"]) == ["feed:C"])
agent.fetch_feed_items = lambda c: items("D", False)
st = agent.sync_feeds(g, "cal", state, cfg, True)
check("UID: tørkørsel ændrer ikke state", sorted(state["events"]) == ["feed:C"] and st["uændret"] == 1)

# 2. Ugeplan
mon = date(2030, 11, 11)


def ev(d, h, title, loc=None):
    s = datetime(2030, 11, d, h, 0, tzinfo=TZ)
    return N(start_datetime=s, end_datetime=s + timedelta(minutes=45), title=title, location=loc, has_substitute=False)


kids = [N(id=11, name="Emma Hansen", _raw={"userId": "em1", "institutionProfile": {"institutionCode": "1"}}),
        N(id=22, name="Oscar Hansen", _raw={"userId": "os1", "institutionProfile": {"institutionCode": "1"}}),
        N(id=33, name="Ukendt Barn", _raw={"userId": "uk1"})]


class W:
    async def get_ugeplan(s, *a):
        return [N(name="Emma Hansen", institutions=[N(letters=[N(group_name="2.a", content_html="<p>Tirsdag tur til skoven.</p>")])])]
    async def get_meebook_weekplan(s, *a): raise RuntimeError("401 test")
    async def get_momo_reminders(s, *a):
        return [N(user_name="Oscar Hansen", team_reminders=[N(due_date="2030-11-14", team_name="0.b", subject_name="Dansk", reminder_text="Yndlingsbog")], assignment_reminders=[])]


class C:
    widgets = W()
    async def get_calendar_events(s, ids, a, b):
        return [ev(12, 10, "Idræt", "Hallen"), ev(12, 10, "Idræt", "Hallen")] if ids == [11] else []
    async def get_profile_context(s): return {"data": {"userId": "sess"}}
    async def get_widgets(s): return [N(widget_id=x, name="W"+x, widget_supplier="S", widget_type="t") for x in ["0029", "0004", "0062"]]


plan = asyncio.run(agent.fetch_week_plan(C(), N(children=kids), cfg, mon, mon + timedelta(days=4)))
check("Ugeplan: idræt i skema, dublet fjernet", plan["children"]["Emma"]["schema"] == {"2030-11-12": ["10:00-10:45 Idræt (Hallen)"]})
check("Ugeplan: MinUddannelse-tekst hos Emma", plan["children"]["Emma"]["ugeplan"][0]["tekst"] == "Tirsdag tur til skoven.")
check("Ugeplan: Huskelisten hos Oscar", plan["children"]["Oscar"]["huskeliste"][0]["tekst"] == "Yndlingsbog")
check("Ugeplan: Meebook-fejl er en note, ikke en fejl", any("Meebook" in n for n in plan["notes"]))
check("Ugeplan: widget-navne gemmes", plan["widgets"][0]["navn"] == "W0029")
check("Fri: sidste lektion pr. dag", plan["children"]["Emma"]["slut"] == {"2030-11-12": "10:45"})
check("Fri: fra skema som reserve", agent.fri_from_schema(plan) == [{"date": "2030-11-12", "children": ["Emma"], "time": "10:45"}])
html_fri = agent.mail_html(cfg, [], [], {}, None, [], None, [
    {"date": "2030-11-14", "children": ["Emma"], "time": "12:00", "note": "Matematikkens dag"},
    {"date": "2030-11-14", "children": ["Oscar"], "time": "11:20"}])
check("Fri: linje i mailen med afvigelse fremhævet", "<li>[Emma 2.a] <b>Fri kl. 12.00</b> (Matematikkens dag).</li>" in html_fri and "<li>[Oscar 0.b] Fri kl. 11.20.</li>" in html_fri and "Torsdag 14/11" in html_fri)
html_dup = agent.mail_html(cfg, [], [], {}, None, [{"date": "2030-11-14", "children": ["Emma"], "text": "Matematikkens dag."}], None,
    [{"date": "2030-11-14", "children": ["Emma"], "time": "12:00", "note": "Matematikkens dag"}])
check("Fri: grund gentages ikke, når den står i teksten", "<li>[Emma 2.a] Matematikkens dag. <b>Fri kl. 12.00</b>.</li>" in html_dup)
html_dup2 = agent.mail_html(cfg, [], [], {}, None, [{"date": "2030-11-14", "children": ["Emma"], "text": "Matematikkens dag."}], None,
    [{"date": "2030-11-14", "children": ["Emma"], "time": "12:00", "note": "Matematikkens dag kl. 8-12, herefter fri"}])
check("Fri: lang grund gentages heller ikke", "<li>[Emma 2.a] Matematikkens dag. <b>Fri kl. 12.00</b>.</li>" in html_dup2)
check("Ugeplan: weekend giver næste uge", agent.plan_week(date(2030, 11, 10)) == (mon, mon + timedelta(days=4)))
check("Ugeplan: hverdag giver denne uge", agent.plan_week(date(2030, 11, 13)) == (mon, mon + timedelta(days=4)))

# 2b. Meebook: kobling på UniLogin, tom liste giver note
class W2(W):
    async def get_meebook_weekplan(s, *a):
        return [N(name="Emma", unilogin="EM1", week_plan=[N(date="2030-11-13", tasks=[
            N(pill="Idræt", title="Udendørs idræt", type="task", content="<p>Husk løbesko</p>")])])]
class C2(C):
    widgets = W2()
plan2 = asyncio.run(agent.fetch_week_plan(C2(), N(children=kids), cfg, mon, mon + timedelta(days=4)))
mb = [u for u in plan2["children"]["Emma"]["ugeplan"] if u["kilde"] == "Meebook"]
check("Meebook: koblet på UniLogin med dato", mb == [{"kilde": "Meebook", "dato": "2030-11-13", "tekst": "[Idræt] Udendørs idræt Husk løbesko"}])
check("Meebook: dansk dato omsættes", agent._plan_date("onsdag 13. nov.", mon) == "2030-11-13"
      and agent._plan_date("13. nov.", mon) == "2030-11-13" and agent._plan_date("2030-11-12", mon) == "2030-11-12")
class W5(W):
    async def get_meebook_weekplan(s, *a):
        return [N(name="Emma", unilogin="em1", week_plan=[N(date="tirsdag 12. nov.", tasks=[
            N(pill="Dansk", title="", type="comment", content="Husk frilæsningsbog")])])]
class C5(C):
    widgets = W5()
plan5 = asyncio.run(agent.fetch_week_plan(C5(), N(children=kids), cfg, mon, mon + timedelta(days=4)))
mb5 = [u for u in plan5["children"]["Emma"]["ugeplan"] if u["kilde"] == "Meebook"]
check("Meebook: 'comment' fjernet og dato i ISO", mb5 == [{"kilde": "Meebook", "dato": "2030-11-12", "tekst": "[Dansk] Husk frilæsningsbog"}])
class W3(W):
    async def get_meebook_weekplan(s, *a): return []
class C3(C):
    widgets = W3()
plan3 = asyncio.run(agent.fetch_week_plan(C3(), N(children=kids), cfg, mon, mon + timedelta(days=4)))
check("Meebook: tom ugeplan giver note", any("Meebook gav ingen ugeplan" in n for n in plan3["notes"]))
class C4(C2):
    async def get_widgets(s): raise RuntimeError("nede")
plan4 = asyncio.run(agent.fetch_week_plan(C4(), N(children=kids), cfg, mon, mon + timedelta(days=4)))
check("Meebook: prøves selvom widget-listen fejler", "Meebook" in plan4["sources"])

# 2c. Ældre opslag markeres som baggrund
since_t = datetime(2030, 11, 8, 12, 0, tzinfo=TZ)
pi = agent.prepare_input([
    {"id": 1, "title": "Temadag", "timestamp": "2030-11-05T14:37:24+00:00", "attachments": [{"name": "program.pdf"}]},
    {"id": 2, "title": "Ny", "timestamp": "2030-11-09T08:00:00+00:00", "attachments": []}], [], since_t, work / "runs" / "pi")
check("Kontekst: gammelt opslag new=false uden download", pi["posts"][0]["new"] is False and pi["posts"][0]["attachments"] == [{"name": "program.pdf"}])
check("Kontekst: nyt opslag new=true", pi["posts"][1]["new"] is True)

g_all = ["5A", "Team 3. - 5. årgang", "Skolen inkl. forældre", "Team 0. - 2. årgang", "0B kontaktforældre", "0B", "B-sporet",
         "5.A Kontaktforældre", "0B (SFO)", "Sydafdelingen (SFO Afd)"]
check("Guide: grupper filtreres efter klasse", agent.groups_for_class(g_all, "5.a") == ["5A", "Team 3. - 5. årgang", "Skolen inkl. forældre", "5.A Kontaktforældre", "Sydafdelingen (SFO Afd)"]
      and agent.groups_for_class(g_all, "0.b") == ["Skolen inkl. forældre", "Team 0. - 2. årgang", "0B kontaktforældre", "0B", "B-sporet", "0B (SFO)", "Sydafdelingen (SFO Afd)"])

# 2d. Omformulerede aftaler skrives ikke igen
it0 = {"key": "aula:1:2030-11-14:moede", "children": ["Emma"], "title": "Kontaktforældremøde", "date": "2030-11-14",
       "end_date": None, "start": None, "end": None, "location": "Hos Testforælder", "notes": "Pizza.", "source": "Tråd"}
st_c, g_c = {"events": {}}, G()
agent.upsert(g_c, "cal", st_c, cfg, it0["key"], it0, "aula", False)
rec0 = st_c["events"][it0["key"]]
check("Gentagelse: state husker sted og noter", rec0.get("location") == "Hos Testforælder" and rec0.get("notes") == "Pizza.")
reworded = dict(it0, notes="Der er noteret pizza til mødet.")
check("Gentagelse: omformuleret uden grund er uændret", agent.aula_unchanged(cfg, rec0, reworded))
check("Gentagelse: med grund opdateres", not agent.aula_unchanged(cfg, rec0, dict(reworded, update_reason="tid aftalt")))
check("Gentagelse: ny tid opdateres", not agent.aula_unchanged(cfg, rec0, dict(it0, start="19:00")))
check("Gentagelse: gammel state uden end-felter virker", agent.aula_unchanged(cfg, {k: v for k, v in rec0.items() if k not in ("end", "end_date")}, reworded))
ex = agent.existing_event({"id": rec0["id"], "subject": "x", "start": {"dateTime": "2030-11-14T00:00"}, "isAllDay": True},
                          {rec0["id"]: it0["key"]}, st_c)
check("Gentagelse: existing_events viser noter", ex["notes"] == "Pizza." and ex["location"] == "Hos Testforælder")
html_r = agent.mail_html(cfg, [("opdateret", dict(it0, update_reason="tid aftalt"))], [], {})
check("Gentagelse: grunden står i mailen", "(opdateret: tid aftalt)" in html_r)

# 2e. Lange tråde skæres til
long_thread = {"thread_id": 9, "subject": "Lang", "participants": [], "regarding_children": [], "messages":
    [{"send_datetime": f"2030-10-{(i % 28) + 1:02d}T08:00:00+00:00", "content_html": f"gammel {i}"} for i in range(100)]
    + [{"send_datetime": "2030-11-09T08:00:00+00:00", "content_html": "ny"}]}
pt = agent.prepare_input([], [long_thread], since_t, work / "runs" / "pt")["threads"][0]
check("Lange tråde: alle nye + 30 ældre", len(pt["messages"]) == 31 and pt["older_messages_omitted"] == 70
      and pt["messages"][-1]["text"] == "ny" and pt["messages"][0]["text"] == "gammel 70")

# 2f. Deltagerlister og billeder sendes ikke til AI'en
th = {"thread_id": 7, "subject": "Fødselsdag", "participant_count": 42, "regarding_children": ["Emma"],
      "participants": ["Anne Hansen (Sofie)"], "messages": [{"send_datetime": "2030-11-09T08:00:00+00:00", "content_html": "Hej"}]}
pth = agent.prepare_input([], [th], since_t, work / "runs" / "pth", cfg)["threads"][0]
check("Deltagere: kun antal, ingen navneliste", pth.get("participant_count") == 42 and "participants" not in pth)
check("Deltagere: egne børn fra config", agent.own_children(cfg, ["Emma Testesen", "Sofie Hansen", "Emma T"]) == ["Emma"])
check("Billeder auto: kort invitation sendes", agent.allow_images("auto", "Emma inviterer til fødselsdag", 1))
check("Billeder auto: fotos fra tur sendes ikke", not agent.allow_images("auto", "Her er billeder fra turen", 2))
check("Billeder auto: mange billeder sendes ikke", not agent.allow_images("auto", "", 4))
check("Billeder auto: lang tekst uden henvisning sendes ikke", not agent.allow_images("auto", "x" * 400, 1))
check("Billeder auto: lang tekst med invitation sendes", agent.allow_images("auto", "x" * 400 + " se invitationen", 1))
check("Billeder never/always", not agent.allow_images("never", "", 1) and agent.allow_images("always", "billeder fra festen", 9))
check("Billeder: standard og ukendt værdi giver text", agent.images_mode({"send_images": "måske"}) == "text" and agent.images_mode(None) == "text"
      and agent.images_mode({"send_images": "auto"}) == "auto")

class FakeHttp:
    def __init__(s): s.urls = []
    def get(s, url):
        s.urls.append(url)
        return N(content=b"x", raise_for_status=lambda: None)
fh = FakeHttp()
att_dir = work / "runs" / "att"; att_dir.mkdir(parents=True, exist_ok=True)
photos = [{"id": i, "name": f"foto{i}.jpg", "file": {"url": f"https://x/{i}"}} for i in range(5)]
res = agent.handle_attachments(photos, att_dir, fh, "Billeder fra juleklip", "auto")
check("Billeder: frasorterede hentes ikke", fh.urls == [] and all(r.get("image_not_sent") for r in res)
      and not any("image_file" in r for r in res))
inv = [{"id": 9, "name": "invitation.png", "file": {"url": "https://x/9"}}]
res2 = agent.handle_attachments(inv, att_dir, fh, "Se invitationen", "auto")
check("Billeder: invitation hentes og sendes", fh.urls == ["https://x/9"] and res2[0].get("image_file") == "attachments/9_invitation.png")
check("Billeder: payload_images springer frasorterede over", agent.payload_images({"a": res + res2}) == ["attachments/9_invitation.png"])

# 2g. Tekst i billeder læses lokalt; kun teksten sendes
fh2 = FakeHttp()
real_ocr = agent.ocr_images
agent.ocr_images = lambda paths: {p: ("Fødselsdag lørdag 5/12 kl. 11" if "invitation" in p.name else "") for p in paths}
mixed = [{"id": 1, "name": "invitation.png", "file": {"url": "https://x/1"}}, {"id": 2, "name": "foto.jpg", "file": {"url": "https://x/2"}}]
res3 = agent.handle_attachments(mixed, att_dir, fh2, "Hej alle", "text")
by = {r["name"]: r for r in res3}
check("OCR: tekst fra invitation sendes som image_text", by["invitation.png"].get("image_text") == "Fødselsdag lørdag 5/12 kl. 11")
check("OCR: foto uden tekst sendes ikke", "image_text" not in by["foto.jpg"] and by["foto.jpg"].get("image_not_sent"))
check("OCR: selve billederne sendes aldrig og slettes straks", not any("image_file" in r for r in res3)
      and all(r.get("image_not_sent") for r in res3) and not list(att_dir.glob("1_invitation.png")) and not list(att_dir.glob("2_foto.jpg")))
agent.ocr_images = lambda paths: None
res4 = agent.handle_attachments(mixed, att_dir, FakeHttp(), "Hej alle", "text")
check("OCR: uden OCR sendes hverken billede eller tekst", all(r.get("image_not_sent") and "image_text" not in r and "image_file" not in r for r in res4)
      and not list(att_dir.glob("1_invitation.png")))
many = [{"id": i, "name": f"f{i}.jpg", "file": {"url": f"https://x/{i}"}} for i in range(25)]
fh3 = FakeHttp()
agent.handle_attachments(many, att_dir, fh3, "", "text")
check("OCR: uden OCR får AI'en en note, og forælderen en besked", all("kunne ikke læses" in r.get("note", "") for r in res4)
      and "blev ikke læst" in (agent.ocr_problem() or "") and str(len(res4)) in agent.ocr_problem())
agent._ocr_state.clear()
check("OCR: ingen besked, når alt virker", agent.ocr_problem() is None)
agent._ocr_state["warned"] = True
check("OCR: besked når dansk mangler", "dansk tekstgenkendelse" in agent.ocr_problem())
agent._ocr_state.clear()
check("OCR: højst 10 billeder hentes pr. opslag", len(fh3.urls) == agent.IMAGE_TEXT_MAX_FILES)
check("OCR: uden Windows findes OCR ikke (None)", agent.sys.platform == "win32" or real_ocr([att_dir / "x.png"]) is None)

# 2g. Navne på andre end familien får dæknavne og sættes tilbage i svaret
ncfg = {"parent": {"name": "Anders Bech"}, "children": [{"name": "Emma", "label": "Emma 2.a", "class": "2.a"},
                                                     {"name": "Oscar", "label": "Oscar 0.b", "class": "0.b"}]}
nm = agent.NameMask(ncfg, [("Hugo Jensen", "child"), ("Louise Holm Hansen (Hugo 1.B)", "guardian"), ("Hans Skov", "guardian"),
                           ("Ida Lund", "child"), ("Ida Bak", "child"), ("Mette Dam", "employee"), ("Oscar Olsen", "child")])
npl = {"posts": [{"author": "Mette Dam", "author_role": "employee", "date": "2030-11-09", "key": "aula:1:hugo",
                  "text": "Hans mor kommer. Vi mødes med Hans Skov og Ida Lund. Ida og Oscar kommer også."}],
       "threads": [{"subject": "Hugos fødselsdag", "messages": [
           {"sender": "Louise Holm Hansen", "text": "Hugo fylder 7. Hilsen Louise og Karen Ny"}]},
           {"subject": "Svar", "messages": [{"sender": "Karen Ny", "text": "Vi kommer"}]}]}
nm.add_from_payload(npl)
nx = nm.mask(npl)
ntext = json.dumps(nx, ensure_ascii=False)
check("Navne: børn, forældre og medarbejdere får dæknavne", not any(n in ntext for n in ("Hugo", "Louise", "Skov", "Ida", "Mette", "Karen")))
check("Navne: rollen fremgår af dæknavnet", nx["posts"][0]["author"].startswith("Medarbejder ") and nx["threads"][0]["messages"][0]["sender"].startswith("Forælder "))
check("Navne: ejefald bevares", re.fullmatch(r"Barn \d+s fødselsdag", nx["threads"][0]["subject"]) is not None)
check("Navne: et af familiens fornavne skjules også, når en anden har det", "Oscar" not in nx["posts"][0]["text"])
check("Navne: 'Hans' først i en sætning er ikke et navn", nx["posts"][0]["text"].startswith("Hans mor"))
check("Navne: samme person får samme dæknavn", nx["threads"][0]["messages"][0]["sender"] in nx["threads"][0]["messages"][0]["text"])
check("Navne: nøgler og datoer røres ikke", nx["posts"][0]["key"] == "aula:1:hugo" and nx["posts"][0]["date"] == "2030-11-09")
hugo = nx["threads"][0]["subject"].split("s fød")[0]
back = nm.restore({"title": f"{hugo}s fødselsdag", "notes": f"{nx['threads'][0]['messages'][0]['sender']} inviterer.", "key": "aula:1:barn-1"})
check("Navne: sættes tilbage i svaret", back["title"] == "Hugos fødselsdag" and back["notes"] == "Louise inviterer." and back["key"] == "aula:1:barn-1")
check("Navne: to med samme fornavn holdes adskilt", sorted(v for v in nm.back.values() if v.startswith("Ida")) == ["Ida", "Ida Lund"])
check("Navne: uden navneliste ændres intet", agent.NameMask(ncfg, []).mask({"t": "Hugo kommer"}) == {"t": "Hugo kommer"})

# 2h. Gruppelister i Aulas nuværende form (én post pr. rolle med institutionProfiles) og tavs fejl
real_shape = [
    {"portalRole": "child", "institutionProfiles": [{"id": 1, "fullName": "Hugo Jensen"}, {"id": 2, "fullName": "Liv Kjær"}]},
    {"portalRole": "guardian", "institutionProfiles": [{"id": 3, "fullName": "Louise Holm Hansen"}]},
    {"portalRole": "employee", "institutionProfiles": [{"id": 4, "fullName": "Mette Dam"}, {"id": 5, "name": ""}]},
]
pg = agent.parse_group_members(real_shape)
check("Gruppeliste: nuværende form giver navne og roller",
      pg == [("Hugo Jensen", "child"), ("Liv Kjær", "child"), ("Louise Holm Hansen", "guardian"), ("Mette Dam", "employee")])
check("Gruppeliste: ældre form (én post pr. person) læses stadig",
      agent.parse_group_members([{"institutionProfileId": 7, "fullName": "Emma Lund", "portalRole": "child"}]) == [("Emma Lund", "child")])
check("Gruppeliste: for- og efternavn i hver sit felt", agent.parse_group_members(
    [{"portalRole": "guardian", "institutionProfiles": [{"firstName": "Karen", "lastName": "Ny"}]}]) == [("Karen Ny", "guardian")])
check("Gruppeliste: uventet indhold giver tom liste og ingen fejl",
      agent.parse_group_members(None) == [] and agent.parse_group_members(["x", 3, {"a": 1}]) == [])


class FakeResp:
    def __init__(self, data): self._d = data
    def raise_for_status(self): pass
    def json(self): return {"data": self._d}


class FakeAulaClient:
    api_url = "https://aula/api"

    def __init__(self, members, fail=()):
        self.members, self.fail, self.calls = members, set(fail), []

    async def get_groups(self, child_institution_profile_ids): return [type("G", (), {"id": 1, "name": "1B"})(),
                                                                       type("G", (), {"id": 2, "name": "Nord"})()]

    async def _request_with_version_retry(self, method, url, params=None):
        self.calls.append(params)
        if params["groupId"] in self.fail:
            raise RuntimeError("fejl")
        return FakeResp(self.members)


fake_prof = type("P", (), {"children": [type("C", (), {"id": 11})()]})()
fc = FakeAulaClient(real_shape)
got = asyncio.run(agent.fetch_people(fc, fake_prof))
check("fetch_people: henter direkte fra groups.getMembershipsLight", len(got) == 8 and all(c["method"] == "groups.getMembershipsLight" for c in fc.calls))
check("fetch_people: ingen advarsel, når der hentes navne", agent._names_state["warning"] is None)
got0 = asyncio.run(agent.fetch_people(FakeAulaClient([{"role": "x"}]), fake_prof))
check("fetch_people: 0 navne giver en advarsel til ugemailen", got0 == [] and "ingen navne" in agent._names_state["warning"])
gotf = asyncio.run(agent.fetch_people(FakeAulaClient(real_shape, fail=(1, 2)), fake_prof))
check("fetch_people: alle grupper fejler giver også advarsel", gotf == [] and agent._names_state["warning"])
agent._names_state["warning"] = None

# Fornavne, der også er ord: kun "Hans" og de få andre springes over, og kun uden efternavn
nm2 = agent.NameMask(ncfg, [("Liv Kjær", "child"), ("Hans Skov", "guardian"), ("Line Moe", "guardian"), ("Rune Bro", "child")])
t2 = nm2.mask_text("Liv kommer. Line og Rune er med. Hans mor henter. Hans Skov henter også. Mark kommer.")
check("Navne: almindelige fornavne som Liv, Line og Rune skjules også først i en sætning",
      all(n not in t2 for n in ("Liv", "Line", "Rune", "Skov")))
check("Navne: 'Hans mor' springes stadig over, men 'Hans Skov' skjules", "Hans mor henter" in t2 and t2.count("Hans") == 1)
check("Navne: sætningsstart efter mellemrum og linjeskift virker ens", nm2._sentence_start("a.  ", 4) and nm2._sentence_start("a.\n", 3)
      and not nm2._sentence_start("a og ", 5))

# Efternavne: også når hele navnet ikke står på listerne, og når efternavnet står alene
nm4 = agent.NameMask(ncfg, [("Simon Hansen", "child"), ("Anne Jensen", "guardian"), ("Anne Skov", "guardian"),
                            ("Ida Hansen", "guardian"), ("Mette Kirk", "employee"), ("Rasmus Lind", "child")])
src4 = ("Anne Hansen henter Simon. Dansk med Kirk. Fru Jensen kommer, og Hansens bil holder ude. "
        "Skov og strand i morgen. Vi ses hos Skov. Familien Lind kommer. Ida Marie Hansen ringer.")
t4 = nm4.mask_text(src4)
check("Efternavne: fornavn + kendt efternavn skjules, selvom hele navnet ikke står på listerne",
      "Anne Hansen" not in t4 and t4.startswith("Person "))
check("Efternavne: alene skjules (efter 'med', 'Fru' og i ejefald)", all(n not in t4 for n in ("Kirk", "Jensen", "Hansen")))
check("Efternavne: rollen følger efternavnet, når den er entydig", re.search(r"med Medarbejder \d+\.", t4) is not None)
check("Efternavne: ord som 'Skov' først i en sætning skjules ikke, men gør midt i en sætning",
      "Skov og strand" in t4 and "hos Skov" not in t4)
check("Efternavne: også familiens efternavn skjules", "Lind" not in t4)
check("Efternavne: alt sættes tilbage, som det stod", nm4.restore({"t": t4})["t"] == src4)

# Familien får faste dæknavne. Fornavn alene er kun familiens, når sammenhængen siger det
fam_people = [("Emma Bech", "child"), ("Oscar Bech", "child"), ("Anders Bech", "guardian"), ("Oscar Holt", "child"),
              ("Emma Lind", "child"), ("Anders Krog", "guardian"), ("Lone Dahl", "guardian"), ("Sofie Dahl", "child")]
fam_info = {"parent": "Anders Bech", "children": ["Emma Bech", "Oscar Bech"]}
fam_groups = {"2A": ["Emma Bech", "Sofie Dahl"], "0B": ["Oscar Bech", "Oscar Holt"], "3A": ["Emma Lind"],
              "Alle forældre": ["Anders Bech", "Anders Krog", "Lone Dahl"]}
fam_part = {1: ["Anders Bech", "Lone Dahl (Sofie 2A)"], 2: ["Anders Bech", "Anders Krog (Oscar 0B)"]}
fpl = {
    "today": "2030-11-10",
    "children": [{"name": "Emma", "label": "Emma 2.a", "class": "2.a", "aula_groups": ["2A"]},
                 {"name": "Oscar", "label": "Oscar 0.b", "class": "0.b", "aula_groups": ["0B"]}],
    "posts": [{"groups": ["2A"], "author": "Lone Dahl", "text": "Emma skal have idrætstøj med."},
              {"groups": ["3. årgang"], "author": "Lone Dahl", "text": "Emma fra 3.a har fødselsdag."},
              {"groups": ["0B"], "author": "Lone Dahl", "text": "Oscar kommer også."}],
    "threads": [{"thread_id": 1, "subject": "Tur", "regarding_children": ["Emma"], "messages": [
                    {"sender": "Anders Bech", "text": "Hej Anders. Emma er syg. Emma Bech har feber."}]},
                {"thread_id": 2, "subject": "Møde", "regarding_children": [], "messages": [
                    {"sender": "Anders Krog", "text": "Hej Anders. Familien Bech er inviteret."}]}],
    "existing_events": [{"key": "aula:1:x", "subject": "[Oscar 0.b] Fri", "notes": ""}],
    "week_plan": {"children": {"Emma": {"huskeliste": [{"tekst": "Kage: Emma"}]}, "Oscar": {"huskeliste": []}}},
}
fm = agent.NameMask(ncfg, fam_people, fam_info, fam_groups, fam_part)
fm.add_from_payload(fpl)
fx = fm.mask_payload(copy.deepcopy(fpl))
ftext = json.dumps(fx, ensure_ascii=False)
check("Familie: ingen af familiens navne i det, der sendes", not any(n in ftext for n in ("Emma", "Oscar", "Anders", "Bech")))
check("Familie: fornavn alene i et opslag til klassen er eget barn", fx["posts"][0]["text"] == "Eget barn 1 (2.a) skal have idrætstøj med.")
check("Familie: fornavn alene i et opslag til en anden klasse får fælles dæknavn",
      re.fullmatch(r"Barn \d+ fra 3\.a har fødselsdag\.", fx["posts"][1]["text"]) is not None)
check("Familie: en anden i klassen med samme fornavn giver fælles dæknavn", re.fullmatch(r"Barn \d+ kommer også\.", fx["posts"][2]["text"]) is not None)
th1 = fx["threads"][0]
check("Familie: forælderen som afsender og i tråden", th1["messages"][0]["sender"] == "Forælderen"
      and th1["messages"][0]["text"] == "Hej Forælderen. Eget barn 1 (2.a) er syg. Eget barn 1 (2.a) har feber.")
check("Familie: regarding_children får dæknavn", th1["regarding_children"] == ["Eget barn 1 (2.a)"])
check("Familie: forælderens fornavn er fælles, når en anden deltager har det",
      re.fullmatch(r"Hej Forælder \d+\. Familien (Person|Forælder|Barn) \d+ er inviteret\.", fx["threads"][1]["messages"][0]["text"]) is not None)
check("Familie: kalenderens mærke bliver dæknavn", fx["existing_events"][0]["subject"] == "[Eget barn 2 (0.b)] Fri")
check("Familie: ugeplanen pr. barn under dæknavn", sorted(fx["week_plan"]["children"]) == ["Eget barn 1 (2.a)", "Eget barn 2 (0.b)"]
      and fx["week_plan"]["children"]["Eget barn 1 (2.a)"]["huskeliste"][0]["tekst"] == "Kage: Eget barn 1 (2.a)")
check("Familie: børnenes oplysninger under dæknavn", [c["name"] for c in fx["children"]] == ["Eget barn 1 (2.a)", "Eget barn 2 (0.b)"]
      and fx["children"][0]["label"] == "Eget barn 1 (2.a)" and fx["children"][0]["aula_groups"] == ["2A"])
fres = fm.restore({"calendar": [{"key": "aula:1:x", "children": ["Eget barn 1 (2.a)"], "title": "Eget barn 1 (2.a)s fødselsdag",
                                 "notes": "Forælderen skal bage. Eget barn 2 tager med."}],
                   "husk": [{"children": ["Eget barn 2 (0.b)", "eget barn 1"], "text": "Kage: Eget Barn 1 (2.a)"}],
                   "fri": [{"children": [fx["posts"][1]["text"].split(" fra")[0]]}]})
check("Familie: sættes tilbage i children, titel og noter", fres["calendar"][0]["children"] == ["Emma"]
      and fres["calendar"][0]["title"] == "Emmas fødselsdag" and fres["calendar"][0]["notes"] == "Anders skal bage. Oscar tager med.")
check("Familie: tåler små variationer i dæknavnet", fres["husk"][0]["children"] == ["Oscar", "Emma"] and fres["husk"][0]["text"] == "Kage: Emma")
check("Familie: fælles dæknavn sættes tilbage som fornavnet", fres["fri"][0]["children"] == ["Emma"])
solo = agent.NameMask(ncfg, [("Emma Bech", "child")], fam_info)
check("Familie: entydigt fornavn er altid eget barn, også uden sammenhæng", solo.mask_text("Oscar og Emma kommer") == "Eget barn 2 (0.b) og Eget barn 1 (2.a) kommer")
check("Familie: uden Aulas fulde navne virker fornavnene stadig", agent.NameMask(ncfg, []).mask_text("Emma") == "Eget barn 1 (2.a)")
fsec = agent.family_section({**ncfg, "parent": {"name": "Anders Bech", "role": "far", "contact_parent_in": ["2.a"]},
                             "family_notes": ["Oscar går til fodbold om tirsdagen"]}, solo)
check("Familie: familieafsnittet uden navne", not any(n in fsec for n in ("Emma", "Oscar", "Anders", "Bech"))
      and "**Eget barn 1 (2.a)** går i **2.a**" in fsec and "Forælderen er kontaktforælder i: 2.a" in fsec
      and "Eget barn 2 (0.b) går til fodbold" in fsec)
check("Familie: uden navneskjul står navnene som før", "Forælderen hedder Anders Bech" in agent.family_section(
    {**ncfg, "parent": {"name": "Anders Bech"}}))

# Mailadresser, telefonnumre og adresser får dæknavne og sættes ind igen
cm = agent.NameMask(ncfg, [("Lone Dahl", "guardian")])
csrc = ("Fødselsdag lørdag kl. 14 på Strandvejen 12, 3140 Ålsgårde. Svar til Lone på 12 34 56 78 eller lone.dahl@mail.dk. "
        "Ring evt. 1234 5678, +45 87654321 eller 22 333 444. Vi bor på Kirkebakken 4B, 1. th. "
        "Mødet er kl. 10.00-12.00 den 25.11.2026 (uge 48), lokale 307, 2026-11-25. Igen: 12 34 56 78.")
ctext = cm.mask_text(csrc)
check("Kontakt: mail, telefon og adresse sendes ikke", not any(x in ctext for x in (
    "Strandvejen", "3140", "12 34 56 78", "lone.dahl", "1234 5678", "87654321", "22 333 444", "Kirkebakken")))
check("Kontakt: dæknavne som Mail, Telefon og Adresse", "på Adresse 1. Svar til" in ctext and "Telefon 1 eller Mail 1" in ctext
      and "Vi bor på Adresse 2" in ctext)
check("Kontakt: samme nummer får samme dæknavn", ctext.endswith("Igen: Telefon 1."))
check("Kontakt: klokkeslæt, datoer, uger og lokaler røres ikke",
      "kl. 10.00-12.00 den 25.11.2026 (uge 48), lokale 307, 2026-11-25" in ctext and "kl. 14" in ctext)
check("Kontakt: navnet skjules stadig", "Lone" not in ctext)
check("Kontakt: alt sættes tilbage, som det stod", cm.restore({"t": ctext})["t"] == csrc)
cres = cm.restore({"calendar": [{"key": "aula:1:x", "location": "Adresse 1", "notes": "Svar på Telefon 1 eller Mail 1."}]})
check("Kontakt: sættes ind igen i sted og noter", cres["calendar"][0]["location"] == "Strandvejen 12, 3140 Ålsgårde"
      and cres["calendar"][0]["notes"] == "Svar på 12 34 56 78 eller lone.dahl@mail.dk.")
check("Kontakt: virker også uden navnelister", agent.NameMask({}, []).mask_text("Tlf. 12345678") == "Tlf. Telefon 1")

# Eksisterende aftalers key (med fornavne i sluggen) sendes ikke til AI'en
nm3 = agent.NameMask(ncfg, [("Hugo Jensen", "child")])
kp = {"existing_events": [{"key": "aula:12:2030-12-05:hugos-foedselsdag", "subject": "Hugos fødselsdag"},
                          {"key": None, "subject": "Møde"}], "posts": []}
nm3.opaque_keys(kp)
kp = nm3.mask(kp)
check("Navne: key sendes som neutral reference", kp["existing_events"][0]["key"] == "aula:ref-1" and "hugo" not in json.dumps(kp, ensure_ascii=False).lower())
res_k = {"calendar": [{"key": "aula:ref-1", "title": "x"}, {"key": "aula:99:ny", "title": "y"}]}
nm3.restore_keys(res_k)
check("Navne: key sættes tilbage, nye keys røres ikke", res_k["calendar"][0]["key"] == "aula:12:2030-12-05:hugos-foedselsdag"
      and res_k["calendar"][1]["key"] == "aula:99:ny")

# Hele vejen gennem run_ai: det, der sendes, er skjult; det, der kommer tilbage, er sat ind igen
sent = {}
def _fake_cc(c, prompt, d):
    sent["prompt"] = prompt
    return ('```json\n{"calendar": [{"key": "aula:ref-1", "children": ["Eget barn 1 (2.a)"], "title": "Barn 1s fødselsdag", '
            '"date": "2030-12-05"}], "weekly_mail": [], "fri": [], "husk": []}\n```')
orig_cc, orig_state = agent.run_claude_code, dict(agent._names_state)
agent.run_claude_code = _fake_cc
agent._names_state["people"] = [("Hugo Jensen", "child")]
rd = work / "run_e2e"; rd.mkdir(exist_ok=True)
e2e_cfg = {**cfg, "ai_mode": "claude-code", "hide_names": True}
e2e = agent.run_ai(e2e_cfg, {"children": cfg["children"], "posts": [{"author": "Mette Dam", "text": "Hugo har fødselsdag, Emma kommer. Ring 12345678", "date": "2030-11-01"}], "threads": [],
                             "existing_events": [{"key": "aula:12:2030-12-05:hugos-foedselsdag", "subject": "Hugos fødselsdag"}]}, rd)
agent.run_claude_code = orig_cc
agent._names_state.clear(); agent._names_state.update(orig_state)
check("run_ai: ingen navne eller numre i prompten, heller ikke familiens", all(n not in sent["prompt"] for n in (
    "Hugo", "Mette", "Dam", "hugos-foedselsdag", "Emma", "Oscar", "Testforælder", "12345678")) and '"children": ["Eget barn 1 (2.a)"]' in sent["prompt"])
check("run_ai: egne børn sættes tilbage i children", e2e["calendar"][0]["children"] == ["Emma"])
check("run_ai: titel og key sættes tilbage i svaret", e2e["calendar"][0]["title"] == "Hugos fødselsdag"
      and e2e["calendar"][0]["key"] == "aula:12:2030-12-05:hugos-foedselsdag")

# 3. weekly med husk, og med login-fejl i begge tilstande
agent.sync_feeds = lambda *a: {"ny": 0}
agent.sync_manual = lambda *a: None
agent.RUNS_DIR = work / "runs"
agent.now_local = lambda: datetime(2030, 11, 10, 7, 0, tzinfo=TZ)


fetch_args = {}
async def fake_fetch(c, since, week, context_since=None):
    fetch_args.update(since=since, ctx=context_since)
    return [], [], plan
agent.aula_fetch = fake_fetch

g = G(); agent.connect_graph = lambda c, s: g
seen_payload = {}
def _fake_claude(c, p, d):
    seen_payload.update(p)
    return {"calendar": [], "weekly_mail": [], "husk": [
    {"date": "2030-11-12", "children": ["Emma"], "text": "Tur til skoven. Idræt (idrætstøj).", "source": "Ugeplan"}]}
agent.run_ai = _fake_claude
_unused = lambda c, p, d: {"calendar": [], "weekly_mail": [], "husk": [
    {"date": "2030-11-12", "children": ["Emma"], "text": "Tur til skoven. Idræt (idrætstøj).", "source": "Ugeplan"}]}
state = {"events": {}}
rc = agent.cmd_weekly(cfg, state, False, None)
subj, html = g.mails[-1]
check("Weekly: rå data og widgets sendes ikke til Claude", all(k not in (seen_payload.get("week_plan") or {}) for k in ("raw", "widgets")))
check("Weekly: fri fra skemaet, når Claude ikke giver fri", "<li>[Emma 2.a] Tur til skoven. Idræt (idrætstøj). Fri kl. 10.45.</li>" in g.mails[-1][1])
check("Weekly: baggrund hentes fra 10 dage før skoleugen", fetch_args["ctx"] == datetime(2030, 11, 1, 0, 0, tzinfo=TZ))
agent._names_state["warning"] = "Navneskjulning: test-advarsel om 0 navne."
rc_w = agent.cmd_weekly(cfg, {"events": {}}, False, None)
check("Weekly: advarsel om 0 hentede navne står i ugemailen", "test-advarsel om 0 navne" in g.mails[-1][1] and rc_w == 1)
agent._names_state["warning"] = "Navneskjulning: skal ikke vises."
rc_w2 = agent.cmd_weekly({**cfg, "hide_names": False}, {"events": {}}, False, None)
check("Weekly: ingen navneadvarsel, når skjulning er slået fra", "Navneskjulning" not in g.mails[-1][1])

# 3b. Aftaler fra kalenderen står på dagen i "Husk i ugen", uanset om de er nye
def cev(subject, start, end=None, allday=False):
    return {"id": "e" + subject[:6] + start, "subject": subject, "start": {"dateTime": start + ".0000000"}, "end": {"dateTime": (end or start) + ".0000000"},
            "isAllDay": allday}
evs = [cev("[Emma 2.a] Skole-hjem-samtale", "2030-11-12T14:20:00", "2030-11-12T14:40:00"),
       cev("[Emma 2.a + Oscar 0.b] Forældremøde", "2030-11-13T19:00:00", "2030-11-13T20:30:00"),
       cev("[Oscar 0.b] Temadag", "2030-11-14T00:00:00", "2030-11-16T00:00:00", allday=True),
       cev("[Emma 2.a] Før vinduet", "2030-11-08T10:00:00", "2030-11-08T11:00:00"),
       cev("[Emma 2.a] Efter ugen", "2030-11-20T10:00:00", "2030-11-20T11:00:00"),
       cev("Uden mærke", "2030-11-12T10:00:00", "2030-11-12T11:00:00"),
       cev("[Ukendt 9.z] Fremmed barn", "2030-11-12T10:00:00", "2030-11-12T11:00:00"),
       cev("[Emma 2.a] Skole-hjem-samtale", "2030-11-12T14:20:00", "2030-11-12T14:40:00")]
cn = agent.calendar_day_notes(cfg, evs, date(2030, 11, 10), date(2030, 11, 15))
check("Kalender: tid og titel på dagen for det rigtige barn", cn["2030-11-12"]["Emma"] == [("kl. 14.20 Skole-hjem-samtale", "Skole-hjem-samtale")])
check("Kalender: fælles mærke giver aftalen til begge børn", cn["2030-11-13"]["Emma"][0][0] == "kl. 19.00 Forældremøde" and cn["2030-11-13"]["Oscar"][0][0] == "kl. 19.00 Forældremøde")
check("Kalender: heldagsaftale over flere dage kommer på hver dag i vinduet", cn["2030-11-14"]["Oscar"][0][0] == "Temadag" and cn["2030-11-15"]["Oscar"][0][0] == "Temadag" and "2030-11-16" not in cn)
check("Kalender: aftaler uden for ugen, uden mærke eller for ukendt barn tages ikke med",
      "2030-11-08" not in cn and "2030-11-20" not in cn and len(cn["2030-11-12"]) == 1)
check("Kalender: dublet-aftale vises kun én gang", len(cn["2030-11-12"]["Emma"]) == 1)
html_cal = agent.mail_html(cfg, [], [], {}, None, [], None, [], cn)
check("Kalender: mailen viser aftalerne på dagen, også uden husk og fri",
      "<b>Tirsdag 12/11</b>" in html_cal and "[Emma 2.a] <b>Kl. 14.20 Skole-hjem-samtale.</b>" in html_cal
      and "<b>Kl. 19.00 Forældremøde.</b>" in html_cal and "[Oscar 0.b] <b>Temadag.</b>" in html_cal)
html_dup = agent.mail_html(cfg, [], [], {}, None, [{"date": "2030-11-12", "children": ["Emma"], "text": "Skole-hjem-samtale kl. 14.20, husk skemaet."}], None, [], cn)
check("Kalender: ikke dobbelt, når teksten allerede nævner aftalen", html_dup.count("Skole-hjem-samtale") == 1)
check("Kalender: uden aftaler ændres mailen ikke", "Husk i ugen" not in agent.mail_html(cfg, [], [], {}, None, [], None, [], {}))
evs.append(cev("[Oscar 0.b] Fødselsdag hos Mille", "2030-11-16T13:00:00", "2030-11-16T16:00:00"))
evs.append(cev("[Emma 2.a] Efter weekenden", "2030-11-18T13:00:00", "2030-11-18T16:00:00"))
g.list_events = lambda *a: evs
agent._names_state["warning"] = None
rc_c = agent.cmd_weekly(cfg, {"events": {}}, False, None)
check("Weekly: kalenderens aftaler står på dagen i den sendte mail", "Kl. 14.20 Skole-hjem-samtale." in g.mails[-1][1] and "Tirsdag 12/11" in g.mails[-1][1])
check("Weekly: weekendens aftaler kommer med, dagen efter weekenden gør ikke", "Kl. 13.00 Fødselsdag hos Mille." in g.mails[-1][1] and "Efter weekenden" not in g.mails[-1][1])
def _bad_list(*a): raise RuntimeError("Graph nede")
g.list_events = _bad_list
n_mails = len(g.mails)
agent.cmd_weekly(cfg, {"events": {}}, False, None)
check("Weekly: kalenderen kan ikke læses giver stadig en ugemail", len(g.mails) == n_mails + 1)
g.list_events = lambda *a: []
agent._names_state["warning"] = None
check("Weekly: vedhæftninger slettet efter kørslen", not any((d / "attachments").exists() for d in (work / "runs").iterdir() if d.is_dir() and d.name[:2] == "20"))
html_today = agent.mail_html(cfg, [], [], {}, None, [{"date": "2030-11-10", "children": ["Emma"], "text": "Lektie til mandag: Læs side 12."}], None, [])
check("Lektier: søndag vises som i dag", "Søndag 10/11 (i dag)" in html_today and "Lektie til mandag" in html_today)
check("Mail: kalender-links kun nævnt, når der er links",
      "Kalender-links" not in agent.mail_html(dict(cfg, feeds=[]), [], [], {}) and "Kalender-links" in agent.mail_html(dict(cfg, feeds=[{"url": "x"}]), [], [], {}))
check("Lektier: i morgen bliver til ugedag", agent.lektie_weekday("Tur. Lektie til i morgen: Kap 3.", "2030-11-13") == "Tur. Lektie til torsdag: Kap 3."
      and agent.lektie_weekday("Lektie til i morgen: x", "2030-11-10") == "Lektie til mandag: x")
html_lk = agent.mail_html(cfg, [], [], {}, None, [
    {"date": "2030-11-13", "children": ["Emma"], "text": "Tur til skoven. Lektie til i morgen: Kap. 3 + opgaver."},
    {"date": "2030-11-13", "children": ["Oscar"], "type": "lektie", "text": "Lektie til torsdag: Læs side 4"}], None,
    [{"date": "2030-11-13", "children": ["Emma"], "time": "13:40"}, {"date": "2030-11-13", "children": ["Oscar"], "time": "12:00"}])
check("Lektier: egen linje efter fri", "<li>[Emma 2.a] Tur til skoven. Fri kl. 13.40.<br>Lektie til torsdag: Kap. 3 + opgaver.</li>" in html_lk
      and "<li>[Oscar 0.b] Fri kl. 12.00.<br>Lektie til torsdag: Læs side 4.</li>" in html_lk)
check("Weekly: emne med kommende uge og husk", subj == "Aula-agent uge 46: 0 aftaler, 1 ting at huske")
check("Weekly: huskeliste i mailen", "Husk i ugen" in html and "Tirsdag 12/11" in html and "[Emma 2.a]" in html)
check("Weekly: ingen fejl, last_weekly sat", rc == 0 and state.get("last_weekly"))

# Claude Code: udløbet login
cfg_cc = dict(cfg, ai_mode="claude-code")
fake_out = json.dumps({"is_error": True, "result": "OAuth session expired and could not be refreshed"})
orig_run = subprocess.run
agent.shutil.which = lambda x: "/bin/claude"
agent.subprocess.run = lambda *a, **k: N(returncode=1, stdout=fake_out, stderr="")
agent.run_ai = agent.__dict__["run_ai"]  # placeholder, genindlæses nedenfor
import importlib  # noqa: E402
real = importlib.reload(agent)
real.sync_feeds = lambda *a: {"ny": 0}; real.sync_manual = lambda *a: None
real.RUNS_DIR = work / "runs"; real.now_local = lambda: datetime(2030, 11, 10, 7, 0, tzinfo=TZ)
real.aula_fetch = fake_fetch
real.shutil.which = lambda x: "/bin/claude"
real.subprocess.run = lambda *a, **k: N(returncode=1, stdout=fake_out, stderr="")
g = G(); real.connect_graph = lambda c, s: g
state = {"events": {}}
rc = real.cmd_weekly(cfg_cc, state, False, None)
subj, html = g.mails[-1]
check("Claude Code-login: mail med fejlboks og /login-vejledning", "(fejl, handling krævet)" in subj and "/login" in html)
check("Claude Code-login: last_weekly ikke flyttet", rc == 1 and "last_weekly" not in state)

# API: 401
real.httpx.post = lambda *a, **k: N(status_code=401, text="invalid x-api-key", headers={})
cfg_api = dict(cfg, ai_mode="api", anthropic_api_key="sk-ant-test")
g = G(); real.connect_graph = lambda c, s: g
state = {"events": {}}
rc = real.cmd_weekly(cfg_api, state, False, None)
subj, html = g.mails[-1]
check("API 401: mail med vejledning om ny nøgle", "(fejl, handling krævet)" in subj and "console.anthropic.com" in html)

# OpenAI API: 401
cfg_oa = dict(cfg, ai_mode="openai-api", openai_api_key="sk-proj-test")
g = G(); real.connect_graph = lambda c, s: g
rc = real.cmd_weekly(cfg_oa, {"events": {}}, False, None)
subj, html = g.mails[-1]
check("OpenAI 401: mail med vejledning om ny nøgle", "(fejl, handling krævet)" in subj and "platform.openai.com" in html
      and "OpenAI kunne ikke logge ind" in html)

# Codex: ikke logget ind
real.find_codex = lambda c: "/bin/codex"
def codex_logged_out(args, **kw):
    if args[1:] == ["--version"]:
        return N(returncode=0, stdout="codex-cli 0.167.0", stderr="")
    return N(returncode=1, stdout='{"type":"error","message":"Not logged in"}', stderr="")
real.subprocess.run = codex_logged_out
g = G(); real.connect_graph = lambda c, s: g
state = {"events": {}}
rc = real.cmd_weekly(dict(cfg, ai_mode="codex"), state, False, None)
subj, html = g.mails[-1]
check("Codex-login: mail med codex login-vejledning", "(fejl, handling krævet)" in subj and "codex login" in html
      and "ChatGPT kunne ikke logge ind" in html and "last_weekly" not in state)

# OpenAI API: billedværktøj, ingen lagring hos OpenAI, standardmodel og pris
from PIL import Image  # noqa: E402
rdo = work / "runs" / "openai"; (rdo / "attachments").mkdir(parents=True)
Image.new("RGB", (50, 50), "blue").save(rdo / "attachments" / "a.png")
bodies = []
REPLIES = [
    {"status": "completed", "usage": {"input_tokens": 1000, "output_tokens": 50, "input_tokens_details": {"cached_tokens": 0}},
     "output": [{"type": "reasoning", "id": "r1", "encrypted_content": "x"},
                {"type": "function_call", "call_id": "c1", "name": "laes_billede", "arguments": '{"image_file": "attachments/a.png"}'}]},
    {"status": "completed", "usage": {"input_tokens": 1500, "output_tokens": 100, "input_tokens_details": {"cached_tokens": 1000}},
     "output": [{"type": "message", "content": [{"type": "output_text", "text": '```json\n{"calendar": []}\n```'}]}]},
]
def fake_post(url, headers=None, json=None, timeout=None):
    bodies.append((url, headers, __import__("json").loads(__import__("json").dumps(json))))
    return N(status_code=200, json=lambda: REPLIES.pop(0), headers={}, text="")
real.httpx.post = fake_post
text = real.run_openai_api({"openai_api_key": "sk-proj-test"}, "prompt", rdo)
u, h, b1 = bodies[0]; _, _, b2 = bodies[1]
check("OpenAI: Responses API med nøgle i header", u == "https://api.openai.com/v1/responses" and h["authorization"] == "Bearer sk-proj-test")
check("OpenAI: GPT-6.1 Sol på high som standard", b1["model"] == "gpt-6.1-sol" and b1["reasoning"] == {"effort": "high"})
check("OpenAI: gemmes ikke hos OpenAI", b1["store"] is False and "reasoning.encrypted_content" in b1["include"])
check("OpenAI: billedværktøjet tilbydes", b1["tools"][0]["name"] == "laes_billede" and b1["tools"][0]["type"] == "function")
out_item = b2["input"][-1]
check("OpenAI: billedet sendes som input_image", out_item["type"] == "function_call_output" and out_item["call_id"] == "c1"
      and out_item["output"][0]["type"] == "input_image" and out_item["output"][0]["image_url"].startswith("data:image/jpeg;base64,"))
check("OpenAI: tænkning sendes med tilbage", any(i.get("type") == "reasoning" for i in b2["input"]))
use = __import__("json").loads((rdo / "ai_usage.json").read_text(encoding="utf-8"))
check("OpenAI: svar og pris", '"calendar"' in text and use["images"] == 1 and abs(use["estimated_usd"] - (1500 * 2 + 1000 * 0.10 + 150 * 10) / 1e6) < 1e-9)

# OpenAI API: fejlet svar og tomt svar giver tydelige fejl
REPLIES[:] = [{"status": "failed", "error": {"message": "server_error"}, "output": [], "usage": {}}]
try:
    real.run_openai_api({"openai_api_key": "sk"}, "p", rdo); msg = ""
except RuntimeError as e:
    msg = str(e)
check("OpenAI: failed-status giver fejl med årsag", "failed" in msg and "server_error" in msg)
REPLIES[:] = [{"status": "completed", "output": [], "usage": {}}]
try:
    real.run_openai_api({"openai_api_key": "sk"}, "p", rdo); msg = ""
except RuntimeError as e:
    msg = str(e)
check("OpenAI: intet endeligt svar giver fejl", "intet endeligt svar" in msg)
real.httpx.post = lambda *a, **k: N(status_code=404, text='{"error":{"code":"model_not_found","message":"The model gpt-x does not exist"}}', headers={})
try:
    real.run_openai_api({"openai_api_key": "sk", "openai_model": "gpt-x"}, "p", rdo); msg = ""
except RuntimeError as e:
    msg = str(e)
check("OpenAI: manglende modeladgang giver vejledning", "ikke adgang til modellen gpt-x" in msg)
real.httpx.post = lambda *a, **k: N(status_code=429, text='{"error":{"code":"insufficient_quota"}}', headers={})
try:
    real.run_openai_api({"openai_api_key": "sk"}, "p", rdo); msg = ""
except RuntimeError as e:
    msg = str(e)
check("OpenAI: manglende kredit giver vejledning uden ventetid", "kredit" in msg)

# Aula-login udløbet
async def aula_expired(c, s, w, x=None): raise real.AulaLoginRequired("x")
real.aula_fetch = aula_expired
g = G(); real.connect_graph = lambda c, s: g
state = {"events": {}}
rc = real.cmd_weekly(cfg_cc, state, False, None)
subj, html = g.mails[-1]
check("Aula-login: mail med login-aula-vejledning", "login-aula" in html and "last_weekly" not in state)

# ugeplan slået fra
seen = {}
async def no_plan(c, s, w, x=None): seen["w"] = w; seen["x"] = x; return [], [], None
real.aula_fetch = no_plan
g = G(); real.connect_graph = lambda c, s: g
real.cmd_weekly(dict(cfg_cc, ugeplan=False), {"events": {}}, False, None)
check("ugeplan=false: ugeplan og baggrund hentes ikke", seen["w"] is None and seen["x"] is None and "Husk i ugen" not in g.mails[-1][1])

# 4. Indhentning af ugens kørsel (--indhent) og lås, så to kørsler ikke kører samtidig
A = importlib.reload(agent)
d = lambda *x: datetime(*x, tzinfo=TZ)
# 22. nov. 2026 er en søndag
check("indhent: søndag kl. 12 -> samme søndag 07:00", A.last_scheduled("Sunday", "07:00", d(2026, 11, 22, 12, 0)) == d(2026, 11, 22, 7, 0))
check("indhent: mandag -> søndagen før", A.last_scheduled("Sunday", "07:00", d(2026, 11, 23, 11, 59)) == d(2026, 11, 22, 7, 0))
check("indhent: lørdag -> søndagen ugen før", A.last_scheduled("Sunday", "07:00", d(2026, 11, 21, 22, 0)) == d(2026, 11, 15, 7, 0))
check("indhent: lige før tiden tæller som i dag", A.last_scheduled("søndag", "07:00", d(2026, 11, 22, 6, 55)) == d(2026, 11, 22, 7, 0))
check("indhent: søndag 06:00 -> søndagen før", A.last_scheduled("Sunday", "07:00", d(2026, 11, 22, 6, 0)) == d(2026, 11, 15, 7, 0))
mon = d(2026, 11, 23, 12, 0)
check("indhent: kørt mandagen før -> mangler", A.weekly_due({"last_weekly": d(2026, 11, 16, 10, 49).isoformat()}, "Sunday", "07:00", mon))
check("indhent: kørt søndag 07:01 -> mangler ikke", not A.weekly_due({"last_weekly": d(2026, 11, 22, 7, 1).isoformat()}, "Sunday", "07:00", mon))
check("indhent: kørt med fejl og mail -> mangler ikke", not A.weekly_due({"last_weekly": d(2026, 11, 1, 7, 0).isoformat(), "last_weekly_try": d(2026, 11, 22, 9, 0).isoformat()}, "Sunday", "07:00", mon))
check("indhent: aldrig kørt -> mangler", A.weekly_due({}, "Sunday", "07:00", mon))
check("indhent: kørt 06:56 ved oplåsning -> opgaven 07:00 kører ikke igen",
      not A.weekly_due({"last_weekly": d(2026, 11, 22, 6, 58).isoformat()}, "Sunday", "07:00", d(2026, 11, 22, 7, 0)))
check("indhent: lørdag aften i hånden -> søndag kører stadig",
      A.weekly_due({"last_weekly": d(2026, 11, 21, 22, 0).isoformat()}, "Sunday", "07:00", d(2026, 11, 22, 7, 0)))

lockp = work / "test.lock"
l1 = A.acquire_run_lock(lockp)
l2 = A.acquire_run_lock(lockp)
check("lås: anden kørsel får ikke låsen", l1 is not None and l2 is None)
l1.close()
l3 = A.acquire_run_lock(lockp)
check("lås: frigives, når første kørsel slutter", l3 is not None)
l3.close()

# Hele vejen gennem main(): springes stille over, når ugen er kørt; kører, når den mangler
calls = []
A.cmd_weekly = lambda c, s, dry, days: (calls.append(dry), s.__setitem__("last_weekly", A.now_local().isoformat()), 0)[-1]
A.now_local = lambda: d(2026, 11, 23, 12, 0)
A.LOCK_FILE = work / "agent.lock"
A.save_json(A.STATE_FILE, {"events": {}, "last_weekly": d(2026, 11, 22, 7, 2).isoformat()})
sys.argv = ["agent.py", "weekly", "--indhent", "Sunday", "07:00"]
rc = A.main()
check("main --indhent: ugen er kørt -> stille, rc 0, ingen kørsel", rc == 0 and calls == [])
A.save_json(A.STATE_FILE, {"events": {}, "last_weekly": d(2026, 11, 16, 10, 49).isoformat()})
rc = A.main()
st = json.loads(A.STATE_FILE.read_text(encoding="utf-8"))
check("main --indhent: søndag mangler -> kører og gemmer", rc == 0 and calls == [False] and st["last_weekly"].startswith("2026-11-23"))
rc = A.main()
check("main --indhent: anden oplåsning samme dag -> kører ikke igen", calls == [False])
held = A.acquire_run_lock(A.LOCK_FILE)
A.save_json(A.STATE_FILE, {"events": {}})
rc = A.main()
check("main --indhent: anden kørsel i gang -> stille, rc 0", rc == 0 and calls == [False])
sys.argv = ["agent.py", "weekly"]
rc = A.main()
st = json.loads(A.STATE_FILE.read_text(encoding="utf-8"))
check("main weekly i hånden: anden kørsel i gang -> rc 1 og state urørt", rc == 1 and calls == [False] and st == {"events": {}})
held.close()
rc = A.main()
check("main weekly uden --indhent kører altid", rc == 0 and calls == [False, False])
sys.argv = ["agent.py", "weekly", "--indhent", "Søndagx", "07:00"]
check("main --indhent: ugyldig dag -> rc 1", A.main() == 1 and calls == [False, False])

# Fejl i weekly, som sender fejlmail, tæller som ugens forsøg (ingen ny mail ved hver oplåsning)
g4 = G()
def boom(*a): raise RuntimeError("bum")
A.cmd_weekly = boom
A.Graph = lambda c: g4
A.save_json(A.STATE_FILE, {"events": {}})
sys.argv = ["agent.py", "weekly", "--indhent", "Sunday", "07:00"]
rc = A.main()
st = json.loads(A.STATE_FILE.read_text(encoding="utf-8"))
check("main: fejl -> fejlmail og last_weekly_try", rc == 1 and len(g4.mails) == 1 and "last_weekly_try" in st)
rc = A.main()
check("main: næste oplåsning efter fejl -> ingen ny mail", rc == 0 and len(g4.mails) == 1)

print("\n" + ("Alle tests bestået" if not fails else f"{fails} fejl"))
sys.exit(1 if fails else 0)
