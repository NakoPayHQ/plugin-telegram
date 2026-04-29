# NakoPay for Telegram

Accept Bitcoin and other crypto in Telegram chats - send `/invoice 25 USD`, get a payable checkout link back. Wallet-to-wallet, non-custodial. NakoPay never holds your funds.

[![Status](https://img.shields.io/badge/status-beta-yellow)](https://nakopay.com/integrations/telegram)
[![License](https://img.shields.io/badge/license-MIT-green)](../LICENSE)

## How this integration works

NakoPay ships an open-source Telegram bot that you run yourself, one bot per merchant account. Why self-host? Because Telegram ties a bot's identity to a single owner token, and the cleanest way to bill against your own NakoPay account is to point your own bot at your own API key.

**v0.1.0 = single-merchant mode.** Multi-merchant linking, `/balance`, and a hosted `@NakoPayBot` are on the roadmap but not in this release.

## Requirements

- A Telegram account.
- A NakoPay account (free) - <https://nakopay.com>.
- Somewhere to run a small Python container (any VPS, Fly.io, Railway, your laptop, etc.).
- 5 minutes.

## Quick start

### 1. Create your bot

1. Open <https://t.me/BotFather> in Telegram.
2. Send `/newbot`.
3. Pick a display name (e.g. "MyShop Pay") and a username ending in `bot` (e.g. `myshop_pay_bot`).
4. BotFather replies with an **HTTP API token** like `123456:ABC-DEF...`. Save it.

### 2. Get a NakoPay API key

Go to <https://nakopay.com/dashboard/api-keys>, click **Create key**, copy the `sk_test_...` value. Use `sk_test_` for sandbox, `sk_live_` for real money.

### 3. Download the bot

Either clone the mirror:

```bash
git clone https://github.com/NakoPayHQ/plugin-telegram.git
cd plugin-telegram
```

or download the zip:

```bash
curl -L -o nakopay-telegram.zip \
  https://github.com/NakoPayHQ/plugin-telegram/releases/latest/download/nakopay-telegram.zip
unzip nakopay-telegram.zip && cd telegram
```

### 4. Configure

```bash
cp .env.example .env
$EDITOR .env
```

Set:

- `TELEGRAM_BOT_TOKEN` - the token from step 1.
- `NAKOPAY_API_KEY` - the `sk_test_...` / `sk_live_...` key from step 2.

`NAKOPAY_API_BASE` defaults to the canonical hosted endpoint and you should leave it alone unless you self-host the entire NakoPay backend.

### 5. Run

With Docker (recommended):

```bash
docker compose up -d
docker compose logs -f bot
```

Or directly with Python 3.11+:

```bash
pip install -r requirements.txt
python -m nakopay_telegram.bot
```

The bot long-polls Telegram, so no inbound webhook or public URL is needed.

### 6. Use it

Open a chat with your bot in Telegram (or add it to a group) and try:

| Command | What it does |
|---|---|
| `/start` | Welcome message. |
| `/help` | List commands. |
| `/invoice 25 USD` | Creates a $25 payment link. |
| `/invoice 0.001 BTC for "Coffee"` | Creates a 0.001 BTC payment link with a description. |
| `/last` | Shows your 5 most recent invoices and their status. |

## Roadmap (not in v0.1.0)

The bot currently replies to these commands with a "not available yet" notice:

- `/connect <link_token>` - link a single hosted bot to many merchants.
- `/disconnect` - unlink.
- `/balance` - settled-balance summary across coins.

These ship once the corresponding backend endpoints (`telegram-link`, `balance`) are deployed. Track progress on the [project roadmap](https://nakopay.com/docs/integrations/telegram).

## Privacy

The bot only sees:
- The chat IDs and usernames of people who message it (so it can reply).
- The slash commands you send it.

It does not read other messages in groups, does not store chat history, and never sees private keys or wallet seeds. Your `NAKOPAY_API_KEY` lives only in your own environment.

## Support

- Issues: <https://github.com/NakoPayHQ/plugin-telegram/issues>
- Email: support@nakopay.com
- Docs: <https://nakopay.com/docs/integrations/telegram>

## License

MIT - see [`../LICENSE`](../LICENSE).
