"""NakoPay Telegram bot - self-host reference implementation."""
__version__ = "0.2.0"

from .bot import Bot, Telegram, main  # noqa: F401
from .config import Config, load  # noqa: F401
from .nakopay_client import NakoPayClient, NakoPayError  # noqa: F401
from .storage import Storage  # noqa: F401
from .webhook import verify_signature, format_event  # noqa: F401

try:
    from .webhook import app as webhook_app  # noqa: F401
except Exception:
    webhook_app = None
