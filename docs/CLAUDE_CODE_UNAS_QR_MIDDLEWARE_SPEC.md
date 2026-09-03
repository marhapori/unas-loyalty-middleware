# Claude Code feladatleírás – UNAS QR-alapú bolti hűségpont middleware

## Szerep és cél

Egy külső, biztonságos webalkalmazást/middleware-t kell megtervezned és megvalósítanod, amely összeköti:

1. a fizikai üzletben használt QR-kód-olvasót vagy kasszai böngészőt;
2. az alkalmazás saját adatbázisát és tranzakciónaplóját;
3. az UNAS vásárlói API-ját.

A vásárló az UNAS-profiljában megjelenő QR-kódot mutatja fel. A pénztáros beolvassa, az alkalmazás azonosítja a vásárlót, megmutatja az aktuális UNAS pontegyenleget, majd jogosultság és megerősítés után pontot ír jóvá vagy von le.

A meglévő UNAS-sablon már működik. A profiloldalon a QR tartalma:

```text
unas-loyalty:v1:<opaque-token>
```

A token UNAS vásárlói paraméterének azonosítója jelenleg:

```text
6590861
```

A jelenlegi `TEST-LOYALTY-0001` érték kizárólag kézi tesztelésre szolgál; éles tokenként nem használható.

## Kötelező előzetes felderítés

Mielőtt jelentős kódot írsz:

1. Vizsgáld meg a repository teljes tartalmát, a meglévő technológiai stacket és az esetleges korábbi WordPress-integrációból származó fájlokat.
2. Keresd meg az esetleges `.env.example`, Docker, deployment, adatbázis, webhook, UNAS API, QR, loyalty, points, POS és WordPress nyomokat.
3. Ne írj felül meglévő működést, migrációt vagy felhasználói változtatást.
4. Készíts rövid megvalósítási tervet, és jelöld meg a még hiányzó üzleti döntéseket.
5. Ha elérhetővé válik a régi WordPress-rendszer forrása vagy dokumentációja, először térképezd fel, mi hasznosítható újra. Ne tervezz újra indokolatlanul egy már bizonyított folyamatot.

Ha nincs meglévő alkalmazáskód, javasolt alapstack:

- TypeScript és Node.js;
- PostgreSQL;
- egyszerű reszponzív belső webes kasszafelület;
- háttérfeladat-kezelés tartós queue/outbox megoldással;
- Docker-alapú futtatás;
- automatizált tesztek és adatbázis-migrációk.

Más, már használt és karbantartható stack megtartható. A helyes működés fontosabb, mint a konkrét framework.

## Külső rendszerek és hivatalos dokumentáció

Az UNAS API:

- HTTPS-alapú;
- XML kéréseket és válaszokat használ;
- minden művelet POST kérés;
- alap URL-je `https://api.unas.eu/shop/`;
- PREMIUM és VIP csomaggal használható;
- API-login után kapott tokent igényel.

Hivatalos dokumentáció:

- API áttekintés: https://unas.hu/tudastar/api
- Login: https://unas.hu/tudastar/api/azonositas-login-keres
- Vásárlók: https://unas.hu/tudastar/api/vasarlok
- getCustomer: https://unas.hu/tudastar/api/vasarlok-getCustomer-keres
- Vásárlói adatszerkezet: https://unas.hu/tudastar/api/vasarlok-adatszerkezet
- Vásárlói példák: https://unas.hu/tudastar/api/vasarlok-peldak
- Automata folyamatok: https://unas.hu/tudastar/api/automata-folyamatok
- Webhook ellenőrzés: https://unas.hu/tudastar/api/automata-folyamatok-webhook-ellenorzes

Az implementáció előtt ellenőrizd a dokumentáció aktuális mezőit és limitjeit. Ne feltételezz nem dokumentált JSON API-t vagy atomi pontegyenleg-növelő végpontot.

## Funkcionális követelmények

### 1. QR-token létrehozása új vásárlóknál

Elsődleges, VIP csomag esetén használható folyamat:

1. Az UNAS `customer_registration` eseményhez webhook művelet tartozik.
2. Az UNAS POST kérést küld a middleware publikus HTTPS webhook végpontjára.
3. A middleware a nyers request body és az `X-UNAS-HMAC` fejléc alapján ellenőrzi a webhook HMAC-SHA256 aláírását.
4. Az eseményt tartósan rögzíti, duplikáció ellen védi, majd gyorsan `2xx` választ ad.
5. Háttérfeladatban meghatározza az UNAS vásárló-ID-t. Ne feltételezd a webhook payload pontos szerkezetét: készíts izolált adaptert, és a valós UNAS tesztpayload alapján véglegesítsd.
6. Lekéri a vásárlót `getCustomer` segítségével.
7. Ha a `6590861` paraméternek már van érvényes tokenje, nem generál újat.
8. Ha nincs, kriptográfiailag biztonságos, legalább 128 bit entrópiájú opaque tokent generál.
9. `setCustomer` `modify` művelettel beírja a tokent a `6590861` vásárlói paraméterbe.
10. A saját adatbázisban eltárolja a token hashét és az UNAS vásárló-ID kapcsolatát.

