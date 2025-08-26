import logging
import os
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

# --- Estados do ConversationHandler ---
(
    ASK_CLIENT_NAME, ASK_CLIENT_PHONE, ASK_CLIENT_PACKAGE, ASK_CLIENT_VALUE,
    ASK_CLIENT_DUE, ASK_CLIENT_SERVER, ASK_CLIENT_EXTRA, CONFIRM_CLIENT
) = range(8)

# --- Banco de dados ---
async def create_pool():
    return await asyncpg.create_pool(dsn=POSTGRES_URL)

async def init_db(pool):
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS clientes (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                nome TEXT,
                telefone TEXT,
                pacote TEXT,
                valor TEXT,
                vencimento TEXT,
                servidor TEXT,
                outras_informacoes TEXT
            );
        """)

async def add_cliente(pool, user_id, nome, telefone, pacote, valor, vencimento, servidor, outras_informacoes):
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO clientes (user_id, nome, telefone, pacote, valor, vencimento, servidor, outras_informacoes)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """,
            user_id, nome, telefone, pacote, valor, vencimento, servidor, outras_informacoes
        )

# --- Teclados ---
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

# --- Utilitário para parse de data ---
def parse_date(dtstr):
    try:
        return date.fromisoformat(dtstr)
    except:
        try:
            d, m, y = map(int, dtstr.split("/"))
            return date(y, m, d)
        except:
            return None

# --- Handlers principais ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bem-vindo! Use o menu abaixo:", reply_markup=menu_keyboard)

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

# --- Fluxo de cadastro de cliente ---
async def ask_client_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["nome"] = update.message.text
    await update.message.reply_text("Agora envie o telefone do cliente:")
    return ASK_CLIENT_PHONE

async def ask_client_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["telefone"] = update.message.text
    await update.message.reply_text("Escolha o pacote:", reply_markup=package_keyboard)
    return ASK_CLIENT_PACKAGE

