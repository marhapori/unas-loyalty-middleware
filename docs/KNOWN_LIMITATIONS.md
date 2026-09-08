# Ismert korlatok es eles indulas elotti teendok

## NYITOTT (2026-09-07): egyedi domain (huseg.trendidivat.hu) bevezetese folyamatban

**Elozmeny (2026-09-06)**: egy elado telefonjan (Android, MIUI-alapu
kameraapp) a beolvasott `https://unas-loyalty-middleware.fly.dev/scan/...`
QR-kodot a kamera "Szoveg"-kent (nem "Link"-kent) ismerte fel - nem lehetett
kozvetlenul megnyitni bongeszoben, csak masolni/beilleszteni a kasszafelulet
kezi beviteli mezojebe (ezt a `loyalty_app/loyalty/qr.py::extract_token()`
mar korabban is tamogatta ket formatum elfogadasaval). Felteveses ok: a
`.dev` egy ujabb/kevesbe elterjedt TLD, amit nehany telefon beepitett
URL-felismero regex-e nem ismer fel automatikusan. Vegleges megoldaskent egy
sajat, ismerosebb TLD-vel rendelkezo aldomaint vezetunk be - lasd lent.

Allapot (frissitve 2026-09-07 este):

- A Fly.io-n **letrehozva es HITELESITVE** a tanusitvany
  `huseg.trendidivat.hu`-ra (Let's Encrypt, `fly certs check` szerint
  "Issued"/"verified"). `https://huseg.trendidivat.hu/health/live` es
  `/login` is HTTP 200-at ad.
  **FIGYELEM**: korabban tevesen `hutseg.trendidivat.hu` (extra "t" betuvel)
  lett felveve es dokumentalva - ez a hibas tanusitvany torolve lett, a
  helyes `huseg.trendidivat.hu` valtotta fel. Ha barhol meg `hutseg`-et
  latsz (regi jegyzet, kepernyokep, UNAS-beallitas), az elirasnak szamit.
