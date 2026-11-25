# Pris og valg af AI

[Tilbage til forsiden](../README.md)

## Pris

Med Claude Code koster agenten intet ekstra; kørslerne tæller i dit abonnement (én kørsel om ugen).

Med Claude API-nøgle betaler du for det, Claude læser. Det afhænger af, hvor meget skolen skriver. Beregnet med Anthropics listepriser for Opus 5.5 ud fra tokenforbruget i rigtige kørsler med to børn (november 2026):

| Kørsel | Indhold | Anslået pris |
|---|---|---|
| Første kørsel, 30 dage tilbage | flere hundrede opslag og beskeder, Word/PDF-filer, tekst fra billeder | ca. 0,70-1,00 dollar (5-7 kr.) |
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

Billeder sendes som standard ikke; kun teksten i dem, og den fylder meget lidt. Har du sat `send_images` til `auto` eller `always`, bliver billederne skaleret ned, før de sendes. Med API-nøgle og Claude Code ser AI'en så kun dem, reglerne i `regler.md` siger, den skal se. Med Codex sendes de med fra start (højst 12).

## Kvalitet med ChatGPT

Agenten er udviklet og testet med Claude Opus. ChatGPT-understøttelsen er ny, og kvaliteten kan svinge. **Brug ChatGPT Plus eller Pro eller en API-nøgle. Med Go eller Free skal du regne med store mangler:**

- **Med ChatGPT Go eller Free** bruger Codex en mindre model (GPT-6 Luna). Vi har sammenlignet den med Claude Opus på tre rigtige kørsler: Fri-tiderne var de samme, og huskelisten var næsten den samme. Men Luna overså flere ting i ugemailen, fx et kontaktforældremøde og dage, hvor begge børn havde noget samtidig, og satte et par punkter på det forkerte barn. I en fjerde kørsel (11. nov. 2026) fik kun 2 af ugens 10 fri-tider en tid, ugemailen fik ét punkt, hvor Claude Opus fandt fire, og en note om varmt tøj kom på den forkerte fødselsdag. Aftalerne i kalenderen var de samme som med Claude. Regn derfor med, at kalenderen er til at stole på, men at ugemailen og huskelisten kan mangle noget.
- **Med ChatGPT Plus eller højere** bruger agenten GPT-6.1 Sol, og med API-nøgle også GPT-6.1 Sol som standard. Sol og den større GPT-6 Astra er ikke testet på rigtige kørsler endnu. I uafhængige test ligger de tæt på Claude Opus, så kvaliteten vil sandsynligvis være bedre end med Go og Free.

Kig ugemailen og kalenderen igennem de første uger, og skriv gerne i [Feedback](../README.md#feedback), hvad der manglede.
