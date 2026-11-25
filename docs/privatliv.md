# Privatliv og sikkerhed

[Tilbage til forsiden](../README.md)

## Hvad agenten gemmer, og hvad det giver adgang til

| Fil i agent-mappen | Giver adgang til | Beskyttelse |
|---|---|---|
| `aula_tokens.dat` | At læse dit Aula (beskeder, opslag, børnenes data). Ikke MitID, bank eller borger.dk | Krypteret med Windows (DPAPI) |
| `graph_token_cache.dat` | At læse og skrive din kalender og sende mail fra din Outlook-konto | Krypteret med Windows (DPAPI) |
| `config.json` | Indstillinger. Med API-nøgle også nøglen, som giver adgang til at bruge Claude eller OpenAI på din regning | API-nøglen er krypteret med Windows (DPAPI) |
| `runs\` | Kopier af det, AI'en læste (beskeder fra andre forældre, referater) og nøglen til dæknavnene (`navne.json`) | Slettes efter 7 dage. Vedhæftede filer og billeder slettes lige efter kørslen |

Krypteringen er bundet til din Windows-bruger på netop denne computer. En kopi af filerne virker ikke på en anden computer eller hos en anden bruger. Den beskytter ikke mod nogen, der er logget ind som dig, eller mod skadelig software, der kører som dig. Slå derfor også **BitLocker** (Windows' diskkryptering) til, og brug en adgangskode eller PIN på din Windows-bruger.

Ældre installationer med ukrypterede filer bliver krypteret automatisk ved første kørsel, og de ukrypterede filer slettes.

## Det sendes til AI'en

**Kort fortalt:** AI'en får teksten fra opslag, beskeder, vedhæftede filer og skolens ugeplan, så den kan finde datoer og ting, der skal huskes. Navne er skiftet ud med dæknavne, før teksten sendes, og det samme er mailadresser, telefonnumre og adresser, som nogen har skrevet i teksten. Agenten henter ikke kontaktoplysninger fra Aula. Størstedelen af det, der sendes, er altså ikke oplysninger om, hvem folk er, men om hvad der skal ske og hvornår. I en test med 30 dages Aula-indhold fra to klasser (ca. 10.000 ord) var 353 steder navne eller skrevne mailadresser, telefonnumre og adresser. Alle var skiftet ud, og ingen navne fra Aulas lister stod tilbage i klartekst.

Agenten filtrerer ikke på dine børn, før indholdet sendes. Den sender alle opslag og tråde, du kan se i Aula, som er nye siden sidste kørsel (minus 2 dage for en sikkerheds skyld), plus opslag og tråde fra ca. 10 dage før den kommende skoleuge som sammenhæng. Første kørsel tager de sidste 30 dage. Det er AI'en, der sorterer, hvad der gælder dine børn.

| Sendes | Sendes ikke |
|---|---|
| `regler.md` og et afsnit om familien fra `config.json`: klasse, skole, Aula-grupper, klubber og dine noter. Dit navn og børnenes navne er erstattet af "Forælderen" og "Eget barn 1 (4.c)" osv. | MitID-brugernavn og -adgangskode, Aula- og Outlook-login, API-nøgler |
| Opslag: titel, dato, tekst, forfatterens rolle, grupper. Forfatterens navn er erstattet af et dæknavn | Deltagerlisten i tråde (navne på alle forældre og børn i tråden). Højst antallet sendes |
| Tråde: emne, og hvilke af dine egne børn tråden vedrører (som "Eget barn 1 (4.c)" osv.) | Aulas gruppelister og kontaktlister. Agenten bruger kun navnene fra gruppelisterne, på din computer, til at finde navne i teksten |
| Beskeder: afsenderen som dæknavn (fx "Forælder 5"), Aulas beskrivelse af afsenderen, dato og tekst. Nye beskeder og op til 30 ældre pr. tråd | Billeder i Aulas galleri, profilbilleder og Aula-dokumenter (Sikker fildeling) |
| Teksten fra vedhæftede PDF- og Word-filer i nye opslag og beskeder (op til 20.000 tegn pr. fil) | Vedhæftninger i ældre beskeder (kun filnavnet) |
| Teksten i vedhæftede billeder i nye opslag og beskeder, læst på din egen computer (op til 3.000 tegn pr. billede, højst 10 billeder pr. opslag eller besked) | Selve billederne, så længe `send_images` er `text` (standard) eller `never`. Fotos uden tekst giver ingenting; AI'en får kun at vide, at der var et billede |
| Skema, ugeplan og Huskelisten for den kommende skoleuge | |
| Aftaler, der allerede står i din kalender "Skole og fritid", så der ikke kommer dubletter | Dine andre Outlook-kalendere og din mail |

**Sådan skjules det.** Alt i tabellen går gennem det samme filter på din computer, før det sendes:

- **Andre børn, forældre og ansatte:** Agenten henter navnene fra Aulas lister over de grupper, dine børn er med i (klasse, årgang, SFO og forældregrupper), og tager afsenderne med. Står fornavnet eller efternavnet på listerne, bliver navnet til fx "Barn 3", "Forælder 5" eller "Medarbejder 2". Det gælder også hele navne, der ikke står samlet på listerne (fx en søskende), og efternavne alene ("Dansk med Hansen"). Samme person får altid samme dæknavn.
- **Din egen familie:** Du er "Forælderen", og børnene er "Eget barn 1 (4.c)", "Eget barn 2 (1.b)" osv., også i titlerne på aftaler i kalenderen. Står et af børnenes fornavne alene, bliver det kun til "Eget barn", når teksten handler om barnet (tråden vedrører barnet, opslaget er til klassen, eller det står i barnets ugeplan), og ingen anden i klassen har samme fornavn. Ellers får det samme dæknavn som de andre med det fornavn. Dit fornavn alene bliver "Forælderen" i dine beskedtråde, medmindre en anden deltager har samme fornavn.
- **Skrevne mailadresser, telefonnumre og adresser:** Står der fx et telefonnummer i en besked, en adresse i en invitation eller en mail i en signatur, bliver det til "Telefon 1", "Adresse 1" eller "Mail 1". Agenten henter ikke kontaktoplysninger fra Aulas profiler eller kontaktlister, så det er kun det, der står i selve teksterne.
- **Bagefter** sætter agenten de rigtige navne, numre og adresser ind igen i kalenderen og ugemailen, så du har dem, når du skal bruge dem. Listen over, hvem der er hvem (`navne.json`), bliver på din computer og slettes sammen med kørslens mappe efter 7 dage. Henter agenten ingen navne fra grupperne (fx hvis Aula ændrer formen på listerne), står det øverst i ugemailen.

**Det fanger ikke alt.** Agenten kan kun skjule det, den kan genkende. Det her kan slippe igennem:

- Navne, der ikke står på Aulas lister: bedsteforældre, trænere, foredragsholdere, kælenavne og stavefejl.
- Personer, der står med et andet navn i Aula end det, der bruges i teksten. Har fx et barn og en forælder navne- og adressebeskyttelse, står de i Aula under et andet navn. Skriver de selv eller andre deres rigtige navn eller adresse i en besked, kan det komme med til AI'en.
- Mellemnavne, der ikke står på listerne, og efternavne, der også er almindelige ord, først i en sætning (fx "Skov").
- Lærerinitialer, fx i skemaet.
- Navne i billeder med utydelig tekst.
- Udenlandske telefonnumre, numre skrevet på andre måder (fx 12-34-56-78) og adresser uden postnummer og uden en typisk endelse som -vej eller -gade.

Selvom navnene er skiftet ud, kan indholdet stadig knyttes til personer via skole, klasse og hvad der står. Juridisk er det derfor stadig personoplysninger.

- **Claude:** Med API-nøgle bruges indholdet ikke til træning og slettes inden for 30 dage. Med Claude Code (abonnement) opbevares det i 30 dage. Har du tilladt træning i Claudes privatlivsindstillinger (claude.ai/settings/data-privacy-controls), bruges det til træning og opbevares op til 5 år.
- **ChatGPT og OpenAI:** Med OpenAI API-nøgle bruges indholdet ikke til træning, og det opbevares op til 30 dage i OpenAIs logs til misbrugsovervågning. Agenten beder om, at svarene ikke gemmes som lagrede svar i API'et, men det ændrer ikke de 30 dage. Med et ChatGPT-abonnement (Codex) kan OpenAI bruge indholdet til træning, medmindre du slår det fra: chatgpt.com > **Indstillinger > Datastyring > Gør modellen bedre for alle** = fra. Indstillingen gælder hele din ChatGPT-konto. OpenAIs hjælpeside nævner ikke Codex specifikt, så vi går ud fra, at den også gælder Codex. Med ChatGPT-login følger opbevaringen din ChatGPT-kontos vilkår; OpenAI angiver ikke en særskilt periode for Codex. At slå træning fra betyder ikke, at OpenAI ikke opbevarer noget.
- **For alle udbydere:** Ved mistanke om misbrug eller krav i loven kan data opbevares længere.
- **Din MitID-adgangskode gemmes ingen steder** og sendes ikke til AI'en. Nye logins godkendes altid i MitID-appen.
- AI'ens svar kan kun blive til aftaler i din egen kalender og en mail til dig selv. Står der instruktioner til AI'en i en besked fra en anden, kan de ikke få adgang til dine login eller sende noget til andre:
  - Med Claude Code må Claude kun læse filer i kørslens egen mappe.
  - Med Codex sender Codex-programmet Aula-indholdet til OpenAI og får svaret tilbage; det er den eneste netværkstrafik. Selve modellen kører i en midlertidig mappe uden for agent-mappen, i en sikker Windows-sandkasse: MXC på nyere Windows 11, ellers Codex' egen "elevated"-sandkasse. Kommandoer, den forsøger at køre på computeren, kan ikke skrive filer, har intet netværk og kan ikke læse filer i din brugermappe (fx Dokumenter, Skrivebord, browserprofiler og login-filer) ud over den midlertidige mappe. Med den ældre sandkasse kan de se navne på mapper og filer, men ikke indholdet; med MXC heller ikke navnene. Agenten slår Codex' shell, websøgning og andre værktøjer fra og bruger ikke din egen Codex-opsætning, MCP-servere eller regler. Kan sandkassen ikke starte, kører agenten ikke Codex, og den skifter aldrig til en svagere sandkasse.
  - Med API-nøgle kan AI'en kun se de billeder, agenten selv sender. Som standard er det ingen.

## Sendes data til USA, og er det lovligt?

Ja, Aula-indholdet sendes til Claude (Anthropic) eller ChatGPT (OpenAI), og begge behandler data i USA. Det gælder også beskeder fra lærere og andre forældre, referater og teksten i vedhæftede billeder. Kendte navne og de mailadresser, telefonnumre og adresser, der står i teksterne, er erstattet med dæknavne (se ovenfor), men enkelte kan slippe igennem. Selve billederne sendes ikke, medmindre du selv ændrer `send_images`. Dine logins og din kalender bliver på din egen computer, og intet sendes til mig.

**Slå træning fra.** Se ovenfor, hvor indstillingen findes i Claude og ChatGPT. Med træning slået fra slettes data efter højst 30 dage. Med en API-nøgle bruges data aldrig til træning. Med træning slået til kan andre familiers beskeder indgå i træningsdata i op til 5 år, og det synes jeg ikke, man skal gøre.

**GDPR:** Bruger du agenten som privatperson til dine egne børn, er det efter min vurdering omfattet af GDPR's undtagelse for rent personlige aktiviteter (artikel 2, stk. 2, litra c). Anthropic og OpenAI har selv ansvaret for deres behandling af data. Jeg er ikke jurist. Bruger du den i en officiel rolle (skole, forening, institution), gælder undtagelsen ikke.

## Sådan trækker du adgangen tilbage

- **Outlook:** account.microsoft.com > Privatliv > Apps og tjenester, fjern "Microsoft Graph Command Line Tools". Slet `graph_token_cache.dat`.
- **Aula:** slet `aula_tokens.dat`. Login udløber også af sig selv efter noget tid.
- **API-nøgle:** slet den på console.anthropic.com under API Keys eller på platform.openai.com under API keys.
- **Codex (ChatGPT):** kør `codex logout`.
- **Planlagt kørsel:** Opgavestyring > "Aula-kalenderagent ugentlig" > Slet.

`.gitignore` sørger for, at config, login, logs og kørsler aldrig kommer med, hvis du selv lægger projektet på GitHub.
