import logging
import os
import sys
import asyncio
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
    ContextTypes, ConversationHandler
)
import asyncpg

# --- Variáveis de ambiente ---
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
POSTGRES_URL = os.environ.get("POSTGRES_URL")

# --- Estados do ConversationHandler ---
ASK_CLIENT_NAME, ASK_CLIENT_PHONE = range(2)

# --- Funções de banco de dados ---
async def create_pool():
    return await asyncpg.create_pool(dsn=POSTGRES_URL)

async def init_db(pool):
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS clientes (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                nome TEXT,
                telefone TEXT
            );
        """)

async def add_cliente(pool, user_id, nome, telefone):
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO clientes (user_id, nome, telefone) VALUES ($1, $2, $3)",
            user_id, nome, telefone
        )

# --- Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [KeyboardButton("ADICIONAR CLIENTE")]
    ]
    markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("Bem-vindo! Use o menu abaixo:", reply_markup=markup)

async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "ADICIONAR CLIENTE":
        await update.message.reply_text("Digite o nome do cliente:")
        return ASK_CLIENT_NAME
    return ConversationHandler.END

async def ask_client_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["novo_cliente_nome"] = update.message.text
    await update.message.reply_text("Agora envie o telefone do cliente:")
    return ASK_CLIENT_PHONE

async def ask_client_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nome = context.user_data["novo_cliente_nome"]
    telefone = update.message.text
    user_id = update.effective_user.id
    pool = context.application.bot_data["pool"]
    await add_cliente(pool, user_id, nome, telefone)
    await update.message.reply_text("Cliente adicionado com sucesso!")
    return ConversationHandler.END

async def main():
    logging.basicConfig(level=logging.INFO)
    application = Application.builder().token(TOKEN).build()

    # Pool de conexões Postgres
    pool = await create_pool()
    await init_db(pool)
    application.bot_data["pool"] = pool

    # Conversa para adicionar cliente
    conv_add_cliente = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^ADICIONAR CLIENTE$"), handle_menu)],
        states={
            ASK_CLIENT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_client_name)],
            ASK_CLIENT_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_client_phone)],
        },
        fallbacks=[]
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(conv_add_cliente)

    await application.run_polling()

if __name__ == "__main__":
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
