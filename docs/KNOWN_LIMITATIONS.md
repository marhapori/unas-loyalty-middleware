# Ismert korlatok es eles indulas elotti teendok

## 2026-09-04: datetime naive/aware hiba Postgresen (megtalalva es javitva)

Miutan a Render Web Service-t SQLite-rol Postgresre allitottuk at (lasd lent),
a hatterworker minden iteracioban elszallt:
`TypeError: can't compare offset-naive and offset-aware datetimes` a
`webhook_events.next_attempt_at` mezo osszehasonlitasanal. Ok: a modellek
`datetime` oszlopai nem voltak explicit idozona-tudatosra jelolve
(`DateTime(timezone=True)`) - SQLite-on ez sosem okozott hibat (a hattér
sosem kenyszeritette ki a kulonbseget azon a kodutant, amit teszteltunk), de
Postgresen a `TIMESTAMP WITHOUT TIME ZONE` oszlop naiv datetime-ot ad vissza,
ami a `datetime.now(timezone.utc)`-val valo osszehasonlitasnal elszallt.

Javitva: minden datetime oszlop explicit `DateTime(timezone=True)` tipust
kapott (`models.py`), uj migracio (`de2c0497de17`) allitja at a meglevo
oszlopokat, es a `worker.py` osszehasonlitasa vedelmi normalizalast is kapott
(`_aware()`), ugyanazt a mintat kovetve, amit a `service.py` mar korabban is
hasznalt egy hasonlo helyen. Regressziosteszt: `tests/test_worker.py`.

**Tanulsag**: a SQLite-alapu helyi tesztelés nem fedi le teljesen a Postgres
viselkedeset ezen a teruleten - ha kesobb tovabbi datetime-osszehasonlitast
irunk kodban, mindig `DateTime(timezone=True)` oszloptipust hasznaljunk, es
kerdojelezzuk meg, ha egy DB-bol olvasott datetime-ot kozvetlenul
osszehasonlitunk egy Python-oldali `datetime.now(...)`-val.

## Megoldott: veletlen teszt-adminfiok

A `/api/admin/bootstrap` vegpont egyik diagnosztikai teszthivasa kozben
(2026-09-03) veletlenul letrejott egy `x` felhasznalonevu adminfiok a teszt
SQLite adatbazisban. Idokozben ez a teljes adatbazissal egyutt megszunt (lasd
lent, "Render Postgres hasznalata") - nincs teendo, csak dokumentacios
nyomkent hagyva itt.

## 2026-09-03: elso eles UNAS-teszt eredmenye

Valodi UNAS API-kulccsal es egy valodi teszt webshoppal (`webaruhazmester01.unas.hu`)
elvegeztuk az elso vegponti tesztet (ngrok-alagutas webhook + kozvetlen
API-hivasok). Eredmeny:

- ✅ **HMAC webhook-alairas ellenorzes** valodi UNAS-alairassal helyesen mukodik.
- ✅ **`getCustomer` keres `<Params>` gyokerelem-feltetelezes beigazolodott** -
  valodi `Id` szuro es lapozas is helyesen mukodott.
- ✅ **`getCustomer` valasz feldolgozas** (`Contact/Name`, `Email`,
  `PointsAccount/Balance`, `Params/Param`) helyesen mukodik eles adaton.
- ✅ **`setCustomer` token-visszairas** ténylegesen megtortent es fuggetlen
  visszaolvasassal is megerositve.
- 🔧 **Talalt es javitott hiba**: a valodi `customer_registration` webhook JSON
  teste a vasarlo-azonositot a top-level **`customerID`** kulcs alatt kuldi
  (nem `Id`/`CustomerId`/stb., ahogy korabban feltetelezve volt). A
  `loyalty_app/loyalty/webhook_adapter.py` `_CANDIDATE_PATHS` listaja mar
  frissitve lett a valodi mezonevvel, es a docstringje tartalmazza a teljes
  valodi payload-peldat. A hiba a tervezett vedohalonak koszonhetoen semmilyen
  adatvesztest nem okozott - az esemeny `needs_review` allapotba kerult,
  utana a javitott kod ujra sikeresen feldolgozta.

## Amit valos UNAS API-kulccsal meg ellenorizni kell

