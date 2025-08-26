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
from datetime import date, timedelta, datetime

# --- Variáveis de ambiente ---
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
POSTGRES_URL = os.environ.get("POSTGRES_URL")

# --- Estados do ConversationHandler ---
(
    ASK_CLIENT_NAME, ASK_CLIENT_PHONE, ASK_CLIENT_PACKAGE, ASK_CLIENT_VALUE,
    ASK_CLIENT_DUE, ASK_CLIENT_SERVER, ASK_CLIENT_EXTRA
) = range(7)

# ==============================
# Utilitários de Data e Dinheiro
# ==============================
def parse_date(dtstr: str | None):
    """Aceita 'YYYY-MM-DD' ou 'DD/MM/YYYY' e retorna date, senão None."""
    if not dtstr:
        return None
    dtstr = dtstr.strip()
    # tenta ISO
    try:
        return date.fromisoformat(dtstr)
    except Exception:
        pass
    # tenta BR
    try:
        d, m, y = map(int, dtstr.split("/"))
        return date(y, m, d)
    except Exception:
        return None

def parse_money(txt: str | None) -> Decimal:
    """Converte '50', '50,00', 'R$ 1.234,56' etc. para Decimal(1234.56)."""
    if not txt:
        return Decimal("0")
    s = txt.strip()
    # remove tudo exceto dígitos, ponto e vírgula
    s = re.sub(r"[^0-9,\.]", "", s)
    # se tem vírgula, troca por ponto (formato BR)
    if "," in s and "." in s:
        # remove separadores de milhar
        s = s.replace(".", "")
    s = s.replace(",", ".")
    if s == "":
        return Decimal("0")
    try:
        return Decimal(s)
    except InvalidOperation:
        return Decimal("0")

def fmt_money(val: Decimal) -> str:
    """Formata Decimal em BR: R$ 1.234,56."""
    q = val.quantize(Decimal("0.01"))
    # usa ponto para milhar e vírgula decimal
    inteiro, _, frac = f"{q:.2f}".partition(".")
    # aplica milhar
    inteiro = f"{int(inteiro):,}".replace(",", ".")
    return f"{inteiro},{frac}"

def month_bounds(today: date | None = None):
    if not today:
        today = date.today()
    start = today.replace(day=1)
    # próximo mês
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
    # se seu provedor exige SSL, garanta ?sslmode=require na URL
    return await asyncpg.create_pool(dsn=POSTGRES_URL)

async def init_db(pool):
    async with pool.acquire() as conn:
        # cria tabela base
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
                outras_informacoes TEXT
            );
        """)
        # adiciona colunas novas sem quebrar se já existirem
        await conn.execute("ALTER TABLE clientes ADD COLUMN IF NOT EXISTS status_pagamento TEXT DEFAULT 'pendente';")
        await conn.execute("ALTER TABLE clientes ADD COLUMN IF NOT EXISTS data_pagamento TEXT;")

async def add_cliente(pool, user_id, nome, telefone, pacote, valor, vencimento, servidor, outras_informacoes):
    async with pool.acquire() as conn:
        try:
            cliente_id = await conn.fetchval(
                """
                INSERT INTO clientes 
                    (user_id, nome, telefone, pacote, valor, vencimento, servidor, outras_informacoes)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
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
# Handlers
# =========
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
    texto = update.message.text
    if texto == "🛠️ PACOTE PERSONALIZADO":
        await update.message.reply_text("Digite o nome do pacote personalizado:")
        return ASK_CLIENT_PACKAGE  # continua até digitar
    else:
        context.user_data["pacote"] = texto
        await update.message.reply_text("Escolha o valor:", reply_markup=value_keyboard)
        return ASK_CLIENT_VALUE

async def ask_client_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text
    if texto == "💸 OUTRO VALOR":
        await update.message.reply_text("Digite o valor do pacote (use números, ex: 50 ou 50,00):")
        return ASK_CLIENT_VALUE  # continua até digitar
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

    cliente_id = await add_cliente(
        pool, user_id, dados["nome"], dados["telefone"], dados["pacote"],
        dados["valor"], dados["vencimento"], dados["servidor"], outras_informacoes
    )

    if cliente_id:
        resumo = (
            f"Cliente cadastrado com sucesso! ✅\n"
            f"<b>ID:</b> {cliente_id}\n"
            f"<b>Nome:</b> {dados.get('nome')}\n"
            f"<b>Telefone:</b> {dados.get('telefone')}\n"
            f"<b>Pacote:</b> {dados.get('pacote')}\n"
            f"<b>Valor:</b> {dados.get('valor')}\n"
            f"<b>Vencimento:</b> {dados.get('vencimento')}\n"
            f"<b>Servidor:</b> {dados.get('servidor')}\n"
            f"<b>Outras informações:</b> {outras_informacoes or '-'}"
        )
    else:
        resumo = "❌ Erro ao salvar cliente. Verifique os logs."

    await update.message.reply_html(resumo, reply_markup=menu_keyboard)
    context.user_data.clear()
    return ConversationHandler.END

