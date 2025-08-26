import logging
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from datetime import datetime, timedelta
import pickle
import os

# Configurações via variáveis de ambiente
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "COLE_SEU_TOKEN_AQUI")
CHAVE_PIX = os.environ.get("CHAVE_PIX", "SUA_CHAVE_PIX")
PRECO = float(os.environ.get("PRECO", 20.00))
DIAS_GRATIS = int(os.environ.get("DIAS_GRATIS", 7))

# Estados do ConversationHandler
ASK_PHONE, TEST_PERIOD, PAYMENT = range(3)

# Banco de dados simples (arquivo pickle)
DB_FILE = 'users.pkl'

def load_users():
    if not os.path.exists(DB_FILE):
        return {}
    with open(DB_FILE, 'rb') as f:
        return pickle.load(f)

def save_users(users):
    with open(DB_FILE, 'wb') as f:
        pickle.dump(users, f)

users = load_users()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    # Checar se já está registrado
    if user_id in users:
        await update.message.reply_text("Você já iniciou seu teste grátis.")
        return ConversationHandler.END

    # Pedir número de telefone
    button = KeyboardButton('Enviar meu número', request_contact=True)
    markup = ReplyKeyboardMarkup([[button]], one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("Olá! Para começar, envie seu número de telefone.", reply_markup=markup)
    return ASK_PHONE

async def ask_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    contact = update.message.contact
    if not contact or not contact.phone_number:
        await update.message.reply_text("Por favor, use o botão para enviar seu número.")
        return ASK_PHONE

    # Registrar usuário
    users[user_id] = {
        'phone': contact.phone_number,
        'start_date': datetime.now(),
        'paid': False
    }
    save_users(users)
    await update.message.reply_text(
        f"Seu teste grátis começou! Você tem {DIAS_GRATIS} dias de acesso.\nApós esse período, será necessário pagar R${PRECO:.2f} via Mercado Pago (PIX)."
    )
    return ConversationHandler.END

async def check_access(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in users:
        await update.message.reply_text("Use /start para começar.")
        return

    user = users[user_id]
    start = user['start_date']
    if isinstance(start, str):  # Corrigir datas serializadas
        start = datetime.fromisoformat(start)
    dias = (datetime.now() - start).days

    if user.get('paid', False):
        await update.message.reply_text("Acesso liberado! Obrigado pelo pagamento.")
        return

    if dias < DIAS_GRATIS:
        await update.message.reply_text(f"Você está no período de teste grátis. Dias restantes: {DIAS_GRATIS - dias}")
    else:
        await update.message.reply_text(
            f"Seu teste grátis terminou. Para continuar, pague R${PRECO:.2f} via PIX:\n"
            f"Chave PIX: {CHAVE_PIX}\n"
            "Após o pagamento, envie o comprovante para liberação."
        )

async def set_paid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Comando manual para liberar acesso após pagamento
    user_id = update.effective_user.id
    if user_id in users:
        users[user_id]['paid'] = True
        save_users(users)
        await update.message.reply_text("Pagamento confirmado! Acesso liberado. Obrigado!")
    else:
        await update.message.reply_text("Você não está registrado. Use /start.")

def main():
    logging.basicConfig(level=logging.INFO)
    application = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            ASK_PHONE: [MessageHandler(filters.CONTACT, ask_phone)],
        },
        fallbacks=[],
    )

    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("acesso", check_access))
    application.add_handler(CommandHandler("liberar", set_paid))  # acesso manual

    application.run_polling()

if __name__ == "__main__":
    main()
