"""Errors raised by the Komari status plugin."""


class KomariError(Exception):
    """Base error for the Komari status plugin."""


class RenderTimeoutError(KomariError):
    """The page did not finish loading in time."""


class LoginFailedError(KomariError):
    """Automatic login to the Komari panel failed."""
