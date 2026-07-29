"""
CryptoBot Crypto Pay API client на чистом aiohttp.
Поддержка прокси для обхода блокировок.
"""
import aiohttp
from app.config import settings

MAINNET_URL = "https://pay.crypt.bot/api"
TESTNET_URL = "https://testnet-pay.crypt.bot/api"

def _base_url() -> str:
    return MAINNET_URL if settings.CRYPTO_BOT_IS_MAINNET else TESTNET_URL

def _headers() -> dict:
    return {"Crypto-Pay-API-Token": settings.CRYPTO_BOT_TOKEN}

def _get_proxy():
    # Можно использовать отдельный прокси для крипты или общий
    return settings.PROXY_URL_CRYPTO or settings.PROXY_URL

class CryptoInvoice:
    def __init__(self, data: dict):
        self.invoice_id = data.get("invoice_id")
        self.status = data.get("status")
        self.asset = data.get("asset")
        self.amount = data.get("amount")
        self.bot_invoice_url = data.get("bot_invoice_url")
        self.mini_app_invoice_url = data.get("mini_app_invoice_url")
        self.raw = data

async def create_infinite_invoice(asset: str, amount: float, description: str, payload: str = None, allow_anonymous: bool = True):
    url = f"{_base_url()}/createInvoice"
    body = {
        "asset": asset.upper(),
        "amount": str(amount),
        "description": description[:1024],
        "allow_anonymous": allow_anonymous,
        "allow_comments": True,
    }
    if payload:
        body["payload"] = payload[:128]

    proxy = _get_proxy()
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=_headers(), json=body, proxy=proxy) as resp:
            data = await resp.json()
            if not data.get("ok"):
                raise Exception(f"CryptoBot API error: {data}")
            return CryptoInvoice(data["result"])

async def get_invoice_status(invoice_id: int):
    url = f"{_base_url()}/getInvoices"
    proxy = _get_proxy()
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=_headers(), json={"invoice_ids": str(invoice_id)}, proxy=proxy) as resp:
            data = await resp.json()
            items = data.get("result", {}).get("items", [])
            return CryptoInvoice(items[0]) if items else None

async def check_invoice_paid(invoice_id: int) -> bool:
    inv = await get_invoice_status(invoice_id)
    return bool(inv and inv.status == "paid")

def get_crypto_client():
    return None
