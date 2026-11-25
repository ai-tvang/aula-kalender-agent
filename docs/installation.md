# Installation i detaljer

[Tilbage til forsiden](../README.md)

## Det skal du have

- **Windows 10 eller 11.** Det er det eneste, der er testet.
- **En personlig Outlook-konto** (@outlook.com, @hotmail.com, @live.dk). Arbejdskonti blokerer ofte for den slags adgang. Outlook-appen skal ikke være installeret; agenten logger selv ind.
- **Adgang til Claude eller ChatGPT** på én af fire måder. Installationen spørger, hvilket abonnement du har:
  - **Claude Code (anbefalet)** med et betalt Claude-abonnement (Pro eller Max). Kørslerne tæller med i dit almindelige forbrug og koster ikke ekstra. Claude-appen er ikke nok, men installationen installerer Claude Code for dig, og du logger ind én gang undervejs.
  - **Codex** med et ChatGPT-abonnement (Plus eller Pro). Go og Free virker teknisk, men giver store mangler i ugemailen og huskelisten og kan ikke anbefales. Codex følger med abonnementet, og kørslerne bruger af den Codex-kvote, abonnementet giver. Du betaler ikke ekstra, men der er forbrugsgrænser, som afhænger af abonnementet. ChatGPT-appen er ikke nok, men installationen installerer Codex (OpenAIs program til kommandolinjen) for dig, og du logger ind med din ChatGPT-konto én gang. Se [Kvalitet med ChatGPT](pris.md#kvalitet-med-chatgpt).
  - **Claude API-nøgle** fra [console.anthropic.com](https://console.anthropic.com/settings/keys). Du betaler pr. kørsel, i dag omkring 6-10 kr. om måneden med Opus (se [Pris](pris.md)). Kræver betalingskort og lidt kredit.
  - **OpenAI API-nøgle** fra [platform.openai.com](https://platform.openai.com/api-keys). Du betaler pr. kørsel. Et ChatGPT-abonnement giver ikke API-adgang; den betales for sig. Kræver betalingskort og lidt kredit.
- **Dit login til Claude eller ChatGPT** (e-mail og adgangskode eller Google/Apple-login). Installationen åbner browseren og beder dig logge ind. Er du allerede logget ind på claude.ai eller chatgpt.com i browseren, går det hurtigere.
- **MitID-appen** og adgang til Aula som forælder.
- En computer, der **kører agenten om søndagen**. Sover eller er den slukket kl. 7, kører agenten, første gang du logger på eller låser skærmen op bagefter, og mailen kommer få minutter efter. Mange nyere bærbare (Modern Standby) bliver ikke vækket af planlagte opgaver, og Windows indhenter dem ikke selv; derfor starter opgaven også ved logon og oplåsning og kører kun, hvis ugens kørsel mangler.

## Installation

1. Åbn **PowerShell**: klik på Start, skriv `PowerShell` og tryk Enter.
2. Kopiér linjen herunder (brug kopi-ikonet til højre), indsæt den i PowerShell med højreklik, og tryk Enter:
   ```
   irm https://raw.githubusercontent.com/ai-tvang/aula-kalender-agent/main/install.ps1 | iex
   ```
3. Følg vinduet. Selve opsætningen tog ca. 7 minutter i vores test, inklusive MitID, Outlook-login og første kørsel. Skal Python og Claude Code eller Codex installeres først, kommer det oveni. Hav din telefon med MitID-appen klar, og log gerne ind på claude.ai eller chatgpt.com i browseren først:
   1. **Python og uv** installeres automatisk.
   2. **AI:** Du vælger Claude, ChatGPT eller API-nøgle. Med Claude installeres **Claude Code**; du logger ind i browseren og skriver `/exit`, når den er klar. Med ChatGPT installeres **Codex**; du logger ind med din ChatGPT-konto i browseren. På nyere Windows 11 bruger Codex Windows' indbyggede sandkasse (MXC) uden videre. På ældre Windows beder Windows én gang om administrator-godkendelse til Codex' sandkasse. Har du allerede Claude Code eller Codex, bruges det, men du bliver stadig spurgt, så du selv vælger.
   3. **MitID-brugernavn**, og godkendelse i MitID-appen. Agenten henter selv dine børn, deres skole, klasse og Aula-grupper, dit navn og om du er kontaktforælder.
   4. **Outlook-login** med en kode på microsoft.com/link. Ugemailen går til den konto, du logger ind med, og kalenderen "Skole og fritid" oprettes.

   Derefter opretter scriptet en ugentlig kørsel søndag kl. 7 og laver første kørsel med det samme (læser 30 dage tilbage). Kan agenten ikke finde et barns klasse, bliver du spurgt om den.

Agenten ligger bagefter i `C:\Users\<dig>\Aula-kalenderagent`, og du finder genvejene ved at søge på **Aula-agent** i Start-menuen: **Aula-agent kør nu**, **Aula-agent log ind på Aula igen**, **Aula-agent log ind på Outlook igen**, **Aula-agent opsætning** og **Aula-agent åbn mappen**. Du skal ikke bruge PowerShell igen.

**Opdatering:** kør samme linje igen. Den finder selv din installation, også hvis du har installeret fra ZIP et andet sted. Dine indstillinger, login og den planlagte kørsel bevares, og genvejene i Start-menuen opdateres.

**Skift AI:** kør **Aula-agent opsætning** fra Start-menuen, og vælg `claude`, `chatgpt` eller `api` (API-nøgle). Mangler programmet, tilbyder opsætningen at installere det.

Navne, klasser, Aula-grupper og noter om familien kan rettes bagefter i `config.json`. Kør **Aula-agent opsætning** fra Start-menuen for at opdatere fra Aula; det, du har rettet, bliver bevaret.

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

Linjen henter [install.ps1](../install.ps1) fra dette repo og kører den. Du kan åbne filen og læse den først; den er kort. Den gør tre ting:

1. Henter agenten som ZIP-fil fra GitHub og lægger den i `C:\Users\<dig>\Aula-kalenderagent`.
2. Starter [opsaet.ps1](../opsaet.ps1), som installerer Python (via winget fra python.org), uv (fra astral.sh) og, alt efter dit valg, Claude Code (fra claude.ai) eller Codex (fra chatgpt.com).
3. Opsætningen opretter en planlagt opgave og genveje i Start-menuen.

Intet sendes til forfatteren af agenten. Hvad agenten gemmer og sender til AI'en, står under [Privatliv og sikkerhed](privatliv.md), og hvordan du fjerner det igen, under [Sådan trækker du adgangen tilbage](privatliv.md#sådan-trækker-du-adgangen-tilbage).

### Hjælp fra Claude eller ChatGPT

Du kan indsætte linket til denne side i Claude eller ChatGPT og skrive fx "Hjælp mig med at installere den her trin for trin". Går noget galt, så kopiér teksten fra PowerShell-vinduet ind i chatten. Fjern navne på børn og andre forældre først.

### Hvis noget går galt

| Det ser du | Gør sådan |
|---|---|
| Rød tekst om `iexirm` eller en lang, forkert kommando | Linjen blev indsat to gange. Tryk Esc, og indsæt den én gang. |
| Fejl om, at scripts er deaktiveret ("running scripts is disabled") | Brug linjen fra trin 2. Ved den manuelle vej: kør `powershell -ExecutionPolicy Bypass -File .\opsaet.ps1`. |
| "STOP: Din brugermappe ligger i OneDrive" | Brug den manuelle vej, og læg mappen uden for OneDrive, fx `C:\Aula-kalenderagent`. |
| "Python 3.14 kunne ikke installeres" | Installer Python 3.14 fra [python.org](https://www.python.org/downloads/windows/), og kør linjen igen. |
| `claude` findes ikke, eller Claude Code beder om login under kørslen | Åbn et nyt PowerShell-vindue, kør `claude`, log ind og skriv `/exit`. Kør derefter **Aula-agent opsætning** fra Start-menuen (eller linjen igen). |
| Du har ikke et Claude-abonnement | Vælg ChatGPT, hvis du har ChatGPT Plus eller Pro, ellers en API-nøgle (se [Det skal du have](#det-skal-du-have)). |
| Ugemailen siger, at ChatGPT ikke kunne logge ind | Kør **Aula-agent opsætning** fra Start-menuen, og sig ja til at logge ind i Codex. Kør derefter **Aula-agent kør nu**. (Avanceret: `codex login` i PowerShell.) |
| "Codex kunne ikke starte sin sikre sandkasse" | Kør **Aula-agent opsætning** fra Start-menuen, og sig ja til at sætte sandkassen op. På ældre Windows beder Windows om administrator-godkendelse. Agenten kører ikke Codex uden sandkassen. (Avanceret: `codex sandbox setup --elevated --current-user`.) |
| "Codex CLI er for gammel" | Kør **Aula-agent opsætning** fra Start-menuen, og sig ja til at opdatere Codex. (Avanceret: `npm install -g @openai/codex@latest`.) |
| MitID spørger, om du vil logge ind som privatperson eller et firma | Vælg dig selv som privatperson. |
| "Codes read. Approve the login in your MitID app." | Teksten er på engelsk, men betyder bare: godkend i MitID-appen. |
| Outlook-login: kode og microsoft.com/link | Åbn microsoft.com/link i browseren, skriv koden, log ind med din personlige Outlook-konto og godkend. Vinduet fortsætter selv. |
| Outlook-login afvises, eller du bliver bedt om en administrator | Det er sandsynligvis en arbejds- eller skolekonto. Brug en personlig konto, fx en ny gratis @outlook.com. |
| Opsætningen stoppede halvvejs | Kør linjen eller **Aula-agent opsætning** igen. Det, der allerede er gemt (fx MitID og Outlook), genbruges. |
| Ingen ugemail søndag | Computeren var slukket eller sov. Agenten kører, første gang du logger på eller låser op. Kommer mailen ikke da, så se `logs\agent.log` via **Aula-agent åbn mappen**. Installeret før 23. nov. 2026: kør installationslinjen igen (svar N), så opgaven får de nye udløsere. |

Står din fejl ikke her, så opret et [issue](https://github.com/ai-tvang/aula-kalender-agent/issues) med teksten fra vinduet (uden navne).
