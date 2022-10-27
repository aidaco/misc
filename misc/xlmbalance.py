from pathlib import Path
from datetime import datetime
import sqlite3
import asyncio
import time
import json
import sys
from functools import cache
import contextlib

import aiohttp
from rich.table import Table
from rich.panel import Panel
from rich.console import Group
from rich import print
import typer


def ratelimiter(rate: float = 1.0, sync: int = 1):
    """Limit rate and concurrency to.
    rate is limit in req/sec.
    sync object controls concurrency, pass an asyncio.Semaphore(n) for n concurrent tasks.

    Default is serial requests 1/sec."""

    rate_sem = asyncio.Semaphore(value=sync)

    @contextlib.asynccontextmanager
    async def ratelimit():
        async with rate_sem:
            start = time.perf_counter()
            try:
                yield
            finally:
                if (rem := (1/rate) - (time.perf_counter() - start)) > 0:
                    await asyncio.sleep(rem)
    return ratelimit


async def hzn_req(session, ratelimit, endpoint):
    HORIZON_URL = "https://horizon.stellar.org"
    async with ratelimit():
        async with session.get(HORIZON_URL + "/" + endpoint) as response:
            return await response.json()


async def get_coinbase_xlm_price(session):
    async with session.get(
        "https://api.coinbase.com/v2/prices/XLM-USD/buy"
    ) as resp:
        json = await resp.json()
        return float(json["data"]["amount"])


async def get_trades(session, ratelimit, base: tuple, counter: tuple, n: int = 200):
    """Takes tuples of (type, code, issuer)"""
    url = f"trades/?base_asset_type={base[0]}&base_asset_code={base[1]}&base_asset_issuer={base[2]}&counter_asset_type={counter[0]}&counter_asset_code={counter[1]}&counter_asset_issuer={counter[2]}&order=desc&limit={n}"
    resp = await hzn_req(session, ratelimit, url)
    return resp


async def get_asset(session, ratelimit, code: str, issuer: str):
    return await hzn_req(session, ratelimit, f"assets?asset_code={code}&asset_issuer={issuer}")


async def calc_avg_xlm_price(session, ratelimit, asset: tuple):
    native = ("native", "XLM", "")
    trades = (await get_trades(session, ratelimit, native, asset))["_embedded"]["records"]
    prices = [int(t["price"]["n"]) / int(t["price"]["d"]) for t in trades]
    return sum(prices) / len(prices)


async def parse_credit_balance(session, ratelimit, balance: dict):
    asset = (balance["asset_type"], balance["asset_code"], balance["asset_issuer"])
    avg_price = await calc_avg_xlm_price(session, ratelimit, asset)
    amt = float(balance["balance"])
    return f"{balance['asset_code']}", amt, amt / avg_price


async def parse_lp_balance(session, ratelimit, balance: dict):
    shares = float(balance["balance"])
    lp_id = balance["liquidity_pool_id"]
    lp_data = await hzn_req(session, ratelimit, f"liquidity_pools/{lp_id}")
    pct = float(balance["balance"]) / float(lp_data["total_shares"])
    assets = {}
    total_xlm = 0
    for h in lp_data["reserves"]:
        amt = float(h["amount"]) * pct
        if h["asset"] == "native":
            assets[("native", "XLM", "")] = amt
            total_xlm += amt
        else:
            code, iss = h["asset"].split(":")
            data = (await get_asset(session, ratelimit, code, iss))["_embedded"]["records"][0]
            asset = (data["asset_type"], data["asset_code"], data["asset_issuer"])
            assets[asset] = amt
            total_xlm += amt / await calc_avg_xlm_price(session, ratelimit, asset)
    return f"{'/'.join(a[1] for a in assets)}", shares, total_xlm

async def get_holding(session, ratelimit, balance):
    match balance["asset_type"]:
        case "credit_alphanum4" | "credit_alphanum12":
            return await parse_credit_balance(session, ratelimit, balance)
        case "liquidity_pool_shares":
            return await parse_lp_balance(session, ratelimit, balance)
        case "native":
            return "XLM", float(balance["balance"]), float(balance["balance"])

