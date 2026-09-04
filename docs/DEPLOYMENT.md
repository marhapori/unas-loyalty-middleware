# Eles telepitesi utmutato

## Render.com (jelenleg hasznalt teszt/staging kornyezet)

A repo tartalmaz egy `render.yaml` blueprint-et, de a Render "Blueprint" opcioja
nem minden fioktipusnal/regioban erheto el - ha nalad nincs, a "New Web Service"
kezi utat kell hasznalni, ugyanazokkal az ertekekkel:

- **Git Provider** fulon (nem "Public Git Repository", mert a repo privat) kosd
  ossze a GitHub-fiokot es valaszd ki a repot.
- Build Command: `pip install -e .`
- Start Command: `alembic upgrade head && uvicorn loyalty_app.main:app --host 0.0.0.0 --port $PORT`
- Kornyezeti valtozok: lasd a `render.yaml` fajl `envVars` listajat - minden
  `sync: false` jelolt erteket (`UNAS_API_KEY`, `UNAS_WEBHOOK_HMAC_SECRET`,
  `APP_BASE_URL`, `ADMIN_BOOTSTRAP_TOKEN`) kezzel kell megadni, a tobbit
  masold at onnan.
- `APP_BASE_URL`-t a deploy UTAN, a tenyleges `https://<nev>.onrender.com`
  cimmel toltsd ki, majd mentsd el ujra (ez ujra deployt indit).

### Elso bolt/admin felhasznalo letrehozasa (Shell nelkul)

Az ingyenes Render Web Service csomagnak **nincs Shell hozzaferese** (fizetos
funkcio), igy a `python -m loyalty_app.cli seed-store` / `create-user`
parancsokat nem lehet kozvetlenul futtatni a futo peldanyon. Ehelyett:

1. Allitsd be az `ADMIN_BOOTSTRAP_TOKEN` kornyezeti valtozot Render-en egy eros,
   veletlen ertekre.
2. Hivd meg a bootstrap vegpontot (pl. helyi gepedrol, curl-lal):

```bash
curl -X POST https://<nev>.onrender.com/api/admin/bootstrap \
  -H "Content-Type: application/json" \
  -H "X-Bootstrap-Token: <az ADMIN_BOOTSTRAP_TOKEN erteke>" \
  -d '{"storeName":"Fo bolt","storeCode":"BOLT01","username":"kassza1","password":"eros_jelszo_ide","role":"admin"}'
```

3. A vegpont idempotens - ha a bolt/felhasznalo mar letezik, nem hoz letre
   masodpeldanyt (`storeCreated`/`userCreated`: `false` a valaszban).
4. **Utana toroljed/uresitsd ki** az `ADMIN_BOOTSTRAP_TOKEN` erteket Render-en -
   ures ertekkel a vegpont mindig `404`-et ad vissza (alapertelmezetten
   letiltva), igy nem marad nyitva egy admin-letrehozo vegpont a neten.

**Ismert korlat**: az ingyenes Render Web Service csomag lemeze **nem tartos** -
inaktivitas utani "elalvasnal" vagy uj deploynal a SQLite-fajl (es benne minden
kasszas fiok/tranzakcio) elveszhet, es ilyenkor a fenti bootstrap-lepest ujra
el kell vegezni. Ez jelenleg tudatosan elfogadott, ideiglenes allapot a
tovabbi teszteleshez - eles hasznalat elott a Render Postgres hozzaadasa
javasolt (lasd lent, "Atallas SQLite-rol Postgresre").

## Minimalis kovetelmeny

- Egy szerver (VPS/gep), amin fut Python 3.12+.
- Publikus HTTPS URL (a webhook vegpont csak HTTPS-en fogadhato el az UNAS altal,
  es a kasszas bejelentkezes/session-cookie is HTTPS-t igenyel biztonsagosan).
- A `.env` fajlban valodi, titkos `UNAS_API_KEY`, `UNAS_WEBHOOK_HMAC_SECRET` es
  `SESSION_SECRET` ertekek.

