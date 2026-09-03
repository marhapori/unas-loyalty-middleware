# Ismert korlatok es eles indulas elotti teendok

## Amit valos UNAS API-kulccsal meg ellenorizni kell

1. **`getCustomer` keres gyokerelem**: a `getProduct`/`getOrder` mintajara
   `<Params>` gyokerelemet feltetelezunk a `getCustomer` keresnel (lasd
   `loyalty_app/unas/xml_utils.py` tetejen levo megjegyzest). A hivatalos
   dokumentacio (`getCustomer keres` oldal) felsorolja a szuromezoket, de nem
   mutat teljes pelda-XML-t. A `getCustomer` **valasz** szerkezetet, a
   `setCustomer` keres/valasz szerkezetet es a login valasz mezoit viszont **elo
   dokumentaciobol ellenoriztuk** 2026-09-03-an (lasd az XML builderek/parserek
   docstringjeit) - ezek nagy biztonsaggal helyesek.
2. **Auth-hiba HTTP-statusza**: a `UnasClient` 401/403 HTTP-statuszt kezel
   hitelesitesi hibakent (es ekkor egyszer ujra-bejelentkezik). A gyakorlati
   utmutato szerint az altalanos hibak jellemzoen HTTP 400 + `<Error>` XML-t
   adnak - nem biztos, hogy a lejart/hibas token kulon 401-et kap. Ha az elso
   valodi teszt azt mutatja, hogy a lejart token is 400-at ad, a
   `unas/client.py` `_post_once` fuggvenyet kell ehhez igazitani (a hibauzenet
   szovege alapjan).
3. **`customer_registration` webhook payload szerkezete**: nincs hivatalos
   pelda. A `loyalty_app/loyalty/webhook_adapter.py` tobb elterjedt
   mezonev-mintat probal (`Id`, `CustomerId`, `Customer.Id` stb.), es ha
   egyiket sem talalja, `webhook_events.process_status='needs_review'`-ra
   allitja az esemenyt es elmenti a (maszkolt) nyers payloadot admin
   attekintesre. **Az elso valodi webhook utan ellenorizd ezt a tablat, es
   sziikseg eseten egeszitsd ki az adaptert.**
4. **`getCustomer` valasz uzleti mezoi**: a `PointsAccount.Balance` `float`
   tipusu a UNAS adatszerkezetben, bar a peldak egesz ertekeket mutatnak. A
   kod `int()`-tel kerekit lefele hiba nelkul, de ha a valosagban tizedes
   pontertekek is elofordulnanak, ezt at kell gondolni (jelenleg a
   specifikacio es minden pelda egesz pontokat felteteleez).

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
- Nincs valodi UNAS API-kulccsal vegzett teszt ebben a fejlesztesi korben -
  ezt az elso eles/staging UNAS-kulccsal el kell vegezni a
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
