# Fejlesztoi utmutato

Ez a dokumentum azoknak szol, akik egy **masik gepen/eszkozon** vennek fel a
munkat ezen a projekten: uj funkciot adnanak hozza, meglevot modositananak,
vagy csak meg akarjak erteni, hova nyuljanak. A *miert igy epul fel a rendszer*
kerdesre a [docs/ARCHITECTURE_DECISIONS.md](ARCHITECTURE_DECISIONS.md) valaszol,
a *hogyan fut / hogyan koltoztetheto* kerdesre a
[docs/VPS_ATALLAS.md](VPS_ATALLAS.md) es a [docs/DEPLOYMENT.md](DEPLOYMENT.md).
Ez a dokumentum a napi fejlesztoi munkafolyamatot es a legjellemzobb
modositasi mintakat irja le.

## 1. Elso lepesek uj gepen

```powershell
git clone <repo-url>
cd unas-loyalty-middleware
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
Copy-Item .env.example .env
# .env: legalabb UNAS_API_KEY, UNAS_WEBHOOK_HMAC_SECRET, SESSION_SECRET
alembic upgrade head
python -m loyalty_app.cli seed-store --name "Fo bolt" --code BOLT01
python -m loyalty_app.cli create-user --username admin1 --role admin --store-code BOLT01
pytest -q
uvicorn loyalty_app.main:app --reload
```

Ha `pytest -q` zold es a szerver elindul, a fejlesztoi kornyezet kesz. Valodi
UNAS API-kulcs **nem** kell a teszteles/fejlesztes tobbsegehez - a tesztek
mockolt UNAS klienssel (`tests/fake_unas.py`) es respx-mockolt HTTP retegel
futnak. Csak akkor kell valodi kulcs, ha ele UNAS-hivast is ki akarsz probalni
(pl. `backfill-customers` egy valodi teszt-shop ellen).

## 2. Hol van mi (fejlesztoi nezopont)

```
src/loyalty_app/
  main.py              FastAPI app-factory: middleware, router-regisztracio, lifespan (worker inditasa/leallitasa)
  config.py            Settings - MINDEN uj kornyezeti valtozo ide kerul (lasd 4. pont)
  db.py                engine/session, SQLite BEGIN IMMEDIATE, DB-URL normalizalas (postgres:// -> postgresql+psycopg://)
  models.py            SQLAlchemy modellek (lasd 5. pont - migraciohoz kell)
  security.py          token gen/hash, bcrypt jelszo, HMAC ellenorzes, log-maszkolas (RedactingFilter)
  concurrency.py       KeyedLockRegistry - vasarlonkenti asyncio.Lock
  rate_limit.py         in-memory sliding-window rate limiter

  unas/
    client.py           UnasClient - login+token cache, XML hivasok epitese/parse-olasa
    xml_utils.py         XML builder/parser helperek (defusedxml)
    exceptions.py        UnasApiError, UnasTransientError

  loyalty/
    qr.py                QR payload parse/validalas (extract_token, validate_token_shape)
    rules.py              pontszamitas, min/max beváltás validacio (RuleViolation)
    service.py            UZLETI LOGIKA: scan/earn/redeem/reverse - IDE nyulsz uj tranzakcio-tipusnal
    webhook_adapter.py     UNAS customer_registration payload -> UNAS vasarlo-ID
    errors.py              LoyaltyServiceError es alosztalyai

  worker.py             hatter poller: webhook_events feldolgozasa, elakadt pending tranzakciok egyeztetese

  api/
    deps.py              FastAPI dependency-k: get_db, get_current_user, require_role, verify_same_origin, get_unas_client
    schemas.py            Pydantic request/response modellek - UJ VEGPONTNAL IDE IS KELL
    auth_routes.py         /login, /logout
    pages.py               /register, /scan/{token} (Jinja2 oldalak)
    scan_routes.py          /api/scans/resolve
    loyalty_routes.py       /api/loyalty/earn|redeem|transactions/:id/reverse|transactions|config
    webhook_routes.py       /webhooks/unas/customer-registration
    admin_routes.py         /api/admin/bootstrap (Shell nelkuli hosting-hoz, lasd DEPLOYMENT.md)
    health_routes.py        /health/live|ready|outbound-ip

  templates/, static/    kasszafelulet: login.html, register.html, register.js, styles.css (nincs build-lepes, egyszeruen szerkesztheto)
  cli.py                  Typer CLI: seed-store, create-user, backfill-customers

migrations/versions/    Alembic migraciok (lasd 5. pont)
tests/                  pytest, fake_unas.py + respx mockolt UnasClienssel
```

## 3. Tipikus modositasi feladatok

### 3.1 Uj API-vegpont hozzaadasa

