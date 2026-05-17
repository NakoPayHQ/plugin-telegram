# Changelog

## [0.2.0] - 2026-05-01

### Added
- Full command set: /invoice, /tip, /balance, /rates, /refund, /export, /connect, /disconnect, /status, /help
- Multi-merchant mode via /connect (per-chat API key storage)
- Webhook receiver (Starlette ASGI) with HMAC-SHA256 verification
- CSV export via /export command
- Status emoji on invoice listings
- `X-NakoPay-Version: 2025-04-20` header
- Idempotency key auto-generation for POST requests

## [0.1.0] - 2026-04-01

### Added
- Initial bot scaffold with /invoice, /last, /help commands
- Single-merchant mode
- Long-polling Telegram integration