Javasolt tokenforma:

```text
L1_<base64url-encoded-random-128-bit-value>
```

Példa:

```text
L1_5QvNRt2X8mK4zY7pBc9DfA
```

Ne kerüljön a tokenbe e-mail-cím, név, telefonszám, nyers UNAS-ID vagy növekvő sorszám.

Példa visszaírásra:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Customers>
  <Customer>
    <Action>modify</Action>
    <Id>41704472</Id>
    <Params>
      <Param>
        <Id>6590861</Id>
        <Value><![CDATA[L1_5QvNRt2X8mK4zY7pBc9DfA]]></Value>
      </Param>
    </Params>
  </Customer>
</Customers>
```

Alternatíva, ha a regisztrációs webhook nem elérhető:

- időzített szinkron `getCustomer` hívásokkal;
- `RegTimeStart`/`RegTimeEnd` időablak használata;
- néhány perces átfedés az időablakok között;
- tartós cursor/high-water mark;
- üres `6590861` paraméterrel rendelkező vásárlók idempotens feldolgozása.

Ne kizárólag memóriában tartsd az utolsó szinkronidőt. Újraindítás vagy hiba után se maradhasson ki vásárló.

### 2. Meglévő vásárlók backfillje

Legyen adminisztrátori vagy CLI művelet, amely:

1. lapozva lekéri a meglévő UNAS-vásárlókat;
2. megkeresi azokat, akiknél a `6590861` paraméter üres;
3. egyedi tokeneket generál;
4. az UNAS limiteket betartva visszaírja az értékeket;
5. folytatható, idempotens és biztonságosan újrafuttatható;
6. számlálókat és hibajelentést ad: feldolgozott, létrehozott, kihagyott, sikertelen.

Legyen `dry-run` mód, amely nem ír az UNAS-ba.

### 3. QR-kód beolvasása a boltban

Az elsődleges bemeneti eszköz USB-s vagy Bluetooth-os QR-olvasó, amely billentyűzetként működik. A felület:

- automatikusan fókuszáljon a beolvasó mezőre;
- kezelje a scanner által küldött Entert;
- vágja le a whitespace karaktereket;
- kizárólag a `unas-loyalty:v1:` prefixet fogadja el;
- validálja a token formátumát és maximális hosszát;
- ne keressen részleges tokenre;
- ugyanazt a gyors beolvasást ne dolgozza fel többször;
- hibás tokennél ne jelenítsen meg vásárlói adatot.

Sikeres beolvasás után jelenjen meg:

- vásárló megjelenítendő neve;
- aktuális UNAS pontegyenleg;
- token maszkolt vége vagy rövid kártyaazonosító;
- jóváírás és beváltás indítására szolgáló művelet;
- egyértelmű állapotjelzés: betöltés, siker, hiba, ismételt tranzakció.

A teljes token ne jelenjen meg a kasszásnak, URL-ben vagy naplóban.

### 4. Pontjóváírás

A jóváírási folyamat:

1. QR beolvasása.
2. Vásárló azonosítása a saját token-hash táblából.
3. Friss vásárlói adat és egyenleg lekérése az UNAS-ból.
4. Nyugta/tranzakció külső azonosítójának rögzítése.
5. Vásárlási összeg vagy POS-tétellista fogadása.
6. A konfigurált üzleti szabály alapján a járó pont kiszámítása.
7. Kasszás számára előnézet: régi egyenleg, változás, várható új egyenleg.
8. Explicit megerősítés.
9. Vásárlónkénti zárolás alatt az egyenleg ismételt ellenőrzése.
10. Új teljes egyenleg beküldése `setCustomer` segítségével.
11. Csak sikeres UNAS-válasz után jelenjen meg sikeres állapot.
12. Auditnapló és tranzakcióstátusz mentése.

Az UNAS API a teljes `PointsAccount.Balance` értéket állítja be. Ne kezeld úgy, mintha az API atomi `+N` műveletet támogatna.

Példa:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Customers>
  <Customer>
    <Action>modify</Action>
    <Id>41704472</Id>
    <PointsAccount>
      <Balance>1572</Balance>
    </PointsAccount>
  </Customer>
</Customers>
```

