import logging
import os
from datetime import datetime, timedelta
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
ASK_CLIENT_NAME, ASK_CLIENT_PHONE, ASK_CLIENT_PACKAGE, ASK_CLIENT_VALUE, ASK_CLIENT_EXPIRY, ASK_CLIENT_SERVER, ASK_CLIENT_OTHER_INFO = range(7)

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
                telefone TEXT,
                pacote TEXT,
                valor TEXT,
                data_vencimento TEXT,
                servidor TEXT,
                outras_informacoes TEXT
            );
        """)

async def add_cliente(pool, user_id, nome, telefone, pacote, valor, data_vencimento, servidor, outras_informacoes):
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO clientes (user_id, nome, telefone, pacote, valor, data_vencimento, servidor, outras_informacoes) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)",
            user_id, nome, telefone, pacote, valor, data_vencimento, servidor, outras_informacoes
        )

# --- Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [KeyboardButton("➕ ADICIONAR CLIENTE")]
    ]
    markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("Bem-vindo! Use o menu abaixo:", reply_markup=markup)

async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "➕ ADICIONAR CLIENTE":
        await update.message.reply_text("Digite o nome do cliente:")
        return ASK_CLIENT_NAME
    return ConversationHandler.END

async def ask_client_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["novo_cliente_nome"] = update.message.text
    await update.message.reply_text("Agora envie o telefone do cliente:")
    return ASK_CLIENT_PHONE

async def ask_client_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["novo_cliente_telefone"] = update.message.text
    
    # Keyboard para pacotes
    keyboard = [
        [KeyboardButton("📅 MENSAL"), KeyboardButton("📆 TRIMESTRAL")],
        [KeyboardButton("📅 SEMESTRAL"), KeyboardButton("📅 ANUAL")],
        [KeyboardButton("🛠️ PACOTE PERSONALIZADO")]
    ]
    markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("Selecione o pacote:", reply_markup=markup)
    return ASK_CLIENT_PACKAGE

async def ask_client_package(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["novo_cliente_pacote"] = update.message.text
    
    # Keyboard para valores
    keyboard = [
        [KeyboardButton("25"), KeyboardButton("30"), KeyboardButton("35")],
        [KeyboardButton("40"), KeyboardButton("45"), KeyboardButton("50")],
        [KeyboardButton("60"), KeyboardButton("70"), KeyboardButton("90")],
        [KeyboardButton("💸 OUTRO VALOR")]
    ]
    markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("Selecione o valor:", reply_markup=markup)
    return ASK_CLIENT_VALUE

async def ask_client_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["novo_cliente_valor"] = update.message.text
    
    # Gerar sugestões de data baseado no pacote
    pacote = context.user_data["novo_cliente_pacote"]
    
    hoje = datetime.now()
    sugestoes = []
    
    if "MENSAL" in pacote.upper():
        # Calcular próximo mês mantendo o dia
        try:
            if hoje.month == 12:
                prox_mes = hoje.replace(year=hoje.year + 1, month=1)
            else:
                prox_mes = hoje.replace(month=hoje.month + 1)
        except ValueError:
            # Caso o dia não exista no próximo mês (ex: 31 de janeiro -> 28 de fevereiro)
            prox_mes = hoje.replace(day=28) + timedelta(days=32)
            prox_mes = prox_mes.replace(day=min(hoje.day, 28))
        sugestoes.append(prox_mes.strftime("%d/%m/%Y"))
    elif "TRIMESTRAL" in pacote.upper():
        data_3_meses = hoje + timedelta(days=90)
        sugestoes.append(data_3_meses.strftime("%d/%m/%Y"))
    elif "SEMESTRAL" in pacote.upper():
        data_6_meses = hoje + timedelta(days=180)
        sugestoes.append(data_6_meses.strftime("%d/%m/%Y"))
    elif "ANUAL" in pacote.upper():
        data_1_ano = hoje + timedelta(days=365)
        sugestoes.append(data_1_ano.strftime("%d/%m/%Y"))
    
    # Sempre adicionar próximo mês como opção adicional
    try:
        if hoje.month == 12:
            prox_mes_extra = hoje.replace(year=hoje.year + 1, month=1)
        else:
            prox_mes_extra = hoje.replace(month=hoje.month + 1)
    except ValueError:
        prox_mes_extra = hoje.replace(day=28) + timedelta(days=32)
        prox_mes_extra = prox_mes_extra.replace(day=min(hoje.day, 28))
    
    if prox_mes_extra.strftime("%d/%m/%Y") not in sugestoes:
        sugestoes.append(prox_mes_extra.strftime("%d/%m/%Y"))
    
    keyboard = []
    for data in sugestoes[:2]:  # Máximo 2 sugestões
        keyboard.append([KeyboardButton(data)])
    keyboard.append([KeyboardButton("📅 OUTRA DATA")])
    
    markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("Selecione a data de vencimento:", reply_markup=markup)
    return ASK_CLIENT_EXPIRY

async def ask_client_expiry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["novo_cliente_data_vencimento"] = update.message.text
    
    # Keyboard para servidores
    keyboard = [
        [KeyboardButton("⚡ FAST PLAY"), KeyboardButton("🏅 GOLD PLAY")],
        [KeyboardButton("📺 EITV"), KeyboardButton("🖥️ X SERVER")],
        [KeyboardButton("🛰️ UNITV"), KeyboardButton("🆙 UPPER PLAY")],
        [KeyboardButton("🪶 SLIM TV"), KeyboardButton("🛠️ CRAFT TV")],
        [KeyboardButton("🖊️ OUTRO SERVIDOR")]
    ]
    markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("Selecione o servidor:", reply_markup=markup)
    return ASK_CLIENT_SERVER

async def ask_client_server(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["novo_cliente_servidor"] = update.message.text
    
    # Keyboard para outras informações
    keyboard = [
        [KeyboardButton("PULAR")]
    ]
    markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("Digite outras informações (ou clique em PULAR):", reply_markup=markup)
    return ASK_CLIENT_OTHER_INFO

async def ask_client_other_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    outras_info = update.message.text if update.message.text != "PULAR" else ""
    
    # Coletar todos os dados
    nome = context.user_data["novo_cliente_nome"]
    telefone = context.user_data["novo_cliente_telefone"]
    pacote = context.user_data["novo_cliente_pacote"]
    valor = context.user_data["novo_cliente_valor"]
    data_vencimento = context.user_data["novo_cliente_data_vencimento"]
    servidor = context.user_data["novo_cliente_servidor"]
    
    user_id = update.effective_user.id
    pool = context.application.bot_data["pool"]
    
    # Salvar no banco
    await add_cliente(pool, user_id, nome, telefone, pacote, valor, data_vencimento, servidor, outras_info)
    
    # Restaurar keyboard principal
    keyboard = [
        [KeyboardButton("➕ ADICIONAR CLIENTE")]
    ]
    markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    # Mensagem de confirmação
    mensagem_confirmacao = f"""✅ Cliente adicionado com sucesso!

