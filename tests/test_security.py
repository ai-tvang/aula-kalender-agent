"""Test af sikkerhedslaget med falsk Windows-kryptering. Kør: python3 test_security.py <repo>"""
import asyncio, json, shutil, sys, tempfile, types
from pathlib import Path
from types import SimpleNamespace as N

repo = Path(sys.argv[1]); work = Path(tempfile.mkdtemp())
for f in ("agent.py", "regler.md", "config.example.json"):
    shutil.copy(repo / f, work / f)

# Falsk aula-pakke (kun det, sikkerhedslaget bruger)
home = Path(tempfile.mkdtemp())
aula = types.ModuleType("aula"); cfgmod = types.ModuleType("aula.config"); ts = types.ModuleType("aula.token_storage")
cfgmod.DEFAULT_TOKEN_FILE = home / ".config" / "aula" / "tokens.json"
class TokenStorage: pass
ts.TokenStorage = TokenStorage
sys.modules.update({"aula": aula, "aula.config": cfgmod, "aula.token_storage": ts})

sys.path.insert(0, str(work))
import agent  # noqa: E402

fails = 0
def check(name, cond):
    global fails
    print(("OK   " if cond else "FEJL ") + name); fails += not cond

# Falsk DPAPI: vender bytes om og tilføjer en "bruger-nøgle"
USER = {"key": b"bruger1"}
def fake_dpapi(data, protect):
    if protect:
        return USER["key"] + data[::-1]
    if not data.startswith(USER["key"]):
        raise OSError("forkert bruger")
    return data[len(USER["key"]):][::-1]
agent._dpapi = fake_dpapi
agent.can_protect = lambda: True

# 1. Tekst krypteres og kan låses op
enc = agent.protect_text("hemmelig")
check("Kryptering: præfiks og ikke klartekst", enc.startswith("DPAPI1:") and "hemmelig" not in enc)
check("Kryptering: kan låses op", agent.unprotect_text(enc) == "hemmelig")
USER["key"] = b"bruger2"
try:
    agent.unprotect_text(enc); ok = False
except agent.SecretUnreadable:
    ok = True
check("Kryptering: anden bruger kan ikke låse op", ok)
USER["key"] = b"bruger1"

# 2. Gammel Outlook-cache migreres
agent.GRAPH_CACHE_LEGACY.write_text('{"AccessToken": {"x": 1}}', encoding="utf-8")
text = agent.read_secret(agent.GRAPH_CACHE, agent.GRAPH_CACHE_LEGACY)
check("Migrering: indhold læst", json.loads(text) == {"AccessToken": {"x": 1}})
check("Migrering: ukrypteret fil slettet", not agent.GRAPH_CACHE_LEGACY.exists())
check("Migrering: ny fil krypteret", agent.GRAPH_CACHE.read_text(encoding="utf-8").startswith("DPAPI1:"))
check("Migrering: læses igen", json.loads(agent.read_secret(agent.GRAPH_CACHE, agent.GRAPH_CACHE_LEGACY)) == {"AccessToken": {"x": 1}})

# 3. Aula-tokens: gammel fil i ~/.config/aula flyttes og krypteres
cfgmod.DEFAULT_TOKEN_FILE.parent.mkdir(parents=True)
cfgmod.DEFAULT_TOKEN_FILE.write_text(json.dumps({"tokens": {"access": "abc"}}), encoding="utf-8")
st = agent.aula_token_storage()
data = asyncio.run(st.load())
check("Aula: gamle tokens læst", data == {"tokens": {"access": "abc"}})
check("Aula: gammel fil slettet, ny krypteret", not cfgmod.DEFAULT_TOKEN_FILE.exists()
      and agent.AULA_TOKENS.read_text(encoding="utf-8").startswith("DPAPI1:"))
asyncio.run(st.save({"tokens": {"access": "ny"}}))
check("Aula: gem og læs", asyncio.run(st.load()) == {"tokens": {"access": "ny"}}
      and "ny" not in agent.AULA_TOKENS.read_text(encoding="utf-8"))
USER["key"] = b"bruger2"
check("Aula: kopieret fil giver nyt login i stedet for nedbrud", asyncio.run(st.load()) is None)
USER["key"] = b"bruger1"

# 4. API-nøgle
cfg = {"anthropic_api_key": "sk-ant-klar"}
check("API-nøgle: krypteres", agent.protect_config_secrets(cfg) and cfg["anthropic_api_key"].startswith("DPAPI1:"))
check("API-nøgle: bruges dekrypteret", agent.api_key(cfg) == "sk-ant-klar")
check("API-nøgle: krypteres ikke to gange", not agent.protect_config_secrets(cfg))