async def get_holdings(session, ratelimit, pubkey: str) -> list[tuple[str, float, float]]:
    account = await hzn_req(session, ratelimit, f"accounts/{pubkey}")
    return await asyncio.gather(
        *(
            get_holding(session, ratelimit, b)
            for b in account['balances']
            if float(b['balance']) > 0
        )
    )


def ensuredb(connection):
    connection.executescript('''
        PRAGMA journal_mode=WAL;
        PRAGMA synchronous=NORMAL;
        CREATE TABLE IF NOT EXISTS holdings (
            id INTEGER PRIMARY KEY,
            pubkey TEXT NOT NULL,
            datetime TEXT UNIQUE NOT NULL,
            xlmprice REAL NOT NULL,
            data TEXT
        );
        CREATE TABLE IF NOT EXISTS updates (
            id INTEGER PRIMARY KEY,
            pubkey TEXT NOT NULL UNIQUE,
            added_at TEXT NOT NULL
        );
    ''')

DEFAULTDB = Path.cwd() / 'stellarholdings.sqlite3'

db = typer.Typer()
@db.command()
def ensure(dbfile: Path = DEFAULTDB):
    connection = sqlite3.connect(dbfile)
    ensuredb(connection)

@db.command()
def add(pubkey: str, dbfile: Path = DEFAULTDB):
    with sqlite3.connect(dbfile) as connection:
        ensuredb(connection)
        connection.execute('INSERT INTO updates (pubkey, added_at) VALUES (?, ?)', (pubkey, datetime.now().isoformat()))

@db.command()
def view(dbfile: Path = DEFAULTDB):
    with sqlite3.connect(dbfile) as connection:
        ensuredb(connection)
        tracking = [*connection.execute('SELECT pubkey, added_at FROM updates;')]
        rows = [*connection.execute('SELECT pubkey, datetime, xlmprice, data FROM holdings;')]

    t = Table(title='Tracking')
    t.add_column('PUBKEY')
    t.add_column('ADDED')
    for pk, dt in tracking:
        t.add_row(pk, dt)

    print(t)

    values = (
        (
            pk,
            dt,
            sum(
                x*xp
                for _, _, x in json.loads(d)
            )
        )
        for pk, dt, xp, d in rows
    )

    series = {}
    for pk, dt, val in values:
        series[pk] = series.get(pk, [])
        series[pk].append((dt, val))

    for pk, vals in series.items():
        t = Table(title=pk)
        t.add_column('Datetime')
        t.add_column('Value')
        for dt, val in vals:
            t.add_row(dt, f'{val:.2f}')
        print(t)


@db.command()
def update(dbfile: Path = DEFAULTDB):
    async def _get_data(pubkeys):
        async with aiohttp.ClientSession() as session:
            ratelimit = ratelimiter()
            return await asyncio.gather(
                get_coinbase_xlm_price(session),
                *(get_holdings(session, ratelimit, pubkey) for pubkey in pubkeys),
            )

    with sqlite3.connect(dbfile) as connection:
        ensuredb(connection)
        pubkeys = [r[0] for r in connection.execute('SELECT pubkey FROM updates;')]
        xlmprice, *holdings = asyncio.run(_get_data(pubkeys))
        now = datetime.now().isoformat()
        rows = [(pubkey, now, xlmprice, json.dumps(holding)) for pubkey, holding in zip(pubkeys, holdings)]
        connection.executemany('INSERT INTO holdings (pubkey, datetime, xlmprice, data) VALUES(?, ?, ?, ?)', rows)

cli = typer.Typer()
cli.add_typer(db, name='db')


@cli.command()
def value(pubkey: str):
    async def _get_data(pubkey):
        async with aiohttp.ClientSession() as session:
            ratelimit = ratelimiter()
            return await asyncio.gather(
                get_holdings(session, ratelimit, pubkey),
                get_coinbase_xlm_price(session),
            )

    holdings, xlmprice = asyncio.run(_get_data(pubkey))
    table = Table()
    table.add_column('SYM')
    table.add_column('AMT')
    table.add_column('USD')
    for label, amount, xlm in reversed(sorted(holdings, key=lambda t: t[2])):
        table.add_row(label, f'{amount:.8f}', f'{xlm*xlmprice:.2f}')
    table.add_row('-', '-', f'[green]{sum(map(lambda h: h[2], holdings))*xlmprice:.2f}[/]')
    print(table)


if __name__ == "__main__":
    cli()
