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

# --- Agendamento opcional (APScheduler) ---
try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    APSCHED_AVAILABLE = True
except Exception:
    APSCHED_AVAILABLE = False

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
        try:
            cid = await conn.fetchval(
                """INSERT INTO clientes 
                   (user_id, nome, telefone, pacote, valor, vencimento, servidor, outras_informacoes)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8) RETURNING id""",
                user_id, nome, telefone, pacote, valor, vencimento, servidor, outras_informacoes
            )
            logging.info(f"Cliente salvo com ID {cid}")
            return cid
        except Exception as e:
            logging.exception(f"Erro ao salvar cliente: {e}")
            return None

async def get_cliente(pool, cid: int, user_id: int):
    async with pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM clientes WHERE id=$1 AND user_id=$2", cid, user_id)

async def get_template(pool, nome: str):
    async with pool.acquire() as conn:
        return await conn.fetchrow("SELECT conteudo FROM templates WHERE nome=$1", nome)

# =================
# Templates (helper)
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
    # Agendado para rodar 1x/dia; envia logs (troque por send_message se quiser)
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
                logging.info(f"[Aviso {dias}] Para {c['nome']}: {msg}")
                # Exemplo de envio real: await context.bot.send_message(chat_id=<seu_chat_id>, text=msg)

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
        [KeyboardButton("✅ Salvar"), KeyboardButton("❌ Cancelar / Menu Principal")]
    ],
    resize_keyboard=True, is_persistent=True
)

cancel_keyboard = ReplyKeyboardMarkup(
    [[KeyboardButton("❌ Cancelar / Menu Principal")]],
    resize_keyboard=True
)

# =========
# Cancelar (fallback)
# =========
async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ Operação cancelada. Voltando ao menu.", reply_markup=menu_keyboard)
    return ConversationHandler.END

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
    elif text == "GERENCIAR TEMPLATES":
        return await templates_menu(update, context)
    return ConversationHandler.END

async def ask_client_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["nome"] = update.message.text
    await update.message.reply_text("Agora envie o telefone do cliente:", reply_markup=cancel_keyboard)
    return ASK_CLIENT_PHONE

async def ask_client_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["telefone"] = update.message.text
    await update.message.reply_text("Escolha o pacote:", reply_markup=package_keyboard)
    return ASK_CLIENT_PACKAGE

