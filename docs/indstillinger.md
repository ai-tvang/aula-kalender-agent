# Indstillinger og daglig brug

[Tilbage til forsiden](../README.md)

## Hvad den gør hver uge

Hver uge (som standard søndag kl. 7):

1. Henter nye opslag og beskedtråde fra Aula siden sidste kørsel, inklusive tråden og vedhæftede Word- og PDF-filer. Tekst i vedhæftede billeder (fx en invitation) læses på din egen computer; selve billederne sendes ikke videre (se `send_images` nedenfor).
2. Lader AI'en (Claude eller ChatGPT) læse dem efter reglerne i `regler.md` og finde de bekræftede datoer.
3. Henter dine kalender-links (fx Aula-kalenderen eller sportsklubben) og fletter dem ind.
4. Opretter eller opdaterer aftaler i en separat Outlook-kalender, som standard "Skole og fritid". Den laver ikke dubletter, og flyttede datoer bliver rettet.
5. Henter skemaet, ugeplanerne og Huskelisten for den kommende skoleuge (MinUddannelse, Meebook eller EasyIQ, alt efter hvad skolen bruger) og laver en "Husk i ugen"-liste pr. dag og barn: ture, idræt og svømning, ting der skal med (fx en opladet computer), lektier, og hvornår barnet har fri. Aftaler fra din kalender (møder, skole-hjem-samtaler) står også på dagen med klokkeslæt (lørdag og søndag med), uanset om opslaget om dem var nyt.
6. Sender dig en ugemail med huskelisten øverst. Går noget galt (fx et udløbet login), står fejlen øverst i mailen med en sådan-gør-du-vejledning, og emnet får "(fejl, handling krævet)".

**Med i kalenderen:** skolebegivenheder hvor forældre er inviteret, kontaktforældremøder og -arrangementer, bekræftede fødselsdage og legeaftaler (med svarfrist), pligter med dato (gaveliste, rengøring), ferie og fridage fra Aula-kalenderen.

**Ikke med i kalenderen:** elevture uden forældre, "husk madpakke"-beskeder, forslag og ubekræftede datoer, efterlysninger og generel information. Ture og husk-beskeder for den kommende uge kommer i stedet på huskelisten i ugemailen.

## config.json

Guiden skriver `config.json` for dig. Du kan køre den igen når som helst (fx når børnene skifter klasse efter sommerferien), så foreslår den dine nuværende svar:

```
uv run --python-preference only-system agent.py opsaet
```

Du kan også rette filen selv. Felterne:

