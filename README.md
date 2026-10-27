# Fractie-app PVV Hengelo (proef)

Aparte proefversie, afgeleid van de fractie-app van PVV Almelo. Bevat geen Almelo-gegevens,
geen inzendmap, geen Google Apps Script en geen fractiecode.

- `index.html` – de app (tabs Agenda, Wie is wie, Over)
- `data.json` – agenda; wordt gevuld door `scripts/notubiz_agenda.py`
- `scripts/notubiz_agenda.py` – haalt vergaderingen op via de openbare Notubiz-API (api.notubiz.nl)
- `.github/workflows/agenda.yml` – draait het script elke nacht op GitHub en zet data.json bij

Testen: `python3 scripts/notubiz_agenda.py --test` toont de organisatie-id van Hengelo en de eerste vijf vergaderingen.
Online zetten: repo `pvv-hengelo-app` aanmaken, deze map erin, GitHub Pages aanzetten (branch main, map /).
