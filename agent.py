# /// script
# requires-python = ">=3.14"
# dependencies = [
#   "aula==1.16.0",
#   "msal>=1.31",
#   "httpx",
#   "icalendar>=6",
#   "recurring-ical-events>=3",
#   "python-docx",
#   "pypdf",
#   "beautifulsoup4",
#   "pillow",
# ]
# ///
"""
Aula-kalenderagent: finder de datoer i Aula, som forældre skal bruge, og lægger
dem i en Outlook-kalender. Kalender-links (fx Aula-kalenderen eller en
sportsklub) kan flettes ind i samme kalender.

Uofficielt projekt. Ikke lavet eller godkendt af Aula, KL, STIL eller Netcompany.

Kommandoer (køres fra mappen med denne fil):
    uv run --python-preference only-system agent.py opsaet
    uv run --python-preference only-system agent.py login-aula
    uv run --python-preference only-system agent.py login-outlook
    uv run --python-preference only-system agent.py daily  [--dry-run]
    uv run --python-preference only-system agent.py weekly [--dry-run] [--days N]
    uv run --python-preference only-system agent.py manual [--dry-run]

opsaet:      logger ind i Aula med MitID, henter børn, skole og klasser og
             skriver config.json efter få spørgsmål.
login-aula:  nyt MitID-login, når Aula-login er udløbet.
daily:       holder Aula-login i live og synkroniserer kalender-links (ingen AI).
weekly:      daily + læser nye opslag og beskeder med AI'en, skriver aftaler og
             sender en ugemail.
manual:      lægger aftalerne fra manuelle_aftaler.json i kalenderen med det samme
             (det sker også ved hver daily og weekly).

AI'en kan køre på fire måder ("ai_mode" i config.json):
- "claude-code": Claude Code ("claude"-kommandoen), tæller i dit Claude-abonnement.
- "api": API-nøgle fra console.anthropic.com ("anthropic_api_key"), betaling pr. forbrug.
- "codex": Codex CLI ("codex"-kommandoen), tæller i dit ChatGPT-abonnement.
- "openai-api": API-nøgle fra platform.openai.com ("openai_api_key"), betaling pr. forbrug.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import getpass
import hashlib
import io
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time as _time
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import msal
from bs4 import BeautifulSoup

BASE = Path(__file__).resolve().parent
CONFIG_FILE = BASE / "config.json"
STATE_FILE = BASE / "state.json"
GRAPH_CACHE = BASE / "graph_token_cache.dat"
GRAPH_CACHE_LEGACY = BASE / "graph_token_cache.json"
AULA_TOKENS = BASE / "aula_tokens.dat"
RULES_FILE = BASE / "regler.md"
RUNS_DIR = BASE / "runs"
LOG_DIR = BASE / "logs"
EXAMPLE_CONFIG = BASE / "config.example.json"
RUN = "uv run --python-preference only-system agent.py"

TZ = ZoneInfo("Europe/Copenhagen")
GRAPH_TZ = "Romance Standard Time"

# Standard: Microsofts offentlige klient-id for Microsoft Graph PowerShell. Det
# understøtter personlige Outlook/Hotmail-konti uden egen app-registrering.
# Har du din egen app-registrering, så sæt "graph_client_id" og evt.
# "graph_authority" i config.json.
DEFAULT_GRAPH_CLIENT_ID = "14d82eec-204b-4c2f-b7e8-296a70dab67e"
DEFAULT_GRAPH_AUTHORITY = "https://login.microsoftonline.com/consumers"
GRAPH_SCOPES = [
    "https://graph.microsoft.com/Calendars.ReadWrite",
    "https://graph.microsoft.com/Mail.Send",
]

DOC_EXT = {".pdf", ".docx"}
IMG_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic"}

log = logging.getLogger("aula-agent")


# --------------------------------------------------------------------------- #
# Hjælpere
# --------------------------------------------------------------------------- #
def setup_logging() -> None:
    LOG_DIR.mkdir(exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    fh = logging.FileHandler(LOG_DIR / "agent.log", encoding="utf-8")
    fh.setFormatter(fmt)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(logging.Formatter("  Bemærk: %(message)s"))
    sh.setLevel(logging.WARNING)
    log.setLevel(logging.INFO)
    log.addHandler(fh)
    log.addHandler(sh)


def say(text: str) -> None:
    """Kort besked i vinduet (og i loggen)."""
    print(text, flush=True)
    log.info(text.strip())


def load_json(path: Path, default):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return default


def save_json(path: Path, data) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def now_local() -> datetime:
    return datetime.now(TZ)


def html_to_text(html: str | None) -> str:
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    text = soup.get_text("\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def parse_dt(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def desktop_notice(text: str) -> None:
    """Sidste udvej, hvis der hverken kan sendes mail eller logges ind."""
    try:
        target = Path.home() / "Desktop" / "AULA-AGENT - HANDLING KRÆVET.txt"
        target.write_text(text, encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


class AulaLoginRequired(Exception):
    pass


class AiLoginRequired(Exception):
    """Login til AI'en er udløbet, eller API-nøglen er afvist."""


ClaudeLoginRequired = AiLoginRequired  # gammelt navn


class CodexSandboxError(RuntimeError):
    """Codex' sikre sandkasse kan ikke starte eller håndhæve læseforbuddene."""

CLAUDE_AUTH_PATTERN = re.compile(
    r"Failed to authenticate|OAuth|not logged in|Please run /login|Invalid API key|authentication_error",
    re.I,
)
CODEX_AUTH_PATTERN = re.compile(
    r"not logged in|codex login|401 Unauthorized|status: 401|\"status\":401|unauthorized|"
    r"refresh token|token (?:has )?expired|sign in again|log in again",
    re.I,
)
# Alle fejl om sandkassen stopper kørslen; der skiftes aldrig til en svagere sandkasse.
CODEX_SANDBOX_PATTERN = re.compile(
    r"sandbox|deny-read|unsandboxed|restricted.token|CreateProcessAsUser|firewall|sandbox user", re.I)
CODEX_MODEL_PATTERN = re.compile(r"not supported when using Codex with a ChatGPT account|model_not_found", re.I)


SECRET_PREFIX = "DPAPI1:"
_DPAPI_ENTROPY = b"aula-kalender-agent"


