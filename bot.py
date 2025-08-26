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

# --- Variáveis de ambiente ---
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
POSTGRES_URL = os.environ.get("POSTGRES_URL")

# --- Estados ---
(
    ASK_CLIENT_NAME, ASK_CLIENT_PHONE, ASK_CLIENT_PACKAGE, ASK_CLIENT_VALUE,
    ASK_CLIENT_DUE, ASK_CLIENT_SERVER, ASK_CLIENT_EXTRA,
    EDIT_FIELD, SEND_MESSAGE
) = range(9)

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

async def add_cliente(pool, user_id, nome, telefone, pacote, valor, vencimento, servidor, outras_informacoes):
    async with pool.acquire() as conn:
        try:
            cliente_id = await conn.fetchval(
                """
                INSERT INTO clientes 
                    (user_id, nome, telefone, pacote, valor, vencimento, servidor, outras_informacoes)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                RETURNING id
                """,
                user_id, nome, telefone, pacote, valor, vencimento, servidor, outras_informacoes
            )
            logging.info(f"Cliente salvo com ID {cliente_id}")
            return cliente_id
        except Exception as e:
            logging.exception(f"Erro ao salvar cliente: {e}")
            return None

# =========
# Teclados
# =========
menu_keyboard = ReplyKeyboardMarkup(
    [
        [KeyboardButton("ADICIONAR CLIENTE")],
        [KeyboardButton("LISTAR CLIENTES")]
    ],
    resize_keyboard=True
)

# =========
# Listar clientes com dashboard
# =========
async def listar_clientes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pool = context.application.bot_data["pool"]
    user_id = update.effective_user.id
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM clientes WHERE user_id=$1 ORDER BY vencimento ASC NULLS LAST", user_id)

    total = len(rows)
    hoje = date.today()

    vencem_hoje = sum(1 for r in rows if r["vencimento"] and parse_date(r["vencimento"]) == hoje)
    vencem_3dias = sum(1 for r in rows if r["vencimento"] and 0 <= (parse_date(r["vencimento"]) - hoje).days <= 3)
    vencem_7dias = sum(1 for r in rows if r["vencimento"] and 0 <= (parse_date(r["vencimento"]) - hoje).days <= 7)

    valores_recebidos = sum(parse_money(r["valor"]) for r in rows if r["status_pagamento"] == "pago")
    valores_previstos = sum(parse_money(r["valor"]) for r in rows)

    resumo = (
        f"📋 <b>Resumo dos clientes</b>\n"
        f"Total: <b>{total}</b>\n"
        f"Vencem hoje: <b>{vencem_hoje}</b>\n"
        f"Vencem até 3 dias: <b>{vencem_3dias}</b>\n"
        f"Vencem até 7 dias: <b>{vencem_7dias}</b>\n\n"
        f"💰 Recebido no mês: <b>R$ {fmt_money(valores_recebidos)}</b>\n"
        f"📊 Previsto: <b>R$ {fmt_money(valores_previstos)}</b>\n\n"
        "Selecione um cliente para ver detalhes:"
    )

    buttons = []
    for r in rows:
        nome = r["nome"]
        venc = r["vencimento"]
        if not venc:
            label = f"⚪ {nome} – sem vencimento"
        else:
            vdt = parse_date(venc)
            if vdt:
                dias = (vdt - hoje).days
                if dias < 0:
                    status_emoji = "🔴"
                elif dias <= 5:
                    status_emoji = "🟡"
                else:
                    status_emoji = "🟢"
            else:
                status_emoji = "⚪"
            label = f"{status_emoji} {nome} – {venc}"
        buttons.append([InlineKeyboardButton(label, callback_data=f"cliente_{r['id']}")])

    reply_markup = InlineKeyboardMarkup(buttons) if buttons else None
    message = update.effective_message if hasattr(update, "effective_message") else update.message
    await message.reply_html(resumo, reply_markup=reply_markup)

# =========
# Menu de ações do cliente
# =========
async def cliente_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    cid = int(q.data.replace("cliente_", ""))
    pool = context.application.bot_data["pool"]
    user_id = update.effective_user.id
    async with pool.acquire() as conn:
        r = await conn.fetchrow("SELECT * FROM clientes WHERE id=$1 AND user_id=$2", cid, user_id)
    if r:
        detalhes = (
            f"<b>ID:</b> {r['id']}\n"
            f"<b>Nome:</b> {r['nome']}\n"
            f"<b>Telefone:</b> {r['telefone']}\n"
            f"<b>Pacote:</b> {r['pacote']}\n"
            f"<b>Valor:</b> {r['valor']}\n"
            f"<b>Vencimento:</b> {r['vencimento']}\n"
            f"<b>Servidor:</b> {r['servidor']}\n"
            f"<b>Status:</b> {r['status_pagamento']}\n"
            f"<b>Pago em:</b> {r['data_pagamento'] or '-'}\n"
            f"<b>Outras informações:</b> {r['outras_informacoes'] or '-'}"
        )
        kb = [
            [InlineKeyboardButton("✏️ Editar", callback_data=f"editmenu_{r['id']}")],
            [InlineKeyboardButton("🔄 Renovar", callback_data=f"renew_{r['id']}")],
            [InlineKeyboardButton("🗑️ Excluir", callback_data=f"delete_{r['id']}")],
            [InlineKeyboardButton("📩 Enviar mensagem", callback_data=f"msg_{r['id']}")]
        ]
        await q.edit_message_text(detalhes, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))

