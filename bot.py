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
    EDIT_FIELD, SEND_MESSAGE, RENEW_DATE
) = range(10)

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

package_keyboard = ReplyKeyboardMarkup(
    [
        ["📅 MENSAL", "📆 TRIMESTRAL"],
        ["📅 SEMESTRAL", "📅 ANUAL"],
        ["🛠️ PACOTE PERSONALIZADO"]
    ],
    resize_keyboard=True, one_time_keyboard=True
)

value_keyboard = ReplyKeyboardMarkup(
    [
        ["25", "30", "35", "40", "45"],
        ["50", "60", "70", "90"],
        ["💸 OUTRO VALOR"]
    ],
    resize_keyboard=True, one_time_keyboard=True
)

server_keyboard = ReplyKeyboardMarkup(
    [
        ["⚡ FAST PLAY", "🏅 GOLD PLAY", "📺 EITV"],
        ["🖥️ X SERVER", "🛰️ UNITV", "🆙 UPPER PLAY"],
        ["🪶 SLIM TV", "🛠️ CRAFT TV", "🖊️ OUTRO SERVIDOR"]
    ],
    resize_keyboard=True, one_time_keyboard=True
)

extra_keyboard = ReplyKeyboardMarkup(
    [
        [KeyboardButton("✅ Salvar"), KeyboardButton("❌ Cancelar")]
    ],
    resize_keyboard=True, is_persistent=True
)

# =========
# Fluxo de cadastro de cliente
# =========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bem-vindo! Escolha uma opção:", reply_markup=menu_keyboard)

async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "ADICIONAR CLIENTE":
        context.user_data.clear()
        await update.message.reply_text("Digite o nome do cliente:", reply_markup=ReplyKeyboardRemove())
        return ASK_CLIENT_NAME
    elif text == "LISTAR CLIENTES":
        await listar_clientes(update, context)
        return ConversationHandler.END
    return ConversationHandler.END

async def ask_client_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["nome"] = update.message.text
    await update.message.reply_text("Agora envie o telefone do cliente:")
    return ASK_CLIENT_PHONE

async def ask_client_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["telefone"] = update.message.text
    await update.message.reply_text("Escolha o pacote:", reply_markup=package_keyboard)
    return ASK_CLIENT_PACKAGE

