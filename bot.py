import logging
import os
import re
from decimal import Decimal, InvalidOperation
from telegram import (
    Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
    InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
    ContextTypes, ConversationHandler, CallbackQueryHandler
)
import asyncpg
from datetime import date, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# --- Variáveis de ambiente ---
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
POSTGRES_URL = os.environ.get("POSTGRES_URL")

# --- Estados ---
(
    ASK_CLIENT_NAME, ASK_CLIENT_PHONE, ASK_CLIENT_PACKAGE, ASK_CLIENT_VALUE,
    ASK_CLIENT_DUE, ASK_CLIENT_SERVER, ASK_CLIENT_EXTRA,
    EDIT_FIELD, SEND_MESSAGE, RENEW_DATE,
    TEMPLATE_ACTION, TEMPLATE_NAME, TEMPLATE_CONTENT, TEMPLATE_EDIT
) = range(14)

# ==============================
# Utilitários
# ==============================
def parse_date(dtstr: str | None):
    if not dtstr:
        return None
    dtstr = dtstr.strip()
    try:
        return date.fromisoformat(dtstr)
    except Exception:
        pass
    try:
        d, m, y = map(int, dtstr.split("/"))
        return date(y, m, d)
    except Exception:
        return None

def parse_money(txt: str | None) -> Decimal:
    if not txt:
        return Decimal("0")
    s = txt.strip()
    s = re.sub(r"[^0-9,\.]", "", s)
    if "," in s and "." in s:
        s = s.replace(".", "")
    s = s.replace(",", ".")
    if s == "":
        return Decimal("0")
    try:
        return Decimal(s)
    except InvalidOperation:
        return Decimal("0")

def fmt_money(val: Decimal) -> str:
    q = val.quantize(Decimal("0.01"))
    inteiro, _, frac = f"{q:.2f}".partition(".")
    inteiro = f"{int(inteiro):,}".replace(",", ".")
    return f"{inteiro},{frac}"

def month_bounds(today: date | None = None):
    if not today:
        today = date.today()
    start = today.replace(day=1)
    if start.month == 12:
        next_month_start = date(start.year + 1, 1, 1)
    else:
        next_month_start = date(start.year, start.month + 1, 1)
    end = next_month_start - timedelta(days=1)
    return start, end

def cycle_days_from_package(pacote: str | None) -> int:
    mapping = {
        "📅 MENSAL": 30,
        "📆 TRIMESTRAL": 90,
        "📅 SEMESTRAL": 180,
        "📅 ANUAL": 365,
    }
    if not pacote:
        return 30
    key = pacote.strip().upper()
    return mapping.get(key, 30)

# =================
# Banco de Dados
# =================
async def create_pool():
    return await asyncpg.create_pool(dsn=POSTGRES_URL)

