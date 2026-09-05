# Hogyan működik a rendszer, és mit kell módosítani VPS-re költözéskor

Ez a dokumentum két részből áll: (1) a rendszer működésének rövid, átfogó
leírása, hogy értsd, mi mit csinál; (2) egy konkrét, lépésenkénti útmutató és
ellenőrzőlista, ha a jelenlegi hostingról (Fly.io + Render Postgres) egy saját
VPS-re költöztetnétek.

## 1. Hogyan működik a rendszer - áttekintés

### 1.1. Mi ez az egész?

Egy önálló, kis Python-alkalmazás (`loyalty_app`), ami a fizikai bolti kasszát
köti össze a UNAS webáruház API-jával, hogy a vásárlók a saját QR-kódjukat
felmutatva pontot gyűjthessenek/válthassanak be. A UNAS maga NEM tud ilyen
bolti pontkezelést; ezt a középréteget (middleware) ezért kellett megépíteni.

### 1.2. Fő komponensek

```
┌─────────────────┐      ┌──────────────────────────┐      ┌─────────────┐
│  UNAS webáruház  │◄────►│  loyalty_app (ez a repo)  │◄────►│  Postgres   │
│  (profil-QR,     │ HTTPS│  FastAPI szerver          │ SQL  │  adatbázis  │
│  webhook, API)   │ XML  │  + háttérfolyamat         │      │             │
└─────────────────┘      └──────────────────────────┘      └─────────────┘
                                    ▲
                                    │ HTTPS (böngésző)
                                    │
                          ┌─────────────────────┐
                          │  Kasszás böngészője   │
                          │  (login + kassza UI)  │
                          └─────────────────────┘
```

- **`src/loyalty_app/main.py`** - a FastAPI alkalmazás belépési pontja. Indításkor
  elindít egy háttérfolyamatot (`worker.py`) is, ami ugyanabban a Python-
  processzben fut, párhuzamosan a webszerverrel.
- **`src/loyalty_app/unas/client.py`** - a UNAS API kliens: bejelentkezés
  (token-kezeléssel), `getCustomer`, `setCustomer` hívások, XML építés/parszolás.
  Ez az EGYETLEN hely, ahonnan a rendszer a UNAS-t hívja.
- **`src/loyalty_app/loyalty/service.py`** - az üzleti logika: QR-beolvasás
  feloldása, pont jóváírás/beváltás/visszavonás, konkurencia- és
  idempotencia-védelemmel (ugyanaz a tranzakció nem hajtódik végre kétszer).
- **`src/loyalty_app/worker.py`** - háttérfolyamat, ami percenként többször
  lefut: feldolgozza a beérkezett UNAS webhookokat (új vásárló → token
  kiosztás), és egyezteti az elakadt ("pending") tranzakciókat.
- **`src/loyalty_app/api/`** - a HTTP végpontok: bejelentkezés, kasszafelület
  (`/register`, `/scan/{token}`), a JSON API (`/api/scans/resolve`,
  `/api/loyalty/earn`, `/redeem`, `/transactions/{id}/reverse`), a UNAS
  webhook fogadó (`/webhooks/unas/customer-registration`), health-check
  végpontok, és egy admin-bootstrap végpont (lásd 1.5).
- **`src/loyalty_app/templates/`, `static/`** - a kasszafelület HTML/JS/CSS-e
  (nincs külön frontend build, sima Jinja2 + natúr JavaScript).
- **Postgres adatbázis** - 5 tábla: `stores`, `registers`, `users` (kasszás
  fiókok), `loyalty_customers` (token → UNAS vásárló-ID összerendelés, csak a
  token HASH-e van tárolva, soha nem a nyers érték), `loyalty_transactions`
  (minden pontmozgás auditnaplója), `webhook_events` (a UNAS webhookok tartós
  "postafiókja" - lásd lent).

### 1.3. A QR-kód és a `/scan/{token}` végpont

A vásárló UNAS-profiljában megjelenő QR-kód tartalmát a UNAS sablon
`main.cfg` fájljának `common_vars.profile_loyalty_qr.payload_prefix` értéke
határozza meg: a QR szövege = `payload_prefix + a vásárló 6590861-es
paraméterének értéke (a titkos token)`.

