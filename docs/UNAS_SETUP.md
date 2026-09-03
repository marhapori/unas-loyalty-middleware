# UNAS admin/API/webhook beallitasi utmutato

## 1. Elofeltetel

A boltnak **VIP** csomagja van (ezt a beszelgetesben megerositve) - ez sziikseges
a `customer_registration` automatizmus/webhook funkciohoz. Ha ezt kesobb Premiumra
valtjatok, az uj vasarlok automatikus tokenizalasa mar nem lesz azonnali; ekkor a
`python -m loyalty_app.cli backfill-customers` parancsot kell rendszeresen (pl.
cron/utemezett feladatkent) futtatni ahelyett.

## 2. API-kulcs letrehozasa

`Beallitasok -> Kulso kapcsolatok -> API kapcsolat` az UNAS adminban.

1. Hozz letre egy uj, kulon API-kulcsot ennek az integracionak, pl. "Husegpont
   middleware".
2. Csak a sziikseges vegpontokat engedelyezd:
   - `getCustomer`
   - `setCustomer`
3. Opcionalisan korlatozd a hivo IP-cimet/CIDR-t a middleware szerverere.
4. A kapott kulcsot masold a `.env` fajl `UNAS_API_KEY` erteke ala. **Soha ne
   keruljon Gitbe vagy logba.**

## 3. A `6590861` vasarloi parameter

A vasarloi profilon mar megjelenik a QR-kod egy meglevo UNAS-sablonbol, ami a
`6590861` azonositoju vasarloi parameter erteket `unas-loyalty:v1:<ertek>` alakban
kodolja. Ellenorizd az adminban (`Vasarlok -> Vasarloi parameterek`), hogy ez a
parameter letezik es szoveges tipusu. Ha az azonosito idokozben megvaltozott,
frissitsd a `.env` `UNAS_LOYALTY_PARAM_ID` erteket is.

## 4. `customer_registration` automatizmus (webhook)

Az adminban: `Automatizmusok` (vagy `Automata folyamatok`) menu, uj automatizmus
letrehozasa:

- **Esemeny**: uj vasarlo regisztracioja (`customer_registration`)
- **Muvelet**: webhook kuldese
- **Cel URL**: `https://<a-te-domain-ed>/webhooks/unas/customer-registration`
  (a middleware kozvetlenul HTTPS-en legyen elerheto, lasd
  [DEPLOYMENT.md](DEPLOYMENT.md))
- **HMAC titok**: generalj egy eros veletlen erteket, allitsd be itt ES a
  middleware `.env` `UNAS_WEBHOOK_HMAC_SECRET` mezojeben is - a kettonek
  pontosan egyeznie kell.

> A webhook pontos payload-szerkezetet a hivatalos dokumentacio nem irja le
> peldaval. A middleware `loyalty_app/loyalty/webhook_adapter.py` fajlja egy
> izolalt adaptert hasznal, ami tobb elterjedt mezonev-mintat probal. Az elso
> valodi webhook utan ellenorizd a `webhook_events` tablat: ha
> `process_status='needs_review'`, nezd meg a `raw_payload_masked` mezot, es
> egeszitsd ki az adaptert a tenyleges mezonevvel. Lasd
> [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md).

## 5. Ellenorzes

1. Inditsd el a middleware-t (lasd README).
2. Regisztralj egy teszt vasarlot a webaruhazban (vagy varj egy valodi
   regisztraciora).
3. Nezd meg pár masodperc mulva a `webhook_events` es `loyalty_customers`
   tablakat, vagy az adminban a vasarlo `6590861` parameteret - meg kell
   jelennie egy `L1_...` erteknek.
4. A vasarloi profil QR-kodja ettol kezdve mar a valodi, middleware altal ismert
   tokent kodolja.

## 6. Meglevo vasarlok (backfill)

A regisztracios webhook csak az UJ vasarlokat kezeli. A mar meglevo
vasarlokhoz futtasd egyszer (majd idorol idore, ha kell):

```powershell
python -m loyalty_app.cli backfill-customers --dry-run   # eloszor csak nezd meg
python -m loyalty_app.cli backfill-customers               # aztan tenylegesen ir
```

## 7. Limitek

Az UNAS API VIP csomagnal a `getCustomer`/`setCustomer` vegpontokra kulon,
szigorubb ora/hivas limitek vonatkoznak (lasd
[UNAS_API_gyakorlati_utmutato.md](UNAS_API_gyakorlati_utmutato.md) 11. fejezet es
a hivatalos [limitacios oldal](https://unas.hu/tudastar/api/limitaciok)). A
middleware sajat, ennel szigorubb belso rate limitet is alkalmaz
(`UNAS_MAX_REQUESTS_PER_SECOND`), de nagy `backfill-customers` futtatasnal erdemes
figyelni a hivasszamot, kulonosen sok vasarlonal.
