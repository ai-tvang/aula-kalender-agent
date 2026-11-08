# Tests

Tests med falske svar fra Aula, Outlook og Claude. Intet rigtigt login bruges, og intet sendes.

Kør fra repo-mappen (kræver `httpx`, `msal` og `beautifulsoup4`):

```
python -I tests/test_agent.py .
python -I tests/test_guide.py .
python -I tests/test_security.py .
```

Windows-krypteringen (DPAPI) er erstattet af en falsk i `test_security.py`. Den rigtige testes af `agent.py opsaet`, som stopper med en fejl, hvis krypteringen ikke virker.
