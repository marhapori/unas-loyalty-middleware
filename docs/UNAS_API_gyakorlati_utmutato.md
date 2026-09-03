# UNAS API – gyakorlati útmutató működő integráció készítéséhez

Frissítve: 2026. szeptember 3.

Ez a dokumentum fejlesztési alapanyagként is használható: beadható a Claude Code-nak a projekt gyökerében, és végigvezet az UNAS API-kapcsolat felépítésén. Az első javasolt projekt egy biztonságos, csak olvasási jogosultságú CLI alkalmazás, amely termékeket és rendeléseket tölt le, majd JSON- és CSV-fájlba menti őket.

> Fontos: az UNAS API dokumentációja folyamatosan változhat. Egy konkrét végpont implementálása előtt mindig ellenőrizni kell annak aktuális „kérés”, „válasz”, „adatszerkezet” és „példák” oldalát a [hivatalos UNAS API-dokumentációban](https://unas.hu/tudastar/api).

## 1. Mi az UNAS API, és miben tér el egy tipikus REST API-tól?

Az UNAS API külső programok és egy UNAS webáruház kétirányú összekapcsolására szolgál. Lekérdezhetők, létrehozhatók, módosíthatók és – ahol a végpont engedi – törölhetők többek között termékek, készletek, rendelések, vásárlók és kategóriák.

A legfontosabb technikai sajátosságok:

- az alap URL: `https://api.unas.eu/shop/`;
- minden funkció külön útvonalon érhető el, például `login`, `getProduct`, `getOrder`, `setStock`;
- minden hívás HTTP `POST` metódust használ, a lekérdezések is;
- a kérések és válaszok jellemzően XML-formátumúak;
- a kapcsolat TLS 1.2 vagy TLS 1.3 protokollt igényel;
- sikeres kérésnél jellemzően HTTP 200 érkezik;
- általános hibánál jellemzően HTTP 400 és egy `<Error>` gyökérelemű XML-válasz érkezik;
- nincs klasszikus JSON REST API, nincs OpenAPI/Swagger séma, és nem a HTTP metódus jelzi a művelet jellegét;
- az azonosítás kétlépcsős: API-kulccsal tokent kérünk, majd a tokent Bearer fejlécben használjuk.

Az API Premium és VIP UNAS előfizetéssel használható. A hivatalos alapelvek és protokolladatok az [UNAS API főoldalán](https://unas.hu/tudastar/api) találhatók.

## 2. Mire van szükség a kezdéshez?

### UNAS-oldali feltételek

1. Premium vagy VIP előfizetésű áruház.
2. Hozzáférés az UNAS adminisztrációhoz.
3. Egy külön API-kulcs a projekthez.
4. Csak a valóban szükséges végpontok engedélyezése.
5. Opcionálisan IP-cím vagy CIDR-tartomány korlátozás.

Az API-kulcs az adminisztrációban a következő helyen hozható létre:

`Beállítások → Külső kapcsolatok → API kapcsolat`

Adj neki egyértelmű nevet, például `Claude Code – olvasási teszt`. Első körben csak ezeket engedélyezd:

- `getProduct`
- `getOrder`

Ha más törzsadatokat is le szeretnél kérni, később külön hozzáadható például a `getCategory`, `getStock` vagy `getOrderStatus`. Írási végpontot – például `setProduct`, `setStock`, `setOrder` – az első fejlesztési szakaszban ne engedélyezz.

Az API-kulcs alapú azonosítás az ajánlott megoldás. A régi felhasználónév–jelszó módszert új integrációhoz az UNAS már nem támogatja. Az adminisztrációban végpontonkénti jogosultság és engedélyezett IP-cím/CIDR is megadható. Részletek: [API-kapcsolat beállítása](https://unas.hu/tudastar/admin/api-kapcsolat).

### Fejlesztői környezet

A projekt Pythonban különösen jó kezdés, mert egyszerű az XML-kezelés, a CSV-export és az automatizálás. Javasolt minimum:

- Python 3.12 vagy újabb;
- `httpx` a HTTP-kérésekhez;
- `xmltodict` az XML egyszerű feldolgozásához;
- `pydantic-settings` a konfigurációhoz;
- `tenacity` az ellenőrzött újrapróbálkozáshoz;
- `pytest` és `respx` a tesztekhez;
- opcionálisan `typer` a parancssori felülethez.

Az API-kulcsot környezeti változóban kell tárolni, nem a forráskódban:

```env
UNAS_API_KEY=ide_kerul_a_valodi_kulcs
UNAS_API_BASE_URL=https://api.unas.eu/shop
UNAS_TIMEOUT_SECONDS=60
```

A `.env` fájl kerüljön a `.gitignore` állományba. A repóba csak `.env.example` kerüljön, valódi titok nélkül.

## 3. Azonosítás és tokenkezelés

### 3.1. Login kérés

Végpont:

```text
POST https://api.unas.eu/shop/login
```

XML-törzs:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Params>
    <ApiKey>AZ_API_KULCS</ApiKey>
    <WebshopInfo>true</WebshopInfo>
</Params>
```

A `WebshopInfo` opcionális. `true` értéknél a válasz az áruház technikai és üzemeltetői adatait is tartalmazhatja. Normál tokenfrissítéshez felesleges, ezért érdemes csak egy külön kapcsolat-ellenőrző parancsban kérni.

### 3.2. Login válasz

A sikeres válasz fontos mezői:

- `Token`: a további hívásokhoz szükséges token;
- `Expire`: lejárat az áruház időzónája szerint `Y.m.d H:i:s` alakban;
- `ExpireTime`: lejárat Unix timestampként;
- `ShopId`: az áruház UNAS-azonosítója;
- `Subscription`: előfizetési csomag;
- `Permissions/Permission`: az API-kulcshoz engedélyezett végpontok;
- `Status`: siker esetén `ok`.

A token a dokumentáció szerint 2 órán át használható. Nem szabad minden API-hívás előtt újra bejelentkezni. A tokent memóriában vagy rövid élettartamú helyi cache-ben kell tartani, és csak lejárat előtt 1–5 perccel frissíteni.

További hívások HTTP-fejléce:

```http
Authorization: Bearer A_KAPOTT_TOKEN
Content-Type: application/xml; charset=utf-8
Accept: application/xml
```

A token használatát és a válasz mezőit az [UNAS login dokumentációja](https://unas.hu/tudastar/api/azonositas-login-valasz) írja le.

### 3.3. Javasolt tokenlogika

1. Ha nincs token, történjen login.
2. Ha van token és `now < expire_time - 60 másodperc`, használjuk újra.
3. Ha lejárt vagy hamarosan lejár, kérjünk újat.
4. Ha egy üzleti végpont hitelesítési hibát ad, egyszer frissítsük a tokent, majd egyszer ismételjük meg a kérést.
5. Ha ez is hibás, álljunk le; ne induljon végtelen újrapróbálkozás.

## 4. Az általános kérési folyamat

Egy működő kliens minden végpontnál ugyanazt a folyamatot követi:

1. XML-kérés összeállítása UTF-8 kódolással.
2. Érvényes token biztosítása.
3. `POST` kérés küldése az `https://api.unas.eu/shop/{function}` címre.
4. HTTP-státusz és válaszfejlécek naplózása – titkok nélkül.
5. A válasz szövegének biztonságos XML-parszolása.
6. `<Error>` válasz felismerése akkor is, ha a HTTP-státusz kezelése már lefutott.
7. A végpont saját siker- vagy entitáseredményének ellenőrzése.
8. Strukturált Python-adattá alakítás.

Minimális Python-vázlat:

```python
from __future__ import annotations

from dataclasses import dataclass
from time import time
import xml.etree.ElementTree as ET

import httpx


class UnasApiError(RuntimeError):
    pass


@dataclass
class TokenState:
    value: str
    expires_at: int


class UnasClient:
    def __init__(self, api_key: str, base_url: str = "https://api.unas.eu/shop"):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.http = httpx.Client(timeout=60.0)
        self._token: TokenState | None = None

    def _post_xml(self, function: str, xml_body: str, authenticated: bool = True) -> ET.Element:
        headers = {
            "Content-Type": "application/xml; charset=utf-8",
            "Accept": "application/xml",
        }
        if authenticated:
            headers["Authorization"] = f"Bearer {self.get_token()}"

        response = self.http.post(
            f"{self.base_url}/{function}",
            content=xml_body.encode("utf-8"),
            headers=headers,
        )

        try:
            root = ET.fromstring(response.content)
        except ET.ParseError as exc:
            raise UnasApiError(
                f"Nem XML válasz érkezett; HTTP {response.status_code}"
            ) from exc

        if root.tag == "Error":
            raise UnasApiError(root.text or "Ismeretlen UNAS API-hiba")

        response.raise_for_status()
        return root

    def login(self) -> TokenState:
        body = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            f"<Params><ApiKey>{self.api_key}</ApiKey></Params>"
        )
        root = self._post_xml("login", body, authenticated=False)
        token = root.findtext("Token")
        expires = root.findtext("ExpireTime")
        if not token or not expires:
            raise UnasApiError("A login válaszból hiányzik a Token vagy az ExpireTime")
        self._token = TokenState(token, int(expires))
        return self._token

    def get_token(self) -> str:
        if self._token is None or time() >= self._token.expires_at - 60:
            self.login()
        assert self._token is not None
        return self._token.value
```

Ez csak szemléltető váz. A végleges megoldásban az XML-elemeket XML-builderrel kell felépíteni, hogy az API-kulcsban vagy adatmezőkben szereplő speciális karakterek megfelelően escape-elve legyenek.

## 5. XML-kezelés: a legfontosabb szabályok

### 5.1. UTF-8 és speciális karakterek

Mindig UTF-8 kódolást használj. Dinamikus adatot ne illessz egyszerű string-összefűzéssel az XML-be. Használj `xml.etree.ElementTree`, `lxml` vagy más XML-buildert, mert az `&`, `<`, `>` és idézőjelek érvénytelen XML-t okozhatnak.

A válaszok szöveges mezői CDATA-szakaszokat is tartalmazhatnak. Ezt egy szabványos XML-parser automatikusan szövegként adja vissza.

### 5.2. Hiányzó, üres és törlendő mező nem ugyanaz

Az UNAS általános `set...` működése szerint:

- ha egy XML-node nincs benne a kérésben, az adott mezőt általában nem kívánod módosítani;
- ha a node benne van, de üres, az általában a korábbi érték törlését jelenti;
- bizonyos végpontok vagy mezők ettől eltérhetnek, ezért írás előtt mindig ellenőrizni kell a konkrét adatszerkezetet.

Ez az egyik legnagyobb kockázat. Nem szabad úgy generálni írási XML-t, hogy az összes ismert mező automatikusan bekerül üres értékkel.

### 5.3. Egy XML-ben több entitás

Több termék, készlet vagy más entitás is küldhető egy kérésben. Az UNAS sorban dolgozza fel őket. Hiba esetén a feldolgozás leáll; a hiba előtti elemek már feldolgozódhattak, a későbbiek nem. Emiatt a többentitásos kérés nem tekinthető atomi tranzakciónak.

Gyakorlati következmények:

- használj mérsékelt batch-méretet;
- legyen minden elemnek stabil külső azonosítója, például cikkszám;
- őrizd meg a batch tartalmát és sorrendjét;
- hiba után ellenőrizd vissza, mi teljesült;
- az újrafuttatás legyen lehetőleg idempotens.

## 6. Fontos végpontcsoportok

| Terület | Olvasás | Írás/ellenőrzés | Tipikus feladat |
| --- | --- | --- | --- |
| Azonosítás | `login` | – | token kérése |
| Rendelések | `getOrder` | `setOrder` | rendelések exportja, státusz/frissítés |
| Készlet | `getStock` | `setStock` | készletszinkron |
| Termékek | `getProduct`, `getProductDB` | `setProduct`, `setProductDB` | termékadatok, árak, képek |
| Termékparaméterek | `getProductParameter` | `setProductParameter` | paramétertörzs kezelése |
| Kategóriák | `getCategory` | `setCategory` | kategóriafa |
| Vásárlók | `getCustomer` | `setCustomer`, `checkCustomer` | ügyféladatok, ellenőrzés |
| Vásárlócsoportok | `getCustomerGroup` | `setCustomerGroup` | csoportok és árlogika |
| Hírlevél | `getNewsletter` | `setNewsletter` | feliratkozók |
| Tartalom | `getPage`, `getPageContent` | `setPage`, `setPageContent` | oldalak, tartalmi elemek |
| Fájlkezelés | `getStorage` | `setStorage` | fájlok és mappák |
| Automata folyamatok | `getAutomatism` | `setAutomatism` | automatizmusok, webhook |
| Rendelési törzsadatok | `getOrderStatus`, `getOrderType` | megfelelő `set...` | státuszok és típusok |
| Értékesítési beállítások | `getCoupon`, `getMethod` | megfelelő `set...` | kuponok, fizetés, szállítás |
| További raktárak | `getWarehouse` | `setWarehouse` | több raktár kezelése |
| Átvételi pontok | `getDeliveryPointGroup`, `getDeliveryPoint` | megfelelő `set...` | pontok és csoportok |
| Egyéb termékfunkciók | `getPackageOffer`, `getProductReview`, `getProductService`, `getSticker`, `getGift`, `getBogo` | megfelelő `set...` | kapcsolódó funkciók |
| Beállítások | `getSetting` | `setSetting` | áfa, pénznem, jogi dokumentumok stb. |

A login válaszban lévő `Permissions` listából programinduláskor ellenőrizhető, hogy az API-kulcs valóban jogosult-e a szükséges funkciókra.

## 7. Termékek lekérése és lapozása

Példa:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Params>
    <StatusBase>1</StatusBase>
    <State>live</State>
    <ContentType>normal</ContentType>
    <LimitNum>100</LimitNum>
    <LimitStart>0</LimitStart>
    <Lang>hu</Lang>
</Params>
```

Fontos `getProduct` szűrők:

- `StatusBase`: 0 inaktív; 1 aktív; 2 aktív, új; 3 aktív, nem vásárolható;
- `State`: `live` vagy az egy hónapra visszamenőleg elérhető `deleted`;
- `Id`, `Sku`: konkrét termék lekérése; több cikkszám vesszővel elválasztható;
- `Parent`: összevont termék alaptípusának cikkszáma;
- `CategoryId`: elsődleges kategória szerinti szűrés;
- `TimeStart`, `TimeEnd`: módosítási Unix timestamp alapján;
- `DateStart`, `DateEnd`: módosítás dátuma `YYYY.MM.DD` alakban;
- `ContentType`: `minimal`, `short`, `normal`, `full`;
- `ContentParam`: `full` lekérésnél a visszaadott paraméterek szűkítése;
- `LimitNum`, `LimitStart`: lapozás;
- `Lang`: kétbetűs ISO 639-1 nyelvkód, például `hu`, `en`, `de`.

Teljes termékállományhoz addig növeld a `LimitStart` értékét a lapmérettel, amíg üres vagy a lapméretnél rövidebb lista nem érkezik. A lapozás közben ugyanazt a rendezési és szűrési logikát kell megtartani. Nagy adatmennyiségnél kerüld a `full` módot; kérd csak azt, amire valóban szükséged van. Részletek: [getProduct kérés](https://unas.hu/tudastar/api/termekek-getProduct-keres).

Inkrementális szinkronnál a sikeresen feldolgozott módosítási timestampet tárold checkpointként. A következő futásban kis átfedéssel indulj – például 2–5 perccel korábbról –, majd a rekordokat UNAS `Id` és módosítási idő alapján deduplikáld. Ez csökkenti annak esélyét, hogy időzítés vagy futás közbeni módosítás miatt adat maradjon ki.

## 8. Rendelések lekérése

Példa az utoljára módosított rendelésekre:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Params>
    <TimeModStart>1798761600</TimeModStart>
    <Order>modify_time_asc</Order>
    <LimitNum>500</LimitNum>
    <LimitStart>0</LimitStart>
    <Lang>customer</Lang>
</Params>
```

Fontos `getOrder` szűrők:

- státusz sorszáma/típusa, neve vagy azonosítója;
- státuszváltási időintervallum;
- vevő email-címe;
- számlázási státusz;
- rendelés leadási ideje vagy dátuma;
- utolsó módosítás ideje;
- konkrét `Key` rendelésazonosító;
- rendezés leadási idő, módosítási idő vagy kulcs alapján;
- `LimitNum` és `LimitStart`;
- `Lang`: `base` vagy `customer`.

Ha nincs `LimitNum`, legfeljebb 500 rendelés érkezik; a `LimitNum` maximuma is 500. Emiatt kötelező a lapozás. Szinkronizáláshoz a `TimeModStart` + `modify_time_asc` általában biztonságosabb, mint kizárólag az új rendelések leadási ideje, mert a már meglévő rendelés státusza és más adata később is módosulhat. Részletek: [getOrder kérés](https://unas.hu/tudastar/api/megrendelesek-getOrder-keres).

Különösen veszélyes mező az `InvoiceAutoSet`: jelenléte/értéke a lekért rendelések számlázási státuszát automatikusan „Számlázva” állapotba teheti. Egyszerű olvasási vagy riportprojektben ezt egyáltalán ne küldd.

A rendelésadatok személyes adatokat tartalmaznak. Ne naplózd korlátlanul a teljes XML-választ, ne tedd tesztfixture-ként nyilvános repóba, és állíts be megfelelő megőrzési/törlési szabályt.

## 9. Írási műveletek biztonságos bevezetése

Az írás csak akkor kerüljön be a projektbe, amikor az olvasás, a tokenfrissítés, a lapozás, a hibakezelés és a naplózás stabil.

Javasolt sorrend:

1. Készíts külön API-kulcsot a write funkciókhoz.
2. Csak egyetlen szükséges `set...` jogosultságot adj neki.
3. Legyen `DRY_RUN=true` alapértelmezés, amely csak elkészíti és maszkolva naplózza az XML-t.
4. Az első valódi teszt egyetlen, erre kijelölt terméken történjen.
5. Módosítás előtt olvasd vissza és mentsd el az aktuális állapotot.
6. Módosítás után azonnal kérdezd le újra és hasonlítsd össze az eredményt.
7. Tömeges futás előtt legyen tételszámkorlát és kézi megerősítés.
8. Batch-hibánál ne ismételd automatikusan az egész csomagot visszaellenőrzés nélkül.

Általános műveleti minták a `set...` kérésekben:

- `add`: új rekord;
- `modify`: meglévő rekord módosítása;
- `delete`: törlés, ha a konkrét végpont és entitás támogatja.

A pontos gyökérelem, azonosító és kötelező mezők végpontonként eltérnek. Ezeket nem szabad másik végpont példájából kikövetkeztetni; a konkrét hivatalos adatszerkezetből kell átvenni.

## 10. Hibakezelés, újrapróbálkozás és naplózás

### Hibatípusok

Érdemes külön kezelni:

- konfigurációs hiba: hiányzó API-kulcs vagy rossz URL;
- hitelesítési hiba: hibás kulcs, lejárt token, hiányzó jogosultság;
- validációs/üzleti hiba: hibás XML-mező vagy nem engedélyezett módosítás;
- limit- vagy tiltási hiba;
- átmeneti hálózati hiba: timeout, kapcsolatmegszakadás;
- szerverhiba: 5xx;
- formátumhiba: nem XML vagy csonka válasz.

### Mikor szabad újrapróbálni?

Exponenciális visszalépéssel, kevés alkalommal újrapróbálható:

- hálózati kapcsolat hiba;
- timeout;
- 502, 503, 504 jellegű átmeneti szerverhiba.

Ne próbáld vakon újra:

- hibás API-kulcsot;
- jogosultsági hibát;
- hibás XML-t vagy üzleti validációs hibát;
- egy többentitásos `set...` kérést, mert annak eleje már feldolgozódhatott;
- limit miatti tiltást a megadott feloldási idő előtt.

Írási kérésnél csak akkor biztonságos automatikusan retry-olni, ha bizonyítható az idempotencia, vagy előbb visszaellenőrzöd az állapotot.

### Naplózás

Minden hívásnál hasznos:

- időpont;
- végpont neve;
- futási/correlation ID;
- HTTP-státusz;
- időtartam;
- batch elemszáma;
- lapozási pozíció;
- UNAS hibaüzenet;
- retry sorszáma.

Soha ne naplózd:

- az API-kulcsot;
- a Bearer tokent;
- teljes rendelési XML-t személyes adatokkal;
- jelszót vagy egyéb titkot.

## 11. Limitek és tiltások

A jelenlegi hivatalos dokumentáció alapján:

- Premium csomag: legfeljebb 2000 hívás/óra/IP;
- VIP csomag: legfeljebb 6000 hívás/óra/IP;
- limitsértésnél az adott IP az adott webáruházhoz 1 órára letiltható;
- az általános végpontokon 20 sikertelen hívás lehet a tiltási küszöb; egy sikeres hívás lenullázza ezt a sikertelen számlálót;
- a `login` végpont különösen szigorú: a dokumentáció 5 sikertelen loginhívás/óra maximumot jelez;
- ha 10 perc alatt 10 olyan hívás érkezik, amelyből az áruház nem azonosítható – például hibás kulcs miatt –, az IP-ről 2 órán át egyik áruház API-ja sem lesz elérhető, és válasz sem feltétlenül érkezik;
- `set...` kérés XML-törzsének maximális mérete 128 MB;
- éjfél körül, ±10 percben karbantartás lehet, ezért oda ne ütemezz integrációt;
- a nagy napi futásokat érdemes nem egész órára, hanem véletlenszerű percre ütemezni.

A tiltási válasz megadhatja, hogy a végpont mikortól használható újra. Ezt a kliensnek értelmeznie kell, majd le kell állnia a jelzett időpontig. Forrás: [UNAS API-limitációk](https://unas.hu/tudastar/api/limitaciok).

A saját kliensben legyen ennél szigorúbb belső korlát, például maximum 5–10 kérés/másodperc és központi rate limiter. A login tokent két órán belül újra kell használni.

## 12. Webhookok

Az UNAS automata folyamatok webhookot tudnak küldeni egy külső URL-re. Ez eseményvezérelt feldolgozást tesz lehetővé, így nem kell minden változásért sűrűn lekérdezni az API-t.

Az adminban generálható HMAC-kulccsal ellenőrizhető a webhook eredete. Az UNAS a `X-Unas-Hmac` fejlécben küldi az aláírást. Az ellenőrzés menete:

1. olvasd be a nyers request body byte-jait – még JSON-parszolás vagy újraszerializálás előtt;
2. számíts HMAC-SHA256 értéket a nyers törzsből a titkos HMAC-kulccsal;
3. a bináris digestet Base64-kódold;
4. konstans idejű összehasonlítással vesd össze a fejléc értékével;
5. csak érvényes aláírás után dolgozd fel az eseményt.

Python-minta:

```python
import base64
import hashlib
import hmac


def verify_unas_webhook(raw_body: bytes, received_signature: str, secret: str) -> bool:
    digest = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode("ascii")
    return hmac.compare_digest(expected, received_signature)
```

További követelmények:

- kizárólag HTTPS publikus végpont;
- gyors 2xx válasz; a hosszú munkát háttérfolyamat végezze;
- deduplikáció, mert ugyanaz az esemény újra érkezhet;
- naplózott eseményazonosító vagy payload-hash;
- HMAC-hiba esetén 401/403 és feldolgozás nélkül leállás;
- a HMAC-titok külön secretként kezelendő.

Az aláírás pontos képlete az [UNAS webhook-ellenőrzési oldalán](https://unas.hu/tudastar/api/automata-folyamatok-webhook-ellenorzes) található.

## 13. Javasolt projektstruktúra Claude Code-hoz

```text
unas-api-client/
├── CLAUDE.md
├── README.md
├── pyproject.toml
├── .env.example
├── .gitignore
├── docs/
│   └── UNAS_API_gyakorlati_utmutato.md
├── src/
│   └── unas_client/
│       ├── __init__.py
│       ├── client.py
│       ├── auth.py
│       ├── config.py
│       ├── exceptions.py
│       ├── xml_utils.py
│       ├── pagination.py
│       ├── models.py
│       └── cli.py
├── exports/
│   └── .gitkeep
└── tests/
    ├── fixtures/
    ├── test_auth.py
    ├── test_errors.py
    ├── test_pagination.py
    └── test_xml_utils.py
```

### Első verzió funkciói

- `unas check-connection`: login, ShopId, előfizetés és jogosultságok kijelzése;
- `unas products export --format json|csv`: termékek lapozott exportja;
- `unas orders export --modified-since ... --format json|csv`: rendelések exportja;
- token cache ugyanazon futáson belül;
- XML-hibák és `<Error>` válaszok kezelése;
- strukturált, titokmentes log;
- timeout és óvatos retry;
- unit tesztek mockolt HTTP-válaszokkal;
- minden parancs read-only.

### Elfogadási feltételek

1. Valódi API-kulcs nélkül a program érthető hibaüzenettel leáll.
2. A kulcs és token soha nem jelenik meg a logban.
3. Egy sikeres futás alatt nem történik fölösleges újralogin.
4. A kliens felismeri a HTTP-hibát és az XML `<Error>` választ is.
5. A termék- és rendeléslista minden lapját letölti.
6. Az üres és egyetlen elemű XML-listát is helyesen kezeli.
7. A CSV UTF-8 BOM-mal is exportálható, hogy a magyar Excel jól nyissa meg.
8. A rendelések személyes adatait tartalmazó export nincs Gitbe követve.
9. A tesztek nem hívják a valódi UNAS API-t.
10. Írási végpont nincs implementálva az első verzióban.

## 14. Indító prompt Claude Code számára

Az alábbi promptot a projektmappa létrehozása után lehet beadni. Ezt a dokumentumot másold a `docs/UNAS_API_gyakorlati_utmutato.md` helyre.

```text
Olvasd el teljesen a docs/UNAS_API_gyakorlati_utmutato.md fájlt, majd készíts
egy Python 3.12+ alapú, csak olvasási jogosultságú UNAS API kliensprojektet.

Elsőként írj rövid megvalósítási tervet és sorold fel a létrehozandó fájlokat.
Ezután implementáld a következőket:

1. Konfiguráció környezeti változókból; a valódi kulcs soha ne kerüljön Gitbe.
2. API-kulcsos login, Bearer token cache és lejárat előtti tokenfrissítés.
3. Általános XML POST kliens, timeout, biztonságos XML-parszolás és
   strukturált kivételek.
4. check-connection CLI parancs, amely megmutatja a ShopId-t, csomagot és
   jogosultságokat, de titkot nem ír ki.
5. getProduct lapozott lekérés és JSON/CSV export.
6. getOrder lapozott lekérés TimeModStart szűrővel és JSON/CSV export.
7. Óvatos retry kizárólag átmeneti hálózati és 5xx hibákra.
8. Pytest tesztek mockolt XML-válaszokkal: sikeres login, hibás login,
   lejárt token, Error XML, nem XML válasz, lapozás 0/1/több oldallal.
9. README pontos telepítési és futtatási parancsokkal Windows PowerShellhez.

Használj httpx, pydantic-settings, typer, xmltodict, tenacity és pytest
csomagokat. Az XML-eket ne dinamikus string-összefűzéssel építsd. Az UNAS API
alap URL-je https://api.unas.eu/shop, és minden funkció POST kérés. Semmilyen
set... végpontot ne implementálj. Minden nagyobb lépés után futtasd a teszteket,
és javítsd a hibákat. Ha az útmutató és egy konkrét hivatalos UNAS végpontoldal
között eltérést találsz, állj meg és jelezd.
```

## 15. Tesztelési stratégia

### Automatizált tesztek

Mockolt válaszokkal tesztelendő:

- sikeres és hibás login;
- token újrafelhasználása és lejárata;
- 200 + normál XML;
- 400 + `<Error>`;
- 200 + `<Error>` védekező tesztként;
- 5xx és timeout retry;
- nem XML hibaoldal;
- üres, egy- és többelemű XML-lista;
- CDATA és magyar ékezetek;
- lapozás megállása;
- CSV oszlopok és kódolás;
- titkok maszkolása a logban.

### Valódi kapcsolat tesztelése

1. Külön, read-only API-kulcs.
2. `check-connection` egyszer.
3. Egy konkrét termék `Sku` vagy `Id` alapján.
4. Kis lap, például 5 termék `minimal` vagy `short` adattal.
5. Egy konkrét rendelés `Key` alapján – ha a kulcs és adatkezelés engedi.
6. Kis dátumtartományú rendeléslista.
7. Teljes, lapozott export.

Ha hibás hitelesítési választ kapsz, ne próbálkozz sorozatban. Ellenőrizd az adminban az API-kulcsot, jogosultságot és IP-korlátozást.

## 16. Élesítés előtti ellenőrzőlista

- [ ] Premium vagy VIP csomag aktív.
- [ ] Külön API-kulcs készült az integrációhoz.
- [ ] Legkisebb szükséges jogosultságok vannak beállítva.
- [ ] Az API-kulcs secretben/környezeti változóban van.
- [ ] `.env`, exportok és személyes adatot tartalmazó fájlok Gitből kizárva.
- [ ] Token cache működik, nincs login minden hívás előtt.
- [ ] Timeout és korlátozott retry beállítva.
- [ ] Rate limiter és hívásszámlálás működik.
- [ ] `<Error>` XML kezelve.
- [ ] Lapozás és inkrementális checkpoint tesztelve.
- [ ] Éjfél körüli futás kerülve.
- [ ] A log nem tartalmaz kulcsot, tokent vagy indokolatlan személyes adatot.
- [ ] Írásnál dry-run, egyrekordos próba és visszaellenőrzés van.
- [ ] Többentitásos írás részleges teljesülésére felkészült a rendszer.
- [ ] Webhooknál a nyers body HMAC-ellenőrzése megtörténik.
- [ ] Az API-változásnapló követése megoldott.

## 17. Ajánlott fejlesztési lépések

**1. mérföldkő – kapcsolat:** konfiguráció, login, token, `check-connection`.

**2. mérföldkő – olvasás:** egy termék, majd lapozott termékexport.

**3. mérföldkő – üzleti adat:** rendelések inkrementális exportja `TimeModStart` alapján.

**4. mérföldkő – megbízhatóság:** checkpoint, deduplikáció, retry, rate limit, strukturált napló, tesztek.

**5. mérföldkő – automatizálás:** ütemezett futtatás, biztonságos tárolás és riport.

**6. mérföldkő – írás:** külön kulcs, dry-run, egy kijelölt rekord, visszaellenőrzés, majd kis batch.

**7. mérföldkő – webhook:** eseményvezérelt feldolgozás HMAC-ellenőrzéssel.

Ezzel a sorrenddel már az első két mérföldkő végén működő, hasznos programod lesz, miközben a webáruház adatait még nem veszélyezteti írási művelet.

## Hivatalos források

- [UNAS API dokumentáció](https://unas.hu/tudastar/api)
- [API-kapcsolat beállítása az adminban](https://unas.hu/tudastar/admin/api-kapcsolat)
- [Azonosítás](https://unas.hu/tudastar/api/azonositas)
- [Login kérés](https://unas.hu/tudastar/api/azonositas-login-keres)
- [Login válasz](https://unas.hu/tudastar/api/azonositas-login-valasz)
- [API-limitációk](https://unas.hu/tudastar/api/limitaciok)
- [getProduct kérés](https://unas.hu/tudastar/api/termekek-getProduct-keres)
- [Termék API-példák](https://unas.hu/tudastar/api/termekek-peldak)
- [getOrder kérés](https://unas.hu/tudastar/api/megrendelesek-getOrder-keres)
- [Webhook ellenőrzés](https://unas.hu/tudastar/api/automata-folyamatok-webhook-ellenorzes)
- [API változásnapló](https://unas.hu/tudastar/api/valtozas-naplo)
