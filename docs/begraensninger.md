# Kendte begrænsninger og muligt senere arbejde

[Tilbage til forsiden](../README.md)

## Kendte begrænsninger

- Aulas API er uofficielt og kan holde op med at virke.
- Outlook-adgangen bruger Microsofts offentlige app til Graph PowerShell, fordi personlige konti ikke kan oprette egne app-registreringer uden Azure. Microsoft kan ændre det. Har du din egen app-registrering, kan du sætte `graph_client_id` i config.
- AI'en kan tolke det samme lidt forskelligt fra kørsel til kørsel. Ugemailen og `runs`-mappen viser, hvad der skete.
- Ugeplaner afhænger af, hvilket system skolen bruger, og af at læreren skriver det i ugeplanen. Kør `agent.py ugeplan` for at se, hvad agenten finder hos jer.
- Tekst i billeder læses med Windows' tekstgenkendelse. Trykt tekst læses godt; håndskrift, pyntede skrifttyper og uskarpe fotos kan give fejl eller ingenting. I vores test mistede en pyntet fødselsdagsinvitation klokkeslættet: aftalen kom i kalenderen på den rigtige dato som heldagsaftale med en note om at tjekke invitationen. Virker tekstgenkendelsen slet ikke på computeren (fx hvis Windows mangler den, eller PowerShell er låst på en arbejdscomputer), eller mangler dansk sprogpakke, så æ, ø og å kan blive læst forkert, står det i ugemailen. Tekstgenkendelsen er kun prøvet på én computer med dansk Windows 11.
- Dæknavne kan ramme forkert: et fornavn, der også er et almindeligt ord (fx Storm, Liv eller Bjørn), kan blive erstattet midt i en sætning, hvor det ikke var et navn. Det rettes tilbage i resultatet, men kan gøre AI'en lidt mindre præcis.
- Kun testet på Windows med Outlook. Google Kalender understøttes ikke endnu.

## Muligt senere arbejde

- **Lærerinitialer.** Aula har initialer på alle profiler, også børn og forældre. Står en lærers initialer i skemaet eller en ugeplan, sendes de i dag, som de står. Agenten kunne skjule medarbejdernes initialer på samme måde som navnene. At skjule alle initialer ville ramme almindelige forkortelser.
- **Navne, der ikke står på Aulas lister.** Bedsteforældre, trænere og personer, der står i Aula under et andet navn (fx ved navne- og adressebeskyttelse), bliver ikke skjult. En liste over danske fornavne kunne fange flere af dem, men rammer også almindelige ord og navne på fx film og bøger. Det er derfor ikke lavet endnu.
- **Andre kalendere og mailtjenester**, fx iPhone og Google.
