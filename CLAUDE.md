# CLAUDE.md

Ez a fajl instrukciokat ad a Claude Code-nak, amikor ebben a repoban dolgozik.

## Mi ez a projekt

UNAS QR husegpont middleware: fizikai boltban a vasarlo felmutatja az UNAS
webaruhaz-profiljaban megjeleno QR-kodot, az elado a sajat telefonjaval (vagy
egy USB QR-olvasoval) beolvassa, a kasszafelulet megmutatja az egyenleget, es
jovair/levon pontokat az UNAS API-n keresztul (`setCustomer`). Onallo Python/
FastAPI szolgaltatas, nincs natulajdon UNAS pontkezeles - ezt potolja.

Reszletes doksik (mindig ezeket olvasd, mielott valtoztatsz):

- [README.md](README.md) - helyi telepites, projektstruktura
- [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) - **fejlesztoi utmutato**: hogyan
  adj hozza uj vegpontot/uzleti szabalyt/migraciot, tesztelesi konvenciok
- [docs/ARCHITECTURE_DECISIONS.md](docs/ARCHITECTURE_DECISIONS.md) - miert
  igy epul fel a rendszer (konkurenciavedelem, worker-minta, CSRF), mit ne
  valtoztass meg gondolkodas nelkul
- [docs/KNOWN_LIMITATIONS.md](docs/KNOWN_LIMITATIONS.md) - **mindig ellenorizd
  ezt eloszor** - nyitott hibak/teendok, valodi incidensek es a javitasuk
- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) - eles telepites (Fly.io elsodleges,
  Render/sajat VPS is dokumentalva)
- [docs/VPS_ATALLAS.md](docs/VPS_ATALLAS.md) - rendszer-attekintes + lepesenkenti
  utmutato sajat VPS-re koltozeshez
- [docs/UNAS_SETUP.md](docs/UNAS_SETUP.md) - UNAS admin/API/webhook beallitas
- [docs/CASHIER_GUIDE.md](docs/CASHIER_GUIDE.md) - kasszas hasznalati utmutato

## Aktualis allapot (2026-09-07)

- **Eles/teszt hosting**: Fly.io, app nev `unas-loyalty-middleware`
  (`unas-loyalty-middleware.fly.dev`). Render.com-rol koltoztettuk at, mert a
  Render szerverei tartosan nem ertek el a UNAS API-t (lasd
  KNOWN_LIMITATIONS.md).
- **Adatbazis**: Render Postgres (kulon, tartos szolgaltatas, nem fugg a
  webalkalmazas hostingjatol - a Fly.io elhagyasa onmagaban NEM erinti). Ha
  majd VPS-re koltoztok es ott sajat Postgres-t vezettek be (nem kotelezo,
  de ajanlott, hogy ne fuggjetek kulso szolgaltatotol), a meglevo adatokat
  `pg_dump`/`pg_restore`-ral at KELL masolni - lasd VPS_ATALLAS.md 2.3, ahol
  mar konkret, futtathato parancsok is vannak hozza.
- **NYITOTT**: egyedi domain (`huseg.trendidivat.hu` - VIGYAZAT, korabban
  tevesen `hutseg` volt dokumentalva egy elirassal, mar javitva) bevezetese
  folyamatban a Fly.io-n, hogy a telefonos QR-beolvasas linkkent ismerje fel
  az URL-t. Tanusitvany felveve, DNS meg nincs megerositve. Reszletek es a
  hatralevo lepesek (APP_BASE_URL, UNAS webhook URL, `main.cfg` payload_prefix
  frissitese) a KNOWN_LIMITATIONS.md tetejen.
- Nincs egyidejuleg tobb alkalmazaspeldany/worker - lasd
  ARCHITECTURE_DECISIONS.md 3-4. pont.

## Munkafolyamat ebben a repoban

```powershell
.venv\Scripts\Activate.ps1
pytest -q                 # mindig futtasd valtoztatas utan
uvicorn loyalty_app.main:app --reload   # helyi ellenorzeshez
```

- Uzleti logika a `loyalty/service.py`-ba kerul, NEM a route-fajlokba - lasd
  docs/DEVELOPMENT.md 3.1-3.2.
- Uj `DateTime` oszlopnal mindig a `models.py`-ban levo `_TZ_DATETIME`
  konstanst hasznald (`DateTime(timezone=True)`) - a csupasz `DateTime`
  korabban mar okozott eles Postgres-hibat SQLite-on nem reprodukalhato
  modon (lasd KNOWN_LIMITATIONS.md, 2026-09-04-es bejegyzes).
- UNAS-hivas mindig `unas/client.py::UnasClient`-en keresztul, XML-t mindig
  `xml_utils.py` builderrel (soha string-osszefuzessel - XXE/escaping kockazat).
- Teszteles kizarolag mockolt UNAS klienssel (`tests/fake_unas.py`) vagy
  respx-mockolt HTTP-vel - automatizalt tesztbol soha ne hivj valodi UNAS API-t.
- Commit/push elott: `pytest -q` zold, es ha migraciot irtal, `alembic upgrade
  head` friss adatbazison hiba nelkul lefusson.

## Git / commit szokasok

- Ertelmes, angol vagy magyar commit uzenet, a valtoztatas OKAT is irja le,
  nem csak a mit-et.
- `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>` sorral zarva.
- Csak akkor push-olj, ha a user kifejezetten keri vagy a munkafolyamat resze
  (ebben a projektben eddig mindig push-oltunk a valtoztatasok utan).
