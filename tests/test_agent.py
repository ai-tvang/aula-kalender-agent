"""Tests af repo-versionen med falske svar. Kør: python3 test_repo.py <repo-mappe>"""
import asyncio
import json
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
check("OCR: højst 10 billeder hentes pr. opslag", len(fh3.urls) == agent.IMAGE_TEXT_MAX_FILES)
check("OCR: uden Windows findes OCR ikke (None)", agent.sys.platform == "win32" or real_ocr([att_dir / "x.png"]) is None)

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

print("\n" + ("Alle tests bestået" if not fails else f"{fails} fejl"))
sys.exit(1 if fails else 0)
