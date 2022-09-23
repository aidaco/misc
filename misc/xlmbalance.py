import asyncio
import sys
from functools import cache

import aiohttp
from rich import print


async def hzn_req(endpoint):
    HORIZON_URL = "https://horizon.stellar.org"
    async with aiohttp.ClientSession() as session:
        async with session.get(HORIZON_URL + "/" + endpoint) as response:
            return await response.json()


async def coinbase_xlm_price():
    async with aiohttp.ClientSession() as session:
        async with session.get(
            "https://api.coinbase.com/v2/prices/XLM-USD/buy"
        ) as resp:
            json = await resp.json()
            return float(json["data"]["amount"])


async def get_account(account_id: str):
    return await hzn_req(f"accounts/{account_id}")


async def get_trades(base: tuple, counter: tuple, n: int = 200):
    """Takes tuples of (type, code, issuer)"""
    resp = await hzn_req(
        f"trades/?base_asset_type={base[0]}&base_asset_code={base[1]}&base_asset_issuer={base[2]}&counter_asset_type={counter[0]}&counter_asset_code={counter[1]}&counter_asset_issuer={counter[2]}&order=desc&limit={n}"
    )
    return resp


async def get_asset(code: str, issuer: str):
    return await hzn_req(f"assets?asset_code={code}&asset_issuer={issuer}")


async def calc_avg_xlm_price(asset: tuple):
    native = ("native", "XLM", "")
    trades = (await get_trades(native, asset))["_embedded"]["records"]
    prices = [int(t["price"]["n"]) / int(t["price"]["d"]) for t in trades]
    return sum(prices) / len(prices)


async def parse_credit_balance(balance: dict):
    asset = (balance["asset_type"], balance["asset_code"], balance["asset_issuer"])
    avg_price = await calc_avg_xlm_price(asset)
    amt = float(balance["balance"])
    return f"{balance['asset_code']}", amt, amt / avg_price


async def parse_lp_balance(balance: dict):
    shares = float(balance["balance"])
    lp_id = balance["liquidity_pool_id"]
    lp_data = await hzn_req(f"liquidity_pools/{lp_id}")
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
            data = (await get_asset(code, iss))["_embedded"]["records"][0]
            asset = (data["asset_type"], data["asset_code"], data["asset_issuer"])
            assets[asset] = amt
            total_xlm += amt / await calc_avg_xlm_price(asset)
    return f"{'/'.join(a[1] for a in assets)}", shares, total_xlm


async def display_balances(account_id):
    account = await get_account(account_id)
    balances = account["balances"]
    holdings = []
    for b in balances:
        if float(b['balance']) > 0:
            match b["asset_type"]:
                case "credit_alphanum4" | "credit_alphanum12":
                    holding = await parse_credit_balance(b)
                case "liquidity_pool_shares":
                    holding = await parse_lp_balance(b)
                case "native":
                    holding = "XLM", float(b["balance"]), float(b["balance"])
            holdings.append(holding)

    for label, amount, xlm_eq in reversed(sorted(holdings, key=lambda t: t[2])):
        print(f"{amount:8.4f} {label.ljust(15)} ≈ {xlm_eq:8.4f} XLM")
    xlm_val = sum(map(lambda t: t[2], holdings))
    print(
        "Total Value:".ljust(26)
        + f"{xlm_val:8.4f} XLM ≈ ${xlm_val * await coinbase_xlm_price():.2f}"
    )
    print(f"{len(holdings)} assets held.")


if __name__ == "__main__":
    account = sys.argv[1]
    asyncio.run(display_balances(account))