async def ask_client_package(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text
    if texto == "🛠️ PACOTE PERSONALIZADO":
        await update.message.reply_text("Digite o nome do pacote personalizado:", reply_markup=cancel_keyboard)
        return ASK_CLIENT_PACKAGE
    else:
        context.user_data["pacote"] = texto
        await update.message.reply_text("Escolha o valor:", reply_markup=value_keyboard)
        return ASK_CLIENT_VALUE

async def ask_client_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text
    if texto == "💸 OUTRO VALOR":
        await update.message.reply_text("Digite o valor do pacote (ex: 50 ou 50,00):", reply_markup=cancel_keyboard)
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
        await update.message.reply_text("Digite a data de vencimento no formato DD/MM/AAAA:", reply_markup=cancel_keyboard)
        return ASK_CLIENT_DUE
    else:
        context.user_data["vencimento"] = texto
        await update.message.reply_text("Escolha o servidor:", reply_markup=server_keyboard)
        return ASK_CLIENT_SERVER

async def ask_client_server(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text
    if texto == "🖊️ OUTRO SERVIDOR":
        await update.message.reply_text("Digite o nome do servidor:", reply_markup=cancel_keyboard)
        return ASK_CLIENT_SERVER
    else:
        context.user_data["servidor"] = texto
        await update.message.reply_text(
            "Se desejar, informe outras informações. Depois clique em ✅ Salvar ou ❌ Cancelar / Menu Principal.",
            reply_markup=extra_keyboard
        )
        context.user_data["outras_informacoes"] = ""
        return ASK_CLIENT_EXTRA

async def ask_client_extra(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text.startswith("✅"):
        return await confirm_client(update, context)
    elif text.startswith("❌"):
        await update.message.reply_text("Cadastro cancelado.", reply_markup=menu_keyboard)
        context.user_data.clear()
        return ConversationHandler.END
    else:
        context.user_data["outras_informacoes"] = text
        await update.message.reply_text("Clique em ✅ Salvar ou ❌ Cancelar / Menu Principal.", reply_markup=extra_keyboard)
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
    vencem_3dias = sum(1 for r in rows if r["vencimento"] and parse_date(r["vencimento"]) and 0 <= (parse_date(r["vencimento"]) - hoje).days <= 3)
    vencem_7dias = sum(1 for r in rows if r["vencimento"] and parse_date(r["vencimento"]) and 0 <= (parse_date(r["vencimento"]) - hoje).days <= 7)

    mes_ini, mes_fim = month_bounds(hoje)
    recebido_mes = Decimal("0")
    previsto_mes = Decimal("0")
    for r in rows:
        v = parse_money(r["valor"])
        vcto = parse_date(r["vencimento"]) if r["vencimento"] else None
        if vcto and mes_ini <= vcto <= mes_fim:
            previsto_mes += v
        if (r["status_pagamento"] or "").lower() == "pago":
            dp = parse_date(r["data_pagamento"] or "")
            if dp and mes_ini <= dp <= mes_fim:
                recebido_mes += v

    resumo = (
        f"📋 <b>Resumo dos clientes</b>\n"
        f"Total: <b>{total}</b>\n"
        f"Vencem hoje: <b>{vencem_hoje}</b>\n"
        f"Vencem até 3 dias: <b>{vencem_3dias}</b>\n"
        f"Vencem até 7 dias: <b>{vencem_7dias}</b>\n\n"
        f"💰 Recebido no mês: <b>R$ {fmt_money(recebido_mes)}</b>\n"
        f"📊 Previsto no mês: <b>R$ {fmt_money(previsto_mes)}</b>\n\n"
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
    r = await get_cliente(pool, cid, user_id)
    if r:
        detalhes = (
            f"<b>ID:</b> {r['id']}\n"
            f"👤 <b>Nome:</b> {r['nome']}\n"
            f"📱 <b>Telefone:</b> {r['telefone']}\n"
            f"📦 <b>Pacote:</b> {r['pacote']}\n"
            f"💵 <b>Valor:</b> {r['valor']}\n"
            f"📅 <b>Vencimento:</b> {r['vencimento']}\n"
            f"🖥️ <b>Servidor:</b> {r['servidor']}\n"
            f"🔖 <b>Status:</b> {r['status_pagamento']}\n"
            f"✅ <b>Pago em:</b> {r['data_pagamento'] or '-'}\n"
            f"📝 <b>Outras:</b> {r['outras_informacoes'] or '-'}"
        )
        kb = [
            [InlineKeyboardButton("✏️ Editar", callback_data=f"editmenu_{r['id']}")],
            [InlineKeyboardButton("🔄 Renovar", callback_data=f"renew_{r['id']}")],
            [InlineKeyboardButton("🗑️ Excluir", callback_data=f"delete_{r['id']}")],
            [InlineKeyboardButton("📩 Enviar mensagem", callback_data=f"msg_{r['id']}")],
            [InlineKeyboardButton("📌 Usar template agora", callback_data=f"use_tpl_{r['id']}")]
        ]
        await q.edit_message_text(detalhes, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))

# =========
# Editar (submenu + teclados)
# =========
async def edit_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    cid = int(q.data.replace("editmenu_", ""))
    fields = [
        ("👤 Nome", "nome"),
        ("📱 Telefone", "telefone"),
        ("📦 Pacote", "pacote"),
        ("💵 Valor", "valor"),
        ("📅 Vencimento", "vencimento"),
        ("🖥️ Servidor", "servidor"),
        ("📝 Outras informações", "outras_informacoes")
    ]
    kb = [[InlineKeyboardButton(f, callback_data=f"editfield_{cid}_{c}")] for f, c in fields]
    await q.edit_message_text("Escolha o que deseja editar:", reply_markup=InlineKeyboardMarkup(kb))

async def edit_field(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    _, cid, campo = q.data.split("_", 2)
    cid = int(cid)
    context.user_data["edit_cliente"] = cid
    context.user_data["edit_campo"] = campo

    if campo == "pacote":
        await q.message.reply_text("Escolha o novo pacote ou digite um personalizado:", reply_markup=package_keyboard)
        return EDIT_FIELD
    elif campo == "valor":
        await q.message.reply_text("Escolha o novo valor ou digite (ex: 50 ou 50,00):", reply_markup=value_keyboard)
        return EDIT_FIELD
    elif campo == "servidor":
        await q.message.reply_text("Escolha o servidor ou digite outro:", reply_markup=server_keyboard)
        return EDIT_FIELD
    elif campo == "vencimento":
        pool = context.application.bot_data["pool"]
        user_id = update.effective_user.id
        r = await get_cliente(pool, cid, user_id)
        hoje = date.today()
        sugestoes = []
        if r and r["pacote"]:
            prox = hoje + timedelta(days=cycle_days_from_package(r["pacote"]))
            sugestoes.append([prox.strftime("%d/%m/%Y")])
        sugestoes.append(["📅 OUTRA DATA"])
        await q.message.reply_text(
            "Escolha a nova data de vencimento ou digite manualmente:",
            reply_markup=ReplyKeyboardMarkup(sugestoes, resize_keyboard=True, one_time_keyboard=True)
        )
        return EDIT_FIELD
    else:
        await q.message.reply_text(f"Digite o novo valor para {campo}:", reply_markup=cancel_keyboard)
        return EDIT_FIELD

async def save_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    novo_valor = update.message.text
    cid = context.user_data.get("edit_cliente")
    campo = context.user_data.get("edit_campo")
    user_id = update.effective_user.id

    if campo == "pacote" and novo_valor == "🛠️ PACOTE PERSONALIZADO":
        await update.message.reply_text("Digite o nome do pacote personalizado:", reply_markup=cancel_keyboard)
        return EDIT_FIELD
    if campo == "valor" and novo_valor == "💸 OUTRO VALOR":
        await update.message.reply_text("Digite o valor (ex: 50 ou 50,00):", reply_markup=cancel_keyboard)
        return EDIT_FIELD
    if campo == "servidor" and novo_valor == "🖊️ OUTRO SERVIDOR":
        await update.message.reply_text("Digite o nome do servidor:", reply_markup=cancel_keyboard)
        return EDIT_FIELD
    if campo == "vencimento" and novo_valor == "📅 OUTRA DATA":
        await update.message.reply_text("Digite a nova data (DD/MM/AAAA):", reply_markup=cancel_keyboard)
        return EDIT_FIELD

    if campo == "vencimento" and not parse_date(novo_valor):
        await update.message.reply_text("❗ Data inválida. Use DD/MM/AAAA ou YYYY-MM-DD.")
        return EDIT_FIELD

    pool = context.application.bot_data["pool"]
    async with pool.acquire() as conn:
        await conn.execute(f"UPDATE clientes SET {campo}=$1 WHERE id=$2 AND user_id=$3", novo_valor, cid, user_id)

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

async def renew_same_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    cid = int(q.data.replace("renew_same_", ""))
    pool = context.application.bot_data["pool"]
    user_id = update.effective_user.id
    r = await get_cliente(pool, cid, user_id)
    if not r:
        await q.edit_message_text("Cliente não encontrado.")
        return
    dias = cycle_days_from_package(r["pacote"])
    base = parse_date(r["vencimento"]) or date.today()
    novo = base + timedelta(days=dias)
    novo_str = novo.strftime("%d/%m/%Y")
    async with pool.acquire() as conn:
        await conn.execute("UPDATE clientes SET vencimento=$1 WHERE id=$2 AND user_id=$3", novo_str, cid, user_id)
    await q.edit_message_text(f"✅ Renovado! Novo vencimento: {novo_str}")

async def renew_new_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    cid = int(q.data.replace("renew_new_", ""))
    context.user_data["renew_cliente"] = cid
    await q.message.reply_text("Digite a nova data de vencimento (DD/MM/AAAA):", reply_markup=cancel_keyboard)
    return RENEW_DATE

async def renew_save_new_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cid = context.user_data.get("renew_cliente")
    user_id = update.effective_user.id
    texto = update.message.text
    if not parse_date(texto):
        await update.message.reply_text("❗ Data inválida. Use DD/MM/AAAA ou YYYY-MM-DD.")
        return RENEW_DATE
    pool = context.application.bot_data["pool"]
    async with pool.acquire() as conn:
        await conn.execute("UPDATE clientes SET vencimento=$1 WHERE id=$2 AND user_id=$3", texto, cid, user_id)
    await update.message.reply_text(f"✅ Renovado! Novo vencimento: {texto}", reply_markup=menu_keyboard)
    context.user_data.clear()
    return ConversationHandler.END

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
    user_id = update.effective_user.id
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM clientes WHERE id=$1 AND user_id=$2", cid, user_id)
    await q.edit_message_text("✅ Cliente excluído com sucesso.")

# =========
# Enviar mensagem (individual, livre)
# =========
async def msg_client(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    cid = int(q.data.replace("msg_", ""))
    context.user_data["msg_cliente"] = cid
    await q.message.reply_text("Digite a mensagem para enviar ao cliente:", reply_markup=cancel_keyboard)
    return SEND_MESSAGE

async def send_message_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.text
    cid = context.user_data.get("msg_cliente")
    await update.message.reply_text(f"📩 Mensagem enviada para cliente {cid}:\n\n{msg}", reply_markup=menu_keyboard)
    context.user_data.clear()
    return ConversationHandler.END

# =========
# USAR TEMPLATE AGORA (para 1 cliente)
# =========
async def use_template_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Abre a lista de templates para um cliente específico."""
    q = update.callback_query
    await q.answer()
    cid = int(q.data.replace("use_tpl_", ""))
    pool = context.application.bot_data["pool"]
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT id, nome FROM templates ORDER BY id")
    if not rows:
        await q.edit_message_text("⚠️ Nenhum template cadastrado. Use o menu GERENCIAR TEMPLATES para criar um.",)
        return
    buttons = []
    for r in rows:
        buttons.append([InlineKeyboardButton(r["nome"], callback_data=f"use_tplsel_{cid}_{r['id']}")])
    buttons.append([InlineKeyboardButton("⬅️ Voltar", callback_data=f"cliente_{cid}")])
    await q.edit_message_text("📌 Escolha um template para enviar agora:", reply_markup=InlineKeyboardMarkup(buttons))

async def use_template_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Seleciona o template, aplica variáveis e envia a mensagem no chat."""
    q = update.callback_query
    await q.answer()
    _, cid_str, tid_str = q.data.split("_", 2)
    cid = int(cid_str)
    tid = int(tid_str)
    pool = context.application.bot_data["pool"]
    user_id = update.effective_user.id

    # Pega cliente e template
    cliente = await get_cliente(pool, cid, user_id)
    if not cliente:
        await q.edit_message_text("Cliente não encontrado.")
        return
    async with pool.acquire() as conn:
        tpl = await conn.fetchrow("SELECT * FROM templates WHERE id=$1", tid)
    if not tpl:
        await q.edit_message_text("Template não encontrado.")
        return

    # Aplica e envia
    texto = aplicar_template(tpl["conteudo"], cliente)
    await q.message.reply_text(f"📨 Mensagem gerada a partir de <b>{tpl['nome']}</b>:\n\n{texto}", parse_mode="HTML")
    # Opcional: se quiser voltar ao menu do cliente depois:
    await cliente_callback(update, context)

# =========
# Templates: CRUD via bot
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
        await update.message.reply_text("Digite o nome do template (ex: aviso_-2, aviso_-1, aviso_0, aviso_1):", reply_markup=cancel_keyboard)
        return TEMPLATE_NAME
    elif choice == "📋 Listar Templates":
        pool = context.application.bot_data["pool"]
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM templates ORDER BY id")
        if not rows:
            await update.message.reply_text("Nenhum template cadastrado.", reply_markup=menu_keyboard)
            return ConversationHandler.END
        buttons = [[InlineKeyboardButton(f"{r['nome']}", callback_data=f"tpl_{r['id']}")] for r in rows]
        await update.message.reply_text("Templates cadastrados:", reply_markup=InlineKeyboardMarkup(buttons))
        return ConversationHandler.END
    elif choice.startswith("❌"):
        return await cancelar(update, context)
    return TEMPLATE_ACTION

async def template_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["tpl_nome"] = update.message.text.strip()
    await update.message.reply_text("Digite o conteúdo do template (use variáveis {nome}, {dias_restantes}, {pacote}, {valor}, {vencimento}, {servidor}):", reply_markup=cancel_keyboard)
    return TEMPLATE_CONTENT

async def template_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nome = context.user_data["tpl_nome"]
    conteudo = update.message.text
    pool = context.application.bot_data["pool"]
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO templates (nome, conteudo) VALUES ($1,$2) ON CONFLICT (nome) DO UPDATE SET conteudo=$2",
            nome, conteudo
        )
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
async def main():
    logging.basicConfig(level=logging.INFO)
    if not TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN não definido.")
    if not POSTGRES_URL:
        raise RuntimeError("POSTGRES_URL não definido.")

    application = Application.builder().token(TOKEN).build()
    pool = await create_pool()
    await init_db(pool)
    application.bot_data["pool"] = pool

    # Conversa de CADASTRO
    conv_add = ConversationHandler(
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
        fallbacks=[MessageHandler(filters.Regex("^❌ Cancelar / Menu Principal$"), cancelar)],
        allow_reentry=True
    )

    # Conversa de EDIÇÃO
    conv_edit = ConversationHandler(
        entry_points=[CallbackQueryHandler(edit_field, pattern=r"^editfield_")],
        states={EDIT_FIELD: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_edit)]},
        fallbacks=[MessageHandler(filters.Regex("^❌ Cancelar / Menu Principal$"), cancelar)],
        allow_reentry=True
    )

    # Conversa de MENSAGEM
    conv_msg = ConversationHandler(
        entry_points=[CallbackQueryHandler(msg_client, pattern=r"^msg_")],
        states={SEND_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, send_message_done)]},
        fallbacks=[MessageHandler(filters.Regex("^❌ Cancelar / Menu Principal$"), cancelar)],
        allow_reentry=True
    )

    # Conversa de RENOVAÇÃO (nova data)
    conv_renew = ConversationHandler(
        entry_points=[CallbackQueryHandler(renew_new_handler, pattern=r"^renew_new_")],
        states={RENEW_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, renew_save_new_date)]},
        fallbacks=[MessageHandler(filters.Regex("^❌ Cancelar / Menu Principal$"), cancelar)],
        allow_reentry=True
    )

    # Conversa de TEMPLATES (CRUD)
    conv_templates = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^GERENCIAR TEMPLATES$"), templates_menu)],
        states={
            TEMPLATE_ACTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, template_action)],
            TEMPLATE_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, template_name)],
            TEMPLATE_CONTENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, template_content)],
            TEMPLATE_EDIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, template_edit_save)],
        },
        fallbacks=[MessageHandler(filters.Regex("^❌ Cancelar / Menu Principal$"), cancelar)],
        allow_reentry=True
    )

    # Handlers gerais
    application.add_handler(CommandHandler("start", start))
    application.add_handler(conv_add)
    application.add_handler(conv_edit)
    application.add_handler(conv_msg)
    application.add_handler(conv_renew)
    application.add_handler(conv_templates)

    # Listar clientes
    application.add_handler(MessageHandler(filters.Regex("^LISTAR CLIENTES$"), listar_clientes))

    # Callbacks de clientes (e menu de uso de template agora)
    application.add_handler(CallbackQueryHandler(cliente_callback, pattern=r"^cliente_"))
    application.add_handler(CallbackQueryHandler(edit_menu, pattern=r"^editmenu_"))
    application.add_handler(CallbackQueryHandler(renew, pattern=r"^renew_"))
    application.add_handler(CallbackQueryHandler(renew_same_handler, pattern=r"^renew_same_"))
    application.add_handler(CallbackQueryHandler(delete_client, pattern=r"^delete_[0-9]+$"))
    application.add_handler(CallbackQueryHandler(delete_yes, pattern=r"^delete_yes_"))
    application.add_handler(CallbackQueryHandler(use_template_menu, pattern=r"^use_tpl_\d+$"))
    application.add_handler(CallbackQueryHandler(use_template_select, pattern=r"^use_tplsel_\d+_\d+$"))

    # Callbacks de templates
    application.add_handler(CallbackQueryHandler(template_callback, pattern=r"^tpl_\d+"))
    application.add_handler(CallbackQueryHandler(template_edit, pattern=r"^tpl_edit_\d+"))
    application.add_handler(CallbackQueryHandler(template_delete, pattern=r"^tpl_del_\d+"))

    # Scheduler de notificações (opcional)
    if APSCHED_AVAILABLE:
        scheduler = AsyncIOScheduler()
        scheduler.add_job(enviar_notificacoes, "cron", hour=9, args=[application])
        scheduler.start()
        logging.info("Scheduler iniciado para notificações diárias às 09:00.")
    else:
        logging.warning("APScheduler não disponível. Notificações automáticas desativadas.")

    await application.run_polling()

import sys, asyncio
if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
