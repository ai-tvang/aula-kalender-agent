# Aula-kalenderagent

Læser Aula for dig hver uge og lægger de datoer, du som forælder skal bruge, ind i din Outlook-kalender. Det gælder forældremøder, kontaktforældrearrangementer, fødselsdage, legeaftaler, svarfrister og skolens begivenheder. Hver aftale bliver mærket med barnets navn og klasse, fx `[Emma 2.a] Forældremøde`.

Hver søndag får du også en ugemail med **Husk i ugen** øverst: én linje pr. barn pr. dag med lektier, ture, idræt og svømning, ting der skal med, og hvornår barnet har fri. Fx:

```
Onsdag 11/11
  [Emma 2.a] Tur til skoven, tøj efter vejret. Fri kl. 13.40.
  Lektie til torsdag: Læsebog kap. 20-22 + opgaver.
  [Oscar 0.b] Idrætstøj og håndklæde. Fri kl. 12.00 (Matematikkens dag).
```

Under huskelisten står de nye aftaler og ting, du bør kigge på selv: tilbud fra klubben, usikre datoer og dage, hvor flere børn har noget samtidig.

**Dine data bliver hos dig.** Agenten kører på din egen computer. Login, indstillinger og alt, den henter, ligger i agent-mappen, og login er krypteret med Windows. Intet sendes til forfatteren af agenten, og der er ingen statistik eller sporing. Ud over selve installationen taler agenten kun med Aula (og skolens ugeplansystem via Aula), din Outlook-konto og den AI, du vælger: Claude (Anthropic) eller ChatGPT (OpenAI), som læser Aula-indholdet for dig. Se [Privatliv og sikkerhed](#privatliv-og-sikkerhed).

**Open source.** Agenten er gratis og må bruges af alle (MIT-licens). Den virker med både Claude og ChatGPT. Der arbejdes på andre kalendere (fx iPhone og Google) og andre mailtjenester. [Feedback](#feedback) er meget velkommen.

**Du skal bruge:** en Windows-computer, en personlig Outlook-konto (fx @outlook.com eller @hotmail.com), MitID-appen og enten et Claude- eller ChatGPT-abonnement eller en API-nøgle. Se [Det skal du have](#det-skal-du-have).

> Uofficielt projekt. Det er ikke lavet eller godkendt af Aula, KL, STIL eller Netcompany, og det bruger Aulas interne API, som kan ændre sig uden varsel.

## Hvad den gør

Hver uge (som standard søndag kl. 7):

1. Henter nye opslag og beskedtråde fra Aula siden sidste kørsel, inklusive hele tråden og vedhæftede Word-, PDF- og billedfiler.
2. Lader AI'en (Claude eller ChatGPT) læse dem efter reglerne i `regler.md` og finde de bekræftede datoer.
3. Henter dine kalender-links (fx Aula-kalenderen eller sportsklubben) og fletter dem ind.
4. Opretter eller opdaterer aftaler i en separat Outlook-kalender, som standard "Skole og fritid". Den laver ikke dubletter, og flyttede datoer bliver rettet.
5. Henter skemaet, ugeplanerne og Huskelisten for den kommende skoleuge (MinUddannelse, Meebook eller EasyIQ, alt efter hvad skolen bruger) og laver en "Husk i ugen"-liste pr. dag og barn: ture, idræt og svømning, ting der skal med (fx en opladet computer), lektier, og hvornår barnet har fri.
6. Sender dig en ugemail med huskelisten øverst. Går noget galt (fx et udløbet login), står fejlen øverst i mailen med en sådan-gør-du-vejledning, og emnet får "(fejl, handling krævet)".

**Med i kalenderen:** skolebegivenheder hvor forældre er inviteret, kontaktforældremøder og -arrangementer, bekræftede fødselsdage og legeaftaler (med svarfrist), pligter med dato (gaveliste, rengøring), ferie og fridage fra Aula-kalenderen.

**Ikke med i kalenderen:** elevture uden forældre, "husk madpakke"-beskeder, forslag og ubekræftede datoer, efterlysninger og generel information. Ture og husk-beskeder for den kommende uge kommer i stedet på huskelisten i ugemailen.

## Det skal du have

- **Windows 10 eller 11.** Det er det eneste, der er testet.
- **En personlig Outlook-konto** (@outlook.com, @hotmail.com, @live.dk). Arbejdskonti blokerer ofte for den slags adgang. Outlook-appen skal ikke være installeret; agenten logger selv ind.
- **Adgang til Claude eller ChatGPT** på én af fire måder. Installationen spørger, hvilket abonnement du har:
  - **Claude Code (anbefalet)** med et betalt Claude-abonnement (Pro eller Max). Kørslerne tæller med i dit almindelige forbrug og koster ikke ekstra. Claude-appen er ikke nok, men installationen installerer Claude Code for dig, og du logger ind én gang undervejs.
  - **Codex** med et ChatGPT-abonnement (Plus, Pro, Go eller Free). Codex følger med abonnementet, og kørslerne bruger af den Codex-kvote, abonnementet giver. Du betaler ikke ekstra, men der er forbrugsgrænser, som afhænger af abonnementet. ChatGPT-appen er ikke nok, men installationen installerer Codex (OpenAIs program til kommandolinjen) for dig, og du logger ind med din ChatGPT-konto én gang. Se [Kvalitet med ChatGPT](#kvalitet-med-chatgpt).
  - **Claude API-nøgle** fra [console.anthropic.com](https://console.anthropic.com/settings/keys). Du betaler pr. kørsel, i dag omkring 6-10 kr. om måneden med Opus (se [Pris](#pris)). Kræver betalingskort og lidt kredit.
  - **OpenAI API-nøgle** fra [platform.openai.com](https://platform.openai.com/api-keys). Du betaler pr. kørsel. Et ChatGPT-abonnement giver ikke API-adgang; den betales for sig. Kræver betalingskort og lidt kredit.
- **Dit login til Claude eller ChatGPT** (e-mail og adgangskode eller Google/Apple-login). Installationen åbner browseren og beder dig logge ind. Er du allerede logget ind på claude.ai eller chatgpt.com i browseren, går det hurtigere.
- **MitID-appen** og adgang til Aula som forælder.
- En computer, der **kører agenten om søndagen**. Er den i dvale, vækkes den (kræver, at vækningstimere er slået til i strømindstillingerne; på mange bærbare kun, når de er sat til strøm). Er den slukket, kører agenten, så snart du tænder den, og mailen kommer få minutter efter.

## Installation

1. Åbn **PowerShell**: klik på Start, skriv `PowerShell` og tryk Enter.
2. Kopiér linjen herunder (brug kopi-ikonet til højre), indsæt den i PowerShell med højreklik, og tryk Enter:
   ```
   irm https://raw.githubusercontent.com/ai-tvang/aula-kalender-agent/main/install.ps1 | iex
   ```
3. Følg vinduet. Det tager 10-15 minutter, og det meste er login. Hav din telefon med MitID-appen klar, og log gerne ind på claude.ai eller chatgpt.com i browseren først:
   1. **Python og uv** installeres automatisk.
   2. **AI:** Du vælger Claude, ChatGPT eller API-nøgle. Med Claude installeres **Claude Code**; du logger ind i browseren og skriver `/exit`, når den er klar. Med ChatGPT installeres **Codex**; du logger ind med din ChatGPT-konto i browseren og godkender, at Codex opretter en sikker sandkasse (Windows spørger om administrator-godkendelse). Har du allerede Claude Code eller Codex, bruges det, men du bliver stadig spurgt, så du selv vælger.
   3. **MitID-brugernavn**, og godkendelse i MitID-appen. Agenten henter selv dine børn, deres skole, klasse og Aula-grupper, dit navn og om du er kontaktforælder.
   4. **Outlook-login** med en kode på microsoft.com/link. Ugemailen går til den konto, du logger ind med, og kalenderen "Skole og fritid" oprettes.

   Derefter opretter scriptet en ugentlig kørsel søndag kl. 7 og laver første kørsel med det samme (læser 30 dage tilbage). Kan agenten ikke finde et barns klasse, bliver du spurgt om den.

Agenten ligger bagefter i `C:\Users\<dig>\Aula-kalenderagent`, og i **Start-menuen > Aula-kalenderagent** finder du genvejene **Kør nu**, **Log ind på Aula igen**, **Log ind på Outlook igen**, **Opsætning** og **Åbn agent-mappen**. Du skal ikke bruge PowerShell igen.

**Opdatering:** kør samme linje igen. Den finder selv din installation, også hvis du har installeret fra ZIP et andet sted, og dine indstillinger og login bevares.

**Skift mellem Claude og ChatGPT:** kør **Opsætning** fra Start-menuen, og vælg den anden. Mangler programmet, tilbyder opsætningen at installere det.

Navne, klasser, Aula-grupper og noter om familien kan rettes bagefter i `config.json`. Kør **Opsætning** fra Start-menuen for at opdatere fra Aula; det, du har rettet, bliver bevaret.

Vil du have en anden dag eller et andet tidspunkt, så åbn PowerShell i agent-mappen og kør `.\opsaet.ps1 -Dag Saturday -Tid "08:00"`.

Har du flyttet agent-mappen, så åbn PowerShell i den nye mappe og kør `powershell -ExecutionPolicy Bypass -File .\opsaet.ps1 -KunGenveje`. Det flytter den planlagte kørsel og genvejene uden at køre guiden igen.

<details>
<summary>Installation uden én-linje-kommandoen</summary>

1. Klik **Code > Download ZIP** og pak det ud, fx til `C:\Users\<dig>\Aula-kalenderagent`. Læg den **ikke** i OneDrive eller en anden synkroniseret mappe.
2. Åbn mappen i Stifinder, højreklik på et tomt sted og vælg **Åbn i Terminal** (Windows 10: hold Shift nede, højreklik og vælg **Åbn PowerShell-vindue her**). Kør:
   ```
   powershell -ExecutionPolicy Bypass -File .\opsaet.ps1
   ```
</details>

### Er det sikkert at køre linjen?

Linjen henter [install.ps1](install.ps1) fra dette repo og kører den. Du kan åbne filen og læse den først; den er kort. Den gør tre ting:

1. Henter agenten som ZIP-fil fra GitHub og lægger den i `C:\Users\<dig>\Aula-kalenderagent`.
2. Starter [opsaet.ps1](opsaet.ps1), som installerer Python (via winget fra python.org), uv (fra astral.sh) og, alt efter dit valg, Claude Code (fra claude.ai) eller Codex (fra chatgpt.com).
3. Opsætningen opretter en planlagt opgave og genveje i Start-menuen.

Intet sendes til forfatteren af agenten. Hvad agenten gemmer og sender til AI'en, står under [Privatliv og sikkerhed](#privatliv-og-sikkerhed), og hvordan du fjerner det igen, under [Sådan trækker du adgangen tilbage](#sådan-trækker-du-adgangen-tilbage).

### Hjælp fra Claude eller ChatGPT

Du kan indsætte linket til denne side i Claude eller ChatGPT og skrive fx "Hjælp mig med at installere den her trin for trin". Går noget galt, så kopiér teksten fra PowerShell-vinduet ind i chatten. Fjern navne på børn og andre forældre først.

### Hvis noget går galt

| Det ser du | Gør sådan |
|---|---|
| Rød tekst om `iexirm` eller en lang, forkert kommando | Linjen blev indsat to gange. Tryk Esc, og indsæt den én gang. |
| Fejl om, at scripts er deaktiveret ("running scripts is disabled") | Brug linjen fra trin 2. Ved den manuelle vej: kør `powershell -ExecutionPolicy Bypass -File .\opsaet.ps1`. |
| "STOP: Din brugermappe ligger i OneDrive" | Brug den manuelle vej, og læg mappen uden for OneDrive, fx `C:\Aula-kalenderagent`. |
| "Python 3.14 kunne ikke installeres" | Installer Python 3.14 fra [python.org](https://www.python.org/downloads/windows/), og kør linjen igen. |
| `claude` findes ikke, eller Claude Code beder om login under kørslen | Åbn et nyt PowerShell-vindue, kør `claude`, log ind og skriv `/exit`. Kør derefter **Opsætning** fra Start-menuen (eller linjen igen). |
| Du har ikke et Claude-abonnement | Vælg ChatGPT, hvis du har et ChatGPT-abonnement, ellers en API-nøgle (se [Det skal du have](#det-skal-du-have)). |
| Ugemailen siger, at ChatGPT ikke kunne logge ind | Kør **Opsætning** fra Start-menuen, og sig ja til at logge ind i Codex. Kør derefter **Kør nu**. (Avanceret: `codex login` i PowerShell.) |
| "Codex kunne ikke starte sin sikre sandkasse" | Kør **Opsætning** fra Start-menuen, og sig ja til at sætte sandkassen op. Windows beder om administrator-godkendelse. Agenten kører ikke Codex uden sandkassen. (Avanceret: `codex sandbox setup --elevated --current-user`.) |
| "Codex CLI er for gammel" | Kør **Opsætning** fra Start-menuen, og sig ja til at opdatere Codex. (Avanceret: `npm install -g @openai/codex@latest`.) |
| MitID spørger, om du vil logge ind som privatperson eller et firma | Vælg dig selv som privatperson. |
| "Codes read. Approve the login in your MitID app." | Teksten er på engelsk, men betyder bare: godkend i MitID-appen. |
| Outlook-login: kode og microsoft.com/link | Åbn microsoft.com/link i browseren, skriv koden, log ind med din personlige Outlook-konto og godkend. Vinduet fortsætter selv. |
| Outlook-login afvises, eller du bliver bedt om en administrator | Det er sandsynligvis en arbejds- eller skolekonto. Brug en personlig konto, fx en ny gratis @outlook.com. |
| Opsætningen stoppede halvvejs | Kør linjen eller **Opsætning** igen. Det, der allerede er gemt (fx MitID og Outlook), genbruges. |
| Ingen ugemail søndag | Computeren var slukket eller i dvale. Agenten kører, når den tændes. Ellers se `logs\agent.log` via **Åbn agent-mappen**. |

Står din fejl ikke her, så opret et [issue](../../issues) med teksten fra vinduet (uden navne).

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

## Pris

Med Claude Code koster agenten intet ekstra; kørslerne tæller i dit abonnement (én kørsel om ugen).

Med Claude API-nøgle betaler du for det, Claude læser. Det afhænger af, hvor meget skolen skriver. Beregnet med Anthropics listepriser for Opus 5.5 ud fra tokenforbruget i rigtige kørsler med to børn (november 2026):

| Kørsel | Indhold | Anslået pris |
|---|---|---|
| Første kørsel, 30 dage tilbage | flere hundrede opslag og beskeder, Word/PDF-filer, billeder | ca. 0,70-1,00 dollar (5-7 kr.) |
| Almindelig uge | nye opslag og beskeder, ugeplan og skema | ca. 0,20-0,30 dollar (1,50-2 kr.) |
| Stille uge | kun ugeplan og skema | ca. 0,10-0,20 dollar |

Det giver omkring 6-10 kr. om måneden. Med `"claude_model": "claude-sonnet-5-5"` i config.json bliver det cirka det halve, men Sonnet overser flere ting. Agenten skriver den faktiske pris for hver kørsel i `logs\agent.log` og i `runs\<tidspunkt>\ai_usage.json`. Du kan sætte en månedlig grænse på console.anthropic.com under Limits, så du aldrig bliver overrasket.

Med Codex (ChatGPT-abonnement) betaler du ikke ekstra; kørslen bruger af den Codex-kvote, der følger med abonnementet. Én kørsel om ugen bør ligge langt under grænserne, men de afhænger af abonnementet og OpenAIs vilkår og kan ændre sig.

Med OpenAI API-nøgle afhænger prisen af modellen. Ud fra OpenAIs listepriser (november 2026) og tokenforbruget i vores test, hvor en almindelig uge brugte 40.000-70.000 tokens:

| Model | Almindelig uge (anslået) |
|---|---|
| `gpt-6.1-sol` (standard) | ca. 0,10-0,20 dollar (1-1,50 kr.) |
| `gpt-6-astra` | ca. 0,50-0,90 dollar (3,50-6 kr.) |

Tallene er anslåede, beregnet ud fra listepriser, og ikke målt på rigtige kørsler med API-nøgle. Priser og modelnavne ændrer sig. Agenten skriver en anslået pris for hver kørsel i loggen. Sæt gerne en månedlig grænse på platform.openai.com under Limits.

Lange beskedtråde (fx kontaktforældrenes) sendes ikke i deres fulde længde hver uge: AI'en får alle nye beskeder og de 30 seneste ældre som sammenhæng.

Billeder bliver skaleret ned, før de sendes. Med API-nøgle ser AI'en kun dem, reglerne i `regler.md` siger, den skal se. Med Codex sendes billederne fra ugens opslag med fra start (højst 12).

### Kvalitet med ChatGPT

Agenten er udviklet og testet med Claude Opus. ChatGPT-understøttelsen er ny, og kvaliteten kan svinge:

- **Med ChatGPT Go eller Free** bruger Codex en mindre model (GPT-6 Luna). Vi har sammenlignet den med Claude Opus på tre rigtige kørsler: Fri-tiderne var de samme, og huskelisten var næsten den samme. Men Luna overså flere ting i ugemailen, fx et kontaktforældremøde og dage, hvor begge børn havde noget samtidig, og satte et par punkter på det forkerte barn.
- **Med ChatGPT Plus eller højere** bruger agenten GPT-6.1 Sol, og med API-nøgle også GPT-6.1 Sol som standard. Sol og den større GPT-6 Astra er ikke testet på rigtige kørsler endnu. I uafhængige test ligger de tæt på Claude Opus, så kvaliteten vil sandsynligvis være bedre end med Go og Free.

Kig ugemailen og kalenderen igennem de første uger, og skriv gerne i [Feedback](#feedback), hvad der manglede.

## Daglig brug

Du skal normalt ikke gøre noget. Vil du køre agenten nu, så brug **Kør nu** i Start-menuen. Kommandoerne til PowerShell (i agent-mappen) er gode at kende:

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

- **Aula:** Start-menuen > Aula-kalenderagent > **Log ind på Aula igen**, og godkend i MitID-appen. Agenten kører bagefter af sig selv.
- **Outlook:** Start-menuen > Aula-kalenderagent > **Log ind på Outlook igen**.
- **Claude Code:** kør `claude`, skriv `/login`, og afslut med `/exit`. Kør derefter `agent.py weekly`.
- **Codex (ChatGPT):** kør **Opsætning** fra Start-menuen, og sig ja til at logge ind i Codex. Kør derefter **Kør nu**.
- **API-nøgle afvist:** lav en ny nøgle på console.anthropic.com eller platform.openai.com, og ret `anthropic_api_key` eller `openai_api_key` i `config.json` (eller kør **Opsætning**).

Fejler Aula eller AI'en, tager næste kørsel automatisk den mistede periode med.

Udløber Aula-login ofte, kan du sætte en daglig opgave op, der holder det i live: `.\opsaet.ps1 -Daglig`.

## Tilpas reglerne

Alt det, AI'en skal tage med eller springe over, står i `regler.md` på almindeligt dansk. Ret i filen, så passer næste kørsel til det. Lav gerne en tørkørsel bagefter.

## Privatliv og sikkerhed

### Hvad agenten gemmer, og hvad det giver adgang til

| Fil i agent-mappen | Giver adgang til | Beskyttelse |
|---|---|---|
| `aula_tokens.dat` | At læse dit Aula (beskeder, opslag, børnenes data). Ikke MitID, bank eller borger.dk | Krypteret med Windows (DPAPI) |
| `graph_token_cache.dat` | At læse og skrive din kalender og sende mail fra din Outlook-konto | Krypteret med Windows (DPAPI) |
| `config.json` | Indstillinger. Med API-nøgle også nøglen, som giver adgang til at bruge Claude eller OpenAI på din regning | API-nøglen er krypteret med Windows (DPAPI) |
| `runs\` | Kopier af det, AI'en læste (beskeder fra andre forældre, referater) | Slettes efter 7 dage. Vedhæftede filer og billeder slettes lige efter kørslen |

Krypteringen er bundet til din Windows-bruger på netop denne computer. En kopi af filerne virker ikke på en anden computer eller hos en anden bruger. Den beskytter ikke mod nogen, der er logget ind som dig, eller mod skadelig software, der kører som dig. Slå derfor også **BitLocker** (Windows' diskkryptering) til, og brug en adgangskode eller PIN på din Windows-bruger.

Ældre installationer med ukrypterede filer bliver krypteret automatisk ved første kørsel, og de ukrypterede filer slettes.

### Det sendes til AI'en

- **Aula-indhold sendes til den AI, du har valgt** (Claude fra Anthropic eller ChatGPT fra OpenAI), hver uge for at blive læst. Det omfatter beskeder fra andre forældre og navne på andre børn. Vær bevidst om det, før du slår agenten til.
- **Claude:** Med API-nøgle bruges indholdet ikke til træning og slettes inden for 30 dage. Med Claude Code (abonnement) opbevares det i 30 dage. Har du tilladt træning i Claudes privatlivsindstillinger (claude.ai/settings/data-privacy-controls), bruges det til træning og opbevares op til 5 år.
- **ChatGPT og OpenAI:** Med OpenAI API-nøgle bruges indholdet ikke til træning, og det opbevares op til 30 dage i OpenAIs logs til misbrugsovervågning. Agenten beder om, at svarene ikke gemmes som lagrede svar i API'et, men det ændrer ikke de 30 dage. Med et ChatGPT-abonnement (Codex) kan OpenAI bruge indholdet til træning, medmindre du slår det fra: chatgpt.com > **Indstillinger > Datastyring > Gør modellen bedre for alle** = fra. Indstillingen gælder hele din ChatGPT-konto. OpenAIs hjælpeside nævner ikke Codex specifikt, så vi går ud fra, at den også gælder Codex. Med ChatGPT-login følger opbevaringen din ChatGPT-kontos vilkår; OpenAI angiver ikke en særskilt periode for Codex. At slå træning fra betyder ikke, at OpenAI ikke opbevarer noget.
- **For alle udbydere:** Ved mistanke om misbrug eller krav i loven kan data opbevares længere.
- **Din MitID-adgangskode gemmes ingen steder** og sendes ikke til AI'en. Nye logins godkendes altid i MitID-appen.
- AI'ens svar kan kun blive til aftaler i din egen kalender og en mail til dig selv. Står der instruktioner til AI'en i en besked fra en anden, kan de ikke få adgang til dine login eller sende noget til andre:
  - Med Claude Code må Claude kun læse filer i kørslens egen mappe.
  - Med Codex sender Codex-programmet Aula-indholdet til OpenAI og får svaret tilbage; det er den eneste netværkstrafik. Selve modellen kører i en midlertidig mappe uden for agent-mappen, i Codex' sikre Windows-sandkasse. Kommandoer, den forsøger at køre på computeren, kan ikke skrive filer, har intet netværk og kan ikke læse noget i din brugermappe (fx Dokumenter, Skrivebord, browserprofiler og login-filer) ud over den midlertidige mappe. Agenten slår Codex' shell, websøgning og andre værktøjer fra og bruger ikke din egen Codex-opsætning, MCP-servere eller regler. Kan sandkassen ikke starte, kører agenten ikke Codex, og den skifter aldrig til en svagere sandkasse.
  - Med API-nøgle kan AI'en kun se de billeder, agenten selv sender.

### Sådan trækker du adgangen tilbage

- **Outlook:** account.microsoft.com > Privatliv > Apps og tjenester, fjern "Microsoft Graph Command Line Tools". Slet `graph_token_cache.dat`.
- **Aula:** slet `aula_tokens.dat`. Login udløber også af sig selv efter noget tid.
- **API-nøgle:** slet den på console.anthropic.com under API Keys eller på platform.openai.com under API keys.
- **Codex (ChatGPT):** kør `codex logout`.
- **Planlagt kørsel:** Opgavestyring > "Aula-kalenderagent ugentlig" > Slet.

`.gitignore` sørger for, at config, login, logs og kørsler aldrig kommer med, hvis du selv lægger projektet på GitHub.

## Kendte begrænsninger

- Aulas API er uofficielt og kan holde op med at virke.
- Outlook-adgangen bruger Microsofts offentlige app til Graph PowerShell, fordi personlige konti ikke kan oprette egne app-registreringer uden Azure. Microsoft kan ændre det. Har du din egen app-registrering, kan du sætte `graph_client_id` i config.
- AI'en kan tolke det samme lidt forskelligt fra kørsel til kørsel. Ugemailen og `runs`-mappen viser, hvad der skete.
- Ugeplaner afhænger af, hvilket system skolen bruger, og af at læreren skriver det i ugeplanen. Kør `agent.py ugeplan` for at se, hvad agenten finder hos jer.
- Kun testet på Windows med Outlook. Google Kalender understøttes ikke endnu.

## Feedback

Feedback er meget velkommen, så projektet kan blive så godt som muligt. Det gælder især:

- Andre skoler end den, agenten er bygget på. Aula, ugeplaner og grupper er sat forskelligt op fra skole til skole.
- Hvor installationen gik i stå, eller hvor en tekst var uklar.
- Aftaler eller husk-punkter, der manglede, eller som ikke burde være kommet med.
- Erfaringer med ChatGPT, og ønsker til andre kalendere og mailtjenester.

Opret et [issue](../../issues) her på GitHub, eller skriv til mig på [LinkedIn](https://www.linkedin.com/in/thomas-christian-vang-1b625828). Fjern navne og beskeder fra Aula, før du indsætter skærmbilleder eller uddrag.

## Tak til

- [nickknissen/aula](https://github.com/nickknissen/aula) (MIT): Python-biblioteket til Aula og MitID, som agenten bygger på.
- [jesperbagger/aula-huskeliste](https://github.com/jesperbagger/aula-huskeliste): et beslægtet projekt med en daglig huskeliste på mail og Google Kalender.

## Licens

MIT. Se [LICENSE](LICENSE).