📝 **Resumo:**
👤 Nome: {nome}
📞 Telefone: {telefone}
📦 Pacote: {pacote}
💰 Valor: {valor}
📅 Vencimento: {data_vencimento}
🖥️ Servidor: {servidor}"""
    
    if outras_info:
        mensagem_confirmacao += f"\n📋 Outras informações: {outras_info}"
    
    await update.message.reply_text(mensagem_confirmacao, reply_markup=markup)
    
    # Limpar dados do usuário
    context.user_data.clear()
    
    return ConversationHandler.END

async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel the conversation"""
    # Restaurar keyboard principal
    keyboard = [
        [KeyboardButton("➕ ADICIONAR CLIENTE")]
    ]
    markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    await update.message.reply_text("❌ Operação cancelada.", reply_markup=markup)
    
    # Limpar dados do usuário
    context.user_data.clear()
    
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
        entry_points=[MessageHandler(filters.Regex("^➕ ADICIONAR CLIENTE$"), handle_menu)],
        states={
            ASK_CLIENT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_client_name)],
            ASK_CLIENT_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_client_phone)],
            ASK_CLIENT_PACKAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_client_package)],
            ASK_CLIENT_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_client_value)],
            ASK_CLIENT_EXPIRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_client_expiry)],
            ASK_CLIENT_SERVER: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_client_server)],
            ASK_CLIENT_OTHER_INFO: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_client_other_info)],
        },
        fallbacks=[CommandHandler("cancel", cancel_conversation)]
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(conv_add_cliente)

    await application.run_polling()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