### 5. Pontbeváltás

A beváltás folyamata hasonló, de kötelezően ellenőrizze:

- a legfrissebb UNAS-egyenleget;
- hogy van-e elegendő pont;
- a minimum/maximum beváltási szabályt;
- az egy tranzakcióban beváltható maximumot;
- hogy negatív egyenleg soha ne keletkezzen;
- a kasszás jogosultságát;
- a nyugtaazonosító egyediségét.

A beváltási pontérték és a pénzbeli érték ne legyen hardcode-olva. Konfigurálható üzleti szabály legyen.

### 6. Visszavonás és visszáru

Alkalmazott tranzakciót ne törölj. Visszavonáskor kompenzáló tranzakció készüljön, amely hivatkozik az eredeti tranzakcióra.

Követelmények:

- ugyanaz a tranzakció csak egyszer vonható vissza;
- a visszavonás is friss UNAS-egyenlegből induljon;
- csak megfelelő jogosultsággal végezhető;
- legyen kötelező indoklás;
- teljes auditnyom maradjon.

## Javasolt belső API

A pontos útvonalak a meglévő projekthez igazíthatók, de legalább az alábbi képességek legyenek:

```text
POST /webhooks/unas/customer-registration
POST /api/scans/resolve
POST /api/loyalty/earn
POST /api/loyalty/redeem
POST /api/loyalty/transactions/:id/reverse
GET  /api/loyalty/transactions
POST /api/admin/customers/backfill
GET  /health/live
GET  /health/ready
```

Példa scan kérés:

```json
{
  "qrPayload": "unas-loyalty:v1:L1_5QvNRt2X8mK4zY7pBc9DfA"
}
```

Példa válasz:

```json
{
  "customer": {
    "displayName": "Krisztián Piller",
    "maskedCardId": "…Bc9DfA"
  },
  "pointsBalance": "1397",
  "currencyOrUnit": "point"
}
```

Ne küldd vissza a teljes tokent, UNAS API tokent vagy szükségtelen személyes adatot.

Példa jóváírási kérés:

```json
{
  "qrPayload": "unas-loyalty:v1:L1_5QvNRt2X8mK4zY7pBc9DfA",
  "externalReceiptId": "STORE-01-20260903-000123",
  "purchaseAmountGross": "17540",
  "pointsDelta": "175",
  "idempotencyKey": "STORE-01-20260903-000123:earn"
}
```

Ha a szerver maga számítja a pontot, a kliens által küldött `pointsDelta` csak előnézeti adat lehet; az autoritatív értéket a szerver számolja újra.

## Adatmodell

Minimum táblák/entitások:

### `loyalty_customers`

- belső UUID;
- UNAS vásárló-ID, egyedi;
- token SHA-256 vagy erősebb egyirányú hash, egyedi;
- tokenverzió;
- státusz: active, revoked, pending;
- létrehozás és módosítás ideje;
- utolsó sikeres UNAS-szinkron ideje.

Lehetőleg ne tárold tartósan a token plaintext változatát. Beolvasáskor hash alapján keress.

### `loyalty_transactions`

- UUID;
- UNAS vásárló-ID vagy belső customer foreign key;
- külső nyugtaazonosító;
- üzlet és kassza azonosítója;
- kasszás felhasználó azonosítója;
- típus: earn, redeem, reversal, adjustment;
- előjeles pontváltozás;
- egyenleg előtte és utána;
- státusz: pending, applied, failed, reversed;
- idempotenciakulcs, egyedi;
- eredeti tranzakció hivatkozása visszavonásnál;
- UNAS válasz technikai referenciája, titkok nélkül;
- hiba kódja és rövid, tisztított leírása;
- létrehozás és alkalmazás ideje.

### `webhook_events`

- eseményazonosító vagy determinisztikus payload hash;
- eseménytípus;
- fogadás ideje;
- ellenőrzési státusz;
- feldolgozási státusz;
- próbálkozások száma;
- következő próbálkozás ideje;
- tisztított hiba.

### `stores`, `registers`, `users`

Szükséges a jogosultsághoz és auditáláshoz. Ha már létezik központi identitásszolgáltató, azt használd.

Minden pontértéket lebegőpontos bináris típus helyett pontos decimális típussal kezelj.

## Konkurencia és idempotencia

Ez kritikus követelmény.

