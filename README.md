# UNAS QR husegpont middleware

Onallo, biztonsagos kozepreteg, ami osszekoti a fizikai bolti kasszat az UNAS
webaruhaz API-javal: a vasarlo UNAS-profiljaban megjeleno QR-kodot beolvasva a
kasszas megnezheti az aktualis pontegyenleget, majd jovairhat vagy levonhat
pontokat.

Hattér es teljes funkcionalis specifikacio:
[docs/CLAUDE_CODE_UNAS_QR_MIDDLEWARE_SPEC.md](docs/CLAUDE_CODE_UNAS_QR_MIDDLEWARE_SPEC.md),
UNAS API reszletek: [docs/UNAS_API_gyakorlati_utmutato.md](docs/UNAS_API_gyakorlati_utmutato.md).

Tovabbi dokumentumok:

- [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) - fejlesztoi utmutato: uj gepen inditas, tipikus modositasi feladatok
- [docs/UNAS_SETUP.md](docs/UNAS_SETUP.md) - UNAS admin/API/webhook beallitas
- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) - eles telepites (jelenleg: Fly.io)
- [docs/VPS_ATALLAS.md](docs/VPS_ATALLAS.md) - a rendszer mukodesenek attekintese, es lepesenkenti utmutato sajat VPS-re koltozeshez
- [docs/CASHIER_GUIDE.md](docs/CASHIER_GUIDE.md) - kasszas hasznalati utmutato
- [docs/ARCHITECTURE_DECISIONS.md](docs/ARCHITECTURE_DECISIONS.md) - tervezesi dontesek es indoklasuk
- [docs/KNOWN_LIMITATIONS.md](docs/KNOWN_LIMITATIONS.md) - ismert korlatok, mit kell meg ellenorizni eles inditas elott

## Tech stack

Python 3.12+, FastAPI, SQLAlchemy 2.0 + Alembic, SQLite alapertelmezetten
(Postgres-re valthato), httpx + defusedxml a UNAS XML API-hoz, Jinja2 + natur JS/CSS
a kasszafeluletnek (nincs Node/npm build-lepes).

## Helyi telepites (Windows PowerShell)

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
Copy-Item .env.example .env
# szerkeszd a .env fajlt: UNAS_API_KEY, UNAS_WEBHOOK_HMAC_SECRET, SESSION_SECRET, uzleti szabalyok
alembic upgrade head
python -m loyalty_app.cli seed-store --name "Fo bolt" --code BOLT01
python -m loyalty_app.cli create-user --username admin1 --role admin --store-code BOLT01
uvicorn loyalty_app.main:app --reload
```

Nyisd meg: <http://127.0.0.1:8000/login>

## Tesztek

```powershell
pytest -q
```

70+ teszt fut valodi UNAS-hivas nelkul (mockolt UnasClient es respx-mockolt HTTP
reteg egyarant). Lasd a `tests/` mappat.

## Parancssori (admin) muveletek

```powershell
python -m loyalty_app.cli seed-store --name "Bolt neve" --code KOD
python -m loyalty_app.cli create-user --username NEV --role admin|cashier --store-code KOD
python -m loyalty_app.cli backfill-customers --dry-run
python -m loyalty_app.cli backfill-customers
```

A `backfill-customers` lapozva vegigmegy a meglevo UNAS-vasarlokon, es azoknak,
akiknek meg nincs husegpont-tokenjuk, general es visszair egyet. `--dry-run`
semmit sem ir sehova, csak szamlal.

## Projektstruktura

```text
src/loyalty_app/
  main.py            FastAPI app, lifespan inditja a hatter workert
  config.py          Settings (pydantic-settings, .env)
  db.py              SQLAlchemy engine/session (SQLite: BEGIN IMMEDIATE tranzakciok)
  models.py           stores, registers, users, loyalty_customers, loyalty_transactions, webhook_events
  security.py         token gen/hash, jelszo hash (bcrypt), HMAC ellenorzes, log-maszkolas
  concurrency.py       vasarlonkenti asyncio lock (egy folyamaton beluli szerializalas)
  unas/                UnasClient: login+token cache, XML builder/parser (defusedxml)
  loyalty/             qr.py, rules.py, service.py (uzleti logika), webhook_adapter.py
  worker.py            hatter poller: webhook_events feldolgozas, pending tranzakcio egyeztetes
  api/                 auth, scan, loyalty, webhook, health route-ok + Jinja2 oldalak
  templates/, static/  kasszafelulet (login, register)
  cli.py               Typer CLI: seed-store, create-user, backfill-customers
migrations/            Alembic
tests/                 pytest, mockolt UNAS klienssel
```