| Felt | Forklaring |
|---|---|
| `mitid_username` | Dit MitID-brugernavn, ikke dit Aula-brugernavn. Find det på mitid.dk. |
| `mitid_identity` | Har du flere identiteter i MitID (fx et firma), så nummeret på dig selv i listen. Normalt 1. |
| `calendar_name` | Navnet på Outlook-kalenderen. Den oprettes automatisk. |
| `notify_email` | Hvor ugemailen og beskeder om udløbet login sendes hen. Standard er den Outlook-konto, du logger ind med. |
| `parent.name` | Dit navn præcis som det står i Aula. Bruges til at genkende dine egne beskeder. |
| `parent.role` | `forælder` (standard), `far` eller `mor`. Med `far` eller `mor` sorteres arrangementer kun for det andet køn fra. |
| `parent.contact_parent_in` | Klasser, hvor du er kontaktforælder. Findes automatisk ud fra dine Aula-grupper. |
| `children[].name` / `label` | Barnets navn, og hvordan det står i kalenderen, fx "Emma 2.a". |
| `children[].class` | Klassen, fx "2.a". |
| `children[].previous_class_names` | Klassens navn sidste år, fx "1A", så gamle tråde stadig kobles til barnet. |
| `children[].aula_groups` | Gruppenavne og ord i Aula, der peger på barnet, fx "2A", "2. årgang", "B-sporet". |
| `children[].department` | Afdeling, hvis skolen har flere. |
| `children[].clubs` | Fritidsklub, SFO eller lignende. Tilbud derfra kommer i ugemailen. |
| `family_notes` | Frie noter til AI'en, fx "Emma går til svømning om tirsdagen". |
| `feeds` | Kalender-links, der flettes ind (se nedenfor). Kan være tom. |
| `ai_mode` | Hvilken AI der læser Aula: `claude-code`, `api` (Claude API-nøgle), `codex` (ChatGPT-abonnement) eller `openai-api` (OpenAI API-nøgle). Ældre installationer har feltet `claude_mode`, som stadig virker. |
| `anthropic_api_key` | Din Claude API-nøgle, hvis `ai_mode` er `api`. Krypteres automatisk. |
| `claude_model` | Claude-model, både ved API-nøgle og Claude Code. Standard `claude-opus-5-5`. `claude-sonnet-5-5` koster det halve, men overser flere ting og holder formatet dårligere. |
| `openai_api_key` | Din OpenAI API-nøgle, hvis `ai_mode` er `openai-api`. Krypteres automatisk. |
| `openai_model` | OpenAI-model. Tom = standard: `gpt-6.1-sol` med API-nøgle. Med Codex prøves `gpt-6.1-sol` først; giver abonnementet ikke adgang til den (Go og Free), bruges abonnementets standardmodel. Kan sættes til fx `gpt-6-astra`. |
| `openai_effort` | Hvor grundigt OpenAI-modellen tænker: `low`, `medium`, `high` (standard), `xhigh` eller `max`. |
| `ugeplan` | `false` slår skema, ugeplaner og huskelisten fra. Standard `true`. |
| `keep_runs_days` | Hvor mange dage kopier af Aula-indhold gemmes i `runs` (standard 7). |
| `hide_names` | `true` (standard): navne erstattes med dæknavne som "Barn 3" og "Forælder 5", og din familie får faste dæknavne ("Forælderen", "Eget barn 1 (4.c)"). Mailadresser, telefonnumre og adresser, som nogen har skrevet i en tekst, skjules på samme måde. Det sker, før indholdet sendes til AI'en, og sættes ind igen i kalenderen og ugemailen bagefter. Navnene findes ud fra Aulas lister over de grupper, dine børn er med i, og ud fra afsenderne. `false`: navne sendes, som de står. |
| `send_images` | Hvad der sker med vedhæftede billeder. `text` (standard): teksten i billedet læses på din computer med Windows' indbyggede tekstgenkendelse (OCR), og kun teksten sendes til AI'en. Billedet selv sendes aldrig og slettes straks. Fotos uden tekst giver ingenting. `auto`: selve billedet sendes, men kun når et opslag eller en besked har højst 3 billeder, teksten ikke handler om fotos, og teksten er kort eller nævner en invitation, vedhæftning eller et program. `always`: alle billeder i nye opslag og beskeder sendes. `never`: billeder hverken læses eller sendes. |

## Kalender-links

Kalender-links er en valgfri bonus. Det er læsningen af opslag og beskeder, der gør det meste af arbejdet.

Mange skoler bruger ikke Aula-kalenderen til begivenheder. Forældremøder, skolefester og kontaktforældrenes arrangementer bliver ofte kun meldt ud som opslag eller beskeder. I vores test var den ene elevs Aula-kalender helt tom, og den anden indeholdt kun "Ferie/fri", som typisk kommer fra SFO'ens ferieregistrering. Skole-hjem-samtaler dukker typisk op i kalenderen, når de bliver booket. Det kan stadig være værd at tilføje linket, men forvent ikke, at det alene giver et fuldt billede.

**Aula-kalenderen:** Gå til Kalender i Aula på computeren, klik **Kalendersynkronisering**, vælg dit barn, fjern fluebenet ved **Skema**, og klik **Opret kalenderlink**. Lav ét link pr. barn.

**Andre kalendere:** Alle links, der ender på `.ics` eller starter med `webcal://`, virker, fx fra en sportsklub. Sæt `children` til de børn, kalenderen gælder for.