async def ask_client_package(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["pacote"] = update.message.text
    await update.message.reply_text("Escolha o valor:", reply_markup=value_keyboard)
    return ASK_CLIENT_VALUE

async def ask_client_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["valor"] = update.message.text
    hoje = date.today()
    pacote = context.user_data.get("pacote", "")
    datas = {
        "📅 MENSAL": hoje + timedelta(days=30),
        "📆 TRIMESTRAL": hoje + timedelta(days=90),
        "📅 SEMESTRAL": hoje + timedelta(days=180),
        "📅 ANUAL": hoje + timedelta(days=365),
    }
    datas_keyboard = []
    if pacote in datas:
        datas_keyboard.append([datas[pacote].strftime("%d/%m/%Y")])
    datas_keyboard.append(["📅 OUTRA DATA"])
    await update.message.reply_text("Escolha a data de vencimento:", reply_markup=ReplyKeyboardMarkup(datas_keyboard, resize_keyboard=True, one_time_keyboard=True))
    return ASK_CLIENT_DUE

async def ask_client_due(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["vencimento"] = update.message.text
    await update.message.reply_text("Escolha o servidor:", reply_markup=server_keyboard)
    return ASK_CLIENT_SERVER

async def ask_client_server(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["servidor"] = update.message.text
    await update.message.reply_text(
        "Se desejar, informe outras informações. Depois, clique em ✅ Salvar para finalizar ou ❌ Cancelar para descartar.",
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
        await update.message.reply_text(
            "Clique em ✅ Salvar para finalizar ou ❌ Cancelar para descartar.",
            reply_markup=extra_keyboard
        )
        return ASK_CLIENT_EXTRA

async def confirm_client(update: Update, context: ContextTypes.DEFAULT_TYPE):
    dados = context.user_data
    user_id = update.effective_user.id
    outras_informacoes = dados.get("outras_informacoes", "")
    pool = context.application.bot_data["pool"]

    for campo in ["nome", "telefone", "pacote", "valor", "vencimento", "servidor"]:
        if campo not in dados:
            await update.message.reply_text(f"Erro: Campo obrigatório '{campo}' não preenchido.", reply_markup=menu_keyboard)
            context.user_data.clear()
            return ConversationHandler.END

    await add_cliente(
        pool, user_id, dados["nome"], dados["telefone"], dados["pacote"],
        dados["valor"], dados["vencimento"], dados["servidor"], outras_informacoes
    )

    resumo = (
        f"Cliente cadastrado com sucesso! ✅\n"
        f"<b>Nome:</b> {dados.get('nome')}\n"
        f"<b>Telefone:</b> {dados.get('telefone')}\n"
        f"<b>Pacote:</b> {dados.get('pacote')}\n"
        f"<b>Valor:</b> {dados.get('valor')}\n"
        f"<b>Vencimento:</b> {dados.get('vencimento')}\n"
        f"<b>Servidor:</b> {dados.get('servidor')}\n"
        f"<b>Outras informações:</b> {outras_informacoes or '-'}"
    )
    await update.message.reply_html(resumo, reply_markup=menu_keyboard)
    context.user_data.clear()
    return ConversationHandler.END

# --- Listar clientes e detalhes ---
async def listar_clientes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pool = context.application.bot_data["pool"]
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT id, nome, vencimento FROM clientes ORDER BY vencimento ASC NULLS LAST")

    total = len(rows)
    hoje = date.today()
    vencem_hoje = sum(1 for r in rows if r["vencimento"] and parse_date(r["vencimento"]) == hoje)
    vencem_3dias = sum(1 for r in rows if r["vencimento"] and 0 <= (parse_date(r["vencimento"]) - hoje).days <= 3)
    vencem_7dias = sum(1 for r in rows if r["vencimento"] and 0 <= (parse_date(r["vencimento"]) - hoje).days <= 7)

    resumo = (
        f"📋 <b>Resumo dos clientes</b>\n"
        f"Total: <b>{total}</b>\n"
        f"Vencem hoje: <b>{vencem_hoje}</b>\n"
        f"Vencem em até 3 dias: <b>{vencem_3dias}</b>\n"
        f"Vencem em até 7 dias: <b>{vencem_7dias}</b>\n"
        "\nSelecione um cliente para ver detalhes:"
    )

    buttons = []
    for r in rows:
        nome = r["nome"]
        venc = r["vencimento"]
        if not venc:
            label = f"{nome} – sem vencimento"
        else:
            dias = (parse_date(venc) - hoje).days if parse_date(venc) else None
            alerta = " ⚠️" if dias is not None and 0 <= dias <= 3 else ""
            label = f"{nome} – {venc}{alerta}"
        buttons.append([InlineKeyboardButton(label, callback_data=f"cliente_{r['id']}")])

    reply_markup = InlineKeyboardMarkup(buttons) if buttons else None

    # Corrigido: usar effective_message para responder certo tanto pra /start quanto pra texto do menu
    message = update.effective_message if hasattr(update, "effective_message") else update.message
    await message.reply_html(resumo, reply_markup=reply_markup)

async def cliente_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cliente_id = int(query.data.replace("cliente_", ""))
    pool = context.application.bot_data["pool"]
    async with pool.acquire() as conn:
        r = await conn.fetchrow("SELECT * FROM clientes WHERE id = $1", cliente_id)
    if r:
        detalhes = (
            f"<b>Nome:</b> {r['nome']}\n"
            f"<b>Telefone:</b> {r['telefone']}\n"
            f"<b>Pacote:</b> {r['pacote']}\n"
            f"<b>Valor:</b> {r['valor']}\n"
            f"<b>Vencimento:</b> {r['vencimento']}\n"
            f"<b>Servidor:</b> {r['servidor']}\n"
            f"<b>Outras informações:</b> {r['outras_informacoes'] or '-'}"
        )
        await query.edit_message_text(detalhes, parse_mode="HTML")
    else:
        await query.edit_message_text("Cliente não encontrado.")

# --- Main ---
async def main():
    logging.basicConfig(level=logging.INFO)
    application = Application.builder().token(TOKEN).build()

    # Pool de conexões Postgres
    pool = await create_pool()
    await init_db(pool)
    application.bot_data["pool"] = pool

    # Conversa para adicionar cliente
    conv_add_cliente = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^ADICIONAR CLIENTE$"), menu_handler),
            MessageHandler(filters.Regex("^LISTAR CLIENTES$"), menu_handler)
        ],
        states={
            ASK_CLIENT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_client_name)],
            ASK_CLIENT_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_client_phone)],
            ASK_CLIENT_PACKAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_client_package)],
            ASK_CLIENT_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_client_value)],
            ASK_CLIENT_DUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_client_due)],
            ASK_CLIENT_SERVER: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_client_server)],
            ASK_CLIENT_EXTRA: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_client_extra)],
        },
        fallbacks=[],
        allow_reentry=True,
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(conv_add_cliente)
    application.add_handler(CallbackQueryHandler(cliente_callback, pattern=r"^cliente_"))

    await application.run_polling()

import sys
import asyncio

if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        asyncio.run(main())
    except RuntimeError as e:
        if "running event loop" in str(e):
            loop = asyncio.get_event_loop()
            loop.run_until_complete(main())
        else:
            raise