Jelenleg ez egy URL: `https://<domain>/scan/<token>` - amikor az ELADÓ a
SAJÁT telefonjával beolvassa ezt a vásárló QR-kódját, a telefon egyenesen
megnyitja ezt a linket. A `/scan/{token}` végpont:
1. Ellenőrzi, hogy az eladó be van-e jelentkezve (ha nem, a login oldalra
   irányít, majd utána visszahozza ide).
2. Automatikusan lefuttatja a vásárló-felismerést, és megjeleníti a nevét +
   pontegyenlegét - nincs kézi begépelés.

A kasszafelületen van egy kézi beviteli mező is (USB-s QR-olvasóhoz, vagy
tartalékként), ami mindkét formátumot elfogadja: a fenti URL-t ÉS a régi,
`unas-loyalty:v1:<token>` szöveges formátumot is (lásd `loyalty/qr.py`).

### 1.4. UNAS webhook - új vásárló automatikus tokenkiosztása

Amikor valaki regisztrál a webáruházban, a UNAS (ha be van állítva rá egy
automatizmus) egy webhookot küld a `/webhooks/unas/customer-registration`
végpontra. A rendszer:
1. Ellenőrzi a HMAC-aláírást (`UNAS_WEBHOOK_HMAC_SECRET`).
2. Elmenti az eseményt a `webhook_events` táblába (ez a "tartós postafiók" -
   nincs Redis/Celery, a DB-tábla maga a várólista), és azonnal `200 OK`-t ad
   vissza a UNAS-nak.
3. A háttérfolyamat (`worker.py`) néhány másodpercen belül feldolgozza:
   lekéri a vásárlót, generál egy titkos tokent, visszaírja a UNAS
   `6590861`-es paraméterébe, és elmenti a token HASH-ét a saját
   adatbázisunkba.

### 1.5. Admin-bootstrap végpont - miért van rá szükség

A `POST /api/admin/bootstrap` végpont ugyanazt csinálja, mint a
`python -m loyalty_app.cli seed-store` / `create-user` parancsok, csak
HTTP-n keresztül. Csak azért kellett, mert a Render ingyenes csomagjának
nincs Shell-hozzáférése a futó szerverhez. **Ha a VPS-en van SSH-hozzáférésed
(értelemszerűen lesz), ez a végpont feleslegessé válik** - egyszerűen
bejelentkezel SSH-val, és futtatod a CLI parancsokat közvetlenül. Az
`ADMIN_BOOTSTRAP_TOKEN` környezeti változót ilyenkor hagyd üresen (ez
alapértelmezetten letiltja a végpontot, `404`-et ad vissza).

### 1.6. Miért Fly.io, és miért nem Render

2026-09-04/05-én kiderült, hogy a Render.com (Frankfurt régió) szerverei
**nem tudták elérni a UNAS API-t** (minden hívás időtúllépéssel elszállt),
miközben ugyanez mindenhonnan máshonnan (saját gép, majd Fly.io) hibátlanul
működött. Ez egy UNAS-oldali (vagy előtte lévő védelmi réteg) IP-alapú
blokknak tűnik a Render szerverei ellen - lásd
[KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) a részletekért. **Ez azt jelenti,
hogy ha VPS-re költöztök, ELŐSZÖR ki kell próbálni, hogy az adott
szolgáltató/IP-tartomány el tudja-e érni a UNAS API-t**, mielőtt bármi mást
csináltok - lásd a 2.1 pontot.

## 2. Költözés VPS-re - lépésről lépésre

### 2.1. ELŐSZÖR: teszteld a UNAS-elérhetőséget az új szerverről

Mielőtt bármit telepítenél, egy egyszerű paranccsal ellenőrizd, hogy az új
VPS el tudja-e érni a UNAS API-t (a fenti 1.6. pont miatt fontos):

