"""Private, SUPERUSER-only QR login helpers for the shared credential store."""

from __future__ import annotations

import asyncio
import io
from collections.abc import Awaitable, Callable
from time import monotonic

import qrcode

from .credential import BilibiliCredential, CredentialManager
from .errors import BilibiliAPIError, BilibiliQRCodeExpiredError, BilibiliQRCodeTimeoutError


QR_LOGIN_TIMEOUT = 180
QR_LOGIN_POLL_INTERVAL = 2.0


def make_qr_png(url: str) -> bytes:
    """Encode Bilibili's one-time login URL locally; never send it to another service."""
    if not url.strip():
        raise ValueError("Bilibili QR login URL was empty")
    code = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    code.add_data(url)
    code.make(fit=True)
    image = code.make_image(fill_color="black", back_color="white")
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


async def wait_for_qr_login(
    client,
    credentials: CredentialManager,
    key: str,
    *,
    timeout: float = QR_LOGIN_TIMEOUT,
    poll_interval: float = QR_LOGIN_POLL_INTERVAL,
    on_scanned: Callable[[], Awaitable[None]] | None = None,
) -> BilibiliCredential:
    """Wait for Bilibili confirmation and persist only the confirmed Cookie."""
    deadline = monotonic() + timeout
    scanned_reported = False
    while monotonic() < deadline:
        result = await client.poll_qr_login(key)
        if result.status == "confirmed":
            return credentials.save_qr_cookie(result.cookie)
        if result.status == "expired":
            raise BilibiliQRCodeExpiredError("Bilibili QR login expired")
        if result.status == "scanned":
            if not scanned_reported:
                scanned_reported = True
                if on_scanned is not None:
                    await on_scanned()
        elif result.status != "waiting":
            raise BilibiliAPIError("Bilibili QR login returned an unknown status")
        remaining = deadline - monotonic()
        if remaining > 0:
            await asyncio.sleep(min(poll_interval, remaining))
    raise BilibiliQRCodeTimeoutError("Bilibili QR login timed out")