def _dpapi(data: bytes, protect: bool) -> bytes:
    """Windows' egen kryptering, bundet til den indloggede Windows-bruger på denne computer."""
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    def blob(b: bytes):
        buf = ctypes.create_string_buffer(b, len(b))
        return Blob(len(b), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf

    crypt32, kernel32 = ctypes.windll.crypt32, ctypes.windll.kernel32
    data_in, _keep1 = blob(data)
    entropy, _keep2 = blob(_DPAPI_ENTROPY)
    data_out = Blob()
    ui_forbidden = 0x1
    if protect:
        ok = crypt32.CryptProtectData(ctypes.byref(data_in), "aula-kalender-agent", ctypes.byref(entropy),
                                      None, None, ui_forbidden, ctypes.byref(data_out))
    else:
        ok = crypt32.CryptUnprotectData(ctypes.byref(data_in), None, ctypes.byref(entropy),
                                        None, None, ui_forbidden, ctypes.byref(data_out))
    if not ok:
        raise OSError(f"Windows-kryptering fejlede (fejlkode {ctypes.GetLastError()})")
    try:
        return ctypes.string_at(data_out.pbData, data_out.cbData)
    finally:
        kernel32.LocalFree(data_out.pbData)


def can_protect() -> bool:
    return sys.platform == "win32"


def protect_text(text: str) -> str:
    """Krypterer på Windows. Andre steder (kun til test) gemmes teksten som den er."""
    if not can_protect():
        return text
    return SECRET_PREFIX + base64.b64encode(_dpapi(text.encode("utf-8"), True)).decode("ascii")


def unprotect_text(text: str) -> str:
    if not text.startswith(SECRET_PREFIX):
        return text
    try:
        return _dpapi(base64.b64decode(text[len(SECRET_PREFIX):]), False).decode("utf-8")
    except Exception as e:  # noqa: BLE001
        raise SecretUnreadable(
            "Login-filen kan ikke låses op. Den er krypteret til en anden Windows-bruger eller computer."
        ) from e


class SecretUnreadable(Exception):
    pass


def write_secret(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(protect_text(text), encoding="utf-8")
    os.replace(tmp, path)


def read_secret(path: Path, legacy: Path | None = None) -> str | None:
    """Læser en krypteret fil. Findes kun en gammel ukrypteret fil, krypteres den og den gamle slettes."""
    if path.exists():
        return unprotect_text(path.read_text(encoding="utf-8"))
    if legacy and legacy.exists():
        text = legacy.read_text(encoding="utf-8")
        write_secret(path, text)
        if can_protect():
            legacy.unlink()
            log.info("Krypterede %s og slettede den ukrypterede fil", path.name)
        return text
    return None


class GraphLoginRequired(Exception):
    pass


# --------------------------------------------------------------------------- #
# Microsoft Graph
# --------------------------------------------------------------------------- #
class Graph:
    def __init__(self, cfg: dict, interactive: bool = False):
        cache = msal.SerializableTokenCache()
        try:
            cached = read_secret(GRAPH_CACHE, GRAPH_CACHE_LEGACY)
        except SecretUnreadable as e:
            log.warning("%s Log ind i Outlook igen.", e)
            cached = None
        if cached:
            cache.deserialize(cached)
        app = msal.PublicClientApplication(
            cfg.get("graph_client_id") or DEFAULT_GRAPH_CLIENT_ID,
            authority=cfg.get("graph_authority") or DEFAULT_GRAPH_AUTHORITY,
            token_cache=cache,
        )
        result = None
        accounts = app.get_accounts()
        self.username = accounts[0].get("username", "") if accounts else ""
        if accounts:
            result = app.acquire_token_silent(GRAPH_SCOPES, account=accounts[0])
        if not result:
            if not interactive:
                raise GraphLoginRequired("Outlook-login udløbet")
            flow = app.initiate_device_flow(scopes=GRAPH_SCOPES)
            if "user_code" not in flow:
                raise RuntimeError(f"Kunne ikke starte Outlook-login: {flow}")
            print()
            uri = flow.get("verification_uri") or "https://www.microsoft.com/link"
            site = uri.replace('https://', '').replace('www.', '').rstrip('/')
            print("  Giv agenten adgang til din Outlook-kalender:")
            print("  1. Åbn en browser på computeren eller telefonen.")
            print(f"  2. Gå til {site}")
            print(f"  3. Skriv koden: {flow['user_code']}")
            print("  4. Log ind med den Outlook-konto, kalenderen skal ligge i (fx @hotmail.com eller @outlook.com).")
            print("  5. Godkend adgangen (\"Microsoft Graph Command Line Tools\").")
            print("  Lad dette vindue stå åbent. Guiden fortsætter selv, når du har godkendt.")
            print()
            result = app.acquire_token_by_device_flow(flow)
        if "access_token" not in result:
            raise RuntimeError(
                f"Outlook-login fejlede: {result.get('error')}: {result.get('error_description')}"
            )
        claims = result.get("id_token_claims") or {}
        self.username = claims.get("preferred_username") or claims.get("email") or self.username
        if cache.has_state_changed:
            write_secret(GRAPH_CACHE, cache.serialize())
        self.http = httpx.Client(
            base_url="https://graph.microsoft.com/v1.0",
            headers={
                "Authorization": f"Bearer {result['access_token']}",
                "Prefer": f'outlook.timezone="{GRAPH_TZ}"',
            },
            timeout=60,
        )

    def req(self, method: str, url: str, **kw):
        r = self.http.request(method, url, **kw)
        if r.status_code >= 400:
            raise RuntimeError(f"Graph {method} {url}: {r.status_code} {r.text[:400]}")
        return r.json() if r.content else None

    def calendar_id(self, name: str) -> str:
        data = self.req("GET", "/me/calendars", params={"$top": "100"})
        for c in data.get("value", []):
            if c.get("name") == name:
                return c["id"]
        log.info("Opretter kalenderen '%s'", name)
        return self.req("POST", "/me/calendars", json={"name": name})["id"]

    def list_events(self, cal_id: str, start: date, end: date) -> list[dict]:
        url = f"/me/calendars/{cal_id}/calendarView"
        params = {
            "startDateTime": f"{start.isoformat()}T00:00:00",
            "endDateTime": f"{end.isoformat()}T00:00:00",
            "$top": "200",
            "$select": "id,subject,start,end,isAllDay",
        }
        out: list[dict] = []
        data = self.req("GET", url, params=params)
        while True:
            out.extend(data.get("value", []))
            nxt = data.get("@odata.nextLink")
            if not nxt:
                break
            data = self.req("GET", nxt)
        return out

    def create_event(self, cal_id: str, body: dict) -> str:
        return self.req("POST", f"/me/calendars/{cal_id}/events", json=body)["id"]

    def update_event(self, event_id: str, body: dict) -> None:
        self.req("PATCH", f"/me/events/{event_id}", json=body)

    def delete_event(self, event_id: str) -> None:
        r = self.http.delete(f"/me/events/{event_id}")
        if r.status_code not in (204, 404):
            raise RuntimeError(f"Graph DELETE: {r.status_code} {r.text[:300]}")

    def send_mail(self, to: str, subject: str, html: str) -> None:
        self.req(
            "POST",
            "/me/sendMail",
            json={
                "message": {
                    "subject": subject,
                    "body": {"contentType": "HTML", "content": html},
                    "toRecipients": [{"emailAddress": {"address": to}}],
                },
                "saveToSentItems": False,
            },
        )


# --------------------------------------------------------------------------- #
# Aftaler
# --------------------------------------------------------------------------- #
def child_prefix(cfg: dict, children: list[str]) -> str:
    labels = [c["label"] for c in cfg["children"] if c["name"] in children]
    return f"[{' + '.join(labels)}] " if labels else ""


def build_event(cfg: dict, item: dict) -> dict:
    """item: title, date, end_date, start, end, location, notes, source, children."""
    title = child_prefix(cfg, item.get("children", [])) + item["title"].strip()
    d = date.fromisoformat(item["date"])
    end_d = date.fromisoformat(item["end_date"]) if item.get("end_date") else d
    notes = (item.get("notes") or "").strip()
    if item.get("source"):
        notes += f"\n\nKilde: {item['source']}"
    notes += "\n\nOprettet af Aula-agenten."
    body = {
        "subject": title[:250],
        "body": {"contentType": "text", "content": notes.strip()},
        "isReminderOn": True,
    }
    if item.get("location"):
        body["location"] = {"displayName": item["location"][:250]}
    if item.get("start"):
        st = datetime.combine(d, time.fromisoformat(item["start"]))
        if item.get("end"):
            et = datetime.combine(end_d, time.fromisoformat(item["end"]))
        else:
            et = st + timedelta(hours=1)
        if et <= st:
            et = st + timedelta(hours=1)
        body.update(
            isAllDay=False,
            showAs="busy",
            reminderMinutesBeforeStart=cfg.get("reminder_minutes_timed", 60),
            start={"dateTime": st.isoformat(timespec="seconds"), "timeZone": GRAPH_TZ},
            end={"dateTime": et.isoformat(timespec="seconds"), "timeZone": GRAPH_TZ},
        )
    else:
        body.update(
            isAllDay=True,
            showAs="free",
            # Heldagsaftaler: påmindelse aftenen før (standard kl. 18).
            reminderMinutesBeforeStart=cfg.get("reminder_minutes_allday", 360),
            start={"dateTime": f"{d.isoformat()}T00:00:00", "timeZone": GRAPH_TZ},
            end={"dateTime": f"{(end_d + timedelta(days=1)).isoformat()}T00:00:00", "timeZone": GRAPH_TZ},
        )
    return body


def body_hash(body: dict) -> str:
    return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


def aula_unchanged(cfg: dict, rec: dict | None, item: dict) -> bool:
    """Sand, hvis AI'en gentager en eksisterende aftale uden ny dato, tid eller titel og uden at
    angive en grund i "update_reason". Så bliver aftalen ikke skrevet igen bare fordi
    AI'en har formuleret noterne lidt anderledes."""
    if not rec or rec.get("source") != "aula" or (item.get("update_reason") or "").strip():
        return False
    subject = build_event(cfg, item)["subject"]
    same = rec.get("subject") == subject and rec.get("date") == item.get("date")
    same = same and (rec.get("start") if "start" in rec else item.get("start")) == item.get("start")
    for f in ("end", "end_date"):
        if f in rec:
            same = same and (rec.get(f) or None) == (item.get(f) or None)
    return same


def upsert(graph: Graph | None, cal_id: str, state: dict, cfg: dict, key: str,
           item: dict, source: str, dry: bool) -> str:
    body = build_event(cfg, item)
    h = body_hash(body)
    rec = state["events"].get(key)
    if rec and rec["hash"] == h:
        return "uændret"
    action = "opdateret" if rec else "ny"
    if dry:
        log.info("[TØRKØRSEL] %s: %s (%s)", action, body["subject"], item["date"])
        return action
    if rec:
        try:
            graph.update_event(rec["id"], body)
        except RuntimeError as e:
            if " 404 " not in str(e):
                raise
            rec = None
            action = "ny"
    if not rec:
        rec = {"id": graph.create_event(cal_id, body)}
    rec.update(hash=h, source=source, date=item["date"], subject=body["subject"],
               start=item.get("start"))
    if source == "aula":
        rec.update(end=item.get("end"), end_date=item.get("end_date"),
                   location=item.get("location") or "", notes=(item.get("notes") or "")[:1500])
    state["events"][key] = rec
    log.info("%s: %s (%s)", action, body["subject"], item["date"])
    return action


# --------------------------------------------------------------------------- #
# Kalender-links (Aula-kalendere og andre .ics-links)
# --------------------------------------------------------------------------- #
def _to_local(value) -> tuple[date, str | None]:
    """Returnerer (dato, 'HH:MM' eller None for heldag)."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=TZ)
        value = value.astimezone(TZ)
        return value.date(), value.strftime("%H:%M")
    return value, None


def fetch_feed_items(cfg: dict) -> dict[str, dict]:
    import icalendar
    import recurring_ical_events

    today = now_local().date()
    start, end = today - timedelta(days=1), today + timedelta(days=cfg.get("feed_days_ahead", 365))
    merged: dict[str, dict] = {}
    by_title_time: dict[tuple, str] = {}

    for feed in cfg["feeds"]:
        url = feed["url"].replace("webcal://", "https://", 1)
        r = httpx.get(url, follow_redirects=True, timeout=60)
        r.raise_for_status()
        cal = icalendar.Calendar.from_ical(r.content)
        events = recurring_ical_events.of(cal).between(start, end)
        uid_count: dict[str, int] = {}
        for ev in events:
            uid_count[str(ev.get("UID"))] = uid_count.get(str(ev.get("UID")), 0) + 1

        for ev in events:
            uid = str(ev.get("UID"))
            d, st = _to_local(ev.decoded("DTSTART"))
            end_d, et = d, None
            if "DTEND" in ev:
                end_d, et = _to_local(ev.decoded("DTEND"))
                if st is None and end_d > d:  # heldags-slut er eksklusiv
                    end_d = end_d - timedelta(days=1)
            title = str(ev.get("SUMMARY", "")).strip() or "(uden titel)"
            key = f"feed:{uid}" if uid_count[uid] == 1 else f"feed:{uid}|{d.isoformat()}{st or ''}"
            match_key = (title.lower(), d.isoformat(), st)

            existing = merged.get(key) or merged.get(by_title_time.get(match_key, ""))
            if existing:
                for c in feed["children"]:
                    if c not in existing["children"]:
                        existing["children"].append(c)
                if feed["name"] not in existing["source"]:
                    existing["source"] += f", {feed['name']}"
                continue

            desc = str(ev.get("DESCRIPTION", "") or "").strip()
            merged[key] = {
                "title": title,
                "date": d.isoformat(),
                "end_date": end_d.isoformat() if end_d != d else None,
                "start": st,
                "end": et if st else None,
                "location": str(ev.get("LOCATION", "") or "").strip(),
                "notes": desc[:1500],
                "source": feed["name"],
                "children": list(feed["children"]),
            }
            by_title_time[match_key] = key
    return merged


def sync_feeds(graph: Graph | None, cal_id: str, state: dict, cfg: dict, dry: bool) -> dict:
    items = fetch_feed_items(cfg)
    stats = {"ny": 0, "opdateret": 0, "uændret": 0, "slettet": 0}

    # Nogle kalender-links giver samme aftale nyt UID ved hver hentning. Findes en
    # aftale under en ny nøgle, og ligger der en forsvundet aftale med samme titel,
    # dato og starttid, flyttes den gamle til den nye nøgle i stedet for slet/opret.
    orphans = {k: r for k, r in state["events"].items()
               if r.get("source") == "feed" and k not in items}
    rekeyed: set[str] = set()
    for key, item in items.items():
        if key in state["events"] or not orphans:
            continue
        subject = build_event(cfg, item)["subject"]
        for old_key, rec in list(orphans.items()):
            if (rec.get("date") == item["date"] and rec.get("subject") == subject
                    and rec.get("start", item.get("start")) == item.get("start")):
                del orphans[old_key]
                rekeyed.add(old_key)
                if dry:
                    log.info("[TØRKØRSEL] nyt UID, beholdes: %s", subject)
                else:
                    state["events"][key] = state["events"].pop(old_key)
                    log.info("nyt UID, beholdt: %s (%s)", subject, item["date"])
                break

    for key, item in items.items():
        if dry and key not in state["events"] and any(
            r.get("subject") == build_event(cfg, item)["subject"] and r.get("date") == item["date"]
            for k, r in state["events"].items() if k in rekeyed
        ):
            stats["uændret"] += 1
            continue
        stats[upsert(graph, cal_id, state, cfg, key, item, "feed", dry)] += 1

    # Slet fremtidige aftaler, der er forsvundet fra et kalender-link.
    today = now_local().date().isoformat()
    for key, rec in list(state["events"].items()):
        if key in rekeyed:
            continue
        if rec.get("source") == "feed" and key not in items and rec.get("date", "") >= today:
            if dry:
                log.info("[TØRKØRSEL] slettes: %s", rec.get("subject"))
            else:
                graph.delete_event(rec["id"])
                del state["events"][key]
                log.info("slettet: %s", rec.get("subject"))
            stats["slettet"] += 1
    log.info("Kalender-links: %s", stats)
    return stats


# --------------------------------------------------------------------------- #
# Manuelle aftaler (manuelle_aftaler.json)
# --------------------------------------------------------------------------- #
MANUAL_FILE = BASE / "manuelle_aftaler.json"


def sync_manual(graph: Graph | None, cal_id: str, state: dict, cfg: dict, dry: bool) -> dict:
    """Aftaler skrevet i hånden, fx fra noter fra et kontaktforældremøde."""
    stats = {"ny": 0, "opdateret": 0, "uændret": 0, "slettet": 0}
    items = load_json(MANUAL_FILE, [])
    keys = set()
    for item in items:
        if not item.get("date") or not item.get("title"):
            continue
        slug = re.sub(r"[^a-z0-9]+", "-", item["title"].lower()).strip("-")[:40]
        key = "manual:" + (item.get("key") or f"{item['date']}:{slug}")
        keys.add(key)
        item.setdefault("source", "Manuelt tilføjet")
        stats[upsert(graph, cal_id, state, cfg, key, item, "manual", dry)] += 1
    # Slet fremtidige aftaler, der er fjernet fra filen.
    today = now_local().date().isoformat()
    for key, rec in list(state["events"].items()):
        if rec.get("source") == "manual" and key not in keys and rec.get("date", "") >= today:
            if dry:
                log.info("[TØRKØRSEL] slettes: %s", rec.get("subject"))
            else:
                graph.delete_event(rec["id"])
                del state["events"][key]
                log.info("slettet: %s", rec.get("subject"))
            stats["slettet"] += 1
    if items or stats["slettet"]:
        log.info("Manuelle aftaler: %s", stats)
    return stats


# --------------------------------------------------------------------------- #
# Aula
# --------------------------------------------------------------------------- #
def aula_token_storage():
    """Aula-tokens krypteret i agent-mappen. En gammel ukrypteret fil fra aula-værktøjet flyttes hertil."""
    from aula.config import DEFAULT_TOKEN_FILE
    from aula.token_storage import TokenStorage

    class EncryptedTokenStorage(TokenStorage):
        async def load(self):
            try:
                text = read_secret(AULA_TOKENS, Path(DEFAULT_TOKEN_FILE))
            except SecretUnreadable as e:
                log.warning("%s Log ind i Aula igen.", e)
                return None
            except Exception as e:  # noqa: BLE001
                log.warning("Kunne ikke læse Aula-login: %s", e)
                return None
            if not text:
                return None
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                return None
            return data if isinstance(data, dict) and "tokens" in data else None

        async def save(self, data):
            write_secret(AULA_TOKENS, json.dumps(data))

        async def clear(self) -> bool:
            if AULA_TOKENS.exists():
                AULA_TOKENS.unlink()
                return True
            return False

    return EncryptedTokenStorage()


async def aula_client(cfg: dict):
    from aula.auth_flow import authenticate_and_create_client

    def on_login_required():
        raise AulaLoginRequired("Aula kræver nyt MitID-login")

    async def pick_identity(identities: list[str]) -> int:
        # Vælg den identitet, der blev valgt ved MitID-login (1 = første).
        return max(0, int(cfg.get("mitid_identity", 1)) - 1)

    return await authenticate_and_create_client(
        cfg["mitid_username"],
        aula_token_storage(),
        on_login_required=on_login_required,
        on_identity_selected=pick_identity,
    )


async def aula_keep_alive(cfg: dict) -> None:
    client = await aula_client(cfg)
    async with client:
        await client.keep_alive()
    log.info("Aula-login holdt i live")


async def aula_login_interactive(username: str, identity: int | None, force: bool) -> int | None:
    """MitID-login i terminalen. Returnerer valgt identitet (1 = første), hvis der var et valg."""
    from aula.auth_flow import authenticate

    try:  # Samme QR-visning som aula-værktøjet (de to halvdele skifter på samme sted).
        from aula.cli import _TerminalQRDisplay

        qr = _TerminalQRDisplay()
        shown = {"intro": False}

        def on_qr(q1, q2):
            if not shown["intro"]:
                print("\nÅbn MitID-appen på din telefon og scan QR-koden herunder:\n")
                shown["intro"] = True
            qr.show(q1, q2)

        on_qr_done = qr.done
    except Exception:  # noqa: BLE001
        qr = None

        def on_qr(q1, q2):
            print("Åbn MitID-appen på din telefon og scan begge QR-koder herunder:")
            q1.print_ascii(invert=True)
            q2.print_ascii(invert=True)

        on_qr_done = None

    chosen: dict[str, int | None] = {"identity": None}

    async def pick(identities: list[str]) -> int:
        if identity and 1 <= identity <= len(identities):
            chosen["identity"] = identity
        else:
            print("\nDu har flere identiteter i MitID. Vælg dig selv som privatperson:")
            for i, name in enumerate(identities, 1):
                print(f"  {i}. {name}")
            chosen["identity"] = ask_int("Nummer", 1, len(identities), 1)
        return chosen["identity"] - 1

    def show_otp(code: str) -> None:
        print(f"\nÅbn MitID-appen på din telefon og skriv denne kode: {code}\n")

    try:
        await authenticate(
            username,
            aula_token_storage(),
            on_qr_codes=on_qr,
            on_qr_done=on_qr_done,
            on_otp_code=show_otp,
            on_login_required=lambda: print("Åbn MitID-appen på din telefon og godkend login til Aula."),
            force_login=force,
            on_identity_selected=pick,
        )
    finally:
        if qr is not None:
            qr.stop()
    return chosen["identity"]


CLASS_RE = re.compile(r"^\s*(\d{1,2})\s*[.\s-]?\s*([a-zA-ZæøåÆØÅ])\s*$")


def normalize_class(name: str) -> str | None:
    """'4C', '4 c' og '4.c' bliver til '4.c'. Andet giver None."""
    m = CLASS_RE.match(name or "")
    return f"{int(m.group(1))}.{m.group(2).lower()}" if m else None


def previous_class_names(cls: str) -> list[str]:
    m = CLASS_RE.match(cls or "")
    if not m or int(m.group(1)) == 0:
        return []
    n, letter = int(m.group(1)) - 1, m.group(2)
    return [f"{n}{letter.upper()}", f"{n}.{letter.lower()}"]


GRADE_RANGE_RE = re.compile(r"(\d{1,2})\.?\s*-\s*(\d{1,2})\.?\s*årgang", re.I)
GRADE_RE = re.compile(r"(\d{1,2})\.\s*årgang", re.I)
CLASS_PREFIX_RE = re.compile(r"^\s*(\d{1,2})\s*[.\s-]?\s*([a-zæøå])(?![a-zæøå])", re.I)


def contact_parent_classes(groups: list[str], classes: list[str]) -> list[str]:
    """Klasser, hvor forælderen er med i kontaktforældregruppen (fx "4.C Kontaktforældre")."""
    out = []
    for g in groups:
        if "kontaktforæld" not in g.lower():
            continue
        c = CLASS_PREFIX_RE.match(g)
        if not c:
            continue
        cls = f"{int(c.group(1))}.{c.group(2).lower()}"
        if cls in classes and cls not in out:
            out.append(cls)
    return out


def groups_for_class(groups: list[str], cls: str) -> list[str]:
    """Aula giver også søskendes grupper, når man spørger på et barn. Behold dem, der passer til klassen.

    Grupper med klasse ("4C", "4.C Kontaktforældre"), årgang, årgangsinterval eller spor beholdes kun,
    hvis de passer. Andre grupper (skolebrede, SFO) beholdes.
    """
    m = CLASS_RE.match(cls or "") or re.match(r"^\s*(\d{1,2})\.([a-zæøå])", cls or "", re.I)
    if not m:
        return [g for g in groups if "forældre" not in g.lower() or "inkl" in g.lower()]
    grade, letter = int(m.group(1)), m.group(2).lower()
    out = []
    for g in groups:
        low = g.lower()
        sp = re.match(r"^\s*([a-zæøå])[\s-]*spor", g, re.I)
        if sp:
            if sp.group(1).lower() == letter:
                out.append(g)
            continue
        r = GRADE_RANGE_RE.search(g)
        if r:
            if int(r.group(1)) <= grade <= int(r.group(2)):
                out.append(g)
            continue
        y = GRADE_RE.search(g)
        if y:
            if int(y.group(1)) == grade:
                out.append(g)
            continue
        c = CLASS_PREFIX_RE.match(g)
        if c and not low.startswith(("team", "hold")):
            if int(c.group(1)) == grade and c.group(2).lower() == letter:
                out.append(g)
            continue
        out.append(g)
    return out


async def aula_discover(cfg: dict) -> dict:
    """Henter forælderens navn og børnenes skole, klasse og grupper fra Aula."""
    client = await aula_client(cfg)
    async with client:
        prof = await client.get_profile()
        children = []
        for c in prof.children:
            groups: list[str] = []
            try:
                for g in await client.get_groups(child_institution_profile_ids=[c.id]):
                    if g.name and g.name not in groups:
                        groups.append(g.name)
            except Exception as e:  # noqa: BLE001
                log.warning("Kunne ikke hente grupper for %s: %s", c.name, e)
            main_group = None
            aula_log = logging.getLogger("aula")
            old_level = aula_log.level
            aula_log.setLevel(logging.ERROR)  # "No daily overview data" i weekender er ikke en fejl
            try:
                ov = await client.get_daily_overview(c.id)
                if ov and ov.main_group and ov.main_group.name:
                    main_group = ov.main_group.name
            except Exception:  # noqa: BLE001
                pass
            finally:
                aula_log.setLevel(old_level)
            guess = normalize_class(main_group or "")
            if not guess:
                guess = next((normalize_class(g) for g in groups if normalize_class(g)), None)
            children.append({
                "full_name": c.name,
                "school": c.institution_name,
                "class_guess": guess or "",
                "groups": groups,
            })
    return {"parent_name": prof.display_name, "children": children}


def _plain(obj):
    from aula.utils.json import to_json

    return json.loads(to_json(obj))


async def aula_fetch(cfg: dict, since: datetime, week: tuple[date, date] | None = None,
                     context_since: datetime | None = None
                     ) -> tuple[list[dict], list[dict], dict | None]:
    """Henter opslag og tråde, der er nye eller ændret siden 'since', og evt. ugeplanen.

    Med 'context_since' (tidligere end 'since') hentes også ældre opslag og tråde som
    baggrund for huskelisten; prepare_input markerer dem med "new": false.
    """
    fetch_since = min(since, context_since) if context_since else since
    from aula.models import Message

    client = await aula_client(cfg)
    async with client:
        prof = await client.get_profile()

        posts: list[dict] = []
        seen_posts: set = set()
        for page in range(1, 11):
            batch = await client.get_posts(
                institution_profile_ids=prof.institution_profile_ids, page=page, limit=20
            )
            if not batch:
                break
            stop = False
            for p in batch:
                pd = _plain(dict(p))
                if pd.get("id") in seen_posts:
                    continue  # aula < 1.15 lod sider overlappe
                seen_posts.add(pd.get("id"))
                ts = parse_dt(pd.get("timestamp"))
                if ts and ts < fetch_since:
                    stop = True
                    continue
                posts.append(pd)
            if stop:
                break

        threads: list[dict] = []
        for page in range(0, 10):
            resp = await client._request_with_version_retry(
                "get",
                f"{client.api_url}?method=messaging.getThreads&sortOn=date&orderDirection=desc&page={page}",
            )
            resp.raise_for_status()
            batch = (resp.json().get("data") or {}).get("threads") or []
            if not batch:
                break
            stop = False
            for t in batch:
                updated = parse_dt(t.get("lastUpdatedDate") or t.get("latestMessage", {}).get("sendDateTime"))
                if updated and updated < fetch_since:
                    stop = True
                    continue
                threads.append(t)
            if stop:
                break

        out_threads = []
        for t in threads:
            msgs: dict[str, dict] = {}
            for mpage in range(0, 10):
                resp = await client._request_with_version_retry(
                    "get",
                    f"{client.api_url}?method=messaging.getMessagesForThread"
                    f"&threadId={t.get('id')}&page={mpage}",
                )
                resp.raise_for_status()
                raw = (resp.json().get("data") or {}).get("messages") or []
                new = 0
                for m in raw:
                    if m.get("messageType") not in ("Message", "MessageEdited"):
                        continue
                    mid = str(m.get("id"))
                    if mid not in msgs:
                        msgs[mid] = _plain(dict(Message.from_dict(m)))
                        new += 1
                if not raw or new == 0:
                    break
            out_threads.append(
                {
                    "thread_id": t.get("id"),
                    "subject": t.get("subject"),
                    # Deltagerlisten ("Forælder (Barn)" for hele klassen) sendes ikke til AI'en.
                    # Kun antallet, og hvilke af ens egne børn tråden vedrører.
                    "participant_count": len(t.get("participants") or []),
                    "regarding_children": own_children(
                        cfg, [c.get("displayName") for c in (t.get("regardingChildren") or []) if isinstance(c, dict)]
                    ),
                    "messages": sorted(msgs.values(), key=lambda m: m.get("send_datetime") or ""),
                }
            )
        week_plan = None
        if week:
            try:
                week_plan = await fetch_week_plan(client, prof, cfg, *week)
            except AulaLoginRequired:
                raise
            except Exception as e:  # noqa: BLE001
                log.exception("Ugeplanen kunne ikke hentes")
                week_plan = {"notes": [f"Ugeplanen kunne ikke hentes: {e}"], "children": {}, "sources": []}
    n_new = sum(1 for x in posts if (parse_dt(x.get("timestamp")) or since) >= since)
    log.info("Aula: %d opslag (%d nye) og %d tråde siden %s", len(posts), n_new, len(out_threads),
             fetch_since.date())
    return posts, out_threads, week_plan


# --------------------------------------------------------------------------- #
# Ugeplan: skema, ugeplaner og Huskelisten for den kommende skoleuge
# --------------------------------------------------------------------------- #
WEEKDAYS = ["mandag", "tirsdag", "onsdag", "torsdag", "fredag", "lørdag", "søndag"]
W_MU_UGEPLAN, W_MU_TASKS, W_MU_SSO = "0029", "0030", "0023"
W_MEEBOOK, W_HUSKELISTEN = "0004", "0062"
W_EASYIQ = ("0128", "0001", "0142")
PLAN_TEXT_MAX = 6000


def plan_week(today: date) -> tuple[date, date]:
    """Hverdag: denne uge. Weekend (fx søndagskørslen): næste uge."""
    monday = today - timedelta(days=today.weekday())
    if today.weekday() >= 5:
        monday += timedelta(days=7)
    return monday, monday + timedelta(days=4)


def _child_name(cfg: dict, aula_name: str | None) -> str | None:
    words = {w.lower() for w in re.split(r"[\s\-]+", aula_name or "") if w}
    for c in cfg["children"]:
        if c["name"].lower() in words:
            return c["name"]
    return None


def own_children(cfg: dict, aula_names: list) -> list[str]:
    """Egne børns fornavne (fra config) ud fra Aulas navne. Andre navne udelades."""
    out: list[str] = []
    for n in aula_names:
        name = _child_name(cfg, n)
        if name and name not in out:
            out.append(name)
    return out


def _plan_date(value: str, monday: date) -> str:
    """Meebook skriver fx "mandag 9. nov."; omsæt til ISO-dato i den aktuelle uge."""
    v = (value or "").strip()
    try:
        return date.fromisoformat(v[:10]).isoformat()
    except ValueError:
        pass
    first = v.split(" ")[0].lower() if v else ""
    if first in WEEKDAYS[:5]:
        return (monday + timedelta(days=WEEKDAYS.index(first))).isoformat()
    m = re.match(r"\D*(\d{1,2})\.", v)
    if m:
        for i in range(5):
            d = monday + timedelta(days=i)
            if d.day == int(m.group(1)):
                return d.isoformat()
    return v


def _clip(text: str) -> str:
    text = (text or "").strip()
    return text if len(text) <= PLAN_TEXT_MAX else text[:PLAN_TEXT_MAX] + " [...]"


async def fetch_week_plan(client, prof, cfg: dict, monday: date, friday: date) -> dict:
    """Henter alt, der siger noget om skoleugen. Fejl i én kilde stopper ikke de andre.

    Skemaet kommer fra Aulas egen kalender. Ugeplaner kommer fra de widgets, skolen
    bruger (MinUddannelse, Meebook, EasyIQ), og Huskelisten fra MoMo.
    """
    iso = monday.isocalendar()
    week = f"{iso.year}-W{iso.week}"
    plan: dict = {
        "week": week,
        "from": monday.isoformat(),
        "to": friday.isoformat(),
        "days": {(monday + timedelta(days=i)).isoformat(): WEEKDAYS[i] for i in range(5)},
        "children": {c["name"]: {"schema": {}, "slut": {}, "ugeplan": [], "huskeliste": [], "opgaver": []}
                     for c in cfg["children"]},
        "sources": [],
        "notes": [],
    }
    kids = {}
    for ch in prof.children or []:
        name = _child_name(cfg, ch.name)
        if name:
            kids[name] = ch
        else:
            log.info("Ugeplan: barnet %s står ikke i config.json, springes over", ch.name)

    def child_for(aula_name):
        return _child_name(cfg, aula_name)

    # Skema (lektioner og begivenheder fra Aulas egen kalender)
    start = datetime.combine(monday, time(0, 0), TZ)
    end = datetime.combine(friday, time(23, 59), TZ)
    for name, ch in kids.items():
        try:
            events = await client.get_calendar_events([ch.id], start, end)
        except Exception as e:  # noqa: BLE001
            plan["notes"].append(f"Skema for {name} kunne ikke hentes: {e}")
            continue
        seen = set()
        for ev in sorted(events, key=lambda e: e.start_datetime):
            sd = ev.start_datetime.astimezone(TZ)
            ed = ev.end_datetime.astimezone(TZ) if ev.end_datetime else sd
            line = f"{sd:%H:%M}-{ed:%H:%M} {ev.title or '(uden titel)'}"
            if ev.location:
                line += f" ({ev.location})"
            if getattr(ev, "has_substitute", False):
                line += " [vikar]"
            key = (sd.date(), line)
            if key in seen:
                continue
            seen.add(key)
            plan["children"][name]["schema"].setdefault(sd.date().isoformat(), []).append(line)
            slut = plan["children"][name]["slut"]
            if ed.date() == sd.date() and ed.strftime("%H:%M") > slut.get(sd.date().isoformat(), ""):
                slut[sd.date().isoformat()] = ed.strftime("%H:%M")
        if events:
            plan["sources"].append(f"Skema {name}")

    # Widgets kræver UniLogin-id'er, institutionskoder og session-id
    child_filter = [str(ch._raw["userId"]) for ch in kids.values() if ch._raw and "userId" in ch._raw]
    inst_filter: list[str] = []
    for ch in kids.values():
        code = ((ch._raw or {}).get("institutionProfile") or {}).get("institutionCode")
        if code and str(code) not in inst_filter:
            inst_filter.append(str(code))
    try:
        ctx = await client.get_profile_context()
        session_uuid = ctx["data"]["userId"]
    except Exception as e:  # noqa: BLE001
        plan["notes"].append(f"Ugeplaner kunne ikke hentes (profil): {e}")
        return plan
    try:
        widgets = await client.get_widgets()
        available = {w.widget_id for w in widgets}
        plan["widgets"] = [{"id": w.widget_id, "navn": w.name, "leverandør": w.widget_supplier,
                            "type": w.widget_type} for w in widgets]
        log.info("Aula-widgets: %s", ", ".join(f"{w.widget_id} {w.name}" for w in widgets) or "ingen")
    except Exception as e:  # noqa: BLE001
        log.warning("Kunne ikke læse listen over widgets: %s", e)
        available = None

    w = client.widgets

    if available is None or W_MU_UGEPLAN in available:
        try:
            for person in await w.get_ugeplan(W_MU_UGEPLAN, child_filter, inst_filter, week, session_uuid):
                name = child_for(person.name)
                for inst in person.institutions:
                    for letter in inst.letters:
                        text = _clip(html_to_text(letter.content_html))
                        if name and text:
                            plan["children"][name]["ugeplan"].append({"kilde": f"MinUddannelse, {letter.group_name}", "tekst": text})
            plan["sources"].append("MinUddannelse ugeplan")
        except Exception as e:  # noqa: BLE001
            plan["notes"].append(f"MinUddannelse-ugeplan kunne ikke hentes: {e}")

    mu_task_widget = next((x for x in (W_MU_TASKS, W_MU_SSO) if available is not None and x in available), None)
    if mu_task_widget:
        try:
            for t in await w.get_mu_tasks(mu_task_widget, child_filter, inst_filter, week, session_uuid):
                name = child_for(t.student_name)
                if name:
                    subj = ", ".join(c.subject_name for c in t.classes if c.subject_name)
                    plan["children"][name]["opgaver"].append(
                        " - ".join(x for x in (t.weekday, subj, t.title, t.task_type) if x)
                    )
            plan["sources"].append("MinUddannelse opgaver")
        except Exception as e:  # noqa: BLE001
            plan["notes"].append(f"MinUddannelse-opgaver kunne ikke hentes: {e}")

    if available is None or W_MEEBOOK in available:
        # Meebook sender UniLogin med; navnet kan være kort, så UniLogin bruges først.
        by_unilogin = {str((ch._raw or {}).get("userId", "")).lower(): name for name, ch in kids.items()}
        try:
            students = await w.get_meebook_weekplan(child_filter, inst_filter, week, session_uuid)
            plan.setdefault("raw", {})["meebook"] = [getattr(st, "_raw", None) for st in students]
            found = 0
            for st in students:
                name = by_unilogin.get(str(st.unilogin or "").lower()) or child_for(st.name)
                if not name:
                    log.info("Meebook: eleven %s kunne ikke kobles til et barn", st.name)
                    continue
                for day in st.week_plan:
                    for t in day.tasks:
                        kind = "" if (t.type or "").lower() in ("comment", "task", "note") else t.type
                        text = " ".join(x for x in (f"[{t.pill}]" if t.pill else "", t.title or kind,
                                                    html_to_text(t.content)) if x)
                        if text:
                            plan["children"][name]["ugeplan"].append(
                                {"kilde": "Meebook", "dato": _plan_date(day.date, monday), "tekst": _clip(text)}
                            )
                            found += 1
            plan["sources"].append("Meebook")
            if not found and (available is not None or students):
                plan["notes"].append(
                    f"Meebook gav ingen ugeplan for {week} (ikke skrevet endnu, eller adgangen er udløbet)."
                )
        except Exception as e:  # noqa: BLE001
            if available is not None:
                plan["notes"].append(f"Meebook-ugeplan kunne ikke hentes: {e}")
            else:
                log.info("Meebook ikke tilgængelig: %s", e)

    easyiq = next((x for x in W_EASYIQ if available is not None and x in available), None)
    if easyiq:
        try:
            from aula.cli import _easyiq_child_user_ids
            all_ids = _easyiq_child_user_ids(ctx)
        except Exception:  # noqa: BLE001
            all_ids = child_filter
        for name, ch in kids.items():
            uid = str((ch._raw or {}).get("userId", ""))
            code = ((ch._raw or {}).get("institutionProfile") or {}).get("institutionCode")
            if not uid:
                continue
            try:
                appts = await w.get_easyiq_weekplan(
                    week, session_uuid, [str(code)] if code else inst_filter, uid,
                    child_profile_id=str(ch.id), all_child_user_ids=all_ids,
                    all_institution_filter=inst_filter, widget_id=easyiq,
                )
            except Exception as e:  # noqa: BLE001
                if type(e).__name__ != "EasyIQChildNotInPortal":
                    plan["notes"].append(f"EasyIQ-ugeplan for {name} kunne ikke hentes: {e}")
                continue
            for a in appts:
                text = " ".join(x for x in (a.start, a.title, html_to_text(a.description)) if x)
                if text:
                    plan["children"][name]["ugeplan"].append({"kilde": "EasyIQ", "tekst": _clip(text)})
            plan["sources"].append(f"EasyIQ {name}")

    if available is not None and W_HUSKELISTEN in available:
        try:
            users = await w.get_momo_reminders(child_filter, inst_filter, session_uuid,
                                               monday.isoformat(), friday.isoformat())
            for u in users:
                name = child_for(u.user_name)
                if not name:
                    continue
                for r in u.team_reminders:
                    plan["children"][name]["huskeliste"].append(
                        {"dato": r.due_date, "hold": r.team_name, "fag": r.subject_name, "tekst": html_to_text(r.reminder_text)}
                    )
                for r in u.assignment_reminders:
                    plan["children"][name]["huskeliste"].append(
                        {"dato": r.due_date, "hold": ", ".join(r.team_names), "tekst": html_to_text(r.assignment_text)}
                    )
            plan["sources"].append("Huskelisten")
        except Exception as e:  # noqa: BLE001
            plan["notes"].append(f"Huskelisten kunne ikke hentes: {e}")

    for n in plan["notes"]:
        log.warning("Ugeplan: %s", n)
    log.info("Ugeplan %s: kilder %s", week, ", ".join(plan["sources"]) or "ingen")
    return plan


def fri_from_schema(plan: dict | None) -> list[dict]:
    """Fri-tidspunkter direkte fra skemaet (bruges, når AI'en ikke har givet nogen)."""
    out = []
    for name, v in ((plan or {}).get("children") or {}).items():
        for d, t in sorted((v.get("slut") or {}).items()):
            out.append({"date": d, "children": [name], "time": t})
    return out


def week_plan_has_content(plan: dict | None) -> bool:
    return bool(plan) and any(
        v["schema"] or v["ugeplan"] or v["huskeliste"] or v["opgaver"] for v in plan["children"].values()
    )


# --------------------------------------------------------------------------- #
# Vedhæftninger
# --------------------------------------------------------------------------- #
def extract_text(path: Path, ext: str) -> str:
    try:
        if ext == ".docx":
            import docx

            d = docx.Document(str(path))
            parts = [p.text for p in d.paragraphs]
            for table in d.tables:
                for row in table.rows:
                    parts.append(" | ".join(c.text.strip() for c in row.cells))
            return "\n".join(p for p in parts if p.strip())
        if ext == ".pdf":
            from pypdf import PdfReader

            return "\n".join((pg.extract_text() or "") for pg in PdfReader(str(path)).pages).strip()
    except Exception as e:  # noqa: BLE001
        return f"[kunne ikke læse tekst: {e}]"
    return ""


IMAGE_MODES = ("text", "auto", "always", "never")
IMAGE_TEXT_MIN = 15       # Færre tegn end det er sjældent en invitation (fx et skilt i baggrunden af et foto).
IMAGE_TEXT_MAX = 3000
IMAGE_TEXT_MAX_FILES = 10  # Flere billeder i ét opslag/én besked er et fotoalbum; resten læses ikke.
IMAGE_AUTO_MAX = 3            # Flere billeder i ét opslag/én besked er typisk fotos fra en tur eller fest.
IMAGE_AUTO_SHORT_TEXT = 300   # Under så mange tegn tekst kan indholdet stå i billedet (fx en invitation).
IMAGE_AUTO_HINT = re.compile(r"invit|indbyd|vedhæft|vedlagt|program", re.I)
IMAGE_AUTO_PHOTOS = re.compile(r"(billeder|fotos?|foto)\s+(fra|af)\b|galleri", re.I)


def images_mode(cfg: dict | None) -> str:
    mode = str((cfg or {}).get("send_images", "text")).strip().lower()
    return mode if mode in IMAGE_MODES else "text"


def allow_images(mode: str, text: str, n_images: int) -> bool:
    """Afgør, om billederne i ét opslag eller én besked må sendes til AI'en.

    "auto": kun når billederne sandsynligvis bærer oplysninger (fx en invitation som billede):
    højst IMAGE_AUTO_MAX billeder, teksten handler ikke om fotos, og teksten er kort eller
    henviser til en invitation, vedhæftning eller et program.
    """
    if mode == "always":
        return True
    if mode in ("never", "text") or n_images == 0 or n_images > IMAGE_AUTO_MAX:
        return False
    text = text or ""
    if IMAGE_AUTO_PHOTOS.search(text):
        return False
    return len(text.strip()) < IMAGE_AUTO_SHORT_TEXT or bool(IMAGE_AUTO_HINT.search(text))


OCR_PS = r"""
$ErrorActionPreference = 'Stop'; $ProgressPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics, ContentType = WindowsRuntime]
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
$null = [Windows.Storage.Streams.RandomAccessStream, Windows.Storage.Streams, ContentType = WindowsRuntime]
$null = [Windows.Globalization.Language, Windows.Globalization, ContentType = WindowsRuntime]
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($op, $type) { $t = $asTask.MakeGenericMethod($type).Invoke($null, @($op)); $t.Wait(-1) | Out-Null; $t.Result }
$lang = New-Object Windows.Globalization.Language 'da-DK'
$danish = [Windows.Media.Ocr.OcrEngine]::IsLanguageSupported($lang)
$engine = $null
if ($danish) { $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($lang) }
if ($null -eq $engine) { $engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages() }
$out = @{ danish = $danish; engine = ($null -ne $engine); texts = @{}; errors = @{} }
if ($null -ne $engine) {
    $out.language = $engine.RecognizerLanguage.LanguageTag
    foreach ($item in ($env:AULA_OCR_PATHS -split '\|')) {
        $p = [string]$item
        try {
            $file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($p)) ([Windows.Storage.StorageFile])
            $stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
            $decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
            $bmp = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
            $res = Await ($engine.RecognizeAsync($bmp)) ([Windows.Media.Ocr.OcrResult])
            $out.texts[$p] = [string](@($res.Lines | ForEach-Object { $_.Text }) -join "`n")
            $stream.Dispose()
        } catch { $out.errors[$p] = [string]$_.Exception.Message }
    }
}
$out | ConvertTo-Json -Compress -Depth 4
"""
OCR_MAX_SIDE = 2600
_ocr_state: dict = {}


def ocr_images(paths: list[Path]) -> dict[Path, str] | None:
    """Læser teksten i billeder lokalt med Windows' indbyggede tekstgenkendelse (OCR).

    Kaldes gennem Windows PowerShell, så der ikke skal installeres noget. Billederne forlader
    ikke computeren. Returnerer None, hvis OCR ikke findes (fx ikke Windows).
    """
    if sys.platform != "win32" or _ocr_state.get("unavailable"):
        return None
    if not paths:
        return {}
    sent: dict[str, Path] = {}
    temp: list[Path] = []
    for p in paths:
        src = p
        try:  # Ret orientering og størrelse, og gem som PNG, som Windows altid kan læse.
            from PIL import Image, ImageOps

            with Image.open(p) as im:
                im = ImageOps.exif_transpose(im).convert("RGB")
                im.thumbnail((OCR_MAX_SIDE, OCR_MAX_SIDE))
                src = p.with_name(p.name + ".ocr.png")
                im.save(src)
            temp.append(src)
        except Exception:  # noqa: BLE001
            src = p
        sent[str(src.resolve())] = p
    try:
        proc = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-EncodedCommand",
             base64.b64encode(OCR_PS.encode("utf-16-le")).decode("ascii")],
            capture_output=True, timeout=60 + 20 * len(sent),
            env={**os.environ, "AULA_OCR_PATHS": "|".join(sent)},
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        text = proc.stdout.decode("utf-8", "replace")
        if "{" not in text:
            raise RuntimeError(re.sub(r"\s+", " ", proc.stderr.decode("utf-8", "replace"))[-600:] or "intet svar")
        data = json.loads(text[text.index("{"): text.rindex("}") + 1])
    except Exception as e:  # noqa: BLE001
        log.warning("Tekstgenkendelse (OCR) af billeder virkede ikke: %s", _short(e))
        _ocr_state["unavailable"] = True
        return None
    finally:
        for t in temp:
            t.unlink(missing_ok=True)
    if not data.get("engine"):
        log.warning("Windows har ingen tekstgenkendelse (OCR) installeret, så billeder læses ikke.")
        _ocr_state["unavailable"] = True
        return None
    if not data.get("danish") and not _ocr_state.get("warned"):
        _ocr_state["warned"] = True
        log.warning("Windows mangler dansk tekstgenkendelse (OCR); bruger %s. Æ, ø og å kan blive læst forkert.",
                    data.get("language"))
    for k, v in (data.get("errors") or {}).items():
        log.warning("Billedet %s kunne ikke læses: %s", sent.get(k, Path(k)).name, v)
    return {orig: (data.get("texts") or {}).get(k, "") or "" for k, orig in sent.items()}


def _att_name(a: dict) -> str:
    return a.get("name") or (a.get("file") or {}).get("name") or "ukendt"


def handle_attachments(atts, att_dir: Path, client: httpx.Client, text: str = "",
                       mode: str = "text") -> list[dict]:
    """Henter vedhæftninger. Billeder: "text" læser teksten lokalt (OCR) og sender kun den;
    "auto"/"always" sender selve billedet efter allow_images; "never" sender intet."""
    atts = [a for a in atts or [] if isinstance(a, dict)]
    # Dokumenter først, så deres tekst tæller med, når der tages stilling til billederne.
    atts.sort(key=lambda a: Path(_att_name(a)).suffix.lower() in IMG_EXT)
    n_images = sum(Path(_att_name(a)).suffix.lower() in IMG_EXT for a in atts)
    images_ok = None
    to_read: list[tuple[dict, Path]] = []
    result = []
    for a in atts:
        f = a.get("file") or {}
        name = _att_name(a)
        ext = Path(name).suffix.lower()
        item = {"name": name, "type": ext.lstrip(".") or "ukendt"}
        url = f.get("url")
        if ext in IMG_EXT and mode == "text":
            if url and len(to_read) < IMAGE_TEXT_MAX_FILES:
                path = att_dir / (str(a.get("id")) + "_" + re.sub(r'[<>:"/\\|?*]', "_", name)[:100])
                try:
                    r = client.get(url)
                    r.raise_for_status()
                    path.write_bytes(r.content)
                    to_read.append((item, path))
                except Exception as e:  # noqa: BLE001
                    item["note"] = f"download fejlede: {e}"
            item["image_not_sent"] = True
            result.append(item)
            continue
        if ext in IMG_EXT:
            if images_ok is None:
                doc_text = " ".join(r.get("text", "") for r in result)
                images_ok = allow_images(mode, f"{text}\n{doc_text}", n_images)
            if not images_ok:
                # Billedet hentes ikke og sendes ikke. AI'en ved kun, at det findes.
                item["image_not_sent"] = True
                result.append(item)
                continue
        if not url:
            result.append(item)
            continue
        safe = re.sub(r'[<>:"/\\|?*]', "_", name)[:100]
        path = att_dir / f"{a.get('id')}_{safe}"
        try:
            r = client.get(url)
            r.raise_for_status()
            path.write_bytes(r.content)
        except Exception as e:  # noqa: BLE001
            item["note"] = f"download fejlede: {e}"
            result.append(item)
            continue
        if ext in DOC_EXT:
            item["text"] = extract_text(path, ext)[:20000]
        elif ext in IMG_EXT:
            item["image_file"] = f"attachments/{path.name}"
        result.append(item)
    if to_read:
        try:
            texts = ocr_images([p for _, p in to_read])
        finally:
            for _, p in to_read:  # Billedet har gjort sit; kun teksten går videre.
                p.unlink(missing_ok=True)
        if texts is None:
            # Tekstgenkendelsen virker ikke her. Sig det til AI'en og (via ocr_problem) til forælderen.
            _ocr_state["unread"] = _ocr_state.get("unread", 0) + len(to_read)
            for item, _ in to_read:
                item["note"] = "billedet kunne ikke læses på computeren (tekstgenkendelse virker ikke)"
            return result
        for item, p in to_read:
            found = (texts.get(p) or "").strip()
            if len(found) >= IMAGE_TEXT_MIN:
                item["image_text"] = found[:IMAGE_TEXT_MAX]
    return result


def ocr_problem() -> str | None:
    """Besked til ugemailen, hvis billeder ikke kunne læses, eller dansk tekstgenkendelse mangler."""
    if _ocr_state.get("unread"):
        n = _ocr_state["unread"]
        return (
            f"{n} billede{'r' if n != 1 else ''} i Aula blev ikke læst, fordi Windows' tekstgenkendelse ikke "
            "virker på denne computer (se logs\\agent.log). Invitationer, der kun findes som billede, kan derfor "
            'mangle, så tjek selv Aula. Vil du hellere sende billederne til AI\'en, så sæt "send_images": "auto" '
            "i config.json."
        )
    if _ocr_state.get("warned"):
        return (
            "Windows mangler dansk tekstgenkendelse, så æ, ø og å i billeder kan blive læst forkert. Tilføj dansk "
            "under Indstillinger > Tid og sprog > Sprog og område."
        )
    return None


OLD_MESSAGES_CONTEXT = 30


def prepare_input(posts: list[dict], threads: list[dict], since: datetime, run_dir: Path,
                  cfg: dict | None = None) -> dict:
    mode = images_mode(cfg)
    att_dir = run_dir / "attachments"
    att_dir.mkdir(parents=True, exist_ok=True)
    out_posts, out_threads = [], []
    with httpx.Client(timeout=60, follow_redirects=True) as http:
        for p in posts:
            owner = p.get("owner") or {}
            ts = parse_dt(p.get("timestamp"))
            post_new = not ts or ts >= since
            post_text = html_to_text(p.get("content_html"))
            out_posts.append(
                {
                    "id": p.get("id"),
                    "title": p.get("title"),
                    "date": p.get("timestamp"),
                    "new": post_new,
                    "author": owner.get("full_name"),
                    "author_role": owner.get("role"),
                    "groups": [g.get("name") for g in p.get("shared_with_groups") or []],
                    "text": post_text,
                    "attachments": handle_attachments(p.get("attachments"), att_dir, http,
                                                      f"{p.get('title') or ''}\n{post_text}", mode)
                    if post_new
                    else [{"name": a.get("name")} for a in p.get("attachments") or []],
                }
            )
        for t in threads:
            msgs = []
            # Lange tråde (fx kontaktforældrenes) kan have hundredvis af beskeder. Send alle nye
            # og de seneste OLD_MESSAGES_CONTEXT ældre som sammenhæng; aftaler fra endnu ældre
            # beskeder står allerede i kalenderen (existing_events).
            all_msgs = t["messages"]
            new_flags = [bool((parse_dt(m.get("send_datetime")) or since) >= since) for m in all_msgs]
            old_idx = [i for i, f in enumerate(new_flags) if not f]
            keep_old = set(old_idx[-OLD_MESSAGES_CONTEXT:])
            omitted = len(old_idx) - len(keep_old)
            for i, m in enumerate(all_msgs):
                is_new = new_flags[i]
                if not is_new and i not in keep_old:
                    continue
                meta = None
                for a in m.get("attachments") or []:
                    meta = meta or (a.get("creator") or {}).get("metadata")
                msg_text = html_to_text(m.get("content_html"))
                msgs.append(
                    {
                        "sender": m.get("sender_name"),
                        "sender_info": meta,
                        "date": m.get("send_datetime"),
                        "new": is_new,
                        "text": msg_text,
                        # Vedhæftninger hentes kun for nye beskeder.
                        "attachments": handle_attachments(m.get("attachments"), att_dir, http, msg_text, mode)
                        if is_new
                        else [{"name": a.get("name")} for a in m.get("attachments") or []],
                    }
                )
            entry = {k: t[k] for k in ("thread_id", "subject", "participant_count", "regarding_children") if k in t}
            if omitted:
                entry["older_messages_omitted"] = omitted
            out_threads.append({**entry, "messages": msgs})
    return {"posts": out_posts, "threads": out_threads}


# --------------------------------------------------------------------------- #
# AI (Claude eller ChatGPT/OpenAI)
# --------------------------------------------------------------------------- #
OUTPUT_SPEC = """
## Output
Svar KUN med ét JSON-objekt i en ```json-blok, med denne form:

{
  "calendar": [
    {
      "key": "aula:<post-id eller thread-id>:<YYYY-MM-DD>:<kort-slug>",
      "children": ["Emma"],
      "title": "Kort titel uden barnets navn (præfiks tilføjes automatisk)",
      "date": "YYYY-MM-DD",
      "end_date": null,
      "start": "HH:MM eller null for heldag",
      "end": "HH:MM eller null",
      "location": "",
      "notes": "Hvad du skal gøre/medbringe, og hvem der arrangerer",
      "source": "Opslag/tråd: <titel>, <dato>",
      "update_reason": "kun ved en eksisterende key: hvad er nyt, fx 'tidspunkt aftalt: kl. 19'"
    }
  ],
  "weekly_mail": [
    {"children": ["Emma"], "category": "usikker|tilbud|overlap|uden dato|andet", "text": "..."}
  ],
  "fri": [
    {"date": "YYYY-MM-DD", "children": ["Emma"], "time": "HH:MM", "note": "grund på 1-3 ord, kun hvis det afviger fra skemaet"}
  ],
  "husk": [
    {"date": "YYYY-MM-DD", "children": ["Emma"], "text": "Idræt: idrætstøj og håndklæde. Computer opladet.", "source": "Skema, Ugeplan 3.a"},
    {"date": "YYYY-MM-DD", "children": ["Emma"], "type": "lektie", "text": "Lektie til torsdag: Læs kap. 3 + opgaver.", "source": "Ugeplan 3.a"}
  ]
}

Regler for "key":
- Brug samme key, hvis det samme arrangement allerede står i "existing_events" med en key, også selvom datoen er flyttet. Så bliver aftalen opdateret i stedet for duplikeret.
- Har nye beskeder ikke ændret noget væsentligt (dato, tid, sted, hvad forælderen skal gøre eller medbringe), så udelad aftalen fra "calendar". Omformulér ikke en eksisterende aftale.
- Er der nyt, så skriv kort i "update_reason", hvad der er nyt, og byg videre på de eksisterende "notes" i stedet for at skrive dem forfra. Uden "update_reason" bliver en aftale med uændret dato, tid og titel ikke opdateret.
- Står arrangementet allerede i "existing_events" (fx fra Aula-kalenderen eller en sportsklub) uden key, så udelad det fra "calendar".
- Ellers: lav en ny, stabil key ud fra kilde-id, dato og et kort slug.
"""


def family_section(cfg: dict) -> str:
    """Bygger afsnittet om familien ud fra config.json."""
    p = cfg["parent"]
    name = p["name"]
    role = p.get("role", "forælder")
    lines = ["## Familien"]
    lines.append(
        f"- Forælderen hedder {name} (står sådan i Aula) og er {role}. "
        f"Beskeder skrevet af {name} tæller som bekræftelser."
    )
    if p.get("contact_parent_in"):
        lines.append(f"- {name} er kontaktforælder i: {', '.join(p['contact_parent_in'])}.")
    for c in cfg["children"]:
        line = f"- **{c['name']}** går i **{c['class']}**"
        if c.get("school"):
            line += f" på {c['school']}"
        if c.get("department"):
            line += f" (afdeling {c['department']})"
        line += "."
        if c.get("previous_class_names"):
            prev = ", ".join(c["previous_class_names"])
            line += f" Klassen hed tidligere {prev}, så tråde med de navne gælder {c['name']}."
        if c.get("aula_groups"):
            line += f" Aula-grupper/ord der peger på {c['name']}: {', '.join(c['aula_groups'])}."
        if c.get("clubs"):
            line += f" Går i: {', '.join(c['clubs'])}."
        lines.append(line)
    if role == "far":
        lines.append("- Arrangementer kun for mødre (fx mødredrinks) er ikke med i kalenderen.")
    elif role == "mor":
        lines.append("- Arrangementer kun for fædre (fx fædreøl) er ikke med i kalenderen.")
    for note in cfg.get("family_notes", []):
        lines.append(f"- {note}")
    return "\n".join(lines) + "\n"


def cleanup_runs(cfg: dict) -> None:
    """Sletter gamle kørsler, da de indeholder Aula-indhold om andre familier."""
    keep_days = cfg.get("keep_runs_days", 7)
    limit = now_local().timestamp() - keep_days * 86400
    if not RUNS_DIR.exists():
        return
    for d in RUNS_DIR.iterdir():
        if d.is_dir() and d.stat().st_mtime < limit:
            shutil.rmtree(d, ignore_errors=True)


# Fælles ------------------------------------------------------------------- #
AI_MODES = ("claude-code", "api", "codex", "openai-api")
DEFAULT_API_MODEL = "claude-opus-5-5"
DEFAULT_OPENAI_MODEL = "gpt-6.1-sol"
# Codex med ChatGPT-login: prøv denne model først. Giver abonnementet ikke adgang
# (fx Go og Free), bruges abonnementets standardmodel i stedet.
DEFAULT_CODEX_MODEL = "gpt-6.1-sol"
DEFAULT_OPENAI_EFFORT = "high"
# Ældre Codex-versioner kan ikke læse OpenAIs nuværende modelliste.
MIN_CODEX_VERSION = (0, 167, 0)


def ai_mode(cfg: dict) -> str:
    """Hvilken AI der læser Aula. "claude_mode" er det gamle navn for feltet."""
    for field in ("ai_mode", "claude_mode"):
        mode = (cfg.get(field) or "").strip().lower()
        if mode in AI_MODES:
            return mode
    if api_key(cfg):
        return "api"
    if openai_key(cfg):
        return "openai-api"
    return "claude-code"


def claude_mode(cfg: dict) -> str:  # gammelt navn
    return ai_mode(cfg)


def is_openai(cfg: dict) -> bool:
    return ai_mode(cfg) in ("codex", "openai-api")


def ai_name(cfg: dict) -> str:
    """Navnet på AI'en i tekster til brugeren."""
    return {"codex": "ChatGPT", "openai-api": "OpenAI"}.get(ai_mode(cfg), "Claude")


def ai_company(cfg: dict) -> str:
    return "OpenAI" if is_openai(cfg) else "Anthropic"


def _stored_key(cfg: dict, field: str, env: str) -> str:
    stored = (cfg.get(field) or "").strip()
    if stored:
        stored = unprotect_text(stored).strip()
    return (stored or os.environ.get(env) or "").strip()


def api_key(cfg: dict) -> str:
    return _stored_key(cfg, "anthropic_api_key", "ANTHROPIC_API_KEY")


def openai_key(cfg: dict) -> str:
    return _stored_key(cfg, "openai_api_key", "OPENAI_API_KEY")


def protect_config_secrets(cfg: dict) -> bool:
    """Krypterer API-nøgler, der står i klartekst i config.json. Returnerer True, hvis cfg blev ændret."""
    changed = False
    for field in ("anthropic_api_key", "openai_api_key"):
        key = (cfg.get(field) or "").strip()
        if key and not key.startswith(SECRET_PREFIX) and can_protect():
            cfg[field] = protect_text(key)
            changed = True
    return changed


API_IMAGE_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
                   ".gif": "image/gif", ".webp": "image/webp"}
MAX_IMAGE_SIDE = 1568
MAX_IMAGE_BYTES = 3_500_000
IMAGE_TOOL_DESCRIPTION = (
    "Viser et vedhæftet billede fra data (feltet image_file). "
    "Brug det kun efter reglerne for vedhæftninger."
)
IMAGE_TOOL_SCHEMA = {
    "type": "object",
    "properties": {"image_file": {"type": "string", "description": "Værdien af image_file, fx attachments/123_foto.jpg"}},
    "required": ["image_file"],
}
IMAGE_TOOL = {"name": "laes_billede", "description": IMAGE_TOOL_DESCRIPTION, "input_schema": IMAGE_TOOL_SCHEMA}


def image_data(run_dir: Path, rel: str) -> tuple[bytes, str] | str:
    """Billede klar til AI'en, skaleret ned for at holde prisen nede. Returnerer (data, mediatype)
    eller en fejltekst. Kun filer i kørslens mappe."""
    root = run_dir.resolve()
    path = (run_dir / rel).resolve()
    if root not in path.parents or not path.is_file():
        return f"Filen {rel} findes ikke."
    try:
        from PIL import Image, ImageOps

        with Image.open(path) as im:
            im = ImageOps.exif_transpose(im)
            im.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
            if im.mode not in ("RGB", "L"):
                im = im.convert("RGB")
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=85)
        return buf.getvalue(), "image/jpeg"
    except Exception as e:  # noqa: BLE001
        media_type = API_IMAGE_TYPES.get(path.suffix.lower())
        data = path.read_bytes()
        if not media_type or len(data) > MAX_IMAGE_BYTES:
            return f"Billedet {rel} kan ikke vises ({e})."
        return data, media_type