```bash
curl -v --max-time 15 -X POST https://api.unas.eu/shop/login \
  -H "Content-Type: application/xml" \
  -d '<?xml version="1.0" encoding="UTF-8"?><Params><ApiKey>TESZT</ApiKey></Params>'
```

Ha ez gyorsan válaszol (akár hibával, pl. érvénytelen kulcs miatt - a lényeg,
hogy VAN válasz, nem időtúllépés), a hálózat rendben van. Ha időtúllépést
kapsz, ne folytasd a költözést ezzel a szolgáltatóval/régióval.

### 2.2. Szerver előkészítése

```bash
# Python 3.12+, PostgreSQL kliens könyvtárak (psycopg-hez), nginx, git
sudo apt update
sudo apt install -y python3.12 python3.12-venv python3-pip nginx git

# Alkalmazás felhasználó (ne root alatt fusson)
sudo useradd -r -m -d /opt/loyalty-app loyaltyapp
sudo -u loyaltyapp git clone https://github.com/marhapori/unas-loyalty-middleware.git /opt/loyalty-app/app
cd /opt/loyalty-app/app
sudo -u loyaltyapp python3.12 -m venv /opt/loyalty-app/.venv
sudo -u loyaltyapp /opt/loyalty-app/.venv/bin/pip install -e .
```

### 2.3. Adatbázis

**Két lehetőség:**

**A) Marad a jelenlegi Render Postgres** (semmit nem kell tenni az
adatbázissal, csak a `DATABASE_URL`-t átvinni a régi szerverről az újra -
lásd 2.4). Egyszerű, de a Render Postgres díjköteles lesz egy idő után, és
egy külső szolgáltatótól függtök feleslegesen, ha már van saját VPS-etek.

**B) Saját Postgres a VPS-en** (ajánlott, ha már úgyis saját szerver van):

```bash
sudo apt install -y postgresql
sudo -u postgres psql -c "CREATE DATABASE loyalty;"
sudo -u postgres psql -c "CREATE USER loyaltyapp WITH PASSWORD 'ide-egy-eros-jelszo';"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE loyalty TO loyaltyapp;"
```

Ha B) mellett döntötök, a **meglévő adatokat át kell másolni** a Render
Postgres-ből az újba (`pg_dump` + `pg_restore`, vagy `pgloader`) - ez a
projekt nem tartalmaz automatikus migrációs szkriptet erre, külön lépésként
kell elvégezni, mielőtt éles forgalmat engedtek az új szerverre.

### 2.4. Környezeti változók (`.env`)

```bash
sudo -u loyaltyapp cp .env.example /opt/loyalty-app/app/.env
sudo -u loyaltyapp nano /opt/loyalty-app/app/.env
```

Töltsd ki mind:

| Változó | Érték |
|---|---|
| `DATABASE_URL` | `postgresql+psycopg://loyaltyapp:jelszo@localhost/loyalty` (saját DB) vagy a meglévő Render External Database URL |
| `UNAS_API_BASE_URL` | `https://api.unas.eu/shop` (nem változik) |
| `UNAS_API_KEY` | a meglévő UNAS API-kulcs (átmásolható a régi szerver `.env`/secret-jéből) |
| `UNAS_LOYALTY_PARAM_ID` | `6590861` (nem változik) |
| `UNAS_WEBHOOK_HMAC_SECRET` | a meglévő HMAC-titok (nem kell újat generálni, csak átmásolni) |
| `SESSION_SECRET` | **generálj ÚJAT** (`python -c "import secrets; print(secrets.token_urlsafe(32))"`) - ez érvényteleníti a régi szerveren bejelentkezett munkameneteket, ami itt elvárt |
| `APP_BASE_URL` | **az ÚJ, végleges publikus cím** (lásd 2.6) |
| Üzleti szabályok (`LOYALTY_*`) | a jelenleg élesben használt értékek - ellenőrizd, hogy nem maradtak-e a régi teszterték (`0.01` stb.) |
| `ADMIN_BOOTSTRAP_TOKEN` | hagyd **üresen** - VPS-en SSH-val úgyis el tudod érni a CLI-t |

### 2.5. Migrációk és systemd szolgáltatás

