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

**Dine data bliver hos dig.** Agenten kører på din egen computer. Login, indstillinger og alt, den henter, ligger i agent-mappen, og login er krypteret med Windows. Intet sendes til forfatteren af agenten, og der er ingen statistik eller sporing. Ud over selve installationen taler agenten kun med Aula (og skolens ugeplansystem via Aula), din Outlook-konto og Claude (Anthropic), som læser Aula-indholdet for dig. Se [Privatliv og sikkerhed](#privatliv-og-sikkerhed).

**Open source.** Agenten er gratis og må bruges af alle (MIT-licens). Der arbejdes på andre AI-modeller end Claude, andre kalendere (fx iPhone og Google) og andre mailtjenester. [Feedback](#feedback) er meget velkommen.

> Uofficielt projekt. Det er ikke lavet eller godkendt af Aula, KL, STIL eller Netcompany, og det bruger Aulas interne API, som kan ændre sig uden varsel.

## Hvad den gør

Hver uge (som standard søndag kl. 7):

1. Henter nye opslag og beskedtråde fra Aula siden sidste kørsel, inklusive hele tråden og vedhæftede Word-, PDF- og billedfiler.
2. Lader Claude læse dem efter reglerne i `regler.md` og finde de bekræftede datoer.
3. Henter dine kalender-links (fx Aula-kalenderen eller sportsklubben) og fletter dem ind.
4. Opretter eller opdaterer aftaler i en separat Outlook-kalender, som standard "Skole og fritid". Den laver ikke dubletter, og flyttede datoer bliver rettet.
5. Henter skemaet, ugeplanerne og Huskelisten for den kommende skoleuge (MinUddannelse, Meebook eller EasyIQ, alt efter hvad skolen bruger) og laver en "Husk i ugen"-liste pr. dag og barn: ture, idræt og svømning, ting der skal med (fx en opladet computer), lektier, og hvornår barnet har fri.
6. Sender dig en ugemail med huskelisten øverst. Går noget galt (fx et udløbet login), står fejlen øverst i mailen med en sådan-gør-du-vejledning, og emnet får "(fejl, handling krævet)".

**Med i kalenderen:** skolebegivenheder hvor forældre er inviteret, kontaktforældremøder og -arrangementer, bekræftede fødselsdage og legeaftaler (med svarfrist), pligter med dato (gaveliste, rengøring), ferie og fridage fra Aula-kalenderen.

**Ikke med i kalenderen:** elevture uden forældre, "husk madpakke"-beskeder, forslag og ubekræftede datoer, efterlysninger og generel information. Ture og husk-beskeder for den kommende uge kommer i stedet på huskelisten i ugemailen.

## Det skal du have

- **Windows 10 eller 11.** Det er det eneste, der er testet.
- **En personlig Outlook-konto** (@outlook.com, @hotmail.com, @live.dk). Arbejdskonti blokerer ofte for den slags adgang. Outlook-appen skal ikke være installeret; agenten logger selv ind.
- **Adgang til Claude** på én af to måder:
  - **Claude Code (anbefalet)** med et betalt Claude-abonnement. Kørslerne tæller med i dit almindelige forbrug og koster ikke ekstra. Claude-appen er ikke nok; det er Claude Code, der skal installeres. Det gøres med Anthropics officielle kommando i PowerShell, `irm https://claude.ai/install.ps1 | iex`, eller med `winget install Anthropic.ClaudeCode`. Git er ikke nødvendigt. Åbn et nyt PowerShell-vindue bagefter, kør `claude` én gang og log ind. Installér Claude Code, før du kører opsætningen, så vælger den det automatisk.
  - **API-nøgle** fra [console.anthropic.com](https://console.anthropic.com/settings/keys), hvis du ikke har et Claude-abonnement. Du betaler pr. kørsel, i dag omkring 6-10 kr. om måneden (se [Pris](#pris)). Kræver betalingskort og lidt kredit.

  Du behøver ikke bruge Claude til andet. Bruger du fx ChatGPT til hverdag, er API-nøglen den nemmeste vej.
- **MitID-appen** og adgang til Aula som forælder.
- En computer, der **kører agenten om søndagen**. Er den i dvale, vækkes den (kræver, at vækningstimere er slået til i strømindstillingerne; på mange bærbare kun, når de er sat til strøm). Er den slukket, kører agenten, så snart du tænder den, og mailen kommer få minutter efter.

## Installation

1. Hent projektet: klik **Code > Download ZIP** og pak det ud, fx til `C:\Users\<dig>\Projects`. Omdøb gerne mappen til `aula-kalenderagent`. Læg den **ikke** i OneDrive eller en anden synkroniseret mappe.
2. Åbn mappen i Stifinder, så du kan se filen `opsaet.ps1`. Højreklik på et tomt sted i mappen og vælg **Åbn i Terminal** (Windows 10: hold Shift nede, højreklik og vælg **Åbn PowerShell-vindue her**). Kør:
   ```
   powershell -ExecutionPolicy Bypass -File .\opsaet.ps1
   ```
3. Scriptet installerer det nødvendige og stiller kun det, Aula og Outlook ikke kan svare på:
   1. **MitID-brugernavn**, og godkendelse i MitID-appen (QR-koden vises i vinduet). Agenten henter selv dine børn, deres skole, klasse og Aula-grupper, dit navn og om du er kontaktforælder.
   2. **Claude:** er Claude Code installeret, bruges den. Ellers indsætter du en API-nøgle.
   3. **Outlook-login** med en kode på microsoft.com/link. Ugemailen går til den konto, du logger ind med, og kalenderen "Skole og fritid" oprettes.

   Derefter opretter scriptet en ugentlig kørsel søndag kl. 7 og laver første kørsel med det samme (læser 30 dage tilbage). Kan agenten ikke finde et barns klasse, bliver du spurgt om den.

Navne, klasser, Aula-grupper og noter om familien kan rettes bagefter i `config.json`. Kør `agent.py opsaet` igen for at opdatere fra Aula; det, du har rettet, bliver bevaret.

Vil du have en anden dag eller et andet tidspunkt: `.\opsaet.ps1 -Dag Saturday -Tid "08:00"`.

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
| `family_notes` | Frie noter til Claude, fx "Emma går til svømning om tirsdagen". |
| `feeds` | Kalender-links, der flettes ind (se nedenfor). Kan være tom. |
| `claude_mode` | `api` (API-nøgle) eller `claude-code`. |
| `anthropic_api_key` | Din API-nøgle, hvis `claude_mode` er `api`. |
| `claude_model` | Model, både ved API-nøgle og Claude Code. Standard `claude-opus-5-5`. `claude-sonnet-5-5` koster det halve, men overser flere ting og holder formatet dårligere. |
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

Med API-nøgle betaler du for det, Claude læser. Det afhænger af, hvor meget skolen skriver. Beregnet med Anthropics listepriser for Opus 5.5 ud fra tokenforbruget i rigtige kørsler med to børn (november 2026):

| Kørsel | Indhold | Anslået pris |
|---|---|---|
| Første kørsel, 30 dage tilbage | flere hundrede opslag og beskeder, Word/PDF-filer, billeder | ca. 0,70-1,00 dollar (5-7 kr.) |
| Almindelig uge | nye opslag og beskeder, ugeplan og skema | ca. 0,20-0,30 dollar (1,50-2 kr.) |
| Stille uge | kun ugeplan og skema | ca. 0,10-0,20 dollar |

Det giver omkring 6-10 kr. om måneden. Med `"claude_model": "claude-sonnet-5-5"` i config.json bliver det cirka det halve, men Sonnet overser flere ting. Agenten skriver den faktiske pris for hver kørsel i `logs\agent.log` og i `runs\<tidspunkt>\claude_usage.json`. Du kan sætte en månedlig grænse på console.anthropic.com under Limits, så du aldrig bliver overrasket.

Lange beskedtråde (fx kontaktforældrenes) sendes ikke i deres fulde længde hver uge: Claude får alle nye beskeder og de 30 seneste ældre som sammenhæng.

Billeder bliver skaleret ned, før de sendes, og Claude ser kun dem, reglerne i `regler.md` siger, den skal se.

## Daglig brug

Du skal normalt ikke gøre noget. Kommandoerne er gode at kende:

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

- **Aula:** kør `uv run --python-preference only-system agent.py login-aula`, godkend i MitID-appen, og kør derefter `agent.py weekly`.
- **Outlook:** kør `agent.py login-outlook`.
- **Claude Code:** kør `claude`, skriv `/login`, og afslut med `/exit`. Kør derefter `agent.py weekly`.
- **API-nøgle afvist:** lav en ny nøgle på console.anthropic.com og ret `anthropic_api_key` i `config.json`.

Fejler Aula eller Claude, tager næste kørsel automatisk den mistede periode med.

Udløber Aula-login ofte, kan du sætte en daglig opgave op, der holder det i live: `.\opsaet.ps1 -Daglig`.

## Tilpas reglerne

Alt det, Claude skal tage med eller springe over, står i `regler.md` på almindeligt dansk. Ret i filen, så passer næste kørsel til det. Lav gerne en tørkørsel bagefter.

## Privatliv og sikkerhed

### Hvad agenten gemmer, og hvad det giver adgang til

| Fil i agent-mappen | Giver adgang til | Beskyttelse |
|---|---|---|
| `aula_tokens.dat` | At læse dit Aula (beskeder, opslag, børnenes data). Ikke MitID, bank eller borger.dk | Krypteret med Windows (DPAPI) |
| `graph_token_cache.dat` | At læse og skrive din kalender og sende mail fra din Outlook-konto | Krypteret med Windows (DPAPI) |
| `config.json` | Indstillinger. Med API-nøgle også nøglen, som giver adgang til at bruge Claude på din regning | API-nøglen er krypteret med Windows (DPAPI) |
| `runs\` | Kopier af det, Claude læste (beskeder fra andre forældre, referater) | Slettes efter 7 dage. Vedhæftede filer og billeder slettes lige efter kørslen |

Krypteringen er bundet til din Windows-bruger på netop denne computer. En kopi af filerne virker ikke på en anden computer eller hos en anden bruger. Den beskytter ikke mod nogen, der er logget ind som dig, eller mod skadelig software, der kører som dig. Slå derfor også **BitLocker** (Windows' diskkryptering) til, og brug en adgangskode eller PIN på din Windows-bruger.

Ældre installationer med ukrypterede filer bliver krypteret automatisk ved første kørsel, og de ukrypterede filer slettes.

### Det sendes til Claude

- **Aula-indhold sendes til Claude** (Anthropic) hver uge for at blive læst. Det omfatter beskeder fra andre forældre og navne på andre børn. Vær bevidst om det, før du slår agenten til. Med API-nøgle gælder Anthropics kommercielle vilkår; med Claude Code gælder vilkårene for dit abonnement.
- **Din MitID-adgangskode gemmes ingen steder** og sendes ikke til Claude. Nye logins godkendes altid i MitID-appen.
- Claudes svar kan kun blive til aftaler i din egen kalender og en mail til dig selv. Med Claude Code må Claude kun læse filer i kørslens egen mappe, ikke login-filerne. Står der instruktioner til Claude i en besked fra en anden, kan de derfor ikke få adgang til dine login eller sende noget til andre.

### Sådan trækker du adgangen tilbage

- **Outlook:** account.microsoft.com > Privatliv > Apps og tjenester, fjern "Microsoft Graph Command Line Tools". Slet `graph_token_cache.dat`.
- **Aula:** slet `aula_tokens.dat`. Login udløber også af sig selv efter noget tid.
- **API-nøgle:** slet den på console.anthropic.com under API Keys.
- **Planlagt kørsel:** Opgavestyring > "Aula-kalenderagent ugentlig" > Slet.

`.gitignore` sørger for, at config, login, logs og kørsler aldrig kommer med, hvis du selv lægger projektet på GitHub.

## Kendte begrænsninger

- Aulas API er uofficielt og kan holde op med at virke.
- Outlook-adgangen bruger Microsofts offentlige app til Graph PowerShell, fordi personlige konti ikke kan oprette egne app-registreringer uden Azure. Microsoft kan ændre det. Har du din egen app-registrering, kan du sætte `graph_client_id` i config.
- Claude kan tolke det samme lidt forskelligt fra kørsel til kørsel. Ugemailen og `runs`-mappen viser, hvad der skete.
- Ugeplaner afhænger af, hvilket system skolen bruger, og af at læreren skriver det i ugeplanen. Kør `agent.py ugeplan` for at se, hvad agenten finder hos jer.
- Kun testet på Windows med Outlook. Google Kalender understøttes ikke endnu.

## Feedback

Feedback er meget velkommen, så projektet kan blive så godt som muligt. Det gælder især:

- Andre skoler end den, agenten er bygget på. Aula, ugeplaner og grupper er sat forskelligt op fra skole til skole.
- Hvor installationen gik i stå, eller hvor en tekst var uklar.
- Aftaler eller husk-punkter, der manglede, eller som ikke burde være kommet med.
- Ønsker til andre AI-modeller, kalendere og mailtjenester.

Opret et [issue](../../issues) her på GitHub, eller skriv til mig på [LinkedIn](https://www.linkedin.com/in/thomas-christian-vang-1b625828). Fjern navne og beskeder fra Aula, før du indsætter skærmbilleder eller uddrag.

## Tak til

- [nickknissen/aula](https://github.com/nickknissen/aula) (MIT): Python-biblioteket til Aula og MitID, som agenten bygger på.
- [jesperbagger/aula-huskeliste](https://github.com/jesperbagger/aula-huskeliste): et beslægtet projekt med en daglig huskeliste på mail og Google Kalender.

## Licens

MIT. Se [LICENSE](LICENSE).