def image_block(run_dir: Path, rel: str) -> dict | str:
    """Billede i Anthropics format."""
    img = image_data(run_dir, rel)
    if isinstance(img, str):
        return img
    data, media_type = img
    return {"type": "image", "source": {"type": "base64", "media_type": media_type,
                                        "data": base64.b64encode(data).decode()}}


def http_post(url: str, headers: dict, body: dict, name: str) -> dict:
    """POST med genforsøg ved overbelastning. 401 betyder afvist nøgle."""
    for attempt in range(5):
        try:
            r = httpx.post(url, headers=headers, json=body, timeout=600)
        except httpx.TransportError as e:
            if attempt == 4:
                raise RuntimeError(f"Kunne ikke nå {name}: {e}") from e
            _time.sleep(10 * (attempt + 1))
            continue
        if r.status_code in (429, 500, 502, 503, 504, 529) and attempt < 4 and "insufficient_quota" not in r.text:
            try:
                wait = float(r.headers.get("retry-after") or 0)
            except ValueError:
                wait = 0
            _time.sleep(min(max(wait, 10 * (attempt + 1)), 90))
            continue
        if r.status_code == 401:
            raise AiLoginRequired(f"{name} afviste nøglen (401)")
        if r.status_code >= 400:
            raise RuntimeError(f"{name} {r.status_code}: {r.text[:600]}")
        return r.json()
    raise RuntimeError(f"{name} svarede ikke efter flere forsøg")