## Telepitesi lepesek (peldaul Linux + systemd)

```bash
python3.12 -m venv /opt/loyalty-app/.venv
/opt/loyalty-app/.venv/bin/pip install -e "/opt/loyalty-app[dev]"
cp .env.example /opt/loyalty-app/.env   # majd szerkeszd
/opt/loyalty-app/.venv/bin/alembic upgrade head
```

Pelda `systemd` szolgaltatas (`/etc/systemd/system/loyalty-app.service`):

```ini
[Unit]
Description=UNAS husegpont middleware
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/loyalty-app
EnvironmentFile=/opt/loyalty-app/.env
ExecStart=/opt/loyalty-app/.venv/bin/uvicorn loyalty_app.main:app --host 127.0.0.1 --port 8000 --workers 1
Restart=on-failure
User=loyaltyapp

[Install]
WantedBy=multi-user.target
```

> **Fontos: `--workers 1`.** A SQLite-alapu konkurenciakezeles (lasd
> [ARCHITECTURE_DECISIONS.md](ARCHITECTURE_DECISIONS.md)) es a folyamaton beluli
> hatter worker csak egyetlen alkalmazasfolyamat mellett garantalt helyesen. Tobb
> workerrel vagy tobb peldannyal futtatva ugyanazon SQLite fajl ellen adatvesztes
> vagy duplikalt feldolgozas tortenhet. Ha tobb workerre/peldanyra van sziikseg,
> elobb valts Postgresre (lasd lent).

Ezutan egy reverse proxy (pl. nginx vagy Caddy) TLS-terminalva iranyitsa a
forgalmat a `127.0.0.1:8000`-re, es publikalja pl. `https://loyalty.pelda.hu`
cimen. Ez lesz az `APP_BASE_URL` es a webhook cel URL alapja is.

```nginx
server {
    listen 443 ssl;
    server_name loyalty.pelda.hu;
    ssl_certificate ...;
    ssl_certificate_key ...;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## Atallas SQLite-rol Postgresre

1. Postgres adatbazis letrehozasa.
2. `.env`: `DATABASE_URL=postgresql+psycopg://user:jelszo@host:5432/loyalty`
3. `pip install psycopg[binary]`
4. `alembic upgrade head` (a migraciok `render_as_batch`-csal keszultek, mindket
   dialektuson futnak).
5. A `systemd` service-ben a `--workers 1` korlatozas ekkor mar feloldhato -
   Postgresen a `SELECT ... FOR UPDATE` sorzarolas biztositja a helyes
   konkurenciakezelest tobb worker/peldany eseten is (lasd
   `loyalty_app/loyalty/service.py`).
6. A meglevo SQLite adatok atmasolasa kulon migracios lepes (pl. `pgloader` vagy
   sajat szkript) - ez a projekt nem tartalmaz automatikus SQLite->Postgres
   adatmigraciot.

## Mentes es visszaallitas

SQLite eseten a `data/loyalty.db` fajl rendszeres mentese (pl. `sqlite3 .backup`
paranccsal, futas kozben is konzisztens, mert WAL modban fut) eleg. Postgres
eseten hasznald a szokasos `pg_dump`/PITR megoldasokat. Teszteld idorol idore a
visszaallitast egy kulon peldanyon.

## Megfigyelhetoseg

- `GET /health/live` - folyamat elesegel-e.
- `GET /health/ready` - adatbazis-kapcsolat OK-e.
- Naplok: strukturalt, `RedactingFilter` maszkolja a kulcsszo-alapon
  titoknak nezo sorokat (lasd `security.py`), de ez csak vedohalo - soha ne
  logolj sajat kodban API-kulcsot, Bearer tokent vagy teljes QR-tokent.
- A `webhook_events` tablaban `process_status='needs_review'` vagy `'failed'`
  sorok, valamint a `loyalty_transactions` tablaban tartosan `'pending'` maradt
  sorok admin figyelmet igenyelnek.