1. Ha uj request/response alak kell, vedd fel a Pydantic modellt
   [`api/schemas.py`](../src/loyalty_app/api/schemas.py)-ban.
2. Ha uzleti logikat is igenyel (nem csak olvasas), az uzleti szabaly a
   [`loyalty/service.py`](../src/loyalty_app/loyalty/service.py)-ba kerul, NEM
   a route-fajlba - a route csak validal, hivja a service-t, es HTTP-hibara
   forditja a kivetelt (lasd `loyalty_routes.py::_raise_for` mintajat).
3. A route-ot a megfelelo `api/*_routes.py` fajlba vedd fel, majd regisztrald
   [`main.py`](../src/loyalty_app/main.py)-ban (`app.include_router(...)`), ha
   uj router-fajlt hoztal letre.
4. Allapotvaltoztato (POST/PUT/DELETE) vegpontnal hasznald a
   `dependencies=[Depends(verify_same_origin)]` mintat (lasd
   `loyalty_routes.py` router-definicioja) - ez a CSRF-vedelem (lasd
   ARCHITECTURE_DECISIONS.md 7. pont).
5. Ha csak bejelentkezett felhasznalonak elerheto: `Depends(get_current_user)`;
   ha csak adminnak: `Depends(require_role("admin"))` (lasd `api/deps.py`).
6. Irj hozza tesztet: masold egy meglevo `tests/test_earn_redeem.py` vagy
   `tests/test_reversal.py` mintajat (FastAPI `TestClient` + `fake_unas`).

### 3.2 Uj uzleti szabaly / uj tranzakcio-tipus

- A pontszamitasi es beváltási szabalyok a
  [`loyalty/rules.py`](../src/loyalty_app/loyalty/rules.py)-ban vannak,
  `RuleViolation` kivetellel jeleznek hibat. Uj szabaly parametereit **mindig**
  a `Settings`-en keresztul tedd konfiguralhatova (lasd 4. pont) - ne irj be
  fix erteket a kodba, mert a spec is ezt kovetelte meg az eredeti
  pontszamitasi/beváltási ertekekre.
- Uj tranzakcio-tipus (pl. `earn`/`redeem`/`reversal` mellé egy negyedik) eseten:
  - vedd fel a `LoyaltyTransaction.type` erteklistajahoz (`models.py`),
  - irj hozza egy uj fuggvenyt `service.py`-ba, ami ugyanazt a mintat koveti,
    mint `earn`/`redeem`: `KeyedLockRegistry` zarolas -> friss UNAS-egyenleg
    lekerese -> `pending` tranzakcio-sor -> UNAS-iras -> vegleges allapot
    (lasd ARCHITECTURE_DECISIONS.md 3. pont - **ne** tarts nyitva DB-tranzakciot
    a UNAS-hivas alatt),
  - `idempotency_key`-t mindig generalj/kovetelj meg, hogy ismetelt kereles ne
    hivja ketszer a UNAS-t.

### 3.3 Uj adatbazis-mezo vagy -tabla (migracio irasa)

```powershell
# modositsd a models.py-t, majd:
alembic revision --autogenerate -m "leiras"
# ELLENORIZD a generalt fajlt migrations/versions/ alatt - SQLite-on az
# autogenerate gyakran ures diffet ad összetettebb valtozasnal (pl. tipusváltás,
# timezone-aware datetime), ilyenkor kezzel kell megirni (lasd
# de2c0497de17_make_datetime_columns_timezone_aware.py mint pelda batch_alter_table hasznalatra)
alembic upgrade head
pytest -q
```

Uj `DateTime` oszlopnal MINDIG a `models.py`-ban mar definialt
`_TZ_DATETIME = DateTime(timezone=True)` konstanst hasznald, ne csupasz
`DateTime`-ot - lasd a Postgres naive/aware datetime hibat a
KNOWN_LIMITATIONS.md-ben, ez pontosan emiatt tortent.

SQLite-specifikus csapda: ha egy migracio oszlopot torol/tipust valt egy
tablan, amire mas tabla FK-val hivatkozik, a `batch_alter_table` hivasok
sorrendje szamit (eloszor a gyermek, utana a szulo tabla) - lasd a fent
emlitett migracio mint pelda.

### 3.4 Uj UNAS API-hivas hozzaadasa

- Minden UNAS-hivas a [`unas/client.py`](../src/loyalty_app/unas/client.py)
  `UnasClient` osztalyan keresztul megy - uj UNAS funkciohoz itt vegyy fel uj
  metodust, ami az `xml_utils.py` builderet hasznalja a keres-XML
  osszeallitasahoz (SOHA ne fuzz ossze XML-t string-kent - XXE es escaping
  kockazat).
