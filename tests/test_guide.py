"""Test af den forenklede guide med falske svar. Kør: python3 test_guide.py <repo>"""
import builtins, json, shutil, sys, tempfile
from pathlib import Path
from types import SimpleNamespace as N

repo = Path(sys.argv[1]); work = Path(tempfile.mkdtemp())
for f in ("agent.py", "regler.md", "config.example.json"):
    shutil.copy(repo / f, work / f)
sys.path.insert(0, str(work))
import agent  # noqa: E402

fails = 0
def check(name, cond):
    global fails
    print(("OK   " if cond else "FEJL ") + name); fails += not cond

FOUND = {"parent_name": "Testforælder Hansen", "children": [
    {"full_name": "Emma Hansen", "school": "Eksempelskolen", "class_guess": "2.a",
     "groups": ["2A", "Team 0. - 2. årgang", "2.A Kontaktforældre", "Team 3. - 5. årgang"]},
    {"full_name": "Oscar Hansen", "school": "Eksempelskolen", "class_guess": "",
     "groups": ["Skolen inkl. forældre", "Team 3. - 5. årgang", "2.A Kontaktforældre"]}]}

async def fake_login(u, i, force): return None
async def fake_discover(cfg): return json.loads(json.dumps(FOUND))
class FakeGraph:
    def __init__(s, cfg, interactive=False): s.username = "test@hotmail.com"; FakeGraph.made = True
    def calendar_id(s, n): FakeGraph.cal = n; return "cal"
agent.aula_login_interactive = fake_login
agent.aula_discover = fake_discover
agent.Graph = FakeGraph
agent.shutil.which = lambda x: "/bin/claude"

prompts = []
answers = iter(["testmitid", "4.b"])
def fake_input(prompt=""):
    prompts.append(prompt); return next(answers)
builtins.input = fake_input

rc = agent.cmd_setup(None)
cfg = json.loads((work / "config.json").read_text(encoding="utf-8"))
check("Guide: kører færdig", rc == 0)
check("Guide: kun 2 spørgsmål (MitID + ukendt klasse)", len(prompts) == 2 and "MitID" in prompts[0] and "Oscar" in prompts[1])
check("Guide: navne og klasser", [(c["name"], c["class"]) for c in cfg["children"]] == [("Emma", "2.a"), ("Oscar", "4.b")])
check("Guide: forælderens navn fra Aula", cfg["parent"]["name"] == "Testforælder Hansen" and cfg["parent"]["role"] == "forælder")
check("Guide: kontaktforælder fundet i grupper", cfg["parent"]["contact_parent_in"] == ["2.a"])
check("Guide: grupper filtreret pr. barn", cfg["children"][0]["aula_groups"] == ["2A", "Team 0. - 2. årgang", "2.A Kontaktforældre"]
      and "2.A Kontaktforældre" not in cfg["children"][1]["aula_groups"])
check("Guide: Claude Code valgt automatisk", cfg["ai_mode"] == "claude-code")
check("Guide: mail fra Outlook-kontoen, kalender oprettet", cfg["notify_email"] == "test@hotmail.com" and FakeGraph.cal == "Skole og fritid")
check("Guide: ingen eksempel-feeds", cfg["feeds"] == [])

# Genkørsel bevarer rettelser og spørger kun om MitID
cfg["children"][0]["name"] = "Emmy"; cfg["parent"]["role"] = "mor"; cfg["parent"]["contact_parent_in"] = []
cfg["family_notes"] = ["Note"]; cfg["notify_email"] = "anden@hotmail.com"
(work / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
FOUND["children"][0]["full_name"] = "Emma Hansen"
prompts.clear(); answers = iter([""])
rc = agent.cmd_setup(cfg)
cfg2 = json.loads((work / "config.json").read_text(encoding="utf-8"))
check("Genkørsel: kun MitID-spørgsmål med Enter", rc == 0 and len(prompts) == 1 and "Enter = behold" in prompts[0])
check("Genkørsel: bevarer rolle, noter, mail og kontaktforælder-valg",
      cfg2["parent"]["role"] == "mor" and cfg2["family_notes"] == ["Note"] and cfg2["notify_email"] == "anden@hotmail.com"
      and cfg2["parent"]["contact_parent_in"] == [])
check("Genkørsel: Oscars klasse huskes", cfg2["children"][1]["class"] == "4.b")

# Uden Claude Code: API-nøgle
agent.shutil.which = lambda x: None
agent.getpass.getpass = lambda prompt="": "sk-ant-test"
agent.check_api_key = lambda k: None
prompts.clear(); answers = iter([""])
rc = agent.cmd_setup(cfg2)
cfg3 = json.loads((work / "config.json").read_text(encoding="utf-8"))
check("Uden Claude Code: API-nøgle", cfg3["ai_mode"] == "api" and cfg3["anthropic_api_key"] == "sk-ant-test")

# Ny bruger uden Claude Code og Codex: spørger om AI og bruger OpenAI-nøgle ved ChatGPT
agent.find_codex = lambda c: None
agent.getpass.getpass = lambda prompt="": "sk-proj-test"
agent.check_openai_key = lambda k: None
fresh = {k: v for k, v in cfg3.items() if k not in ("ai_mode", "claude_mode", "anthropic_api_key")}
prompts.clear(); answers = iter(["", "chatgpt"])
rc = agent.cmd_setup(fresh)
cfg4 = json.loads((work / "config.json").read_text(encoding="utf-8"))
check("ChatGPT uden Codex: spørger om AI og bruger OpenAI-nøgle", rc == 0 and any("chatgpt" in p for p in prompts)
      and cfg4["ai_mode"] == "openai-api" and cfg4["openai_api_key"] == "sk-proj-test")

# Codex installeret: bruges automatisk efter en selvtest
agent.find_codex = lambda c: "/bin/codex"
agent.codex_selftest = lambda c: (None, "gpt-6.1-sol")
prompts.clear(); answers = iter([""])
rc = agent.cmd_setup({k: v for k, v in fresh.items()}, False, "chatgpt")
cfg5 = json.loads((work / "config.json").read_text(encoding="utf-8"))
check("Codex: valgt efter selvtest, ingen ekstra spørgsmål", rc == 0 and cfg5["ai_mode"] == "codex" and len(prompts) == 1)

# Codex virker ikke: tilbyder API-nøgle
agent.codex_selftest = lambda c: ("Codex er ikke logget ind", "")
prompts.clear(); answers = iter(["", "j"])
rc = agent.cmd_setup({k: v for k, v in fresh.items()}, False, "chatgpt")
cfg6 = json.loads((work / "config.json").read_text(encoding="utf-8"))
check("Codex fejler: skifter til OpenAI-nøgle efter ja", rc == 0 and cfg6["ai_mode"] == "openai-api")

# Gammel config med claude_mode virker stadig
check("Gammelt felt claude_mode læses", agent.ai_mode({"claude_mode": "api"}) == "api" and agent.ai_mode({}) == "claude-code")

print("\n" + ("Alle guide-tests bestået" if not fails else f"{fails} fejl"))
sys.exit(1 if fails else 0)