1. **Auth-hiba HTTP-statusza**: a `UnasClient` 401/403 HTTP-statuszt kezel
   hitelesitesi hibakent (es ekkor egyszer ujra-bejelentkezik). A gyakorlati
   utmutato szerint az altalanos hibak jellemzoen HTTP 400 + `<Error>` XML-t
   adnak - nem biztos, hogy a lejart/hibas token kulon 401-et kap. Ezt meg nem
   volt modunk kulon tesztelni (a login mindvegig sikeres volt a teszt soran).
   Ha egy kesobbi futasnal azt tapasztaljatok, hogy a lejart token is 400-at
   ad, a `unas/client.py` `_post_once` fuggvenyet kell ehhez igazitani (a
   hibauzenet szovege alapjan).
2. **`getCustomer` valasz uzleti mezoi**: a `PointsAccount.Balance` `float`
   tipusu a UNAS adatszerkezetben - ezt eles teszt is megerositette (pl.
   `50.0` ertekkel terve vissza). A kod `int()`-tel kerekit lefele hiba
   nelkul; ha tizedes pontertekek is elofordulnanak, ezt at kell gondolni.

## Szandekosan nem implementalt (kesobbi fazis)

- **POS-integracio**: a specifikacio is kulon, 2. fazisnak jeloli. Jelenleg
  csak osszegalapu, kezi pontszamitas van a kasszafeluleten.
- **Termek/SKU-alapu pontozas**: POS-adat nelkul nem elerheto.
- **UNAS-megrendeles letrehozasa fizikai vasarlasbol**: csak a
  `PointsAccount.Balance` modosul, nem keletkezik UNAS-rendeles.
- **Uj vasarlok polling-alapu (nem webhook) szinkronja**: mivel a bolt VIP
  csomaggal rendelkezik, a webhook a fo utvonal. Ha a csomag Premiumra
  valtana, a `backfill-customers` parancsot kellene rendszeresen (cronnal)
  futtatni ehelyett - ez mar ma is mukodik, csak nem automatikus/utemezett.
- **Tobb egyidejű alkalmazaspeldany/worker**: lasd
  [ARCHITECTURE_DECISIONS.md](ARCHITECTURE_DECISIONS.md) 3-4. pont - SQLite +
  in-process worker mellett csak egy peldany futhat biztonsagosan. Postgres-re
  valtva ez a korlat megszunik.

## Tesztelesi korlatok

- Az automatizalt tesztek (`pytest`, 70+ teszt) a service reteget es a
  UNAS-klienst mockolt/respx-elt HTTP-vel tesztelik, **nem** valodi UNAS API
  ellen. A HTTP route-reteg (bejelentkezes, CSRF, rate limit, session) elesben,
  bongeszoben lett manualisan vegigtesztelve egy helyi mock UNAS-szerver ellen
  (lasd fejlesztoi jegyzetek), de nincs hozza automatizalt integraciós teszt.
- Valodi UNAS API-kulccsal es egy valodi teszt webshoppal mar tortent egy
  vegponti teszt (lasd fent, 2026-09-03), de csak egyetlen teszt vasarlon: uj
  vasarlo regisztracioja -> webhook -> tokenkiosztas. A jovairas/bevaltas
  folyamatot (setCustomer PointsAccount.Balance-szal) meg NEM tesztelte
  senki valodi UNAS-on, csak a mock szerverrel es a service-szintu tesztekkel
  - ezt erdemes a kovetkezo lepesben elvegezni a
  [UNAS_SETUP.md](UNAS_SETUP.md) "Ellenorzes" szakasza szerint, mielott
  eles vasarlokon hasznaljatok.
- A QR-olvaso hardveres viselkedese (USB HID billentyuzet-emulacio) nem
  tesztelheto automatan - a `loyalty_app/loyalty/qr.py` logika feltetelezi,
  hogy a scanner a beolvasott szoveg vegen Entert kuld, ahogy a specifikacio
  is leirja.

## Biztonsagi megjegyzesek

- A kasszafelulet a QR-tokent (a beolvasott ertek) a bongeszo JS-memoriajaban
  tartja a kijelolt vasarlo interakcioja alatt (hogy tovabb tudja kuldeni az
  earn/redeem hivasokkal) - soha nem jelenik meg a felhasznaloi feluleten vagy
  URL-ben, de tovabbra is a kliens oldalon van jelen egy rovid ideig. Egy
  szigorubb tovabbfejlesztes egy rovid elettartamu, szerveroldali "scan
  session" azonositot adhatna vissza a QR-token helyett - ez jelenleg nincs
  implementalva.
- A `SESSION_SECRET` es a UNAS-titkok `.env`-ben vannak, sose Gitben - a
  `.gitignore` mar kizarja a `.env` fajlt.