- Ugyanahhoz a vásárlóhoz egyszerre csak egy egyenlegmódosítás futhat.
- Használj adatbázis-szintű row lockot vagy advisory lockot.
- A nyugtaazonosító + művelettípus és az idempotenciakulcs legyen egyedi.
- A megerősítés pillanatában ismét kérd le az UNAS-egyenleget.
- Ne jelezz sikert, amíg az UNAS nem adott sikeres választ.
- Ismeretlen kimenetelű timeout esetén ne ismételd vakon a balance írást; először olvasd vissza az állapotot és egyeztesd a helyi tranzakcióval.
- Az alkalmazás újraindítása után a `pending` tranzakciók legyenek egyeztethetők.

Tartsd szem előtt, hogy az UNAS adminból vagy más integrációból is változhat az egyenleg. A middleware adatbázisa nem lehet a pontegyenleg kizárólagos igazságforrása; módosítás előtt az UNAS aktuális értéke szükséges.

## UNAS API kliens

Készíts izolált, tesztelhető UNAS klienst:

- API-login és token-cache;
- token lejáratának kezelése;
- egyszeri újrabelépés hitelesítési hiba után;
- `getCustomer` ID/email/időablak szerinti lekérés;
- `setCustomer` paraméter- és pontegyenleg-módosítás;
- XML builder és biztonságos XML parser;
- explicit timeout;
- korlátozott retry csak biztonságosan ismételhető hívásoknál;
- rate-limit figyelés;
- strukturált, titokmentes hibák;
- mock/fake implementáció tesztekhez.

Kapcsold ki a külső XML-entitások feldolgozását. Ne építs XML-t stringkonkatenációval felhasználói inputból.

## Biztonság

Kötelező:

- HTTPS minden környezetben, kivéve izolált lokális fejlesztést;
- API-kulcs és minden secret környezeti változóban vagy secret managerben;
- secret ne kerüljön Gitbe, frontend bundle-be, URL-be vagy logba;
- webhook HMAC ellenőrzése a nyers body alapján, constant-time összehasonlítással;
- kasszás bejelentkezés és szerepkörök;
- CSRF-védelem böngészős állapotmódosításnál;
- rate limiting a scan, login és webhook végpontokon;
- inputvalidáció és output encoding;
- teljes token és szükségtelen PII maszkolása;
- auditnapló minden egyenlegmódosításról;
- adatmegőrzési és törlési szabályok;
- adatbázismentés és visszaállítási próba.

A profiloldali `readonly` mező csak felhasználói élmény, nem biztonsági kontroll. A middleware kizárólag a saját adatbázisában aktív tokenként nyilvántartott értéket fogadja el. Ha a vásárló manipulált értéket ment az UNAS-ba, az ne váljon automatikusan érvényes tokenné.

## Kasszai felület

Az MVP egy egyszerű, gyors, billentyűzettel teljesen kezelhető oldal legyen:

1. fókuszált QR-beolvasó mező;
2. vásárlói összefoglaló és aktuális egyenleg;
3. vásárlási összeg vagy pontváltozás mező;
4. „Pont jóváírása” és „Pont beváltása” külön művelet;
5. megerősítő képernyő;
6. jól látható siker/hiba állapot;
7. „Új vásárló beolvasása” művelet;
8. legutóbbi tranzakciók listája;
9. jogosultsághoz kötött visszavonás.

Kerüld a többértelmű gombokat. Jóváírás és levonás színe, előjele és szövege legyen egyértelmű. A dupla kattintást kliens- és szerveroldalon is védd.

Offline állapotban ne engedj pontot módosítani. Mutass egyértelmű „UNAS kapcsolat nem elérhető” hibát.

## Konfiguráció

Készíts `.env.example` fájlt valós titkok nélkül, legalább ezekkel:

```dotenv
DATABASE_URL=
UNAS_API_BASE_URL=https://api.unas.eu/shop
UNAS_API_KEY=
UNAS_LOYALTY_PARAM_ID=6590861
UNAS_WEBHOOK_HMAC_SECRET=
LOYALTY_QR_PREFIX=unas-loyalty:v1:
LOYALTY_POINTS_RULE_MODE=
LOYALTY_POINTS_PER_CURRENCY_UNIT=
LOYALTY_REDEMPTION_VALUE=
SESSION_SECRET=
APP_BASE_URL=
```

Az üzleti szabályokat ne szétszórt konstansokban tárold.

## Megfigyelhetőség

Legyen:

- strukturált naplózás request/correlation ID-val;
- metrika a webhook hibákról, UNAS latencyről és API-hibákról;
- riasztás ismételten sikertelen tokenkiosztásra;
- riasztás elakadt `pending` tranzakciókra;
- health és readiness végpont;
- adminisztrátori egyeztetési lista az eltérő vagy hiányzó tokenekről.