async def ask_client_package(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text
    if texto == "🛠️ PACOTE PERSONALIZADO":
        await update.message.reply_text("Digite o nome do pacote personalizado:")
        return ASK_CLIENT_PACKAGE
    else:
        context.user_data["pacote"] = texto
        await update.message.reply_text("Escolha o valor:", reply_markup=value_keyboard)
        return ASK_CLIENT_VALUE

async def ask_client_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text
    if texto == "💸 OUTRO VALOR":
        await update.message.reply_text("Digite o valor do pacote (ex: 50 ou 50,00):")
        return ASK_CLIENT_VALUE
    else:
        context.user_data["valor"] = texto
        hoje = date.today()
        pacote = context.user_data.get("pacote", "")
        datas = {
            "📅 MENSAL": hoje + timedelta(days=30),
            "📆 TRIMESTRAL": hoje + timedelta(days=90),
            "📅 SEMESTRAL": hoje + timedelta(days=180),
            "📅 ANUAL": hoje + timedelta(days=365),
        }
        sugestoes = []
        if pacote in datas:
            sugestoes.append([datas[pacote].strftime("%d/%m/%Y")])
        sugestoes.append(["📅 OUTRA DATA"])
        await update.message.reply_text(
            "Escolha a data de vencimento ou digite manualmente:",
            reply_markup=ReplyKeyboardMarkup(sugestoes, resize_keyboard=True, one_time_keyboard=True)
        )
        return ASK_CLIENT_DUE

async def ask_client_due(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text
    if texto == "📅 OUTRA DATA":
        await update.message.reply_text("Digite a data de vencimento no formato DD/MM/AAAA:")
        return ASK_CLIENT_DUE
    else:
        context.user_data["vencimento"] = texto
        await update.message.reply_text("Escolha o servidor:", reply_markup=server_keyboard)
        return ASK_CLIENT_SERVER

async def ask_client_server(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text
    if texto == "🖊️ OUTRO SERVIDOR":
        await update.message.reply_text("Digite o nome do servidor:")
        return ASK_CLIENT_SERVER
    else:
        context.user_data["servidor"] = texto
        await update.message.reply_text(
            "Se desejar, informe outras informações. Depois clique em ✅ Salvar ou ❌ Cancelar.",
            reply_markup=extra_keyboard
        )
        context.user_data["outras_informacoes"] = ""
        return ASK_CLIENT_EXTRA

async def ask_client_extra(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "✅ Salvar":
        return await confirm_client(update, context)
    elif text == "❌ Cancelar":
        await update.message.reply_text("Cadastro cancelado.", reply_markup=menu_keyboard)
        context.user_data.clear()
        return ConversationHandler.END
    else:
        context.user_data["outras_informacoes"] = text
        await update.message.reply_text("Clique em ✅ Salvar ou ❌ Cancelar.", reply_markup=extra_keyboard)
        return ASK_CLIENT_EXTRA

async def confirm_client(update: Update, context: ContextTypes.DEFAULT_TYPE):
    dados = context.user_data
    user_id = update.effective_user.id
    outras = dados.get("outras_informacoes", "")
    pool = context.application.bot_data["pool"]

    cliente_id = await add_cliente(
        pool, user_id, dados["nome"], dados["telefone"], dados["pacote"],
        dados["valor"], dados["vencimento"], dados["servidor"], outras
    )

    if cliente_id:
        resumo = (
            f"Cliente cadastrado! ✅\n"
            f"<b>ID:</b> {cliente_id}\n"
            f"👤 <b>Nome:</b> {dados.get('nome')}\n"
            f"📱 <b>Telefone:</b> {dados.get('telefone')}\n"
            f"📦 <b>Pacote:</b> {dados.get('pacote')}\n"
            f"💵 <b>Valor:</b> {dados.get('valor')}\n"
            f"📅 <b>Vencimento:</b> {dados.get('vencimento')}\n"
            f"🖥️ <b>Servidor:</b> {dados.get('servidor')}\n"
            f"📝 <b>Outras:</b> {outras or '-'}"
        )
        await update.message.reply_html(resumo, reply_markup=menu_keyboard)
    else:
        await update.message.reply_text("❌ Erro ao salvar cliente.", reply_markup=menu_keyboard)

    context.user_data.clear()
    return ConversationHandler.END

# =========
# (aqui continuam listar_clientes, cliente_callback, edição com emojis e teclados, renovar, excluir, enviar msg — já atualizados)
# =========

# =========
# Main
# =========
async def main():
    logging.basicConfig(level=logging.INFO)
    application = Application.builder().token(TOKEN).build()
    pool = await create_pool()
    await init_db(pool)
    application.bot_data["pool"] = pool

    conv_add = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^(ADICIONAR CLIENTE|LISTAR CLIENTES)$"), menu_handler)],
        states={
            ASK_CLIENT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_client_name)],
            ASK_CLIENT_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_client_phone)],
            ASK_CLIENT_PACKAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_client_package)],
            ASK_CLIENT_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_client_value)],
            ASK_CLIENT_DUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_client_due)],
            ASK_CLIENT_SERVER: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_client_server)],
            ASK_CLIENT_EXTRA: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_client_extra)],
        },
        fallbacks=[]
    )

    # outros conv_handlers: edição, mensagem, renovação...
    # (iguais à versão anterior, só muda o edit_menu para ter emojis nos botões)

    application.add_handler(CommandHandler("start", start))
    application.add_handler(conv_add)

    await application.run_polling()

import sys, asyncio
if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