# ==========================
# Listagem + Dashboard resumo
# ==========================
async def listar_clientes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pool = context.application.bot_data["pool"]
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT id, nome, vencimento, valor, status_pagamento, data_pagamento
            FROM clientes
            ORDER BY vencimento ASC NULLS LAST
        """)

    total = len(rows)
    hoje = date.today()
    vencem_hoje = sum(1 for r in rows if r["vencimento"] and parse_date(r["vencimento"]) == hoje)
    vencem_3dias = sum(
        1 for r in rows
        if r["vencimento"] and parse_date(r["vencimento"]) is not None
        and 0 <= (parse_date(r["vencimento"]) - hoje).days <= 3
    )
    vencem_7dias = sum(
        1 for r in rows
        if r["vencimento"] and parse_date(r["vencimento"]) is not None
        and 0 <= (parse_date(r["vencimento"]) - hoje).days <= 7
    )

    # --- métricas financeiras do mês ---
    mes_ini, mes_fim = month_bounds(hoje)
    recebido_mes = Decimal("0")
    previsto_mes = Decimal("0")

    for r in rows:
        v = parse_money(r["valor"])
        # previsto: qualquer cliente com vencimento dentro do mês corrente
        vcto = parse_date(r["vencimento"]) if r["vencimento"] else None
        if vcto and mes_ini <= vcto <= mes_fim:
            previsto_mes += v

        # recebido: status 'pago' e data_pagamento no mês corrente
        if (r.get("status_pagamento") or "").lower() == "pago":
            dp = parse_date(r.get("data_pagamento") or "")
            if dp and mes_ini <= dp <= mes_fim:
                recebido_mes += v

    resumo = (
        f"📋 <b>Resumo dos clientes</b>\n"
        f"Total: <b>{total}</b>\n"
        f"Vencem hoje: <b>{vencem_hoje}</b>\n"
        f"Vencem em até 3 dias: <b>{vencem_3dias}</b>\n"
        f"Vencem em até 7 dias: <b>{vencem_7dias}</b>\n"
        f"\n💰 <b>Recebido no mês:</b> <b>R$ {fmt_money(recebido_mes)}</b>"
        f"\n📆 <b>Previsto no mês:</b> <b>R$ {fmt_money(previsto_mes)}</b>\n"
        "\nSelecione um cliente para ver detalhes:"
    )

    buttons = []
    for r in rows:
        nome = r["nome"]
        venc = r["vencimento"]
        if not venc:
            label = f"{nome} – sem vencimento"
        else:
            vdt = parse_date(venc)
            dias = (vdt - hoje).days if vdt else None
            alerta = " ⚠️" if dias is not None and 0 <= dias <= 3 else ""
            label = f"{nome} – {venc}{alerta}"
        buttons.append([InlineKeyboardButton(label, callback_data=f"cliente_{r['id']}")])

    reply_markup = InlineKeyboardMarkup(buttons) if buttons else None
    # usar effective_message para responder tanto a comando quanto a texto
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
            f"<b>ID:</b> {r['id']}\n"
            f"<b>Nome:</b> {r['nome']}\n"
            f"<b>Telefone:</b> {r['telefone']}\n"
            f"<b>Pacote:</b> {r['pacote']}\n"
            f"<b>Valor:</b> {r['valor']}\n"
            f"<b>Vencimento:</b> {r['vencimento']}\n"
            f"<b>Servidor:</b> {r['servidor']}\n"
            f"<b>Status:</b> {r.get('status_pagamento', 'pendente')}\n"
            f"<b>Pago em:</b> {r.get('data_pagamento') or '-'}\n"
            f"<b>Outras informações:</b> {r['outras_informacoes'] or '-'}"
        )
        await query.edit_message_text(detalhes, parse_mode="HTML")
    else:
        await query.edit_message_text("Cliente não encontrado.")

# =========
# Main
# =========
async def main():
    logging.basicConfig(level=logging.INFO)
    if not TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN não definido.")
    if not POSTGRES_URL:
        raise RuntimeError("POSTGRES_URL não definido.")

    application = Application.builder().token(TOKEN).build()

    # Pool de conexões Postgres
    pool = await create_pool()
    await init_db(pool)
    application.bot_data["pool"] = pool

    # Conversa para adicionar cliente
    conv_add_cliente = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^ADICIONAR CLIENTE$"), menu_handler)],
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
    application.add_handler(MessageHandler(filters.Regex("^LISTAR CLIENTES$"), menu_handler))
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