# Claude via API-nøgle ------------------------------------------------------ #
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
# Listepriser i USD pr. million tokens: input, output, cache-skrivning, cache-læsning.
# Kun til den anslåede pris i loggen. Se https://claude.com/pricing.
API_PRICES = {
    "claude-sonnet-5-5": (2.0, 10.0, 2.5, 0.10),
    "claude-opus-5-5": (4.0, 20.0, 5.0, 0.20),
    "claude-haiku-5-5": (0.10, 0.50, 0.125, 0.01),
}


def anthropic_post(key: str, body: dict) -> dict:
    headers = {"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
    return http_post(ANTHROPIC_URL, headers, body, "Claude API")


def check_api_key(key: str) -> str | None:
    """Gratis tjek af nøglen. Returnerer en fejltekst eller None."""
    try:
        r = httpx.get(
            "https://api.anthropic.com/v1/models",
            headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
            timeout=30,
        )
    except httpx.TransportError as e:
        return f"kunne ikke nå api.anthropic.com: {e}"
    if r.status_code == 401:
        return "nøglen blev afvist"
    if r.status_code >= 400:
        return f"fejl {r.status_code}: {r.text[:200]}"
    return None


def api_cost(model: str, usage: dict) -> float | None:
    price = API_PRICES.get(model)
    if not price:
        return None
    inp, out, cw, cr = price
    return (usage.get("input_tokens", 0) * inp + usage.get("output_tokens", 0) * out
            + usage.get("cache_creation_input_tokens", 0) * cw
            + usage.get("cache_read_input_tokens", 0) * cr) / 1_000_000


def run_claude_api(cfg: dict, prompt: str, run_dir: Path) -> str:
    key = api_key(cfg)
    if not key:
        raise RuntimeError("Mangler anthropic_api_key i config.json")
    model = cfg.get("claude_model") or DEFAULT_API_MODEL
    max_turns = int(cfg.get("api_max_turns", 12))
    messages: list[dict] = [
        {"role": "user", "content": [{"type": "text", "text": prompt, "cache_control": {"type": "ephemeral"}}]}
    ]
    usage = {k: 0 for k in ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")}
    images = 0
    for turn in range(1, max_turns + 1):
        body = {
            "model": model,
            "max_tokens": int(cfg.get("api_max_tokens", 32000)),
            "thinking": {"type": "adaptive"},
            "tools": [IMAGE_TOOL],
            "messages": messages,
        }
        if cfg.get("claude_effort"):
            body["output_config"] = {"effort": cfg["claude_effort"]}
        if turn == max_turns:
            body["tool_choice"] = {"type": "none"}
        resp = anthropic_post(key, body)
        for k in usage:
            usage[k] += (resp.get("usage") or {}).get(k) or 0
        content = resp.get("content") or []
        messages.append({"role": "assistant", "content": content})
        if resp.get("stop_reason") == "max_tokens":
            raise RuntimeError("Claudes svar blev for langt (max_tokens). Hæv api_max_tokens i config.json.")
        if resp.get("stop_reason") != "tool_use":
            break
        results = []
        for block in content:
            if block.get("type") != "tool_use":
                continue
            img = image_block(run_dir, str((block.get("input") or {}).get("image_file", "")))
            images += isinstance(img, dict)
            results.append({"type": "tool_result", "tool_use_id": block["id"],
                            "content": [img] if isinstance(img, dict) else img})
        # Flyt cache-markøren til det nyeste, så billeder ikke betales fuldt i hver runde.
        for m in messages[1:]:
            if m["role"] == "user":
                for b in m["content"]:
                    b.pop("cache_control", None)
        if results:
            results[-1]["cache_control"] = {"type": "ephemeral"}
        messages.append({"role": "user", "content": results})

    cost = api_cost(model, usage)
    save_json(run_dir / "ai_usage.json", {"mode": "api", "model": model, "turns": turn, "images": images,
                                           "usage": usage, "estimated_usd": cost})
    log.info(
        "Claude API (%s): %d runder, %d billeder, %d tokens ind (%d fra cache), %d ud%s",
        model, turn, images,
        usage["input_tokens"] + usage["cache_creation_input_tokens"] + usage["cache_read_input_tokens"],
        usage["cache_read_input_tokens"], usage["output_tokens"],
        f", ca. {cost:.2f} USD" if cost is not None else "",
    )
    (run_dir / "ai_output.txt").write_text(json.dumps(content, ensure_ascii=False, indent=1), encoding="utf-8")
    return "".join(b.get("text", "") for b in content if b.get("type") == "text")


# Claude via Claude Code ---------------------------------------------------- #
def find_claude(cfg: dict) -> str | None:
    """Finder claude-kommandoen. Installationen på Windows sætter ikke altid stien,
    så ~/.local/bin bruges som reserve."""
    name = cfg.get("claude_command") or "claude"
    exe = shutil.which(name)
    if exe:
        return exe
    for cand in (Path.home() / ".local" / "bin" / "claude.exe", Path.home() / ".local" / "bin" / "claude"):
        if cand.is_file():
            return str(cand)
    return None


def run_claude_code(cfg: dict, prompt: str, run_dir: Path) -> str:
    exe = find_claude(cfg)
    if not exe:
        raise RuntimeError(
            "Kan ikke finde 'claude'. Installer Claude Code, eller sæt anthropic_api_key i config.json."
        )
    res = subprocess.run(
        [
            exe, "-p", "--output-format", "json",
            # Samme model som ved API-nøgle, så kvaliteten ikke afhænger af Claude Codes standard.
            "--model", cfg.get("claude_model") or DEFAULT_API_MODEL,
            # Kun læseværktøjet, ingen MCP-værktøjer, og alt, der kræver godkendelse, afvises.
            # Læsning uden for kørslens mappe (fx login-filer) er blokeret.
            "--tools", "Read",
            "--disallowedTools", "mcp__*",
            "--strict-mcp-config",
            "--permission-mode", "dontAsk",
            "--settings", json.dumps({"permissions": {"blockReadsOutsideWorkingDirectories": True}}),
        ],
        input=prompt,
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=run_dir,
        timeout=1800,
    )
    (run_dir / "ai_output.txt").write_text(res.stdout or "", encoding="utf-8")
    out = (res.stderr or "") + (res.stdout or "")
    try:
        parsed = json.loads(res.stdout)
    except (json.JSONDecodeError, TypeError):
        parsed = None
    is_error = res.returncode != 0 or (isinstance(parsed, dict) and parsed.get("is_error"))
    if is_error:
        reason = parsed.get("result", "") if isinstance(parsed, dict) else ""
        if CLAUDE_AUTH_PATTERN.search(reason or out):
            raise AiLoginRequired(reason or out[-300:])
        raise RuntimeError(f"Claude fejlede ({res.returncode}): {(reason or out)[-800:]}")
    if not isinstance(parsed, dict):
        return res.stdout or ""
    if parsed.get("total_cost_usd") is not None:
        log.info("Claude Code: ca. %.2f USD (listepris, tæller i abonnementet)", parsed["total_cost_usd"])
    return parsed.get("result", "")


# OpenAI via API-nøgle (Responses API) -------------------------------------- #
OPENAI_URL = "https://api.openai.com/v1/responses"
# Listepriser i USD pr. million tokens: input, cachet input, output.
# Kun til den anslåede pris i loggen. Se https://developers.openai.com/api/docs/pricing.
OPENAI_PRICES = {
    "gpt-6-astra": (10.0, 1.0, 50.0),
    "gpt-6.1-sol": (2.0, 0.10, 10.0),
    "gpt-6.1-terra": (1.0, 0.05, 5.0),
    "gpt-6-sol": (2.0, 0.20, 10.0),
    "gpt-6-luna": (0.10, 0.01, 0.50),
}
OPENAI_IMAGE_TOOL = {"type": "function", "name": "laes_billede", "description": IMAGE_TOOL_DESCRIPTION,
                     "parameters": IMAGE_TOOL_SCHEMA}


def openai_post(key: str, body: dict) -> dict:
    headers = {"authorization": f"Bearer {key}", "content-type": "application/json"}
    try:
        return http_post(OPENAI_URL, headers, body, "OpenAI API")
    except RuntimeError as e:
        msg = str(e)
        if "insufficient_quota" in msg or "billing" in msg.lower():
            raise RuntimeError("OpenAI-kontoen har ikke kredit nok. Fyld op på platform.openai.com under "
                               f"Billing, og kør igen. ({msg[:200]})") from e
        if "model_not_found" in msg or ("model" in msg.lower() and ("does not exist" in msg or "access" in msg.lower())):
            raise RuntimeError(f"Din OpenAI-konto har ikke adgang til modellen {body.get('model')}. Ret openai_model "
                               f"i config.json (fx gpt-6.1-sol), eller tjek kontoen på platform.openai.com. ({msg[:200]})") from e
        raise


def check_openai_key(key: str) -> str | None:
    """Gratis tjek af nøglen. Returnerer en fejltekst eller None."""
    try:
        r = httpx.get("https://api.openai.com/v1/models", headers={"authorization": f"Bearer {key}"}, timeout=30)
    except httpx.TransportError as e:
        return f"kunne ikke nå api.openai.com: {e}"
    if r.status_code == 401:
        return "nøglen blev afvist"
    if r.status_code >= 400:
        return f"fejl {r.status_code}: {r.text[:200]}"
    return None


def openai_cost(model: str, usage: dict) -> float | None:
    price = OPENAI_PRICES.get(model)
    if not price:
        return None
    inp, cached, out = price
    fresh = usage.get("input_tokens", 0) - usage.get("cached_tokens", 0)
    return (fresh * inp + usage.get("cached_tokens", 0) * cached + usage.get("output_tokens", 0) * out) / 1_000_000


def openai_image_output(run_dir: Path, rel: str) -> list[dict] | str:
    img = image_data(run_dir, rel)
    if isinstance(img, str):
        return img
    data, media_type = img
    return [{"type": "input_image", "detail": "high",
             "image_url": f"data:{media_type};base64,{base64.b64encode(data).decode()}"}]


def run_openai_api(cfg: dict, prompt: str, run_dir: Path) -> str:
    """Samme kontrakt som run_claude_api: returnerer svarteksten og skriver forbrug i kørslens mappe."""
    key = openai_key(cfg)
    if not key:
        raise RuntimeError("Mangler openai_api_key i config.json")
    model = cfg.get("openai_model") or DEFAULT_OPENAI_MODEL
    max_turns = int(cfg.get("api_max_turns", 12))
    items: list[dict] = [{"role": "user", "content": [{"type": "input_text", "text": prompt}]}]
    usage = {"input_tokens": 0, "cached_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0}
    images = 0
    text = ""
    for turn in range(1, max_turns + 1):
        body = {
            "model": model,
            "input": items,
            "tools": [OPENAI_IMAGE_TOOL],
            "reasoning": {"effort": cfg.get("openai_effort") or DEFAULT_OPENAI_EFFORT},
            "max_output_tokens": int(cfg.get("api_max_tokens", 32000)),
            # Gemmes ikke hos OpenAI. Tænkningen sendes krypteret tilbage mellem runderne.
            "store": False,
            "include": ["reasoning.encrypted_content"],
        }
        if turn == max_turns:
            body["tool_choice"] = "none"
        resp = openai_post(key, body)
        u = resp.get("usage") or {}
        usage["input_tokens"] += u.get("input_tokens") or 0
        usage["cached_tokens"] += (u.get("input_tokens_details") or {}).get("cached_tokens") or 0
        usage["output_tokens"] += u.get("output_tokens") or 0
        usage["reasoning_tokens"] += (u.get("output_tokens_details") or {}).get("reasoning_tokens") or 0
        output = resp.get("output") or []
        status = resp.get("status") or "completed"
        if status == "incomplete":
            reason = (resp.get("incomplete_details") or {}).get("reason", "")
            if reason == "max_output_tokens":
                raise RuntimeError("Svaret fra OpenAI blev for langt (max_output_tokens). Hæv api_max_tokens i config.json.")
            raise RuntimeError(f"OpenAI stoppede svaret før tid ({reason or 'ukendt grund'}).")
        if status != "completed":
            err = (resp.get("error") or {}).get("message") or status
            raise RuntimeError(f"OpenAI gennemførte ikke svaret ({status}): {err}")
        text = "".join(
            part.get("text", "")
            for item in output if item.get("type") == "message"
            for part in item.get("content") or [] if part.get("type") == "output_text"
        )
        calls = [item for item in output if item.get("type") == "function_call"]
        if not calls:
            break
        items.extend(output)
        for call in calls:
            try:
                rel = str(json.loads(call.get("arguments") or "{}").get("image_file", ""))
            except json.JSONDecodeError:
                rel = ""
            img = openai_image_output(run_dir, rel)
            images += isinstance(img, list)
            items.append({"type": "function_call_output", "call_id": call.get("call_id"), "output": img})

    if not text.strip():
        raise RuntimeError("OpenAI gav intet endeligt svar, så opslag og beskeder blev ikke gennemgået.")
    cost = openai_cost(model, usage)
    save_json(run_dir / "ai_usage.json", {"mode": "openai-api", "model": model, "turns": turn, "images": images,
                                           "usage": usage, "estimated_usd": cost})
    log.info(
        "OpenAI API (%s): %d runder, %d billeder, %d tokens ind (%d fra cache), %d ud%s",
        model, turn, images, usage["input_tokens"], usage["cached_tokens"], usage["output_tokens"],
        f", ca. {cost:.2f} USD" if cost is not None else "",
    )
    (run_dir / "ai_output.txt").write_text(json.dumps(output, ensure_ascii=False, indent=1), encoding="utf-8")
    return text


# ChatGPT via Codex CLI ----------------------------------------------------- #
def find_codex(cfg: dict) -> str | None:
    """Finder codex.exe. npm installerer kun en .cmd/.ps1-indpakning i stien; den selve
    programfil ligger dybere. Indpakningen bruges ikke, fordi cmd.exe kan ødelægge
    argumenter med anførselstegn."""
    name = cfg.get("codex_command") or "codex"
    found = shutil.which(name)
    if found and (sys.platform != "win32" or found.lower().endswith(".exe")):
        return found
    roots = []
    if found:
        roots.append(Path(found).parent)
    if os.environ.get("APPDATA"):
        roots.append(Path(os.environ["APPDATA"]) / "npm")
    for root in roots:
        for pattern in ("node_modules/@openai/codex/node_modules/@openai/codex-win32-*/vendor/*/bin/codex.exe",
                        "node_modules/@openai/codex-win32-*/vendor/*/bin/codex.exe"):
            hits = sorted(root.glob(pattern))
            if hits:
                return str(hits[0])
    for cand in (Path.home() / ".local" / "bin" / "codex.exe", Path.home() / ".codex" / "bin" / "codex.exe"):
        if cand.is_file():
            return str(cand)
    return None


def codex_version(exe: str) -> tuple[int, ...] | None:
    try:
        res = subprocess.run([exe, "--version"], capture_output=True, text=True, encoding="utf-8", timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", (res.stdout or "") + (res.stderr or ""))
    return tuple(int(x) for x in m.groups()) if m else None


def codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")


def codex_deny_paths() -> list[Path]:
    """Mapper, som Codex' kommandoer ikke må læse: hele brugermappen (dokumenter, browserprofiler,
    login) og agent-mappen og Codex' login, hvis de ligger et andet sted. Kun Codex' egen
    arbejdsmappe er undtaget (se codex_args). En profil, der kun tillader arbejdsmappen, afvises af
    Windows-sandkassen, så resten af disken er læsbar, men uden adgang til netværk og skrivning.
    Testet på Windows 11 med Codex 0.167: kørslen bliver ikke mærkbart langsommere."""
    home = Path.home()
    paths = [home]
    for p in (BASE, codex_home()):
        try:
            p.resolve().relative_to(home.resolve())
        except ValueError:
            paths.append(p)
    return [p for p in paths if p.exists()]


def _toml_str(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)


def codex_profile_args() -> list[str]:
    """Sandkasseprofilen "aula": kun læsning, intet netværk, hele brugermappen nægtet undtagen
    Codex' arbejdsmappe, og den stærke Windows-sandkasse."""
    rules = [f"{_toml_str(p.as_posix())}={_toml_str('deny')}" for p in codex_deny_paths()]
    # Arbejdsmappen ligger i %TEMP% under brugermappen. Den mere specifikke regel vinder.
    rules.append('":workspace_roots"={"."="read"}')
    args = [
        "-c", 'permissions.aula.extends=":read-only"',
        "-c", f"permissions.aula.filesystem={{{','.join(rules)}}}",
        "-c", "permissions.aula.network={enabled=false}",
    ]
    if sys.platform == "win32":
        # MXC (nyere Windows 11) kræver ingen administrator og er strengest. Findes den ikke, bruges
        # den stærke "elevated"-sandkasse, som kræver én godkendelse som administrator. Den svage
        # "unelevated" kan ikke nægte læsning, og så nægter Codex at køre.
        # prefer_mxc er markeret som under udvikling i Codex 0.167; selvtesten (codex_sandbox_check)
        # prøver derfor sandkassen af, og alle fejl stopper kørslen.
        args += ["-c", "features.prefer_mxc=true", "-c", "suppress_unstable_features_warning=true",
                 "-c", "windows.sandbox=elevated"]
    return args


def codex_sandbox_check(cfg: dict) -> str | None:
    """Prøver sandkassen af uden model: en kommando i sandkassen skal kunne læse arbejdsmappen,
    men ikke en fil i agent-mappen. Returnerer en fejltekst eller None.
    (Codex starter først sandkassen, når modellen kører en kommando, så en almindelig selvtest
    opdager ikke, at den mangler.)"""
    import tempfile

    exe = find_codex(cfg)
    if not exe:
        return "Codex er ikke installeret."
    work = Path(tempfile.mkdtemp(prefix="aula-codex-sandbox-"))
    canary = BASE / ".sandkassetest.txt"
    try:
        (work / "inde.txt").write_text("INDE-OK", encoding="utf-8")
        canary.write_text("UDE-LAEST", encoding="utf-8")
        if sys.platform == "win32":
            cmd = ["cmd", "/c", f'type "{work / "inde.txt"}" & type "{canary}"']
        else:
            cmd = ["sh", "-c", f'cat "{work / "inde.txt"}"; cat "{canary}"']
        try:
            res = subprocess.run([exe, "sandbox", "-P", "aula", "-C", str(work), *codex_profile_args(), *cmd],
                                 capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
        except (OSError, subprocess.SubprocessError) as e:
            return f"Codex' sikre sandkasse kan ikke starte ({e})."
        out = (res.stdout or "") + (res.stderr or "")
        if "UDE-LAEST" in out:
            return "Codex' sandkasse blokerede ikke læsning af agent-mappen. Agenten bruger ikke Codex på denne computer."
        if "INDE-OK" not in out:
            return f"Codex' sikre sandkasse kan ikke starte ({out.strip()[-300:] or res.returncode})."
        return None
    finally:
        canary.unlink(missing_ok=True)
        shutil.rmtree(work, ignore_errors=True)


def codex_args(cfg: dict, exe: str, work: Path, out_file: Path, model: str | None,
               images: list[Path]) -> list[str]:
    """Kommandolinjen til codex exec. Kommandoer, Codex kører, må kun læse (ikke skrive), har intet
    netværk og kan ikke læse de mapper, codex_deny_paths() nævner. Brugerens egen Codex-opsætning,
    MCP-servere og regler indlæses ikke."""
    args = [
        exe, "exec", "--json", "--ephemeral", "--skip-git-repo-check",
        "--ignore-user-config", "--ignore-rules",
        "-C", str(work), "-o", str(out_file),
        "-c", "default_permissions=aula",
        *codex_profile_args(),
        "-c", "approval_policy=never",
        "-c", "web_search=disabled",
        "-c", "project_doc_max_bytes=0",
        "-c", f"model_reasoning_effort={cfg.get('openai_effort') or DEFAULT_OPENAI_EFFORT}",
    ]
    for feature in ("shell_tool", "unified_exec", "multi_agent", "apps", "goals", "image_generation"):
        args += ["-c", f"features.{feature}=false"]
    if model:
        args += ["-m", model]
    for img in images:
        args += ["-i", str(img)]
    args.append("-")
    return args


def codex_images(payload_images: list[str], run_dir: Path, work: Path, limit: int) -> list[tuple[str, Path]]:
    """Kopierer (nedskalerede) billeder til Codex' arbejdsmappe. Codex får dem med i beskeden."""
    out = []
    for rel in payload_images[:limit]:
        img = image_data(run_dir, rel)
        if isinstance(img, str):
            continue
        data, media_type = img
        ext = {"image/jpeg": ".jpg", "image/png": ".png", "image/gif": ".gif", "image/webp": ".webp"}[media_type]
        target = work / f"billede_{len(out) + 1}{ext}"
        target.write_bytes(data)
        out.append((rel, target))
    return out


def _codex_events(stdout: str) -> tuple[dict, list[str]]:
    usage: dict = {}
    errors: list[str] = []
    for line in (stdout or "").splitlines():
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("type") == "turn.completed":
            for k, v in (ev.get("usage") or {}).items():
                usage[k] = usage.get(k, 0) + (v or 0)
        elif ev.get("type") in ("error", "turn.failed"):
            msg = ev.get("message") or (ev.get("error") or {}).get("message") or ""
            errors.append(str(msg))
    return usage, errors


def run_codex(cfg: dict, prompt: str, run_dir: Path, images: list[str] | None = None) -> str:
    """ChatGPT via Codex CLI (tæller i ChatGPT-abonnementet). Kører i en midlertidig mappe uden for
    agent-mappen, så login-filerne aldrig ligger ved siden af."""
    import tempfile

    exe = find_codex(cfg)
    if not exe:
        raise RuntimeError(
            "Kan ikke finde Codex CLI ('codex'). Kør Opsætning fra Start-menuen, eller installer den med: "
            "npm install -g @openai/codex"
        )
    version = codex_version(exe)
    if version is None or version < MIN_CODEX_VERSION:
        found = ".".join(map(str, version)) if version else "ukendt version"
        raise RuntimeError(
            f"Codex CLI er for gammel eller kan ikke læses ({found}, kræver mindst "
            f"{'.'.join(map(str, MIN_CODEX_VERSION))}). Kør Opsætning fra Start-menuen, "
            "eller opdater med: npm install -g @openai/codex@latest"
        )
    work = Path(tempfile.mkdtemp(prefix="aula-codex-"))
    try:
        attached = codex_images(images or [], run_dir, work, int(cfg.get("codex_max_images", 12)))
        if attached:
            prompt += "\n## Vedhæftede billeder\nBillederne er vedhæftet denne besked i denne rækkefølge:\n" + "\n".join(
                f"{i}. {rel}" for i, (rel, _) in enumerate(attached, 1)) + "\n"
        out_file = work / "svar.txt"
        configured = cfg.get("openai_model") or ""
        models = [configured] if configured else [DEFAULT_CODEX_MODEL, None]
        for model in models:
            args = codex_args(cfg, exe, work, out_file, model, [p for _, p in attached])
            res = subprocess.run(args, input=prompt, capture_output=True, text=True, encoding="utf-8",
                                 cwd=work, timeout=1800)
            usage, errors = _codex_events(res.stdout)
            out = "\n".join(errors) + "\n" + (res.stderr or "")
            if res.returncode == 0 and out_file.is_file():
                break
            if model and not configured and CODEX_MODEL_PATTERN.search(out):
                log.info("Abonnementet giver ikke adgang til %s i Codex; bruger standardmodellen", model)
                continue
            if CODEX_AUTH_PATTERN.search(out):
                raise AiLoginRequired(out.strip()[-300:])
            if CODEX_SANDBOX_PATTERN.search(out):
                raise CodexSandboxError(
                    "Codex kunne ikke starte sin sikre sandkasse, så kørslen blev stoppet for at beskytte dine "
                    "filer. Kør Opsætning fra Start-menuen, og sig ja til at sætte sandkassen op (Windows beder "
                    "om administrator-godkendelse). Detaljer: " + out.strip()[-300:]
                )
            raise RuntimeError(f"Codex fejlede ({res.returncode}): {out.strip()[-800:]}")
        text = out_file.read_text(encoding="utf-8")
        (run_dir / "ai_output.txt").write_text(res.stdout or "", encoding="utf-8")
        save_json(run_dir / "ai_usage.json", {"mode": "codex", "model": model or "standard", "images": len(attached),
                                               "usage": usage})
        log.info("Codex (%s): %d tokens ind (%d fra cache), %d ud, %d billeder (tæller i ChatGPT-abonnementet)",
                 model or "abonnementets standardmodel", usage.get("input_tokens", 0),
                 usage.get("cached_input_tokens", 0), usage.get("output_tokens", 0), len(attached))
        return text
    finally:
        shutil.rmtree(work, ignore_errors=True)


def payload_images(payload: dict) -> list[str]:
    """Alle image_file-felter i data, i rækkefølge."""
    found: list[str] = []

    def walk(x):
        if isinstance(x, dict):
            if isinstance(x.get("image_file"), str) and x["image_file"] not in found:
                found.append(x["image_file"])
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    walk(payload)
    return found


IMAGE_TEXT_HINT = 'Tekst i billeder er læst på computeren og står i "image_text". Selve billederne er ikke sendt med.'
IMAGE_HINTS = {
    "api": "Billeder kan ses med værktøjet laes_billede (feltet image_file). Brug det kun efter reglerne for vedhæftninger.",
    "openai-api": "Billeder kan ses med værktøjet laes_billede (feltet image_file). Brug det kun efter reglerne for vedhæftninger.",
    "claude-code": "Billeder ligger som filer i denne mappe (feltet image_file). Læs dem kun efter reglerne for vedhæftninger.",
    "codex": "Billederne er vedhæftet denne besked (se listen sidst). Brug dem kun efter reglerne for vedhæftninger. "
             "Du har ikke brug for at køre kommandoer.",
}


def run_ai(cfg: dict, payload: dict, run_dir: Path) -> dict:
    mode = ai_mode(cfg)
    rules = RULES_FILE.read_text(encoding="utf-8")
    prompt = (
        f"{rules}\n{family_section(cfg)}\n{OUTPUT_SPEC}\n"
        "## Data\n"
        f"{IMAGE_TEXT_HINT if images_mode(cfg) == 'text' else IMAGE_HINTS[mode]}\n\n"
        f"```json\n{json.dumps(payload, ensure_ascii=False, indent=1)}\n```\n"
    )
    (run_dir / "prompt.md").write_text(prompt, encoding="utf-8")
    log.info("Kører %s (%s) på %d opslag og %d tråde ...", ai_name(cfg), mode, len(payload["posts"]), len(payload["threads"]))
    n_new = sum(1 for x in payload["posts"] if x.get("new", True)) + sum(
        1 for t in payload["threads"] if any(m.get("new") for m in t.get("messages", [])))
    what = [f"{n_new} nye opslag og beskedtråde"] if n_new else []
    if payload.get("week_plan"):
        what.append("ugeplanen")
    say(f"{ai_name(cfg)} læser {' og '.join(what) or 'Aula'} (tager typisk 1-3 minutter) …")
    if mode == "api":
        text = run_claude_api(cfg, prompt, run_dir)
    elif mode == "openai-api":
        text = run_openai_api(cfg, prompt, run_dir)
    elif mode == "codex":
        text = run_codex(cfg, prompt, run_dir, payload_images(payload))
    else:
        text = run_claude_code(cfg, prompt, run_dir)
    m = re.search(r"```json\s*(\{.*\})\s*```", text, re.S)
    raw = m.group(1) if m else text[text.find("{"): text.rfind("}") + 1]
    try:
        result = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"{ai_name(cfg)} svarede ikke med gyldig JSON ({e}). Svaret står i ai_output.txt i kørslens mappe.") from e
    if not isinstance(result, dict):
        raise RuntimeError(f"{ai_name(cfg)} svarede ikke i det forventede format.")
    save_json(run_dir / "ai_result.json", result)
    return result



# --------------------------------------------------------------------------- #
# Ugemail
# --------------------------------------------------------------------------- #
def esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


LEKTIE_RE = re.compile(r"\b[Ll]ektier? til [a-zæøå]+:.*$")


def lektie_weekday(text: str, d: str) -> str:
    """'Lektie til i morgen' bliver til 'Lektie til tirsdag' ud fra dagen, punktet står på."""
    try:
        nxt = WEEKDAYS[(date.fromisoformat(d).weekday() + 1) % 7]
    except ValueError:
        return text
    return re.sub(r"(?i)\b(lektie(?:r)? til) i morgen", lambda m: f"{m.group(1)} {nxt}", text)


def mail_html(cfg: dict, changes: list[tuple[str, dict]], mail_items: list[dict], feed_stats: dict,
              errors: list[str] | None = None, husk: list[dict] | None = None,
              plan_note: str | None = None, fri: list[dict] | None = None) -> str:
    parts = ["<div style='font-family:Segoe UI,Arial,sans-serif;font-size:14px'>"]
    if errors:
        parts.append(
            "<div style='border:1px solid #c00;background:#fff3f3;padding:8px 12px;margin-bottom:12px'>"
            "<h3 style='color:#c00;margin:0 0 6px'>Fejl i denne kørsel</h3><ul style='margin:0'>"
        )
        for e in errors:
            parts.append(f"<li>{esc(e)}</li>")
        parts.append("</ul></div>")
    if husk or fri:
        parts.append("<h3>Husk i ugen</h3>")
        order = [c["name"] for c in cfg["children"]]
        days: dict[str, dict[str, dict]] = {}

        def slot(d: str, name: str) -> dict:
            return days.setdefault(d, {}).setdefault(name, {"texts": [], "lektier": [], "fri": None})

        for it in husk or []:
            for name in it.get("children") or []:
                text = lektie_weekday((it.get("text") or "").strip(), it.get("date", ""))
                sl = slot(it.get("date", ""), name)
                if it.get("type") == "lektie" or LEKTIE_RE.match(text):
                    main, lektie = "", text
                else:
                    m = LEKTIE_RE.search(text)
                    main, lektie = (text[:m.start()].strip(), m.group(0).strip()) if m else (text, "")
                if main and main not in sl["texts"]:
                    sl["texts"].append(main)
                if lektie:
                    lektie = lektie if lektie.endswith((".", "!", "?")) else lektie + "."
                    if lektie not in sl["lektier"]:
                        sl["lektier"].append(lektie)
        for it in fri or []:
            for name in it.get("children") or []:
                slot(it.get("date", ""), name)["fri"] = it
        for d in sorted(days):
            try:
                dd = date.fromisoformat(d)
                label = f"{WEEKDAYS[dd.weekday()].capitalize()} {dd.day}/{dd.month}"
                if dd == now_local().date():
                    label += " (i dag)"
            except ValueError:
                label = d or "Uden dato"
            parts.append(f"<p style='margin:8px 0 2px'><b>{esc(label)}</b></p><ul style='margin-top:0'>")
            names = sorted(days[d], key=lambda n: order.index(n) if n in order else len(order))
            for name in names:
                info = days[d][name]
                line = " ".join(t if t.endswith((".", "!", "?")) else t + "." for t in info["texts"])
                f = info["fri"]
                if f:
                    t = (f.get("time") or "").replace(":", ".")
                    if t:
                        fri_txt = f"Fri kl. {t}."
                        note = (f.get("note") or "").strip().rstrip(".")
                        if note:
                            fri_txt = f"<b>{fri_txt[:-1]}</b>."
                            key = re.split(r",|\(| kl\.", note)[0].strip()
                            if key.lower() not in line.lower():
                                fri_txt = fri_txt[:-1] + f" ({esc(note)})."
                    else:
                        fri_txt = f"<b>{esc((f.get('note') or 'Fri hele dagen').rstrip('.'))}</b>."
                    line = (esc(line) + " " if line else "") + fri_txt
                else:
                    line = esc(line)
                for lk in info["lektier"]:
                    line += ("<br>" if line else "") + esc(lk)
                parts.append(f"<li>{esc(child_prefix(cfg, [name]))}{line}</li>")
            parts.append("</ul>")
    if changes:
        parts.append("<h3>Lagt i kalenderen</h3><ul>")
        for action, it in sorted(changes, key=lambda x: (x[1]["date"], x[1].get("start") or "")):
            when = it["date"] + (f" kl. {it['start']}" if it.get("start") else "")
            prefix = child_prefix(cfg, it.get("children", []))
            why = f": {it['update_reason']}" if action == "opdateret" and it.get("update_reason") else ""
            parts.append(f"<li><b>{esc(when)}</b> {esc(prefix + it['title'])} <i>({action}{esc(why)})</i></li>")
        parts.append("</ul>")
    elif errors:
        parts.append("<p>Ingen nye aftaler fra opslag og beskeder (se fejl ovenfor).</p>")
    else:
        parts.append("<p>Ingen nye aftaler fra opslag og beskeder i denne uge.</p>")
    if mail_items:
        parts.append("<h3>Værd at kigge på</h3><ul>")
        for it in mail_items:
            prefix = child_prefix(cfg, it.get("children", []))
            parts.append(f"<li><b>{esc(it.get('category', ''))}</b> {esc(prefix)}{esc(it.get('text', ''))}</li>")
        parts.append("</ul>")
    if plan_note:
        parts.append(f"<p style='color:#666'>{esc(plan_note)}</p>")
    if cfg.get("feeds"):
        parts.append(
            f"<p style='color:#666'>Kalender-links: {feed_stats.get('ny', 0)} nye, "
            f"{feed_stats.get('opdateret', 0)} opdaterede, {feed_stats.get('slettet', 0)} slettede.</p>"
        )
    parts.append("</div>")
    return "".join(parts)


# --------------------------------------------------------------------------- #
# Opsætning
# --------------------------------------------------------------------------- #
def ask(text: str, default: str = "", required: bool = False) -> str:
    while True:
        suffix = f" [{default}, Enter = behold]" if default else ""
        answer = input(f"{text}{suffix}: ").strip()
        if answer:
            return answer
        if default or not required:
            return default
        print("  Skal udfyldes.")


def ask_yes(text: str, default: bool = False) -> bool:
    answer = input(f"{text} [{'J/n' if default else 'j/N'}]: ").strip().lower()
    return default if not answer else answer.startswith(("j", "y"))


def ask_int(text: str, low: int, high: int, default: int) -> int:
    while True:
        answer = input(f"{text} [{default}]: ").strip()
        if not answer:
            return default
        if answer.isdigit() and low <= int(answer) <= high:
            return int(answer)
        print(f"  Skriv et tal fra {low} til {high}.")


def ask_choice(text: str, options: list[str], default: str) -> str:
    while True:
        answer = ask(f"{text} ({'/'.join(options)})", default).lower()
        if answer in options:
            return answer
        print(f"  Vælg en af: {', '.join(options)}")


def heading(text: str) -> None:
    print(f"\n== {text}")


def ask_key(cfg: dict, field: str, current: str, check) -> None:
    """Beder om en API-nøgle, tjekker den og gemmer den krypteret."""
    while True:
        key = getpass.getpass("  Indsæt nøglen (vises ikke" + (", Enter = behold den gemte" if current else "") + "): ").strip()
        key = key or current
        if not key:
            print("  Ingen nøgle indsat.")
            continue
        err = check(key)
        if err is None:
            cfg[field] = protect_text(key)
            print("  OK: nøglen virker.")
            return
        print(f"  Nøglen virker ikke: {err}")
        if not ask_yes("  Prøv igen?", True):
            cfg[field] = protect_text(key)
            return


def set_mode(cfg: dict, mode: str) -> None:
    cfg["ai_mode"] = mode
    cfg.pop("claude_mode", None)


def refresh_path() -> None:
    """Henter PATH fra Windows igen, så et program, der lige er installeret, kan findes."""
    parts = []
    try:
        import winreg

        for root, key in ((winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
                          (winreg.HKEY_CURRENT_USER, "Environment")):
            try:
                with winreg.OpenKey(root, key) as k:
                    parts.append(os.path.expandvars(winreg.QueryValueEx(k, "Path")[0]))
            except OSError:
                pass
    except ImportError:
        pass
    extra = [str(Path.home() / ".local" / "bin")]
    if os.environ.get("APPDATA"):
        extra.append(str(Path(os.environ["APPDATA"]) / "npm"))
    os.environ["PATH"] = os.pathsep.join([os.environ.get("PATH", "")] + parts + extra)


def install_cli(name: str, script_url: str, found) -> bool:
    """Installerer Claude Code eller Codex med udbyderens officielle installationsscript (kun Windows).
    Prøver igen efter en pause (antivirus kan låse den nye fil), og Codex også med npm."""
    for attempt in range(2):
        if attempt:
            print("  Prøver igen om 15 sekunder ...")
            _time.sleep(15)
        staging = Path.home() / ".codex" / "packages" / "standalone" / "releases"
        for d in staging.glob(".staging.*") if staging.is_dir() else []:
            shutil.rmtree(d, ignore_errors=True)
        print(f"  Installerer {name} ...")
        subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", f"irm {script_url} | iex"])
        refresh_path()
        if found():
            return True
    npm = shutil.which("npm")
    if name == "Codex" and npm:
        print("  Prøver at installere Codex med npm ...")
        subprocess.run([npm, "install", "-g", "@openai/codex@latest"])
        refresh_path()
    if found():
        return True
    print(f"  {name} kunne ikke installeres. Tjek i Windows-sikkerhed > Beskyttelseshistorik, om programmet er")
    print("  blokeret, og kør Opsætning igen.")
    return False


API_HINT = "  Vil du hellere bruge en API-nøgle, så kør Opsætning fra Start-menuen igen og vælg api."


def setup_ai(cfg: dict, force_api: bool = False, provider: str | None = None) -> None:
    """Spørger altid, hvilken AI der skal læse Aula (Enter = nuværende eller installerede).
    provider er sat, når opsaet.ps1 allerede har spurgt."""
    has_claude = find_claude(cfg) is not None
    has_codex = find_codex(cfg) is not None
    keep_api = False  # en gemt API-nøgle beholdes kun, når API er valgt eller allerede bruges
    if provider is None and force_api:
        # opsaet.ps1 har allerede fået svaret "API-nøgle"
        heading("2. API-nøgle")
        provider = ask_choice("  Nøgle fra hvem? claude = Anthropic, chatgpt = OpenAI", ["claude", "chatgpt"],
                              "chatgpt" if is_openai(cfg) else "claude")
    elif provider is None:
        heading("2. AI (Claude eller ChatGPT)")
        configured = bool(cfg.get("ai_mode") or cfg.get("claude_mode"))
        if configured and ai_mode(cfg) in ("api", "openai-api"):
            default = "api"
        elif configured:
            default = "chatgpt" if is_openai(cfg) else "claude"
        else:
            default = "chatgpt" if has_codex and not has_claude else "claude"
        print("  Agenten bruger en AI til at læse Aula. Ugens opslag og beskeder sendes til den AI, du vælger.")
        print("  claude  = Claude-abonnement (Pro eller Max) via Claude Code")
        print("  chatgpt = ChatGPT-abonnement via Codex. Indholdet bruges til træning, medmindre du slår")
        print("            det fra i ChatGPT (Indstillinger > Datastyring).")
        print("  api     = API-nøgle fra Anthropic eller OpenAI. Du betaler pr. kørsel; ingen træning.")
        choice = ask_choice("  Hvilken AI skal læse Aula?", ["claude", "chatgpt", "api"], default)
        if choice == "api":
            force_api = True
            keep_api = True
            provider = ask_choice("  Nøgle fra hvem? claude = Anthropic, chatgpt = OpenAI", ["claude", "chatgpt"],
                                  "chatgpt" if is_openai(cfg) else "claude")
        else:
            provider = choice
    else:
        # opsaet.ps1 har allerede spurgt
        heading("2. Test af ChatGPT" if provider == "chatgpt" else "2. Claude")
    if provider == "chatgpt":
        setup_openai(cfg, force_api, has_codex, keep_api)
    else:
        setup_claude(cfg, force_api, has_claude, keep_api)


def setup_claude(cfg: dict, force_api: bool = False, has_code: bool | None = None, allow_keep_api: bool = True) -> None:
    if has_code is None:
        has_code = find_claude(cfg) is not None
    keep_api = allow_keep_api and ai_mode(cfg) == "api" and bool(api_key(cfg))
    if not force_api and has_code and not keep_api:
        set_mode(cfg, "claude-code")
        print("  OK: bruger Claude Code på denne computer (dit Claude-abonnement).")
        print(API_HINT)
        return
    if not force_api and not has_code and not keep_api and sys.platform == "win32" and ask_yes(
            "  Claude Code er ikke installeret. Har du et Claude-abonnement (Pro eller Max), og skal den installeres nu?", True):
        install_cli("Claude Code", "https://claude.ai/install.ps1", lambda: find_claude(cfg))
        exe = find_claude(cfg)
        if exe:
            print("  Log ind i Claude Code: svar på spørgsmålene (Enter er fint), log ind i browseren,")
            print("  og skriv /exit, når Claude Code er klar. Så fortsætter opsætningen.")
            input("  Tryk Enter for at starte Claude Code")
            subprocess.run([exe])
            set_mode(cfg, "claude-code")
            print("  OK: bruger Claude Code på denne computer (dit Claude-abonnement).")
            return
        if not ask_yes("  Vil du bruge en Claude API-nøgle i stedet?", False):
            set_mode(cfg, "claude-code")
            print("  Agenten er sat til Claude Code. Kør Opsætning igen, når den er installeret.")
            return
    if not force_api and not has_code and not keep_api:
        print("  Agenten bruger en API-nøgle fra Anthropic.")
    set_mode(cfg, "api")
    print("  Opret en nøgle på https://console.anthropic.com/settings/keys (kræver betalingskort og")
    print("  lidt kredit, fx 5 dollar). Sæt gerne en månedlig grænse under Limits.")
    ask_key(cfg, "anthropic_api_key", api_key(cfg), check_api_key)


def codex_selftest(cfg: dict) -> tuple[str | None, str]:
    """Kører Codex på en lille prompt. Returnerer (fejltekst eller None, model)."""
    import tempfile

    run_dir = Path(tempfile.mkdtemp(prefix="aula-codex-test-"))
    try:
        text = run_codex(cfg, 'Svar kun med denne JSON: {"ok": true}', run_dir)
        if '"ok"' not in text:
            return f"uventet svar: {text[:200]}", ""
        model = load_json(run_dir / "ai_usage.json", {}).get("model", "")
        err = codex_sandbox_check(cfg)
        if err:
            return err, model
        return None, model
    except AiLoginRequired as e:
        return f"Codex er ikke logget ind ({_short(e)}).", ""
    except CodexSandboxError as e:
        return f"Codex' sikre sandkasse kan ikke starte ({_short(e)}).", ""
    except Exception as e:  # noqa: BLE001
        return _short(e), ""
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)


def setup_openai(cfg: dict, force_api: bool = False, has_codex: bool | None = None, allow_keep_api: bool = True) -> None:
    if has_codex is None:
        has_codex = find_codex(cfg) is not None
    keep_api = allow_keep_api and ai_mode(cfg) == "openai-api" and bool(openai_key(cfg))
    if not force_api and has_codex and not keep_api:
        set_mode(cfg, "codex")
        print("  Tester Codex (ChatGPT) på denne computer ...")
        err, model = codex_selftest(cfg)
        if err is None:
            print("  OK: bruger Codex med dit ChatGPT-abonnement"
                  + (f" ({model})." if model and model != "standard" else " (abonnementets standardmodel)."))
            if model == "standard":
                print("  Dit abonnement giver kun Codex' mindre model (fx Luna med Go eller Free). Den overser")
                print("  flere ting end Claude Opus og GPT-6.1 Sol. Med ChatGPT Plus bruges GPT-6.1 Sol.")
            if os.environ.get("AULA_TRAENING_VIST") != "1":  # opsaet.ps1 har allerede vist den
                print("  Slå træning fra i ChatGPT: Indstillinger > Datastyring > 'Gør modellen bedre for alle'.")
            print(API_HINT)
            return
        exe = find_codex(cfg)
        for _ in range(2):
            if err and exe and "logget ind" in err and ask_yes("  Codex er ikke logget ind. Log ind med din ChatGPT-konto nu?", True):
                subprocess.run([exe, "login"])
            elif err and exe and "for gammel" in err and ask_yes("  Codex er for gammel. Opdater den nu?", True):
                npm = shutil.which("npm")
                if npm:
                    subprocess.run([npm, "install", "-g", "@openai/codex@latest"])
                else:
                    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
                                    "irm https://chatgpt.com/codex/install.ps1 | iex"])
            elif err and exe and "sandkasse" in err and ask_yes(
                    "  Codex' sikre sandkasse mangler. Sæt den op nu? Windows beder om administrator-godkendelse", True):
                subprocess.run([exe, "sandbox", "setup", "--elevated", "--current-user"])
            else:
                break
            err, model = codex_selftest(cfg)
            if err is None:
                print("  OK: Codex virker nu. Kør Opsætning igen, hvis du vil se modellen.")
                return
        print(f"  Codex virker ikke endnu: {err}")
        if not ask_yes("  Vil du bruge en OpenAI API-nøgle i stedet?", False):
            print("  Agenten bruger Codex. Ret fejlen ovenfor, og kør Opsætning igen.")
            return
    elif not force_api and not has_codex and not keep_api and sys.platform == "win32" and ask_yes(
            "  Codex er ikke installeret. Har du et ChatGPT-abonnement, og skal Codex installeres nu?", True):
        if install_cli("Codex", "https://chatgpt.com/codex/install.ps1", lambda: find_codex(cfg)):
            return setup_openai(cfg, False, True, False)
        if not ask_yes("  Vil du bruge en OpenAI API-nøgle i stedet?", False):
            set_mode(cfg, "codex")
            print("  Agenten er sat til Codex. Kør Opsætning igen, når Codex er installeret.")
            return
    if not force_api and not has_codex and not keep_api:
        print("  Agenten bruger en API-nøgle fra OpenAI.")
    set_mode(cfg, "openai-api")
    print("  Opret en nøgle på https://platform.openai.com/api-keys (kræver betalingskort og lidt")
    print("  kredit, fx 5 dollar). Et ChatGPT-abonnement giver ikke API-adgang; det betales for sig.")
    print("  Sæt gerne en månedlig grænse under Limits.")
    ask_key(cfg, "openai_api_key", openai_key(cfg), check_openai_key)


def setup_children(found: dict, existing: dict | None) -> list[dict]:
    """Børn, klasser og grupper fra Aula. Spørger kun, hvis en klasse ikke kan findes."""
    old_children = {c.get("name"): c for c in (existing or {}).get("children", [])}
    children = []
    for c in found["children"]:
        first = c["full_name"].split()[0] if c["full_name"] else "Barn"
        old = old_children.get(first, {})
        name = old.get("name") or first
        cls = old.get("class") or c["class_guess"]
        if not cls:
            print(f"\n  Kunne ikke finde {first}s klasse i Aula ({c['school']}).")
            cls = ask(f"  Hvilken klasse går {first} i? fx 4.c", "", True)
        cls = normalize_class(cls) or cls
        groups = groups_for_class(c["groups"], cls)[:15]
        children.append({
            "name": name,
            "label": f"{name} {cls}",
            "class": cls,
            "school": c["school"],
            "department": old.get("department", ""),
            "previous_class_names": old.get("previous_class_names") or previous_class_names(cls),
            "aula_groups": old.get("aula_groups") or groups,
            "clubs": old.get("clubs", []),
        })
    return children


def check_protection() -> str | None:
    """Prøver Windows-krypteringen af. Returnerer en fejltekst eller None."""
    if not can_protect():
        return None
    try:
        sample = "aula-kalender-agent test æøå"
        if unprotect_text(protect_text(sample)) != sample:
            return "krypteret tekst kom forkert tilbage"
    except Exception as e:  # noqa: BLE001
        return str(e) or e.__class__.__name__
    return None


def cmd_setup(existing: dict | None, force_api: bool = False, provider: str | None = None) -> int:
    print("Opsætning af Aula-kalenderagenten. Det tager et par minutter.")
    heading("Dine data")
    print("  Dit login til Aula og Outlook gemmes krypteret her på computeren. Det kan kun bruges")
    print("  af din Windows-bruger og sendes ikke til nogen. Din MitID-adgangskode gemmes slet ikke.")
    print("  For at finde datoerne sender agenten ugens opslag og beskeder fra Aula til den AI, du")
    print("  vælger (Claude fra Anthropic eller ChatGPT fra OpenAI), som læser dem. Ellers deles intet")
    print("  med andre end din egen Outlook.")
    err = check_protection()
    if err:
        print(f"STOP: Windows-krypteringen af login-filer virker ikke på denne computer ({err}).")
        return 1
    cfg = json.loads(json.dumps(existing)) if existing else load_json(EXAMPLE_CONFIG, {})
    if not existing:
        cfg["mitid_username"] = ""
        cfg["notify_email"] = ""
        cfg["feeds"] = []
        cfg["family_notes"] = []
        cfg["parent"] = {}
        cfg.pop("ai_mode", None)
        cfg.pop("claude_mode", None)

    heading("1. Aula-login med MitID")
    cfg["mitid_username"] = ask("Dit MitID-brugernavn (ikke dit Aula-brugernavn)", cfg.get("mitid_username", ""), True)
    identity = asyncio.run(aula_login_interactive(cfg["mitid_username"], None, force=False))
    cfg["mitid_identity"] = identity or cfg.get("mitid_identity") or 1
    print("  OK: logget ind i Aula.")

    found = asyncio.run(aula_discover(cfg))
    if not found["children"]:
        print("STOP: Fandt ingen børn på din Aula-profil.")
        return 1
    children = setup_children(found, existing)
    cfg["children"] = children

    parent = dict(cfg.get("parent") or {})
    if not parent.get("name") or parent["name"].startswith("Dit fulde navn"):
        parent["name"] = found["parent_name"]
    parent.setdefault("role", "forælder")
    if "contact_parent_in" not in parent or not existing:
        all_groups = [g for c in found["children"] for g in c["groups"]]
        parent["contact_parent_in"] = contact_parent_classes(all_groups, [c["class"] for c in children])
    cfg["parent"] = parent
    cfg.setdefault("feeds", [])
    cfg["feeds"] = [f for f in cfg["feeds"] if "INDSÆT" not in f.get("url", "")]
    cfg["calendar_name"] = cfg.get("calendar_name") or "Skole og fritid"

    print("\n  Fandt: " + ", ".join(f"{c['name']} {c['class']}" for c in children)
          + (f" på {children[0]['school']}" if len({c['school'] for c in children}) == 1 else ""))
    if parent["contact_parent_in"]:
        print(f"  Du er kontaktforælder i: {', '.join(parent['contact_parent_in'])}")

    setup_ai(cfg, force_api, provider)
    save_json(CONFIG_FILE, cfg)

    heading("3. Outlook-login")
    g = Graph(cfg, interactive=True)
    if not cfg.get("notify_email") and g.username:
        cfg["notify_email"] = g.username
    if not cfg.get("notify_email"):
        cfg["notify_email"] = ask("Mailadresse til ugemailen", "", True)
    g.calendar_id(cfg["calendar_name"])
    save_json(CONFIG_FILE, cfg)
    print(f"  OK: kalenderen '{cfg['calendar_name']}' er klar, og ugemailen går til {cfg['notify_email']}.")

    heading("Gemt")
    print(f"Indstillingerne er gemt i {CONFIG_FILE}. Navne, klasser og noter kan rettes dér.")
    return 0


def cmd_login_aula(cfg: dict) -> int:
    identity = asyncio.run(aula_login_interactive(cfg["mitid_username"], cfg.get("mitid_identity"), force=True))
    if identity and identity != cfg.get("mitid_identity"):
        cfg["mitid_identity"] = identity
        save_json(CONFIG_FILE, cfg)
    print("\nAula-login virker.")
    return 0


# --------------------------------------------------------------------------- #
# Kommandoer
# --------------------------------------------------------------------------- #
def notify_login(graph: Graph | None, cfg: dict, state: dict, what: str, how: str) -> None:
    text = f"{what}\n\nSådan gør du: {how}"
    log.warning(what)
    last = state.get("last_login_notice")
    if last and datetime.fromisoformat(last) > now_local() - timedelta(days=2):
        return
    try:
        if graph is None:
            raise RuntimeError("ingen Outlook-forbindelse")
        graph.send_mail(cfg["notify_email"], f"Aula-agent: {what}", f"<p>{esc(text).replace(chr(10), '<br>')}</p>")
    except Exception:  # noqa: BLE001
        desktop_notice(text)
    state["last_login_notice"] = now_local().isoformat()


def connect_graph(cfg: dict, state: dict) -> Graph | None:
    try:
        return Graph(cfg)
    except GraphLoginRequired:
        notify_login(
            None, cfg, state,
            "Outlook-login er udløbet",
            f"Åbn PowerShell i agent-mappen og kør: {RUN} login-outlook",
        )
        return None


def cmd_login_outlook(cfg: dict) -> None:
    g = Graph(cfg, interactive=True)
    cal_id = g.calendar_id(cfg["calendar_name"])
    n = len(g.list_events(cal_id, now_local().date(), now_local().date() + timedelta(days=400)))
    print(f"\nOutlook-login virker. Kalenderen '{cfg['calendar_name']}' har {n} kommende aftaler.")


def cmd_daily(cfg: dict, state: dict, dry: bool) -> int:
    graph = connect_graph(cfg, state)
    if graph is None:
        return 2
    cal_id = graph.calendar_id(cfg["calendar_name"])
    sync_feeds(graph, cal_id, state, cfg, dry)
    sync_manual(graph, cal_id, state, cfg, dry)
    try:
        asyncio.run(aula_keep_alive(cfg))
    except AulaLoginRequired:
        notify_login(graph, cfg, state, "Aula kræver nyt MitID-login",
                     "Åbn Start-menuen > Aula-kalenderagent > Log ind på Aula igen, og godkend i MitID-appen. "
                     f"Har du ikke genvejen: åbn PowerShell i agent-mappen og kør {RUN} login-aula")
    if not dry:
        state["last_daily"] = now_local().isoformat()
    return 0


AULA_LOGIN_HOW = (
    "Åbn Start-menuen > Aula-kalenderagent > Log ind på Aula igen, og godkend i MitID-appen. "
    "Genvejen kører også agenten bagefter. "
    f"Har du ikke genvejen: åbn PowerShell i agent-mappen og kør {RUN} login-aula og derefter {RUN} weekly"
)


def ai_login_how(cfg: dict) -> str:
    mode = ai_mode(cfg)
    if mode == "api":
        return (
            "Claude API afviste nøglen. Lav evt. en ny nøgle på console.anthropic.com, "
            f"og ret anthropic_api_key i config.json (eller kør: {RUN} opsaet). Kør derefter: {RUN} weekly"
        )
    if mode == "openai-api":
        return (
            "OpenAI API afviste nøglen. Lav evt. en ny nøgle på platform.openai.com/api-keys, "
            f"og ret openai_api_key i config.json (eller kør: {RUN} opsaet). Kør derefter: {RUN} weekly"
        )
    if mode == "codex":
        return (
            "Åbn PowerShell, kør: codex login, og log ind med din ChatGPT-konto i browseren. "
            f"Kør derefter i agent-mappen: {RUN} weekly"
        )
    return (
        "Åbn PowerShell, kør: claude, skriv /login og følg anvisningen, og afslut med /exit. "
        f"Kør derefter i agent-mappen: {RUN} weekly"
    )


claude_login_how = ai_login_how  # gammelt navn


def _short(e: BaseException) -> str:
    return (str(e) or e.__class__.__name__)[:300]


def existing_event(e: dict, managed: dict, state: dict) -> dict:
    key = managed.get(e["id"]) or ""
    out = {
        "key": key if key.startswith("aula:") else None,
        "subject": e.get("subject"),
        "start": (e.get("start") or {}).get("dateTime", "")[:16],
        "all_day": e.get("isAllDay"),
    }
    if out["key"]:
        rec = state["events"].get(key, {})
        if rec.get("location"):
            out["location"] = rec["location"]
        if rec.get("notes"):
            out["notes"] = rec["notes"]
    return out


def cmd_weekly(cfg: dict, state: dict, dry: bool, days: int | None) -> int:
    """Ugens kørsel. Sender altid ugemail; fejl står øverst med en sådan-gør-du-vejledning."""
    graph = connect_graph(cfg, state)
    if graph is None:
        return 2
    cal_id = graph.calendar_id(cfg["calendar_name"])
    errors: list[str] = []
    blocking = False  # sand = opslag/beskeder blev ikke gennemgået, så perioden tages med igen næste gang

    try:
        feed_stats = sync_feeds(graph, cal_id, state, cfg, dry)
    except Exception as e:  # noqa: BLE001
        log.exception("Kalender-links fejlede")
        errors.append(f"Kalender-links kunne ikke synkroniseres: {_short(e)}")
        feed_stats = {}
    try:
        sync_manual(graph, cal_id, state, cfg, dry)
    except Exception as e:  # noqa: BLE001
        log.exception("Manuelle aftaler fejlede")
        errors.append(f"Manuelle aftaler kunne ikke synkroniseres: {_short(e)}")

    if days is not None:
        since = now_local() - timedelta(days=days)
    elif state.get("last_weekly"):
        since = datetime.fromisoformat(state["last_weekly"]) - timedelta(days=2)
    else:
        since = now_local() - timedelta(days=cfg.get("first_run_days", 30))

    run_dir = RUNS_DIR / now_local().strftime("%Y%m%d_%H%M")
    run_dir.mkdir(parents=True, exist_ok=True)

    changes: list[tuple[str, dict]] = []
    mail_items: list[dict] = []
    husk: list[dict] = []
    fri: list[dict] = []
    result = None
    posts = threads = week_plan = None
    monday, friday = plan_week(now_local().date())
    use_plan = cfg.get("ugeplan", True)
    context_since = datetime.combine(monday - timedelta(days=10), time(0, 0), TZ)
    say("Læser Aula …")
    try:
        posts, threads, week_plan = asyncio.run(
            aula_fetch(cfg, since, (monday, friday) if use_plan else None,
                       context_since if use_plan else None)
        )
    except AulaLoginRequired:
        log.warning("Aula kræver nyt MitID-login")
        errors.append("Aula kræver nyt MitID-login, så opslag og beskeder blev ikke læst. Sådan gør du: " + AULA_LOGIN_HOW)
        blocking = True
    except Exception as e:  # noqa: BLE001
        log.exception("Aula fejlede")
        errors.append(f"Aula kunne ikke læses, så opslag og beskeder blev ikke læst: {_short(e)}")
        blocking = True

    if week_plan is not None:
        save_json(run_dir / "ugeplan.json", week_plan)
    has_plan = week_plan_has_content(week_plan)
    if posts or threads or has_plan:
        try:
            data = prepare_input(posts or [], threads or [], since, run_dir, cfg)
            today = now_local().date()
            managed = {rec["id"]: key for key, rec in state["events"].items()}
            existing = [
                existing_event(e, managed, state)
                for e in graph.list_events(cal_id, today - timedelta(days=7), today + timedelta(days=400))
            ]
            payload = {
                "today": today.isoformat(),
                "weekday_today": WEEKDAYS[today.weekday()],
                "new_since": since.isoformat(),
                "children": cfg["children"],
                "existing_events": existing,
                "week_plan": {k: v for k, v in week_plan.items() if k not in ("raw", "widgets")} if has_plan else None,
                **data,
            }
            result = run_ai(cfg, payload, run_dir)
        except AiLoginRequired:
            log.warning("%s-login er udløbet eller API-nøglen er afvist", ai_name(cfg))
            errors.append(
                f"{ai_name(cfg)} kunne ikke logge ind, så opslag og beskeder blev ikke gennemgået. "
                "Sådan gør du: " + ai_login_how(cfg)
            )
            blocking = True
            result = None
        except Exception as e:  # noqa: BLE001
            log.exception("Gennemgang af opslag og beskeder fejlede")
            errors.append(
                f"Gennemgangen af opslag og beskeder fejlede: {_short(e)}. "
                f"Se logs\\agent.log, og kør evt. i hånden: {RUN} weekly"
            )
            blocking = True
            result = None
        # Vedhæftninger (andre familiers billeder og dokumenter) gemmes ikke efter kørslen.
        shutil.rmtree(run_dir / "attachments", ignore_errors=True)
        if result is not None:
            for item in result.get("calendar", []):
                try:
                    date.fromisoformat(item["date"])
                    if not item.get("key", "").startswith("aula:"):
                        item["key"] = f"aula:{item.get('key', '')}"
                    if aula_unchanged(cfg, state["events"].get(item["key"]), item):
                        log.info("uændret (kun omformuleret): %s", item.get("title"))
                        continue
                    action = upsert(graph, cal_id, state, cfg, item["key"], item, "aula", dry)
                    if action != "uændret":
                        changes.append((action, item))
                except Exception as e:  # noqa: BLE001
                    log.error("Kunne ikke oprette %s: %s", item, e)
                    errors.append(f"Kunne ikke lægge '{item.get('title', '?')}' ({item.get('date', '?')}) i kalenderen: {_short(e)}")
            mail_items = [m for m in result.get("weekly_mail", []) or [] if isinstance(m, dict)]
            if ocr_problem():
                mail_items.append({"category": "billeder", "children": [], "text": ocr_problem()})
            husk = [h for h in result.get("husk", []) or [] if isinstance(h, dict) and h.get("text")]
            fri = [f for f in result.get("fri", []) or [] if isinstance(f, dict) and f.get("date")]
    elif posts is not None:
        log.info("Ingen nye opslag eller beskeder.")

    plan_note = None
    if week_plan is not None:
        wk = monday.isocalendar().week
        if not has_plan:
            plan_note = f"Ingen skema eller ugeplan fundet i Aula for uge {wk}."
        elif not husk and not fri and result is not None:
            plan_note = f"Intet at huske i uge {wk} ud fra skema og ugeplan ({', '.join(week_plan.get('sources', []))})."
        if week_plan.get("notes"):
            plan_note = ((plan_note or "") + " Ugeplan: " + " ".join(week_plan["notes"])).strip()
    if not fri and has_plan:
        fri = fri_from_schema(week_plan)
    html = mail_html(cfg, changes, mail_items, feed_stats, errors, husk, plan_note, fri)
    (run_dir / "ugemail.html").write_text(html, encoding="utf-8")
    if dry:
        log.info("[TØRKØRSEL] Ugemail gemt i %s (ikke sendt)", run_dir / "ugemail.html")
        say(f"Tørkørsel færdig: {len(changes)} aftaler ville blive lagt i kalenderen. Intet er skrevet eller sendt.")
        say(f"Ugemailen kan ses her: {run_dir / 'ugemail.html'}")
    else:
        week = monday.isocalendar().week
        subject = f"Aula-agent uge {week}: {len(changes)} aftaler"
        if husk:
            subject += f", {len(husk)} ting at huske"
        if errors:
            subject += " (fejl, handling krævet)"
        graph.send_mail(cfg["notify_email"], subject, html)
        if blocking:
            log.warning("Opslag og beskeder blev ikke gennemgået; perioden tages med igen ved næste kørsel.")
        else:
            state["last_weekly"] = now_local().isoformat()
        log.info("Ugemail sendt%s.", " med fejl" if errors else "")
        parts = [f"{len(changes)} aftaler lagt i kalenderen"]
        if husk:
            parts.append(f"{len(husk)} ting at huske")
        say(f"Færdig: {', '.join(parts)}. Ugemailen er sendt til {cfg['notify_email']}.")
    if errors:
        say("Der var fejl i kørslen. De står øverst i ugemailen med en vejledning.")
    return 1 if errors else 0


def cmd_ugeplan(cfg: dict) -> int:
    """Viser hvad agenten kan hente af skema, ugeplaner og Huskelisten. Skriver intet."""
    monday, friday = plan_week(now_local().date())
    _, _, plan = asyncio.run(aula_fetch(cfg, now_local(), (monday, friday)))
    run_dir = RUNS_DIR / (now_local().strftime("%Y%m%d_%H%M") + "_ugeplan")
    run_dir.mkdir(parents=True, exist_ok=True)
    save_json(run_dir / "ugeplan.json", plan)
    print(f"Uge {plan.get('week')} ({plan.get('from')} til {plan.get('to')})")
    print("Kilder: " + (", ".join(plan.get("sources", [])) or "ingen"))
    for wd in plan.get("widgets", []):
        print(f"  Widget {wd['id']}: {wd['navn']} ({wd['leverandør']})")
    for name, v in plan.get("children", {}).items():
        print(f"\n{name}:")
        for d, lines in sorted(v["schema"].items()):
            print(f"  {d} (fri {v.get('slut', {}).get(d, '?')}): " + "; ".join(lines))
        print(f"  Ugeplan-tekster: {len(v['ugeplan'])}, Huskelisten: {len(v['huskeliste'])}, opgaver: {len(v['opgaver'])}")
    for n in plan.get("notes", []):
        print("Bemærk: " + n)
    print(f"\nAlt gemt i {run_dir / 'ugeplan.json'}")
    return 0


def cmd_manual(cfg: dict, state: dict, dry: bool) -> int:
    graph = connect_graph(cfg, state)
    if graph is None:
        return 2
    sync_manual(graph, graph.calendar_id(cfg["calendar_name"]), state, cfg, dry)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Aula-agent")
    ap.add_argument("command", choices=["opsaet", "login-aula", "login-outlook", "daily", "weekly", "manual", "ugeplan"])
    ap.add_argument("--dry-run", action="store_true", help="Vis hvad der ville ske, uden at skrive noget")
    ap.add_argument("--days", type=int, default=None, help="Antal dage tilbage (kun weekly)")
    ap.add_argument("--api", action="store_true", help="Brug API-nøgle i stedet for Claude Code eller Codex (kun opsaet)")
    ap.add_argument("--ai", choices=["claude", "chatgpt"], default=None, help="Vælg AI (kun opsaet)")
    args = ap.parse_args()

    setup_logging()
    cfg = load_json(CONFIG_FILE, None)
    if args.command == "opsaet":
        try:
            return cmd_setup(cfg, args.api, args.ai)
        except (KeyboardInterrupt, EOFError):
            print("\nAfbrudt. Intet er gemt.")
            return 1
    if not cfg:
        log.error("Mangler config.json i %s. Kør først: %s opsaet", BASE, RUN)
        return 1
    state = load_json(STATE_FILE, {"events": {}})
    state.setdefault("events", {})

    if protect_config_secrets(cfg):
        save_json(CONFIG_FILE, cfg)
        log.info("API-nøglen i config.json er krypteret")
    cleanup_runs(cfg)
    try:
        if args.command == "login-aula":
            return cmd_login_aula(cfg)
        if args.command == "login-outlook":
            cmd_login_outlook(cfg)
            return 0
        if args.command == "daily":
            return cmd_daily(cfg, state, args.dry_run)
        if args.command == "manual":
            return cmd_manual(cfg, state, args.dry_run)
        if args.command == "ugeplan":
            return cmd_ugeplan(cfg)
        return cmd_weekly(cfg, state, args.dry_run, args.days)
    except Exception as e:  # noqa: BLE001
        log.exception("Kørslen fejlede")
        text = (
            f"Aula-agenten fejlede {now_local():%d-%m-%Y %H:%M} under '{args.command}'.\n\n"
            f"Fejl: {_short(e)}\n\nSe logs\\agent.log i agent-mappen, og kør evt. i hånden: {RUN} weekly"
        )
        sent = False
        if args.command in ("daily", "weekly", "manual") and not args.dry_run:
            last = state.get("last_error_notice")
            recent = last and datetime.fromisoformat(last) > now_local() - timedelta(days=2)
            if args.command == "weekly" or not recent:
                try:
                    Graph(cfg).send_mail(
                        cfg["notify_email"], "Aula-agent: kørslen fejlede",
                        f"<p>{esc(text).replace(chr(10), '<br>')}</p>",
                    )
                    sent = True
                    state["last_error_notice"] = now_local().isoformat()
                except Exception:  # noqa: BLE001
                    log.exception("Kunne ikke sende fejlmail")
        if not sent:
            desktop_notice(text)
        return 1
    finally:
        if args.command not in ("login-outlook", "login-aula"):
            save_json(STATE_FILE, state)


if __name__ == "__main__":
    sys.exit(main())
