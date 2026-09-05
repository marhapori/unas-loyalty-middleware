# Ismert korlatok es eles indulas elotti teendok

## MEGOLDVA: Render -> UNAS kapcsolati blokk (2026-09-04/05)

**Frissites (2026-09-05)**: 24+ ora varakozas utan a blokk tovabbra is
fennallt a Render-en (tehat nem az 1 oras login-limit tiltas volt), es a
sajat gepunkrol tovabbra is mukodott a UNAS-kapcsolat - ez megerositette,
hogy IP/szolgaltato-specifikus blokkrol van szo. **Athelyeztuk a webalkalmazast
Fly.io-ra** (lasd [DEPLOYMENT.md](DEPLOYMENT.md), "Fly.io" fejezet) - onnan
azonnal, hibatlanul (0.5 masodperc alatt) mukodott ugyanaz a UNAS-hivas,
ugyanazzal az API-kulccsal es adatbazissal. Ez vegleg kizarja, hogy a kodunk,
az API-kulcsunk vagy a UNAS altalanos elerhetosege lett volna a problema -
kifejezetten a Render (Frankfurt regios) kiszolgaloi IP-tartomanya volt
erintett.

**UNAS ugyfelszolgalat is megkeresve** a Render IP-cim (74.220.51.139)
blokkolasaval kapcsolatban - valasz meg nem erkezett. Ha felszabadul a blokk,
a Render visszaallithato lenne (lasd DEPLOYMENT.md), de nincs surgeto ok ra,
mivel a Fly.io stabilan mukodik.

Eredeti hibaleiras (tortenei referenciakent megtartva):

Aznap kesobb, miutan a fenti datetime-hibat javitottuk, kiderult egy sulyosabb
gond: **a Render szerverekrol induló hivasok a UNAS API fele nem kapnak
valaszt** (90+ masodpercig fuggnek, majd idotullepessel elszallnak), miközben:

- a sajat gepemrol (helyi teszteles) a UNAS API mindvegig elerheto volt;
- korabban, ugyanezen a napon, a Render-rol induló hivasok (jovairas/bevaltas/
  visszavonas tesztek) sikeresen mukodtek - tehat ez **nem** eleve fennallo,
  strukturalis blokk volt, hanem valamikor kozben kezdodott.

Lehetseges okok (nincs megerositve):
- a UNAS (vagy elotte egy WAF/CDN) IP-alapon blokkolta a Render kiszolgalo
  IP-jet, esetleg a login-vegpont szigoru (5 sikertelen/ora) limitjenek
  tulzott elerese miatt (lasd a masik, mar javitott bug lehetseges kapcsolatat:
  a datetime-hiba miatt a worker crash-loopolt, bar ez kozvetlenul NEM hivta
  ujra a UNAS-t minden ciklusban - lasd `worker.py` `process_pending_webhooks`
  logika, a crash a UNAS-hivas ELOTT tortent);
- atmeneti UNAS-oldali vagy halozati/routing problema, ami epp egybeesett
  a Render forgalommal.

**Ideiglenes workaround, amit ma hasznaltunk**: a Render Postgres adatbazis
**External Database URL**-jevel kozvetlenul, a fejlesztoi gepunkrol csatlakozva
(psycopg-vel) es a sajat, mukodo UNAS-kapcsolatunkkal manualisan futtattuk le
az `issue_token_for_customer` fuggvenyt egy elakadt teszt-vasarlora. Ez NEM
skalazhato/eles megoldas - csak egyszeri hibaelharitasra jo.

**Kovetkezo lepesek, mielott eles vasarlokon hasznaljatok a rendszert:**
1. Varjunk (a felhasznalo dontese szerint) es probaljuk ujra par ora/nap mulva,
   hatha idokozben magatol felszabadul (pl. ha ez egy ideiglenes UNAS-oldali
   automatikus tiltas volt).
2. Ha tartosan fennall, vegyuk fel a kapcsolatot a UNAS ugyfelszolgalattal:
   blokkolva van-e a Render IP-tartomanya (Frankfurt regio), es fel tudjak-e
   oldani/engedelyezni azt.
3. Ha a UNAS strukturalisan/tartosan blokkolja a Render IP-tartomanyat, masik
   hosting szolgaltatot (pl. Railway, VPS mas IP-tartomannyal) kell
   fontolora venni.
4. **Eles hasznalat elott kotelezo egy vegponti teszt** (jovairas/bevaltas a
   Render-appon keresztul, nem kozvetlen sajat gepi hozzaferessel), ami
   igazolja, hogy a Render->UNAS kapcsolat stabilan mukodik.

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
