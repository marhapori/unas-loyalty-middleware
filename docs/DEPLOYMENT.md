# Eles telepitesi utmutato

## Render.com (jelenleg hasznalt teszt/staging kornyezet)

A repo tartalmaz egy `render.yaml` blueprint-et. Legegyszerubb ut:

1. Render dashboard -> **New** -> **Blueprint** -> valaszd ki a GitHub repot
   (`marhapori/unas-loyalty-middleware`).
2. Render beolvassa a `render.yaml`-t, es kiirja, mely kornyezeti valtozokat kell
   kezzel megadni (`sync: false` jeloltek): `UNAS_API_KEY`,
   `UNAS_WEBHOOK_HMAC_SECRET`, `APP_BASE_URL`. Az elso kettot masold at a helyi
   `.env` fajlbol.
3. `APP_BASE_URL`-t elsore hagyd uresen vagy egy ideiglenes ertekkel - a
   telepites utan Render megmutatja a tenyleges cimet (`https://<nev>.onrender.com`),
   azt masold vissza ide, majd mentsd el ujra (ez ujra deployt indit).
4. A `SESSION_SECRET` automatikusan generalodik (`generateValue: true`), nem kell
   kezzel megadni.
5. Deploy utan a tenyleges URL-lel:
   - frissitsd a UNAS admin `customer_registration` automatizmus webhook URL-jet
     `https://<nev>.onrender.com/webhooks/unas/customer-registration`-ra;
   - frissitsd a UNAS sablon `main.cfg` `profile_loyalty_qr.payload_prefix`
     erteket `https://<nev>.onrender.com/scan/`-ra.

**Ismert korlat**: az ingyenes Render Web Service csomag lemeze **nem tartos** -
inaktivitas utani "elalvasnal" vagy uj deploynal a SQLite-fajl (es benne minden
kasszas fiok/tranzakcio) elveszhet. Ez jelenleg tudatosan elfogadott, ideiglenes
allapot a tovabbi teszteleshez (lasd a beszelgetest) - eles hasznalat elott a
Render Postgres hozzaadasa javasolt (lasd lent, "Atallas SQLite-rol Postgresre").

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