# =========
# Editar
# =========
async def edit_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    cid = int(q.data.replace("editmenu_", ""))
    fields = [
        ("Nome", "nome"), ("Telefone", "telefone"), ("Pacote", "pacote"),
        ("Valor", "valor"), ("Vencimento", "vencimento"),
        ("Servidor", "servidor"), ("Outras informações", "outras_informacoes")
    ]
    kb = [[InlineKeyboardButton(f, callback_data=f"editfield_{cid}_{c}")] for f, c in fields]
    await q.edit_message_text("Escolha o campo que deseja editar:", reply_markup=InlineKeyboardMarkup(kb))

async def edit_field(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    _, cid, campo = q.data.split("_", 2)
    context.user_data["edit_cliente"] = int(cid)
    context.user_data["edit_campo"] = campo
    await q.message.reply_text(f"Digite o novo valor para {campo}:")
    return EDIT_FIELD

async def save_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    novo_valor = update.message.text
    cid = context.user_data.get("edit_cliente")
    campo = context.user_data.get("edit_campo")
    pool = context.application.bot_data["pool"]
    async with pool.acquire() as conn:
        await conn.execute(f"UPDATE clientes SET {campo}=$1 WHERE id=$2", novo_valor, cid)
    await update.message.reply_text(f"✅ {campo} atualizado com sucesso.", reply_markup=menu_keyboard)
    context.user_data.clear()
    return ConversationHandler.END

# =========
# Renovar
# =========
async def renew(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    cid = int(q.data.replace("renew_", ""))
    kb = [
        [InlineKeyboardButton("🔄 Renovar mesmo ciclo", callback_data=f"renew_same_{cid}")],
        [InlineKeyboardButton("📅 Escolher nova data", callback_data=f"renew_new_{cid}")]
    ]
    await q.edit_message_text("Escolha como renovar:", reply_markup=InlineKeyboardMarkup(kb))

# =========
# Excluir
# =========
async def delete_client(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    cid = int(q.data.replace("delete_", ""))
    kb = [
        [InlineKeyboardButton("✅ Sim, excluir", callback_data=f"delete_yes_{cid}")],
        [InlineKeyboardButton("❌ Cancelar", callback_data=f"cliente_{cid}")]
    ]
    await q.edit_message_text("Tem certeza que deseja excluir?", reply_markup=InlineKeyboardMarkup(kb))

async def delete_yes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    cid = int(q.data.replace("delete_yes_", ""))
    pool = context.application.bot_data["pool"]
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM clientes WHERE id=$1", cid)
    await q.edit_message_text("✅ Cliente excluído com sucesso.")

# =========
# Enviar mensagem
# =========
async def msg_client(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    cid = int(q.data.replace("msg_", ""))
    context.user_data["msg_cliente"] = cid
    await q.message.reply_text("Digite a mensagem para enviar ao cliente:")
    return SEND_MESSAGE

async def send_message_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.text
    cid = context.user_data.get("msg_cliente")
    await update.message.reply_text(f"📩 Mensagem enviada para cliente {cid}:\n\n{msg}")
    context.user_data.clear()
    return ConversationHandler.END

# =========
# Main
# =========
async def main():
    logging.basicConfig(level=logging.INFO)
    application = Application.builder().token(TOKEN).build()
    pool = await create_pool()
    await init_db(pool)
    application.bot_data["pool"] = pool

    conv_edit = ConversationHandler(
        entry_points=[CallbackQueryHandler(edit_field, pattern=r"^editfield_")],
        states={EDIT_FIELD: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_edit)]},
        fallbacks=[]
    )
    conv_msg = ConversationHandler(
        entry_points=[CallbackQueryHandler(msg_client, pattern=r"^msg_")],
        states={SEND_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, send_message_done)]},
        fallbacks=[]
    )

    application.add_handler(CommandHandler("start", listar_clientes))
    application.add_handler(conv_edit)
    application.add_handler(conv_msg)
    application.add_handler(MessageHandler(filters.Regex("^LISTAR CLIENTES$"), listar_clientes))
    application.add_handler(CallbackQueryHandler(cliente_callback, pattern=r"^cliente_"))
    application.add_handler(CallbackQueryHandler(edit_menu, pattern=r"^editmenu_"))
    application.add_handler(CallbackQueryHandler(renew, pattern=r"^renew_"))
    application.add_handler(CallbackQueryHandler(delete_client, pattern=r"^delete_[0-9]+$"))
    application.add_handler(CallbackQueryHandler(delete_yes, pattern=r"^delete_yes_"))

    await application.run_polling()

import sys, asyncio
if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