# 5. Claude Code får kun Read i kørslens mappe
seen = {}
def fake_run(args, **kw):
    seen["args"], seen["cwd"] = args, kw.get("cwd")
    return N(returncode=0, stdout=json.dumps({"result": "ok"}), stderr="")
agent.subprocess.run = fake_run
agent.shutil.which = lambda x: "/bin/claude"
rd = work / "runs" / "x"; rd.mkdir(parents=True)
agent.run_claude_code({"claude_command": "claude"}, "prompt", rd)
a = seen["args"]
check("Claude Code: kun Read-værktøjet", a[a.index("--tools") + 1] == "Read" and "--allowedTools" not in a)
check("Claude Code: dontAsk og ingen MCP", a[a.index("--permission-mode") + 1] == "dontAsk" and "--strict-mcp-config" in a
      and a[a.index("--disallowedTools") + 1] == "mcp__*")
check("Claude Code: læsning uden for mappen blokeret",
      json.loads(a[a.index("--settings") + 1]) == {"permissions": {"blockReadsOutsideWorkingDirectories": True}} and seen["cwd"] == rd)
check("Claude Code: Opus som standard", a[a.index("--model") + 1] == "claude-opus-5-5")
agent.run_claude_code({"claude_command": "claude", "claude_model": "claude-sonnet-5-5"}, "prompt", rd)
check("Claude Code: claude_model bruges", seen["args"][seen["args"].index("--model") + 1] == "claude-sonnet-5-5")

# 5b. Codex (ChatGPT) kører uden for agent-mappen med læseforbud, uden netværk og uden brugerens opsætning
calls = []
def fake_codex(args, **kw):
    if args[1:] == ["--version"]:
        return N(returncode=0, stdout="codex-cli 0.167.0", stderr="")
    calls.append({"args": args, "cwd": kw.get("cwd"), "input": kw.get("input")})
    reply = CODEX_REPLIES.pop(0)
    if reply[0] == 0:
        Path(args[args.index("-o") + 1]).write_text('```json\n{"calendar": []}\n```', encoding="utf-8")
    return N(returncode=reply[0], stdout=reply[1], stderr=reply[2])
agent.subprocess.run = fake_codex
agent.find_codex = lambda cfg: "/bin/codex"
OK_EVENTS = '{"type":"turn.completed","usage":{"input_tokens":100,"cached_input_tokens":0,"output_tokens":10}}'
CODEX_REPLIES = [(0, OK_EVENTS, "")]
from PIL import Image  # noqa: E402
(rd / "attachments").mkdir(exist_ok=True)
Image.new("RGB", (3000, 2000), "red").save(rd / "attachments" / "foto.jpg")
text = agent.run_codex({}, "prompt æøå", rd, ["attachments/foto.jpg", "attachments/findes_ikke.jpg"])
c = calls[-1]; a = c["args"]
def cval(prefix):
    return [a[i + 1] for i in range(len(a) - 1) if a[i] == "-c" and a[i + 1].startswith(prefix)]
check("Codex: svaret læses fra -o-filen", '"calendar"' in text)
check("Codex: brugerens opsætning og regler ignoreres", "--ignore-user-config" in a and "--ignore-rules" in a and "--ephemeral" in a)
check("Codex: læse-profil med forbud", cval("default_permissions=") == ["default_permissions=aula"]
      and cval("permissions.aula.extends=") == ['permissions.aula.extends=":read-only"'])
deny = cval("permissions.aula.filesystem=")[0]
check("Codex: agent-mappen er forbudt", json.dumps(agent.BASE.as_posix()) + '="deny"' in deny)
check("Codex: hele brugermappen er forbudt, kun arbejdsmappen må læses",
      json.dumps(Path.home().as_posix()) + '="deny"' in deny and '":workspace_roots"={"."="read"}' in deny)
check("Codex: ingen netværk, ingen websøgning, ingen godkendelser",
      cval("permissions.aula.network=") == ["permissions.aula.network={enabled=false}"]
      and cval("web_search=") == ["web_search=disabled"] and cval("approval_policy=") == ["approval_policy=never"])
check("Codex: shell og andre værktøjer slået fra", "features.shell_tool=false" in a and "features.unified_exec=false" in a)
check("Codex: ingen farlige flag", not any(x in a for x in ("--yolo", "--dangerously-bypass-approvals-and-sandbox", "danger-full-access")))
check("Codex: arbejdsmappe uden for agent-mappen og ryddet op bagefter",
      agent.BASE.resolve() not in Path(c["cwd"]).resolve().parents and not Path(c["cwd"]).exists()
      and a[a.index("-C") + 1] == str(c["cwd"]))