- A hibakezeles mintaja: 401/403 -> `UnasApiError` (auth-hiba), minden mas HTTP
  statusz -> a valasz XML-ben levo `<Error>` uzenet kerul felszinre (lasd a
  `_post_once` fuggvenyt es a hozza tartozo javitas leirasat
  KNOWN_LIMITATIONS.md-ben - ne vezess vissza egy generikus "HTTP {status} hiba"
  uzenetet, mert az elrejti a valodi UNAS hibaszoveget).
- Uj hivas teszteleset a `tests/fake_unas.py` mockkal es/vagy respx-mockolt
  HTTP valasszal old meg (lasd `tests/test_unas_client.py`), NE hivj valodi
  UNAS API-t automatizalt tesztbol.

### 3.5 Kasszafelulet (frontend) modositasa

Nincs build-lepes: a `templates/register.html` + `static/register.js` +
`static/styles.css` kozvetlenul szerkesztheto, `uvicorn --reload` azonnal
latja a valtozast (statikus fajloknal bongeszo-frissites kell). Uj JS-allapot
hozzaadasanal kovesd a meglevo mintat: `fetch()` az `/api/...` vegpontokra,
JSON valasz, DOM-frissites kezzel (nincs frontend framework).

## 4. Uj kornyezeti valtozo (config) hozzaadasa

1. Vedd fel a mezot [`config.py`](../src/loyalty_app/config.py) `Settings`
   osztalyaba (tipus + ertelmes alapertelmezett - uzleti szabalyertekeknel
   `0`/ures string, hogy eles inditas elott kotelezo legyen kitolteni, lasd
   ARCHITECTURE_DECISIONS.md 5. pont).
2. Vedd fel `.env.example`-be egy magyarazo komment kiseretében.
3. Ha a VPS-atallas/deployment dokumentaciot erinti (pl. uj titok, ami
   kornyezetenkent mas), frissitsd a [docs/VPS_ATALLAS.md](VPS_ATALLAS.md)
   env-tablazatat es a [docs/DEPLOYMENT.md](DEPLOYMENT.md)-t is.
4. `tests/conftest.py`-ban allitsd be az `os.environ.setdefault(...)` sort,
   ha a tesztkornyezetnek is ertekre van szuksege hozza.

## 5. Tesztelesi konvenciok

- `pytest -q` a teljes suite; valodi UNAS-hivas soha nem tortenik teszt
  kozben - a `tests/fake_unas.py` egy in-memory FakeUnasClient, `respx` pedig
  a nyers HTTP reteget mockolja ott, ahol az XML-parsolast is tesztelni kell
  (`test_unas_client.py`, `test_unas_xml.py`).
- `tests/conftest.py` `db_session` fixture-je egy tiszta in-memory SQLite
  adatbazist ad minden teszthez (`Base.metadata.create_all`), `settings`
  fixture-je pedig egy determinisztikus, kitoltott `Settings`-peldanyt (nem az
  eles alapertelmezett ures ertekekkel).
- Uj service-fuggvenynel irj legalabb: sikeres eset, elegtelen egyenleg/hibas
  bemenet (`RuleViolation`), UNAS-hiba szimulacio (`fake_unas` hibat dob),
  idempotens ismetles ugyanazzal a kulccsal.
- Konkurenciaerzekeny valtozasnal (pl. uj tranzakcio-tipus) nezd meg
  `test_earn_redeem.py`-ban, hogyan tesztelik a `KeyedLockRegistry`-t
  parhuzamos hivasokkal.

## 6. Mielott commitolsz

```powershell
pytest -q
```

Nincs kulon lint/format-parancs beallitva ebben a projektben (nincs
pre-commit hook) - a `pytest -q` zold futasa a minimalis elvaras. Ha uj
migraciot irtal, ellenorizd, hogy `alembic upgrade head` friss adatbazison is
hiba nelkul lefut.

## 7. Kapcsolodo dokumentumok

- [docs/ARCHITECTURE_DECISIONS.md](ARCHITECTURE_DECISIONS.md) - miert igy
  epul fel a rendszer, mit ne valtoztass meg gondolkodas nelkul
  (konkurenciavedelem, worker-minta, CSRF-megoldas)
- [docs/VPS_ATALLAS.md](VPS_ATALLAS.md) - rendszer-attekintes + koltozesi
  utmutato
- [docs/KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) - ismert korlatok, valodi
  incidensek es javitasuk (erdemes atolvasni, mielott hasonlo teruleten
  dolgozol - pl. datetime-kezeles, webhook payload-mezonevek)
- [docs/CLAUDE_CODE_UNAS_QR_MIDDLEWARE_SPEC.md](CLAUDE_CODE_UNAS_QR_MIDDLEWARE_SPEC.md) -
  eredeti teljes funkcionalis/biztonsagi specifikacio
