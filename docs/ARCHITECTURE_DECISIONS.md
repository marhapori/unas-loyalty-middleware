# Architekturalis dontesek

Rovid ADR-szeru osszefoglalo azokrol a dontesekrol, amik nem kovetkeznek
kozvetlenul a specifikaciobol, hanem a konkret kornyezet (nincs Node/Docker
telepitve, kis leptek, VIP UNAS csomag) alapjan szulettek.

## 1. Python/FastAPI, nem TypeScript/Node

A specifikacio eredetileg Node.js + Postgres stacket javasolt. Ezen a gepen
nincs Node/npm/Docker telepitve, viszont Python 3.13 igen. Python + FastAPI
ugyanazokat a kepessegeket nyujtja (async HTTP, tipizalt konfiguracio, ORM,
tesztelheto XML-kezeles), es a masik mellekelt dokumentum (UNAS API gyakorlati
utmutato) is Pythont javasol az UNAS-integraciohoz - igy a ket dokumentum
konzisztens modon egy stackben valosithato meg.

## 2. SQLite alapertelmezetten, Postgres-kompatibilis kod

Kis leptek (1 bolt, nehany kassza), meg nincs eldontve a hosting. SQLite fajl
alapu, nem igenyel kulon adatbazis-szervert. A kod ugy keszult, hogy Postgres-re
allitas csak `DATABASE_URL` valtoztatas + `pip install psycopg`:

- A modellek/lekerdezesek nem hasznalnak SQLite-specifikus SQL-t.
- A `loyalty_app/loyalty/service.py` a `with_for_update()`-mintat hasznalja a
  vasarlo sor lekerdezesenel - SQLite-on ez nem-op (nincs sorzarolas
  szintaxisa), Postgresen valodi sorzarolas.
- Lasd meg 3. pont: SQLite-on a tenyleges konkurenciavedelmet mas mechanizmus
  adja.

## 3. Ketreteg konkurenciavedelem

- **Elsodleges (SQLite, egy folyamat)**: `loyalty_app/concurrency.py`
  `KeyedLockRegistry` - vasarlonkenti `asyncio.Lock`, ami egy folyamaton belul
  garantalja, hogy ugyanahhoz a vasarlohoz egyszerre csak egy
  earn/redeem/reverse fusson. Ez NEM vedet tobb folyamat/worker kozott.
- **Masodlagos (barhol)**: a `loyalty_transactions.idempotency_key` egyedi
  megszoritas - ha a lock valahogy megis megkerulve lenne (pl. folyamat-
  ujrainditas kozepen), a duplikalt feldolgozas akkor sem tortenhet meg
  ketszer ugyanazzal a kulccsal.
- **Postgres + tobb worker eseten**: a `SELECT ... FOR UPDATE` sorzarolas lesz
  az elsodleges, folyamatok kozotti garancia (lasd 2. pont).
- Kulon fontos: a `db.py`-ban a SQLite motor `BEGIN IMMEDIATE`-tel indit minden
  tranzakciot (nem `BEGIN DEFERRED`-del), ami a teljes adatbazis-irászarolast
  azonnal felveszi tranzakcio elejen - ez elkeruli az "olvas-modosit-ir" tipusu
  lost update hibat. Emiatt a service reteg **szandekosan nem tart nyitva DB
  tranzakciot a UNAS-hivas (halozati I/O) alatt** - a pending tranzakciosor
  kulon, rovid tranzakcioban keszul el a UNAS-hivas elott, majd a vegeredmeny
  egy masik rovid tranzakcioban keriil rogzitesre. Igy egy lassu UNAS-valasz
  nem blokkolja a tobbi (masik vasarlohoz tartozo) irast/olvasast.

## 4. In-process hatter worker, DB-tabla mint outbox

Nincs Redis/Celery/message broker. A `webhook_events` tabla maga a tartos
"queue": a webhook endpoint csak HMAC-et ellenoriz, dedupe-ol es beir egy sort,
majd azonnal 2xx-et ad vissza. Egy `asyncio` háttérfeladat (lasd `worker.py`,
`main.py` `lifespan`) periodikusan feldolgozza a `received` allapotu sorokat, es
egyezteti az elakadt `pending` tranzakciokat. Ez ugyanabban a folyamatban fut,
mint a webszerver - egyszeru, nulla extra infrastruktura, de **csak egyetlen
alkalmazaspeldany** mellett helyes (lasd DEPLOYMENT.md `--workers 1`).

## 5. Osszegalapu pontszamitas, nem termek/SKU-alapu

Nincs POS-integracio ebben a fazisban (a specifikacio is ezt eloirja elso
lepeskent), igy nincs tetel/SKU adat a kasszatol - csak a vegosszeg. A
pontszamitasi szabaly (`LOYALTY_POINTS_RULE_MODE=per_currency_unit`) es minden
parametere (`LOYALTY_POINTS_PER_CURRENCY_UNIT`, kerekites, beváltási ertek,
min/max) konfiguralhato, alapertelmezetten kitoltetlen - eles indulas elott a
boltnak meg kell adnia a valos ertekeket.

## 6. Pontok es osszegek egesz szamkent

A UNAS API pelda-XML-jei (lasd UNAS_API_gyakorlati_utmutato.md es a specifikacio
peldai) egesz pontertekeket hasznalnak. A `loyalty_transactions.points_delta`,
`balance_before`, `balance_after` mind SQL `Integer` tipusu - igy nincs
lebegopontos kerekitesi hiba, es a UNAS `PointsAccount.Balance` mezobe irt ertek
mindig egyertelmu egesz szam.

## 7. Pragmatikus CSRF-vedelem: egyedi fejlec + sajat Host osszehasonlitas

A JSON API vedelmehez nincs kulon CSRF-token-mechanizmus (session-alapu form
helyett). Helyette:

- Minden allapotvaltoztato hivas kotelezoen kuldi az `X-Requested-With:
  XMLHttpRequest` fejlecet - ezt egy sima cross-site HTML form nem tudja
  hozzaadni, es egy cross-site `fetch()` eseten a bongeszo CORS-preflightot
  valtana ki, amit a szerver nem enged.
- Ha az `Origin` fejlec jelen van, a rendszer a **kereles sajat `Host`
  fejlecehez** hasonlitja, nem egy kulon konfiguralt `APP_BASE_URL`-hez. Ez
  szandekos: ha a `Host` es a konfiguralt `APP_BASE_URL` eltero modon
  keriilnek elerve (pl. `127.0.0.1` vs `localhost`, reverse proxy mogott ipv.
  domain), egy fix ertekhez hasonlitas teves elutasitast okozna minden valodi
  keresre. Ezt eles teszteles kozben talaltuk es javitottuk (lasd
  `api/deps.py` `verify_same_origin`).
- Munkamenet-cookie `SameSite=Strict` es (HTTPS mogott) `Secure`.

## 8. Session-alapu kasszas bejelentkezes, nem JWT

Egyszeru, szerveroldali session-cookie (Starlette `SessionMiddleware`,
`itsdangerous` alairassal) - nincs sziikseg tobb-szolgaltatasos
tokenmegosztasra, a kasszafelulet ugyanazon a domainen fut, mint az API.

## 9. Jinja2 + natur JS/CSS, nincs frontend build

Nincs Node/npm ezen a gepen. A kasszafelulet szerveroldalon renderelt HTML +
minimalis vanilla JS (`fetch`, DOM API) - nincs bundler, nincs build-lepes, igy
a fejlesztes es a telepites is egyszerubb marad.