Behandl linkene som adgangskoder. Alle med linket kan se begivenhederne.

## Manuelle aftaler

Noget kommer aldrig skriftligt i Aula, fx det, I aftaler på et kontaktforældremøde. Det kan du skrive i `manuelle_aftaler.json` i agent-mappen (kopiér `manuelle_aftaler.example.json`):

```json
[
  {
    "title": "Halloween for klassen",
    "date": "2026-10-31",
    "start": "16:00",
    "end": "18:00",
    "location": "Hos en af familierne",
    "children": ["Oscar"],
    "notes": "Fra kontaktforældremødet. Tag en ret med."
  },
  {
    "title": "Juleklip",
    "date": "2026-12-01",
    "children": ["Emma", "Oscar"],
    "notes": "Sidste lektion. Tidspunkt aftales med lærerne."
  }
]
```

- `title` og `date` skal udfyldes. Uden `start` bliver det en heldagsaftale.
- `children` er navnene fra `config.json`. De styrer mærket, fx `[Emma 2.a + Oscar 0.b]`.
- Kør `uv run --python-preference only-system agent.py manual` for at lægge dem i kalenderen med det samme. Det sker også ved hver kørsel.
- Retter du en aftale, bliver den opdateret i kalenderen. Ændrer du titel eller dato, bliver den gamle slettet og en ny oprettet.
- Sletter du en aftale i filen, bliver den slettet i kalenderen, hvis den ligger i fremtiden.

## Tilpas reglerne

Alt det, AI'en skal tage med eller springe over, står i `regler.md` på almindeligt dansk. Ret i filen, så passer næste kørsel til det. Lav gerne en tørkørsel bagefter.

## Daglig brug

Du skal normalt ikke gøre noget. Vil du køre agenten nu, så brug **Aula-agent kør nu** i Start-menuen. Kommandoerne til PowerShell (i agent-mappen) er gode at kende:

```
uv run --python-preference only-system agent.py weekly             # kør nu
uv run --python-preference only-system agent.py weekly --dry-run   # vis uden at skrive
uv run --python-preference only-system agent.py weekly --days 30   # læs 30 dage tilbage
uv run --python-preference only-system agent.py daily              # kun kalender-links + hold Aula-login i live
uv run --python-preference only-system agent.py manual             # læg manuelle aftaler i kalenderen nu
uv run --python-preference only-system agent.py ugeplan            # vis hvad der kan hentes af skema og ugeplan (skriver intet)
uv run --python-preference only-system agent.py login-aula         # nyt MitID-login til Aula
uv run --python-preference only-system agent.py opsaet             # kør guiden igen (fx nyt skoleår)
Get-Content logs\agent.log -Tail 20                                # se hvad der skete
```

### Når et login udløber

Søndagens ugemail siger det øverst. Ved den daglige kørsel får du en mail (eller en fil på skrivebordet, hvis Outlook-login er udløbet):

- **Aula:** søg på Aula-agent i Start-menuen, vælg **Aula-agent log ind på Aula igen**, og godkend i MitID-appen. Agenten kører bagefter af sig selv.
- **Outlook:** **Aula-agent log ind på Outlook igen** i Start-menuen.
- **Claude Code:** kør `claude`, skriv `/login`, og afslut med `/exit`. Kør derefter `agent.py weekly`.
- **Codex (ChatGPT):** kør **Aula-agent opsætning** fra Start-menuen, og sig ja til at logge ind i Codex. Kør derefter **Aula-agent kør nu**.
- **API-nøgle afvist:** lav en ny nøgle på console.anthropic.com eller platform.openai.com, og ret `anthropic_api_key` eller `openai_api_key` i `config.json` (eller kør **Aula-agent opsætning**).

Fejler Aula eller AI'en, tager næste kørsel automatisk den mistede periode med.

Udløber Aula-login ofte, kan du sætte en daglig opgave op, der holder det i live: `.\opsaet.ps1 -Daglig`.