async def init_db(pool):
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS clientes (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                nome TEXT NOT NULL,
                telefone TEXT,
                pacote TEXT,
                valor TEXT,
                vencimento TEXT,
                servidor TEXT,
                outras_informacoes TEXT,
                status_pagamento TEXT DEFAULT 'pendente',
                data_pagamento TEXT
            );
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS templates (
                id SERIAL PRIMARY KEY,
                nome TEXT UNIQUE NOT NULL,
                conteudo TEXT NOT NULL
            );
        """)

async def add_cliente(pool, user_id, nome, telefone, pacote, valor, vencimento, servidor, outras_informacoes):
    async with pool.acquire() as conn:
        return await conn.fetchval(
            """INSERT INTO clientes 
               (user_id, nome, telefone, pacote, valor, vencimento, servidor, outras_informacoes)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8) RETURNING id""",
            user_id, nome, telefone, pacote, valor, vencimento, servidor, outras_informacoes
        )

async def get_cliente(pool, cid: int, user_id: int):
    async with pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM clientes WHERE id=$1 AND user_id=$2", cid, user_id)

async def get_template(pool, nome: str):
    async with pool.acquire() as conn:
        return await conn.fetchrow("SELECT conteudo FROM templates WHERE nome=$1", nome)

# =================
# Templates
# =================
def aplicar_template(conteudo: str, cliente: dict) -> str:
    hoje = date.today()
    venc = parse_date(cliente["vencimento"]) if cliente["vencimento"] else None
    dias_rest = (venc - hoje).days if venc else "N/A"
    return conteudo.format(
        nome=cliente["nome"],
        telefone=cliente["telefone"],
        pacote=cliente["pacote"],
        valor=cliente["valor"],
        vencimento=cliente["vencimento"],
        servidor=cliente["servidor"],
        dias_restantes=dias_rest
    )

async def enviar_notificacoes(context: ContextTypes.DEFAULT_TYPE):
    pool = context.application.bot_data["pool"]
    async with pool.acquire() as conn:
        clientes = await conn.fetch("SELECT * FROM clientes")
    hoje = date.today()
    for c in clientes:
        venc = parse_date(c["vencimento"])
        if not venc:
            continue
        dias = (venc - hoje).days
        if dias in (-2, -1, 0, 1):
            tpl = await get_template(pool, f"aviso_{dias}")
            if tpl:
                msg = aplicar_template(tpl["conteudo"], c)
                logging.info(f"Mensagem para {c['nome']}: {msg}")
                # Aqui poderia usar context.bot.send_message()

# =========
# Teclados
# =========
menu_keyboard = ReplyKeyboardMarkup(
    [
        [KeyboardButton("ADICIONAR CLIENTE")],
        [KeyboardButton("LISTAR CLIENTES")],
        [KeyboardButton("GERENCIAR TEMPLATES")]
    ],
    resize_keyboard=True
)

cancel_keyboard = ReplyKeyboardMarkup(
    [[KeyboardButton("❌ Cancelar / Menu Principal")]],
    resize_keyboard=True
)

# =========
# Cancelar
# =========
async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ Operação cancelada. Voltando ao menu.", reply_markup=menu_keyboard)
    return ConversationHandler.END

# =========
# Templates CRUD
# =========
async def templates_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [
        [KeyboardButton("➕ Adicionar Template")],
        [KeyboardButton("📋 Listar Templates")],
        [KeyboardButton("❌ Cancelar / Menu Principal")]
    ]
    await update.message.reply_text("📂 Menu de Templates:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
    return TEMPLATE_ACTION

async def template_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    choice = update.message.text
    if choice == "➕ Adicionar Template":
        await update.message.reply_text("Digite o nome do template (ex: aviso_-1):", reply_markup=cancel_keyboard)
        return TEMPLATE_NAME
    elif choice == "📋 Listar Templates":
        pool = context.application.bot_data["pool"]
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM templates ORDER BY id")
        if not rows:
            await update.message.reply_text("Nenhum template cadastrado.", reply_markup=menu_keyboard)
            return ConversationHandler.END
        buttons = []
        for r in rows:
            buttons.append([InlineKeyboardButton(f"{r['nome']}", callback_data=f"tpl_{r['id']}")])
        await update.message.reply_text("Templates cadastrados:", reply_markup=InlineKeyboardMarkup(buttons))
        return ConversationHandler.END
    elif choice.startswith("❌"):
        return await cancelar(update, context)
    return TEMPLATE_ACTION

async def template_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["tpl_nome"] = update.message.text
    await update.message.reply_text("Digite o conteúdo do template (use variáveis {nome}, {dias_restantes}, etc.):")
    return TEMPLATE_CONTENT

async def template_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nome = context.user_data["tpl_nome"]
    conteudo = update.message.text
    pool = context.application.bot_data["pool"]
    async with pool.acquire() as conn:
        await conn.execute("INSERT INTO templates (nome, conteudo) VALUES ($1,$2) ON CONFLICT (nome) DO UPDATE SET conteudo=$2", nome, conteudo)
    await update.message.reply_text(f"✅ Template '{nome}' salvo!", reply_markup=menu_keyboard)
    context.user_data.clear()
    return ConversationHandler.END

async def template_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    tid = int(q.data.replace("tpl_", ""))
    pool = context.application.bot_data["pool"]
    tpl = await pool.fetchrow("SELECT * FROM templates WHERE id=$1", tid)
    if tpl:
        detalhes = f"📝 <b>{tpl['nome']}</b>\n\n{tpl['conteudo']}"
        kb = [
            [InlineKeyboardButton("✏️ Editar", callback_data=f"tpl_edit_{tpl['id']}")],
            [InlineKeyboardButton("🗑️ Excluir", callback_data=f"tpl_del_{tpl['id']}")]
        ]
        await q.edit_message_text(detalhes, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))

async def template_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    tid = int(q.data.replace("tpl_edit_", ""))
    context.user_data["tpl_edit_id"] = tid
    await q.message.reply_text("Digite o novo conteúdo do template:", reply_markup=cancel_keyboard)
    return TEMPLATE_EDIT

async def template_edit_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tid = context.user_data["tpl_edit_id"]
    conteudo = update.message.text
    pool = context.application.bot_data["pool"]
    async with pool.acquire() as conn:
        await conn.execute("UPDATE templates SET conteudo=$1 WHERE id=$2", conteudo, tid)
    await update.message.reply_text("✅ Template atualizado!", reply_markup=menu_keyboard)
    context.user_data.clear()
    return ConversationHandler.END

async def template_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    tid = int(q.data.replace("tpl_del_", ""))
    pool = context.application.bot_data["pool"]
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM templates WHERE id=$1", tid)
    await q.edit_message_text("✅ Template excluído.")

# =========
# Main
# =========
# =========
# Main
# =========
async def main():
    logging.basicConfig(level=logging.INFO)
    if not TOKEN or not POSTGRES_URL:
        raise RuntimeError("Configuração ausente")

    application = Application.builder().token(TOKEN).build()
    pool = await create_pool()
    await init_db(pool)
    application.bot_data["pool"] = pool

    # Scheduler para notificações
    scheduler = AsyncIOScheduler()
    scheduler.add_job(enviar_notificacoes, "cron", hour=9, args=[application])
    scheduler.start()

    # Conversa de TEMPLATES
    conv_templates = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^GERENCIAR TEMPLATES$"), templates_menu)],
        states={
            TEMPLATE_ACTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, template_action)],
            TEMPLATE_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, template_name)],
            TEMPLATE_CONTENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, template_content)],
            TEMPLATE_EDIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, template_edit_save)],
        },
        fallbacks=[MessageHandler(filters.Regex("^❌ Cancelar / Menu Principal$"), cancelar)]
    )

    # Conversa de ADICIONAR CLIENTE
    conv_add_client = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^ADICIONAR CLIENTE$"), lambda u, c: u.message.reply_text("⚠️ fluxo de cadastro ainda não implementado aqui"))],
        states={},
        fallbacks=[MessageHandler(filters.Regex("^❌ Cancelar / Menu Principal$"), cancelar)]
    )

    # Handlers principais
    application.add_handler(CommandHandler("start", lambda u, c: u.message.reply_text("Bem-vindo!", reply_markup=menu_keyboard)))
    application.add_handler(conv_templates)
    application.add_handler(conv_add_client)

    # Botão LISTAR CLIENTES (aqui você chamaria sua função listar_clientes real)
    application.add_handler(MessageHandler(filters.Regex("^LISTAR CLIENTES$"), lambda u, c: u.message.reply_text("📋 Aqui vai a listagem de clientes")))

    # Callbacks de templates
    application.add_handler(CallbackQueryHandler(template_callback, pattern=r"^tpl_\d+"))
    application.add_handler(CallbackQueryHandler(template_edit, pattern=r"^tpl_edit_\d+"))
    application.add_handler(CallbackQueryHandler(template_delete, pattern=r"^tpl_del_\d+"))

    await application.run_polling()

import sys, asyncio
if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
