from __future__ import annotations

import asyncio
from dataclasses import dataclass

import typer
from sqlalchemy import select
from sqlalchemy.orm import Session

from loyalty_app.config import Settings, get_settings
from loyalty_app.db import SessionLocal
from loyalty_app.loyalty.service import issue_token_for_customer
from loyalty_app.models import Register, Store, User
from loyalty_app.security import hash_password
from loyalty_app.unas.client import UnasClient

app = typer.Typer(help="UNAS husegpont middleware - adminisztracios parancsok")

PAGE_SIZE = 100


@dataclass
class BackfillSummary:
    processed: int = 0
    created: int = 0
    skipped: int = 0
    failed: int = 0


@app.command("create-user")
def create_user(
    username: str = typer.Option(..., prompt=True),
    role: str = typer.Option("cashier", help="cashier vagy admin"),
    store_code: str = typer.Option(None, help="A vasarlohoz rendelt bolt kodja (opcionalis)"),
    password: str = typer.Option(
        None,
        help="Jelszo nem-interaktiv hasznalathoz (pl. telepito szkript). "
        "Ha nincs megadva, interaktivan (rejtve) ker be egyet.",
    ),
) -> None:
    if role not in ("cashier", "admin"):
        typer.echo("A szerepkor csak 'cashier' vagy 'admin' lehet")
        raise typer.Exit(code=1)

    if password is None:
        # hide_input prompts (Click/typer, and stdlib getpass) read straight from
        # the console device on Windows and hang under piped/non-tty stdin - use
        # --password for non-interactive/scripted use instead.
        password = typer.prompt("Jelszo", hide_input=True)
        password_confirm = typer.prompt("Jelszo megerositese", hide_input=True)
        if password != password_confirm:
            typer.echo("A ket jelszo nem egyezik")
            raise typer.Exit(code=1)

    session = SessionLocal()
    try:
        existing = session.execute(select(User).where(User.username == username)).scalar_one_or_none()
        if existing is not None:
            typer.echo(f"Mar letezik felhasznalo ezzel a nevvel: {username}")
            raise typer.Exit(code=1)

        store_id = None
        if store_code:
            store = session.execute(select(Store).where(Store.code == store_code)).scalar_one_or_none()
            if store is None:
                typer.echo(f"Nem talalhato bolt ezzel a koddal: {store_code}")
                raise typer.Exit(code=1)
            store_id = store.id

        user = User(username=username, password_hash=hash_password(password), role=role, store_id=store_id)
        session.add(user)
        session.commit()
        typer.echo(f"Letrehozva: {username} ({role})")
    finally:
        session.close()


@app.command("seed-store")
def seed_store(name: str = typer.Option(...), code: str = typer.Option(...)) -> None:
    session = SessionLocal()
    try:
        existing = session.execute(select(Store).where(Store.code == code)).scalar_one_or_none()
        if existing is not None:
            typer.echo(f"Mar letezik bolt ezzel a koddal: {code}")
            raise typer.Exit(code=1)
        store = Store(name=name, code=code)
        session.add(store)
        session.flush()
        register = Register(store_id=store.id, name=f"{name} - 1. kassza", code=f"{code}-1")
        session.add(register)
        session.commit()
        typer.echo(f"Letrehozva bolt: {name} ({code}), alapertelmezett kassza: {register.code}")
    finally:
        session.close()


@app.command("backfill-customers")
def backfill_customers(
    dry_run: bool = typer.Option(False, "--dry-run", help="Csak szamlal, nem ir a UNAS-ba"),
    limit: int = typer.Option(0, help="Legfeljebb ennyi vasarlot dolgoz fel osszesen (0 = nincs korlat)"),
) -> None:
    asyncio.run(_backfill_customers_async(dry_run=dry_run, limit=limit))


async def run_backfill(session: Session, client, settings: Settings, *, dry_run: bool, limit: int) -> BackfillSummary:
    """Core backfill loop, independent of how the UnasClient/session were built -
    this is what tests exercise directly against a fake client."""
    summary = BackfillSummary()
    offset = 0
    while True:
        page = await client.get_customers_page(limit_start=offset, limit_num=PAGE_SIZE)
        if not page:
            break
        for record in page:
            if limit and summary.processed >= limit:
                break
            summary.processed += 1
            existing_value = (record.params.get(settings.unas_loyalty_param_id) or "").strip()
            if dry_run:
                # Dry-run never writes anywhere (UNAS or local DB) - a cheap preview
                # based on this page's already-fetched param value is sufficient.
                if existing_value:
                    summary.skipped += 1
                else:
                    summary.created += 1
                continue
            try:
                # Always go through issue_token_for_customer (not just when the param
                # looks empty) so the local loyalty_customers row is upserted even for
                # customers whose UNAS param was already set some other way - keeping
                # our DB consistent with UNAS is what makes scan lookups reliable.
                result = await issue_token_for_customer(session, client, settings, record.unas_id)
                if result.created_new_token:
                    summary.created += 1
                else:
                    summary.skipped += 1
            except Exception as exc:  # noqa: BLE001
                summary.failed += 1
                typer.echo(f"HIBA vasarlo {record.unas_id}: {exc}")
        if limit and summary.processed >= limit:
            break
        if len(page) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    return summary


async def _backfill_customers_async(*, dry_run: bool, limit: int) -> None:
    settings = get_settings()
    if not settings.unas_api_key:
        typer.echo("Hianyzik a UNAS_API_KEY kornyezeti valtozo")
        raise typer.Exit(code=1)

    client = UnasClient(
        api_key=settings.unas_api_key,
        base_url=settings.unas_api_base_url,
        timeout_seconds=settings.unas_request_timeout_seconds,
        requests_per_second=settings.unas_max_requests_per_second,
    )
    session = SessionLocal()
    try:
        summary = await run_backfill(session, client, settings, dry_run=dry_run, limit=limit)
    finally:
        session.close()
        await client.aclose()

    mode = "DRY-RUN" if dry_run else "ELES"
    typer.echo(
        f"[{mode}] Feldolgozva: {summary.processed}, letrehozva: {summary.created}, "
        f"kihagyva (mar volt token): {summary.skipped}, sikertelen: {summary.failed}"
    )


if __name__ == "__main__":
    app()
