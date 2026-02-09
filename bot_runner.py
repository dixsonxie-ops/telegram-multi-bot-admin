import asyncio
import sqlite3
import re
import time
import hashlib
import httpx
import os
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

# Railway 持久化磁盘建议挂载到 /app/data
DATA_DIR = os.environ.get("DATA_DIR", "data")
os.makedirs(DATA_DIR, exist_ok=True)

DB_FILE = os.path.join(DATA_DIR, "bot.db")

# ⚠️ 重要：请在 Railway 环境变量中设置 ROBOT_SECRET_KEY
ROBOT_SECRET_KEY = os.environ.get("ROBOT_SECRET_KEY", "RobotSecret123456")

def db_connect():
    conn = sqlite3.connect(DB_FILE, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn

def get_enabled_bots():
    conn = db_connect()
    bots = conn.execute("SELECT * FROM bots WHERE enabled=1 ORDER BY id ASC").fetchall()
    conn.close()
    return bots

def load_rules_for_bot(bot_id: int):
    conn = db_connect()
    rows = conn.execute("SELECT * FROM rules WHERE enabled=1 AND bot_id=? ORDER BY id DESC", (bot_id,)).fetchall()
    conn.close()
    return rows

def set_heartbeat(bot_id: int):
    conn = db_connect()
    conn.execute(
        "INSERT INTO status (bot_id, key, value) VALUES (?, 'bot_last_seen', ?) "
        "ON CONFLICT(bot_id, key) DO UPDATE SET value=excluded.value",
        (bot_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )
    conn.commit()
    conn.close()

def write_log(bot_id, rule_id, message_type, message_text):
    conn = db_connect()
    conn.execute(
        "INSERT INTO logs (ts, bot_id, rule_id, message_type, message_text) VALUES (?, ?, ?, ?, ?)",
        (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), bot_id, rule_id, message_type, (message_text or "")[:5000])
    )
    conn.commit()
    conn.close()

def normalize_list(s: str):
    s = (s or "").replace("，", ",").strip()
    return [x.strip() for x in s.split(",") if x.strip()]

def normalize_keywords(keyword_field: str):
    k = (keyword_field or "").strip()
    if k == "*":
        return ["*"]
    return normalize_list(k)

def normalize_user_ids(rule_row):
    ids = (rule_row["user_ids"] if "user_ids" in rule_row.keys() else "") or ""
    ids = ids.strip()
    if ids:
        return set(normalize_list(ids))
    old = str(rule_row["user_id"] or "").strip()
    return set([old]) if old else set()

def extract_text_for_match(msg):
    return msg.text or msg.caption or ""

def detect_message_type(msg):
    if msg.text: return "text"
    if msg.photo: return "photo"
    if msg.video: return "video"
    if msg.document: return "document"
    if msg.audio: return "audio"
    if msg.voice: return "voice"
    if msg.sticker: return "sticker"
    if msg.animation: return "animation"
    return "other"

def merge_text(original: str, append_text: str) -> str:
    original = (original or "").strip()
    append_text = (append_text or "").strip()
    if not append_text:
        return original
    if not original:
        return append_text
    return f"{original}\n\n{append_text}".strip()

async def send_as_bot(update: Update, context: ContextTypes.DEFAULT_TYPE, target_group_id: str, final_text: str):
    msg = update.message
    if not msg:
        return

    has_media = bool(msg.photo or msg.video or msg.document or msg.audio or msg.voice or msg.animation or msg.sticker)

    if not has_media:
        await context.bot.send_message(chat_id=target_group_id, text=final_text)
        return

    try:
        if msg.caption is not None:
            await context.bot.copy_message(
                chat_id=target_group_id,
                from_chat_id=msg.chat_id,
                message_id=msg.message_id,
                caption=final_text
            )
        else:
            await context.bot.copy_message(
                chat_id=target_group_id,
                from_chat_id=msg.chat_id,
                message_id=msg.message_id
            )
            await context.bot.send_message(chat_id=target_group_id, text=final_text)
    except Exception:
        await context.bot.send_message(chat_id=target_group_id, text=final_text)

def robot_sign(params: dict, secret_key: str) -> str:
    items = []
    for k in sorted(params.keys()):
        if k == "sign":
            continue
        v = params.get(k)
        if v is None:
            continue
        sv = str(v).strip()
        if sv == "":
            continue
        items.append(f"{k}={sv}")
    raw = "&".join(items) + f"&key={secret_key}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest().upper()

async def call_pay_api(base_api: str, query_params: dict) -> dict:
    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        r = await client.get(base_api, params=query_params)
        r.raise_for_status()
        return r.json()

async def query_pay_order_by_mch_order_no(mch_order_no: str, base_api: str):
    async def do_request(ts: str) -> dict:
        params = {"mchOrderNo": mch_order_no, "timestamp": ts}
        params["sign"] = robot_sign(params, ROBOT_SECRET_KEY)
        return await call_pay_api(base_api, params)

    ts_ms = str(int(time.time() * 1000))
    ts_s = str(int(time.time()))

    last = None
    for ts in (ts_ms, ts_s):
        try:
            js = await do_request(ts)
            last = js
            if js.get("code") == 0:
                data = js.get("data") or {}
                pay_order_id = data.get("payOrderId")
                if pay_order_id:
                    return str(pay_order_id), f"OK(ts={ts})"
        except Exception as e:
            last = {"exception": str(e), "ts": ts}
    return None, f"FAIL(resp={last})"

async def build_app(bot_id: int, token: str, name: str) -> Application:
    app = Application.builder().token(token).build()

    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
        set_heartbeat(bot_id)
        if update.message:
            await update.message.reply_text(f"✅ {name} 已启动（bot_id={bot_id}）")

    async def monitor(update: Update, context: ContextTypes.DEFAULT_TYPE):
        set_heartbeat(bot_id)
        msg = update.message
        if not msg:
            return

        chat_id = str(update.effective_chat.id)
        user_id = str(update.effective_user.id)
        text_for_match = extract_text_for_match(msg)
        msg_type = detect_message_type(msg)

        rules = load_rules_for_bot(bot_id)

        for r in rules:
            rule_id = int(r["id"])
            source_group_id = str(r["source_group_id"])
            target_group_id = str(r["target_group_id"])
            action_type = (r["action_type"] or "edit_send").strip()

            if chat_id != source_group_id:
                continue

            allowed_users = normalize_user_ids(r)
            if allowed_users and user_id not in allowed_users:
                continue

            keys = normalize_keywords(str(r["keyword"]))
            matched = None
            if keys == ["*"]:
                matched = "*"
            else:
                if not text_for_match:
                    continue
                for k in keys:
                    if k in text_for_match:
                        matched = k
                        break
            if matched is None:
                continue

            # 功能3：自动回复
            if action_type == "auto_reply":
                reply_text = (r["reply_text"] or "").strip() or "✅ 已收到"
                try:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=reply_text,
                        reply_to_message_id=msg.message_id
                    )
                except Exception:
                    await context.bot.send_message(chat_id=chat_id, text=reply_text)

                write_log(bot_id, rule_id, msg_type, f"[自动回复] 用户:{user_id} kw:{matched}\n{reply_text}")
                return

            # 功能1：编辑后发送
            if action_type == "edit_send":
                append_text = r["append_text"] or ""
                final_text = merge_text(text_for_match, append_text)
                await send_as_bot(update, context, target_group_id, final_text)
                write_log(bot_id, rule_id, msg_type, final_text)
                return

            # 功能2：查询替换后发送
            if action_type == "lookup_replace":
                merchant_regex = r["merchant_regex"] or r"商户订单号[:：]\s*([A-Za-z0-9_-]+)"
                base_api = (r["lookup_url"] or "").strip()
                replace_template = (r["replace_template"] or "支付订单号：{{pay}}").strip()

                if not base_api:
                    final_text = f"{text_for_match}\n\n⚠️ 规则未配置 lookup_url（查询接口URL）"
                    await send_as_bot(update, context, target_group_id, final_text)
                    write_log(bot_id, rule_id, msg_type, final_text)
                    return

                m = re.search(merchant_regex, text_for_match or "")
                if not m:
                    continue

                mch_order_no = m.group(1)
                pay_order_id, debug = await query_pay_order_by_mch_order_no(mch_order_no, base_api)

                if not pay_order_id:
                    final_text = f"{text_for_match}\n\n⚠️ 未查询到支付订单号（商户订单号：{mch_order_no}）\n调试：{debug}"
                    await send_as_bot(update, context, target_group_id, final_text)
                    write_log(bot_id, rule_id, msg_type, final_text)
                    return

                replacement = replace_template.replace("{{pay}}", pay_order_id).replace("{pay}", pay_order_id)
                final_text = re.sub(merchant_regex, replacement, text_for_match, count=1)

                await send_as_bot(update, context, target_group_id, final_text)
                write_log(bot_id, rule_id, msg_type, final_text)
                return

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, monitor))
    return app

async def run_one_bot(bot_id: int, token: str, name: str):
    app = await build_app(bot_id, token, name)
    print(f"🤖 启动机器人 bot_id={bot_id} name={name}")
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    await asyncio.Event().wait()

async def main():
    tasks = {}
    while True:
        enabled = get_enabled_bots()
        enabled_ids = {int(b["id"]) for b in enabled}

        for b in enabled:
            bot_id = int(b["id"])
            if bot_id in tasks and not tasks[bot_id].done():
                continue
            token = str(b["token"]).strip()
            name = str(b["name"]).strip()
            if not token:
                print(f"⚠️ bot_id={bot_id} token 为空，跳过")
                continue
            tasks[bot_id] = asyncio.create_task(run_one_bot(bot_id, token, name))

        for bot_id in list(tasks.keys()):
            if bot_id not in enabled_ids:
                t = tasks[bot_id]
                if not t.done():
                    t.cancel()
                del tasks[bot_id]
                print(f"🛑 已停止 bot_id={bot_id}（后台已禁用）")

        await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())