- Kozben az is kiderult, hogy a Fly.io "personal" org meg **trial
  (probaidoszak)** alatt volt, ami eroforras-korlatot szab - ezt egyszer at
  is lepte az app, es a Fly a teljes appot **"suspended"** allapotba tette
  (ettol nem mukodott sem a sima `fly.dev` cim, sem a cert-hitelesites).
  Fizetesi mod hozzaadasaval (Fly dashboard -> Billing -> "Add Payment
  Method") ez megszunt, az app visszaallt "deployed"/"started" allapotba.
  Ha a jovoben ujra "suspended" allapotot latsz a Fly dashboardon, eloszor
  itt nezz szet, nem a kodban.
- DNS-rekordok (mar bealitva, mukodik):
  ```
  A    huseg.trendidivat.hu -> 66.241.125.247
  AAAA huseg.trendidivat.hu -> 2a09:8280:1::184:fa8:0
  ```

**Hatralevo lepesek** (meg a VPS-re koltozestol fuggetlenul, meg mig Fly.io-n
fut az app):

1. ✅ Fly.io `APP_BASE_URL` secret atallitva `https://huseg.trendidivat.hu`-ra
   (`fly secrets set APP_BASE_URL=... --app unas-loyalty-middleware`,
   elvegezve 2026-09-07-en, mindket gep sikeresen ujrainditva vele).
2. ✅ UNAS admin feluleten (a VALODI, eles boltnal) a `customer_registration`
   webhook URL-je beallitva -> `https://huseg.trendidivat.hu/webhooks/unas/
   customer-registration`, uj HMAC-titokkal (lasd VPS_HANDOFF_SECRETS.md).
   **DE**: a Fly.io app kozben felfuggesztve van (lasd lent, uj bejegyzes),
   szoval ez a webhook jelenleg NEM eri el a szervert - a beallitas kesz, a
   tenyleges mukodes meg nincs igazolva.
3. ⬜ UNAS sablon `main.cfg` `payload_prefix` erteke -> `https://huseg.
   trendidivat.hu/scan/` A VALODI BOLTNAL - ezt meg nem erositettuk meg
   ebben a beszelgetesben (korabban a teszt boltnal mar elvegeztuk, de az
   most mar nem releváns, mert athelyeztuk a beallitast az eles boltra).
   **Ellenorizendo/elvegezendo.**
4. ⬜ Teljes vegponti teszt: uj vasarlo regisztracio -> webhook -> QR a
   profilban -> eladoi telefon kamerajaval beolvasva mar **linkkent**
   ismeri-e fel. Ez csak azutan vegezheto el, hogy a Fly.io app ujra elerheto
   (lasd lent) VAGY mar a VPS-en fut.

**UJ (2026-09-08): a valodi elesboltra allas kozben derult ki, hogy a Fly.io
trial VEGLEGESEN lejart** ("trial has ended" hiba minden `fly secrets
set`/`fly deploy` probalkozasnal) - nem csak resource-korlat-tuli
"suspended" allapot, mint korabban, hanem tartos leallas, amig fizetesi
modot nem adtok hozza VAGY at nem koltoztok VPS-re. Emiatt a most beallitott
uj UNAS-ertekek (`UNAS_API_KEY`, `UNAS_LOYALTY_PARAM_ID`,
`UNAS_WEBHOOK_HMAC_SECRET` - lasd VPS_HANDOFF_SECRETS.md) csak a HELYI
`.env`-ben es az atadasi dokumentumban vannak frissitve, a Fly.io-n MEG A
REGI, TESZT-BOLTI ertekek allnak. Ha a Fly.io app ujra elerhetove valik,
ELOSZOR ezt a harom valtozot kell ott is frissiteni.

**UJ (2026-09-08): 9560 "engedelyezett" vasarlonak mar van tokenje** - ezt
NEM a webhookon/API-n keresztul, hanem egy egyszeri, UNAS Excel-import-alapu
modszerrel poldottuk meg (lasd a beszelgetes tortenete, vagy kerdezd meg az
uzemeltetot), mert 9560 vasarlo API-n keresztuli feltoltese (kb. 19 000
hivas) tullepte volna a UNAS VIP csomag 6000 hivas/ora/IP limitjet (lasd
UNAS_API_gyakorlati_utmutato.md 11. fejezet). Ha kesobb ujra kell ilyen
tomeges backfill-t vegezni (pl. meg tobb "engedelyezett" vasarlo kerul fel),
ugyanezt a modszert erdemes ismetelni, NEM a sima `backfill-customers`
parancsot nagy tetelszamra.

Lasd meg [VPS_ATALLAS.md](VPS_ATALLAS.md) 2.7. pontja: ha a domain a
VPS-koltozes utan is `huseg.trendidivat.hu` marad, a fenti 2-3. pontot **nem**
kell ujra elvegezni, csak a DNS A/AAAA rekordot kell az uj szerver IP-jere
atirni.

## MEGOLDVA (2026-09-06): mobil nezet elcsuszasa es ismetlodo bejelentkezes

Ket kulon hiba jelentkezett a telefonon hasznalt kasszafeluleten:

1. **Mobil nezet elcsuszott/tulcsordult**: a kasszafelulet fooszlopa
   (`.layout`) es a jovairas/bevaltas dobozok (`.op-grid`) fixen ket
   oszlopban voltak megjelenitve CSS-ben, media query nelkul - keskeny
   telefonon ez osszepreselodest/oldalirányú tulcsordulast okozott. Javitva
   egy 720px-es breakpoint-tal (`static/styles.css`), ami alatt a fooszlop,
   a ket muvelet-doboz es a login-kartya is egy oszlopba rendezodik.
2. **Az elado telefonja minden QR-beolvasasnal ujra bejelentkezest kert**:
   a session-cookie `SameSite=Strict`-tel volt beallitva. Amikor a QR-t a
   telefon kamerajaval/kulon QR-olvaso appal olvastak be es a link onnan
   nyilt meg a bongeszoben, ez a bongeszo szemeben egy masik appbol jovo
   (cross-site) navigacio - a `Strict` cookie-t ilyenkor a bongeszo nem
   kuldte el, igy minden beolvasas uj bejelentkezest kenyszeritett ki.
   Javitva: a cookie `SameSite=Lax`-ra allitva (`main.py`), kifejezett
   30 napos `max_age`-dzsel. A CSRF-vedelmet ez nem gyengiti, mert az eleve
   nem a SameSite-attributumra tamaszkodik, hanem egyedi header + Origin-
   ellenorzesre (lasd `api/deps.py` `verify_same_origin` es
   [ARCHITECTURE_DECISIONS.md](ARCHITECTURE_DECISIONS.md) 7. pont).

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
