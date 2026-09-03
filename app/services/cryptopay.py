"""
CryptoBot Crypto Pay API client на чистом aiohttp.
Поддержка http/https и socks-прокси (через aiohttp_socks.ProxyConnector).
"""
import logging
from typing import Optional

import aiohttp

from app.config import settings

MAINNET_URL = "https://pay.crypt.bot/api"
TESTNET_URL = "https://testnet-pay.crypt.bot/api"
TIMEOUT = aiohttp.ClientTimeout(total=30)


def _base_url() -> str:
    return MAINNET_URL if settings.CRYPTO_BOT_IS_MAINNET else TESTNET_URL


def _headers() -> dict:
    return {"Crypto-Pay-API-Token": settings.CRYPTO_BOT_TOKEN}


def _get_proxy() -> Optional[str]:
    # Можно использовать отдельный прокси для крипты или общий
    return settings.PROXY_URL_CRYPTO or settings.PROXY_URL


def _is_socks(proxy: Optional[str]) -> bool:
    return bool(proxy) and proxy.lower().startswith("socks")


class _Session:
    """Обёртка: создаёт сессию с обычным или socks-коннектором."""

    def __init__(self, proxy: Optional[str]):
        self.proxy = proxy
        self._session = None
        self._connector_owner = False

    async def __aenter__(self):
        proxy = self.proxy
        if proxy and _is_socks(proxy):
            # aiohttp не умеет socks через параметр proxy — нужен ProxyConnector
            from aiohttp_socks import ProxyConnector
            connector = ProxyConnector.from_url(proxy)
            self._session = aiohttp.ClientSession(connector=connector, timeout=TIMEOUT)
        else:
            self._session = aiohttp.ClientSession(timeout=TIMEOUT)
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        if self._session is not None:
            await self._session.close()


async def _post(method: str, body: dict) -> dict:
    url = f"{_base_url()}/{method}"
    proxy = _get_proxy()
    async with _Session(proxy) as session:
        kwargs = {"headers": _headers(), "json": body}
        if proxy and not _is_socks(proxy):
            kwargs["proxy"] = proxy
        async with session.post(url, **kwargs) as resp:
            data = await resp.json(content_type=None)
    if not data.get("ok"):
        error = data.get("error", {})
        raise Exception(f"CryptoBot API error {error.get('code')}: {error.get('name')}")
    return data["result"]


class CryptoInvoice:
    def __init__(self, data: dict):
        self.invoice_id = data.get("invoice_id")
        self.status = data.get("status")
        self.asset = data.get("asset")
        self.amount = data.get("amount")
        self.bot_invoice_url = data.get("bot_invoice_url")
        self.mini_app_invoice_url = data.get("mini_app_invoice_url")
        self.raw = data


async def create_infinite_invoice(asset: str, amount: float, description: str, payload: str = None,
                                  allow_anonymous: bool = True):
    body = {
        "asset": asset.upper(),
        "amount": str(amount),
        "description": description[:1024],
        "allow_anonymous": allow_anonymous,
        "allow_comments": True,
    }
    if payload:
        body["payload"] = payload[:128]
    logging.info(f"CRYPTOPAY: create invoice {amount} {asset}")
    result = await _post("createInvoice", body)
    return CryptoInvoice(result)


async def get_invoice_status(invoice_id: int):
    result = await _post("getInvoices", {"invoice_ids": str(invoice_id)})
    items = result.get("items", [])
    return CryptoInvoice(items[0]) if items else None


async def check_invoice_paid(invoice_id: int) -> bool:
    inv = await get_invoice_status(invoice_id)
    return bool(inv and inv.status == "paid")


def get_crypto_client():
    return None
