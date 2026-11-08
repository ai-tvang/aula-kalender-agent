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
