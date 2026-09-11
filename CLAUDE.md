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

## Aktualis allapot (2026-09-08)

- **Eles/teszt hosting**: Fly.io, app nev `unas-loyalty-middleware`
  (`unas-loyalty-middleware.fly.dev`). Render.com-rol koltoztettuk at, mert a
  Render szerverei tartosan nem ertek el a UNAS API-t (lasd
  KNOWN_LIMITATIONS.md). **A Fly.io trial VEGLEGESEN lejart (2026-09-08)** -
  minden `fly deploy`/`fly secrets set` "trial has ended" hibat ad, amig
  fizetesi modot nem adnak hozza VAGY meg nem tortenik a VPS-koltozes
  (Sybell.hu). Emiatt a Fly.io-n MEG A REGI (teszt UNAS-bolti) ertekek
  vannak beallitva - lasd KNOWN_LIMITATIONS.md.
- **Adatbazis**: Render Postgres (kulon, tartos szolgaltatas, nem fugg a
  webalkalmazas hostingjatol - a Fly.io elhagyasa onmagaban NEM erinti). Ha
  majd VPS-re koltoztok es ott sajat Postgres-t vezettek be (nem kotelezo,
  de ajanlott, hogy ne fuggjetek kulso szolgaltatotol), a meglevo adatokat
  `pg_dump`/`pg_restore`-ral at KELL masolni - lasd VPS_ATALLAS.md 2.3, ahol
  mar konkret, futtathato parancsok is vannak hozza.
- **UNAS: atallas a TESZT boltrol (webaruhazmester01.unas.hu) a VALODI eles
  boltra (trendidivat)** (2026-09-08): uj `UNAS_API_KEY`, uj
  `UNAS_LOYALTY_PARAM_ID` (6599411), uj `UNAS_WEBHOOK_HMAC_SECRET` - lasd
  helyi `docs/VPS_HANDOFF_SECRETS.md` (NEM git-ben). A `customer_registration`
  webhook be van allitva a valodi boltra a UNAS adminban, de a Fly.io
  felfuggesztese miatt jelenleg nem eri el a szervert - lasd
  KNOWN_LIMITATIONS.md.
- **9560 "engedelyezett" vasarlonak MAR VAN tokenje** (2026-09-08): egy
  egyszeri, UNAS Excel-import-alapu modszerrel toltottuk fel oket
  (`loyalty_customers` tabla kozvetlen feltoltese + UNAS-oldali tomeges
  parameter-import), NEM API-hivasokkal, mert az API-n keresztuli feltoltes
  tullepte volna a UNAS VIP 6000 hivas/ora limitjet. Lasd
  KNOWN_LIMITATIONS.md a modszer reszleteivel, ha kesobb ujra kell ilyet
  csinalni.
- **NYITOTT**: egyedi domain (`huseg.trendidivat.hu` - VIGYAZAT, korabban
  tevesen `hutseg` volt dokumentalva egy elirassal, mar javitva) bevezetese
  a Fly.io-n. Tanusitvany kesz es hitelesitve, `APP_BASE_URL` es a UNAS
  webhook URL is atallitva mar (a valodi boltra) - a `main.cfg`
  payload_prefix VALODI BOLTRA valo atallitasa meg ellenorizendo, es a
  telefonos vegponti teszt (linkkent ismeri-e fel a kamera) meg nem
  igazolhato, amig a Fly.io app felfuggesztve van. Reszletek a
  KNOWN_LIMITATIONS.md tetejen.
- **Uzleti szabalyok vegleg beallitva (2026-09-08)**: 1 pont = 1 Ft, jovairas
  a brutto vasarlas 0,5%-a, beváltás egy tranzakcioban legfeljebb a rendeles
  vegosszegenek 0,5%-a lehet. Ez utobbihoz uj config (`LOYALTY_REDEMPTION_MAX_
  PERCENT_OF_ORDER`) es uj UI-mezo (vasarlas vegosszege a beváltás dobozban)
  kellett - lasd ARCHITECTURE_DECISIONS.md 5. pont.
- Fontos tapasztalat: a Fly.io "personal" org trial-korlat miatt mar egyszer
  **"suspended"** allapotba kerult az egesz app (nem csak autostop miatti
  "stopped" gepallapot) - ha `fly apps list` "suspended"-et mutat, az
  fizetesi-mod/trial kerdes a Fly dashboardon (Billing), nem kodhiba.
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


2026-09-11: A fix pontplafon megszunt (LOYALTY_REDEMPTION_MAX_POINTS_PER_TX=0). A 10 000 Ft-os bevaltasi osszeghatart a bolt manualisan kezeli.
