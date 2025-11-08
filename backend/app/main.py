# backend/app/main.py
import os
import re
import logging
import httpx
from fastapi import FastAPI, Request, BackgroundTasks, HTTPException

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("telegram_bot")

app = FastAPI()


# ---------- Health ----------
@app.get("/health")
async def health():
    return {"status": "ok"}


# ---------- Utilities ----------
def escape_markdown_v2(text: str) -> str:
    """
    Escape characters according to Telegram MarkdownV2 rules.
    Characters to escape: _ * [ ] ( ) ~ ` > # + - = | { } . !
    """
    if not isinstance(text, str):
        return text
    return re.sub(r'([_*\[\]\(\)~`>#+\-=|{}\.!])', r'\\\1', text)


async def send_message_async(token: str, chat_id: int, text: str, parse_mode: str = "MarkdownV2"):
    """
    Send message via Telegram HTTP API.
    Tries with parse_mode (MarkdownV2) after escaping; on 400 will retry without parse_mode.
    """
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    async with httpx.AsyncClient(timeout=15.0) as client:
        # Prepare payload text depending on parse_mode
        payload_text = text
        if parse_mode == "MarkdownV2":
            payload_text = escape_markdown_v2(text)
        payload = {"chat_id": chat_id, "text": payload_text}
        if parse_mode:
            payload["parse_mode"] = parse_mode
        try:
            resp = await client.post(url, json=payload)
            logger.info("sendMessage status: %s %s", resp.status_code, resp.text)
            # If Telegram returns 400 for entity parse errors, retry without parse_mode
            if resp.status_code == 400 and parse_mode:
                logger.warning("Markdown parse error, retrying without parse_mode")
                fallback = {"chat_id": chat_id, "text": text}
                resp2 = await client.post(url, json=fallback)
                logger.info("sendMessage fallback status: %s %s", resp2.status_code, resp2.text)
                return resp2.json()
            return resp.json()
        except Exception as e:
            logger.exception("Failed to sendMessage: %s", e)
            return None


def parse_command(text: str):
    """
    Return (cmd, args) where cmd includes leading '/', args is remainder string or ''.
    If text is not a command, returns (None, text).
    """
    if not text:
        return (None, "")
    text = text.strip()
    if not text.startswith("/"):
        return (None, text)
    parts = text.split(" ", 1)
    cmd = parts[0].lower()
    args = parts[1].strip() if len(parts) > 1 else ""
    return (cmd, args)


# ---------- Webhook ----------
@app.post("/webhook")
async def receive_webhook(request: Request, background_tasks: BackgroundTasks):
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN not set in environment")
        raise HTTPException(status_code=500, detail="Bot token not configured")

    admin_key = os.getenv("ADMIN_API_KEY", "")

    try:
        update = await request.json()
    except Exception:
        logger.exception("Invalid JSON in webhook")
        raise HTTPException(status_code=400, detail="Invalid JSON")

    logger.info("Received update: %s", update)

    # locate message text and chat_id
    chat_id = None
    text = None
    user_info = {}
    if "message" in update:
        msg = update["message"]
        chat_id = msg.get("chat", {}).get("id")
        text = msg.get("text") or msg.get("caption") or ""
        user_info = {
            "id": msg.get("from", {}).get("id"),
            "username": msg.get("from", {}).get("username"),
            "first_name": msg.get("from", {}).get("first_name"),
        }
    elif "edited_message" in update:
        msg = update["edited_message"]
        chat_id = msg.get("chat", {}).get("id")
        text = msg.get("text") or ""
    elif "callback_query" in update:
        cq = update["callback_query"]
        chat_id = cq.get("message", {}).get("chat", {}).get("id")
        text = cq.get("data", "")

    # if no chat_id, acknowledge
    if not chat_id:
        return {"ok": True, "info": "no chat_id"}

    cmd, args = parse_command(text)

    # default reply
    reply_text = None

    # COMMAND: /start
    if cmd == "/start":
        reply_text = (
            "Hello! I'm alive and running. 🤖\n\n"
            "Available commands:\n"
            "/help - show help\n"
            "/info - bot info\n"
            "/echo <text> - echo back text\n"
            "/setlang <zh|en> - set language\n"
            "/about - about this bot\n\n"
            "If you are an admin, use:\n"
            "/broadcast <admin_key>|<message>  (admin only)"
        )

    # COMMAND: /help
    elif cmd == "/help":
        reply_text = (
            "*Help*\n"
            "/start - start the bot\n"
            "/help - this message\n"
            "/info - info about bot\n"
            "/echo <text> - bot will repeat your text\n"
            "/setlang <zh|en> - set preferred language\n"
            "/about - about this bot\n"
        )

    # COMMAND: /info
    elif cmd == "/info":
        reply_text = "This bot is deployed on Render. It supports basic commands and admin broadcast."

    # COMMAND: /echo
    elif cmd == "/echo":
        reply_text = args if args else "Usage: /echo <text>"

    # COMMAND: /setlang
    elif cmd == "/setlang":
        if args.lower() in ("zh", "cn", "zh-cn"):
            reply_text = "语言已设置为中文 (zh)."
        elif args.lower() in ("en", "en-us"):
            reply_text = "Language set to English (en)."
        else:
            reply_text = "Usage: /setlang <zh|en>"

    # COMMAND: /about
    elif cmd == "/about":
        reply_text = "Telegram group management bot — basic demo. Extend me with features you need."

    # ADMIN COMMAND: /broadcast <admin_key>|<message>
    elif cmd == "/broadcast":
        # expect args like "ADMINKEY|message to send"
        if "|" not in args:
            reply_text = "Usage: /broadcast <admin_key>|<message>"
        else:
            provided_key, bmsg = args.split("|", 1)
            provided_key = provided_key.strip()
            bmsg = bmsg.strip()
            if provided_key and provided_key == admin_key:
                # Demo: reply to admin acknowledging broadcast
                reply_text = f"Broadcast accepted. (Demo mode) Would send: {bmsg}"
                # Real implementation: fetch target chat IDs from DB and loop-send in background
            else:
                reply_text = "Invalid admin key. Access denied."

    # fallback for non-command messages
    else:
        if not cmd:
            reply_text = f"已收到: {text}" if text else "Message received."

    # send reply in background to keep webhook fast
    if reply_text:
        background_tasks.add_task(send_message_async, token, chat_id, reply_text)
    return {"ok": True}
