# backend/app/main.py
import os
from fastapi import FastAPI, Request
import httpx

app = FastAPI()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELE_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.post("/webhook")
async def telegram_webhook(req: Request):
    try:
        data = await req.json()
    except Exception:
        return {"ok": False, "reason": "invalid json"}

    # basic safety check
    if not isinstance(data, dict):
        return {"ok": False, "reason": "invalid payload"}

    # handle messages (basic)
    msg = data.get("message") or data.get("edited_message")
    if msg:
        chat = msg.get("chat", {})
        chat_id = chat.get("id")
        text = msg.get("text", "")
        # You can customize the reply content here
        reply_text = f"已收到: {text or '<no-text>'}"

        if chat_id:
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"{TELE_API}/sendMessage",
                    json={"chat_id": chat_id, "text": reply_text}
                )

    # Always return ok quickly
    return {"ok": True}