Ne logold az UNAS API-kulcsot, auth tokent, teljes QR-tokent vagy teljes webhook személyes adattartalmát.

## Tesztelési követelmények

### Unit tesztek

- QR payload parser;
- token generálás és egyediség;
- pontszámítás;
- minimum/maximum beváltás;
- HMAC ellenőrzés;
- XML request builder;
- XML response parser;
- idempotenciadöntések;
- visszavonási szabályok.

### Integrációs tesztek

- új vásárló tokenkiosztása mock UNAS API-val;
- már tokenizált vásárló webhook-ismétlése;
- érvénytelen webhook;
- UNAS login/tokenfrissítés;
- jóváírás és beváltás;
- kevés egyenleg;
- azonos nyugta ismételt beküldése;
- párhuzamos tranzakció ugyanarra a vásárlóra;
- UNAS timeout és bizonytalan kimenetel;
- sikertelen UNAS válasz;
- visszavonás.

### End-to-end teszt

1. tesztvásárló regisztrál;
2. token bekerül a `6590861` paraméterbe;
3. profilfrissítés után megjelenik a QR;
4. scanner beolvassa;
5. kasszai felület megmutatja az egyenleget;
6. jóváírás után az UNAS-egyenleg változik;
7. profilfrissítés után az új egyenleg jelenik meg;
8. ugyanazon nyugta ismétlése nem változtatja meg újra az egyenleget;
9. beváltás és visszavonás is helyesen működik.

## Elfogadási kritériumok

- Egy új vásárló automatikusan kap tokent webhook esetén célzottan 1 percen belül, polling esetén legkésőbb a beállított szinkronintervallum alatt.
- A token profilfrissítés után QR-kódként megjelenik.
- Érvényes QR alapján a kasszás megkapja a megfelelő vásárlót és friss UNAS-egyenleget.
- Érvénytelen, visszavont vagy manipulált token nem fed fel vásárlói adatot.
- Ugyanaz a nyugta vagy idempotenciakulcs nem módosíthatja kétszer az egyenleget.
- Párhuzamos műveletek nem írják felül egymás eredményét.
- UNAS-hiba esetén a felület nem mutat hamis sikert.
- Minden egyenlegváltozás visszakövethető.
- A teljes folyamat API-kulcs vagy más secret böngészőbe juttatása nélkül működik.
- A rendszer telepíthető dokumentált módon, migrációkkal, `.env.example` fájllal és üzemeltetési leírással.

## Üzleti kérdések, amelyeket implementáció előtt tisztázni kell

Ezeket ne találd ki önállóan; kezeld konfigurálhatóként vagy kérj döntést:

1. Milyen POS/kasszarendszer működik, és van-e API-ja?
2. A kassza át tudja-e adni a nyugtaazonosítót, végösszeget, SKU-kat és mennyiségeket?
3. Összeg- vagy termékalapú a pontszámítás?
4. Mennyi pont jár, és milyen kerekítési szabály szerint?
5. Egy pont milyen pénzbeli értéket képvisel beváltáskor?
6. Van-e minimum vagy maximum beváltás?
7. A teljes vagy csak részleges vásárlás fizethető ponttal?
8. Hogyan kezelendő a visszáru és a részleges visszáru?
9. A fizikai vásárlásból kell-e UNAS-megrendelést létrehozni, vagy csak a pontegyenleget kell módosítani?
10. Hány üzlet, kassza és kasszás használja majd?
11. VIP vagy PREMIUM UNAS csomag áll rendelkezésre?
12. Hol fusson az alkalmazás, és ki üzemeltesse?
13. Mi maradt meg a korábbi WordPress-megoldásból: forráskód, adatbázis, hosting, cron, webhook, plugin, napló vagy dokumentáció?

## Elvárt átadás

- futó alkalmazáskód;
- adatbázis-migrációk;
- tesztek;
- `.env.example`;
- lokális indítási útmutató;
- production deployment útmutató;
- UNAS admin/API/webhook beállítási útmutató;
- kasszás rövid használati útmutató;
- backfill és egyeztető parancsok;
- monitoring és backup leírás;
- architekturális döntési jegyzék;
- ismert korlátok és következő lépések.

Első mérföldkőként ne közvetlen POS-integrációval kezdj. Készíts biztonságos, böngészőből használható kasszai MVP-t USB-s, billentyűzetként működő QR-olvasóhoz. A POS-integráció külön második fázis legyen, miután a pontszabályok és a korábbi WordPress-megoldás működése tisztázódott.