check("Codex: prompt via stdin med billedliste", a[-1] == "-" and c["input"].startswith("prompt æøå")
      and "1. attachments/foto.jpg" in c["input"] and "findes_ikke" not in c["input"])
check("Codex: kun eksisterende billede vedhæftet", a.count("-i") == 1)
check("Codex: GPT-6.1 Sol prøves først", a[a.index("-m") + 1] == "gpt-6.1-sol")
check("Codex: forbrug gemt", json.loads((rd / "ai_usage.json").read_text(encoding="utf-8"))["usage"]["input_tokens"] == 100)

CODEX_REPLIES = [(1, '{"type":"error","message":"The \'gpt-6.1-sol\' model is not supported when using Codex with a ChatGPT account."}', ""),
                 (0, OK_EVENTS, "")]
calls.clear()
agent.run_codex({}, "p", rd)
check("Codex: falder tilbage til abonnementets model (Go/Free)", len(calls) == 2 and "-m" not in calls[1]["args"]
      and json.loads((rd / "ai_usage.json").read_text(encoding="utf-8"))["model"] == "standard")
CODEX_REPLIES = [(1, '{"type":"error","message":"model_not_found"}', "")]
try:
    agent.run_codex({"openai_model": "gpt-6-astra"}, "p", rd); ok = False
except RuntimeError:
    ok = True
check("Codex: valgt model bruges uden tilbagefald", ok and calls[-1]["args"][calls[-1]["args"].index("-m") + 1] == "gpt-6-astra")
CODEX_REPLIES = [(1, "", "failed to prepare windows sandbox wrapper: cannot enforce deny-read restrictions directly; refusing to run unsandboxed")]
try:
    agent.run_codex({"openai_model": "x"}, "p", rd); msg = ""
except RuntimeError as e:
    msg = str(e)
check("Codex: svag sandkasse stopper kørslen med vejledning", "Opsætning" in msg and "sandkasse" in msg)
CODEX_REPLIES = [(1, "", "windows sandbox failed: runner failed during SpawnChild: CreateProcessAsUserW failed")]
try:
    agent.run_codex({"openai_model": "x"}, "p", rd); ok = False
except agent.CodexSandboxError:
    ok = True
check("Codex: andre sandkassefejl stopper også kørslen", ok)
CODEX_REPLIES = [(1, '{"type":"error","message":"Not logged in. Run codex login"}', "")]
try:
    agent.run_codex({"openai_model": "x"}, "p", rd); ok = False
except agent.AiLoginRequired:
    ok = True
check("Codex: manglende login giver login-fejl", ok)
agent.subprocess.run = lambda args, **kw: N(returncode=0, stdout="codex-cli 0.128.0", stderr="")
try:
    agent.run_codex({}, "p", rd); msg = ""
except RuntimeError as e:
    msg = str(e)
check("Codex: for gammel version afvises", "for gammel" in msg)
agent.subprocess.run = lambda args, **kw: N(returncode=1, stdout="", stderr="noget gik galt")
try:
    agent.run_codex({}, "p", rd); msg = ""
except RuntimeError as e:
    msg = str(e)
check("Codex: ukendt version afvises (fejl lukket)", "ukendt version" in msg)

# 5c. OpenAI-nøgle krypteres som Anthropic-nøglen
cfg = {"openai_api_key": "sk-proj-klar", "ai_mode": "openai-api"}
check("OpenAI-nøgle: krypteres", agent.protect_config_secrets(cfg) and cfg["openai_api_key"].startswith("DPAPI1:"))
check("OpenAI-nøgle: bruges dekrypteret", agent.openai_key(cfg) == "sk-proj-klar")

check("Selvtest: virker med kryptering", agent.check_protection() is None)
real = agent._dpapi
agent._dpapi = lambda d, p: (_ for _ in ()).throw(OSError("ingen DPAPI"))
check("Selvtest: fejl opdages", "ingen DPAPI" in (agent.check_protection() or ""))
agent._dpapi = real

# 6. Runs gemmes 7 dage som standard
import os, time
old = work / "runs" / "gammel"; old.mkdir()
t = time.time() - 8 * 86400; os.utime(old, (t, t))
agent.cleanup_runs({})
check("Runs: slettes efter 7 dage", not old.exists() and rd.exists())

print("\n" + ("Alle sikkerheds-tests bestået" if not fails else f"{fails} fejl"))
sys.exit(1 if fails else 0)