```bash
cd /opt/loyalty-app/app
sudo -u loyaltyapp /opt/loyalty-app/.venv/bin/alembic upgrade head
```

Hozz létre egy `/etc/systemd/system/loyalty-app.service` fájlt:

```ini
[Unit]
Description=UNAS husegpont middleware
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/loyalty-app/app
EnvironmentFile=/opt/loyalty-app/app/.env
ExecStart=/opt/loyalty-app/.venv/bin/uvicorn loyalty_app.main:app --host 127.0.0.1 --port 8000 --workers 1
Restart=on-failure
User=loyaltyapp

[Install]
WantedBy=multi-user.target
```

> **Miért `--workers 1`?** A háttérfolyamat (webhook-feldolgozás) csak EGY
> processzben szabad, hogy fusson - ha több workert indítasz, minden webhook
> többször is feldolgozódna. Postgresen ez nem okoz adatvesztést/hibát
> (a `SELECT ... FOR UPDATE` zárolás miatt), csak felesleges duplikált
> munkát - de egyelőre maradjunk 1 workernél, amíg ez nincs külön kezelve.

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now loyalty-app
sudo systemctl status loyalty-app
```

Első bolt/admin felhasználó SSH-n keresztül:

```bash
sudo -u loyaltyapp /opt/loyalty-app/.venv/bin/python -m loyalty_app.cli seed-store --name "Bolt neve" --code KOD
sudo -u loyaltyapp /opt/loyalty-app/.venv/bin/python -m loyalty_app.cli create-user --username eladonev --role admin --store-code KOD
```

### 2.6. Domain, TLS, reverse proxy

Ha a jelenlegi `hutseg.trendidivat.hu` domaint viszitek tovább (ajánlott, ne
kelljen megint a UNAS-oldali beállításokat módosítani), csak a DNS A/AAAA
rekordját kell átírni az ÚJ szerver IP-címére. Ha új domaint választotok,
frissíteni kell mindent, ami a domainre hivatkozik (lásd 2.7).

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d hutseg.trendidivat.hu
```

Nginx reverse proxy (`/etc/nginx/sites-available/loyalty-app`):

```nginx
server {
    listen 443 ssl;
    server_name hutseg.trendidivat.hu;
    # a certbot automatikusan kitolti a ssl_certificate sorokat

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/loyalty-app /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

### 2.7. Amit MINDENKÉPP frissíteni kell máshol (nem a kódban)

Ha a domain NEM változik (csak a mögötte lévő szerver), ezt a két pontot
**nem** kell módosítani. Ha a domain is változik, mindkettőt igen:

1. **UNAS admin → Automatizmusok → `customer_registration` webhook URL-je**:
   `https://<vegleges-domain>/webhooks/unas/customer-registration`
2. **UNAS sablon `main.cfg` → `common_vars.profile_loyalty_qr.payload_prefix`**:
   `https://<vegleges-domain>/scan/`

### 2.8. Ellenőrzőlista éles váltás előtt

- [ ] `curl` teszt a UNAS API-hoz az új szerverről sikeres (2.1)
- [ ] Adatbázis elérhető, migrációk lefutottak (`alembic current` mutatja a
      legutolsó revíziót)
- [ ] `GET /health/live` és `/health/ready` `200 OK`-t ad az új szerveren
- [ ] Be lehet jelentkezni egy meglévő kasszás fiókkal
- [ ] `/scan/<ismert-token>` végpont helyesen mutatja a tesztvásárlót
- [ ] Egy teszt jóváírás/beváltás ténylegesen frissíti a UNAS-oldali
      pontegyenleget (független `getCustomer` lekérdezéssel ellenőrizve)
- [ ] Ha a domain változott: UNAS webhook URL és `main.cfg` frissítve, majd
      egy teszt regisztrációval a webhook-feldolgozás is ellenőrizve
- [ ] `ADMIN_BOOTSTRAP_TOKEN` üresen van hagyva (végpont `404`-et ad)
- [ ] A régi szerver (Fly.io app) csak EZUTÁN állítható le, hogy legyen
      visszaút, ha valami nem stimmel
