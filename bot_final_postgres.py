#!/usr/bin/env python3
# Bot Telegram Gestão de Clientes – Railway + PostgreSQL, tudo em um arquivo

import os
import sys
import logging
import psycopg2
import psycopg2.extras
import pytz
from datetime import datetime, timedelta
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler, CallbackQueryHandler
from telegram import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton

# --------- CONFIGURAÇÕES GLOBAIS ---------

TIMEZONE_BR = pytz.timezone('America/Sao_Paulo')

def agora_br():
    return datetime.now(TIMEZONE_BR)

def formatar_data_br(dt):
    if isinstance(dt, str): dt = datetime.strptime(dt, '%Y-%m-%d')
    return dt.strftime('%d/%m/%Y')

def formatar_datetime_br(dt):
    if dt.tzinfo is None: dt = TIMEZONE_BR.localize(dt)
    return dt.strftime('%d/%m/%Y às %H:%M')

def escapar_html(text):
    if text is None: return ""
    text = str(text)
    text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    text = text.replace('"', '&quot;').replace("'", '&#x27;')
    return text

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO)
logger = logging.getLogger(__name__)

# --- ESTADOS DE CONVERSA ---
NOME, TELEFONE, PACOTE, VALOR, SERVIDOR, VENCIMENTO, CONFIRMAR = range(7)
EDIT_NOME, EDIT_TELEFONE, EDIT_PACOTE, EDIT_VALOR, EDIT_SERVIDOR, EDIT_VENCIMENTO = range(7, 13)
CONFIG_EMPRESA, CONFIG_PIX, CONFIG_SUPORTE = range(13, 16)

# --------- BANCO DE DADOS POSTGRESQL ---------
class DatabaseManager:
    def __init__(self):
        self.conn = psycopg2.connect(
            host=os.getenv('PGHOST'),
            database=os.getenv('PGDATABASE'),
            user=os.getenv('PGUSER'),
            password=os.getenv('PGPASSWORD'),
            port=os.getenv('PGPORT') or 5432
        )
        self.conn.autocommit = True

    def listar_clientes(self, ativo_apenas=True):
        with self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            if ativo_apenas:
                cur.execute("SELECT * FROM clientes WHERE vencimento >= CURRENT_DATE ORDER BY vencimento ASC")
            else:
                cur.execute("SELECT * FROM clientes ORDER BY vencimento ASC")
            resultados = cur.fetchall()
            lista = []
            for row in resultados:
                lista.append(dict(row))
            return lista

    def adicionar_cliente(self, nome, telefone, pacote, valor, vencimento, servidor):
        with self.conn.cursor() as cur:
            cur.execute("""INSERT INTO clientes (nome, telefone, pacote, plano, vencimento, servidor)
                        VALUES (%s, %s, %s, %s, %s, %s)""",
                        (nome, telefone, pacote, valor, vencimento, servidor))
            return True

    def buscar_cliente_por_telefone(self, telefone):
        with self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute("SELECT * FROM clientes WHERE telefone = %s ORDER BY id DESC LIMIT 1", (telefone,))
            r = cur.fetchone()
            return dict(r) if r else None

    def atualizar_cliente(self, cliente_id, campo, valor):
        campos_validos = {'nome', 'telefone', 'pacote', 'valor', 'plano', 'servidor', 'vencimento'}
        if campo == 'valor':
            campo = 'plano'
        if campo not in campos_validos:
            return False
        with self.conn.cursor() as cur:
            cur.execute(f"UPDATE clientes SET {campo}=%s WHERE id=%s", (valor, cliente_id))
            return cur.rowcount > 0

    def excluir_cliente(self, cliente_id):
        with self.conn.cursor() as cur:
            cur.execute("DELETE FROM clientes WHERE id=%s", (cliente_id,))
            return cur.rowcount > 0

    def registrar_renovacao(self, cliente_id, dias, valor):
        with self.conn.cursor() as cur:
            cur.execute("INSERT INTO historico_renovacoes (cliente_id, dias_renovados, valor) VALUES (%s, %s, %s)",
                        (cliente_id, dias, valor))
            return True

    def get_configuracoes(self):
        with self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute("SELECT * FROM configuracoes ORDER BY id DESC LIMIT 1")
            r = cur.fetchone()
            return dict(r) if r else None

    def salvar_configuracoes(self, empresa, pix, suporte):
        config = self.get_configuracoes()
        with self.conn.cursor() as cur:
            if config:
                cur.execute("UPDATE configuracoes SET empresa_nome=%s, pix_key=%s, contato_suporte=%s WHERE id=%s",
                            (empresa, pix, suporte, config['id']))
            else:
                cur.execute("INSERT INTO configuracoes (empresa_nome, pix_key, contato_suporte) VALUES (%s,%s,%s)",
                            (empresa, pix, suporte))
            return True

# --------- TECLADOS ---------
def criar_teclado_principal():
    keyboard = [
        [KeyboardButton("👥 Listar Clientes"), KeyboardButton("➕ Adicionar Cliente")],
        [KeyboardButton("🔍 Buscar Cliente"), KeyboardButton("📊 Relatórios")],
        [KeyboardButton("📄 Templates"), KeyboardButton("⏰ Agendador")],
        [KeyboardButton("📋 Fila de Mensagens"), KeyboardButton("📜 Logs de Envios")],
        [KeyboardButton("📱 WhatsApp Status"), KeyboardButton("🧪 Testar WhatsApp")],
        [KeyboardButton("📱 QR Code"), KeyboardButton("⚙️ Gerenciar WhatsApp")],
        [KeyboardButton("🏢 Empresa"), KeyboardButton("💳 PIX"), KeyboardButton("📞 Suporte")],
        [KeyboardButton("❓ Ajuda")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)

def criar_teclado_cancelar():
    return ReplyKeyboardMarkup([[KeyboardButton("❌ Cancelar")]], resize_keyboard=True, one_time_keyboard=True)

def criar_teclado_confirmar():
    keyboard = [[KeyboardButton("✅ Confirmar"), KeyboardButton("✏️ Editar")], [KeyboardButton("❌ Cancelar")]]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)

def criar_teclado_planos():
    keyboard = [[KeyboardButton("📅 1 mês"), KeyboardButton("📅 3 meses")],
                [KeyboardButton("📅 6 meses"), KeyboardButton("📅 1 ano")],
                [KeyboardButton("✏️ Personalizado"), KeyboardButton("❌ Cancelar")]]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)

def criar_teclado_vencimento():
    keyboard = [[KeyboardButton("✅ Usar data automática"), KeyboardButton("📅 Data personalizada")],
                [KeyboardButton("❌ Cancelar")]]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)

def criar_teclado_valores():
    keyboard = [
        [KeyboardButton("💰 R$ 30,00"), KeyboardButton("💰 R$ 35,00"), KeyboardButton("💰 R$ 40,00")],
        [KeyboardButton("💰 R$ 45,00"), KeyboardButton("💰 R$ 50,00"), KeyboardButton("💰 R$ 60,00")],
        [KeyboardButton("💰 R$ 70,00"), KeyboardButton("💰 R$ 90,00"), KeyboardButton("💰 R$ 135,00")],
        [KeyboardButton("✏️ Valor personalizado"), KeyboardButton("❌ Cancelar")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)

# --------- DECORATOR ADMIN ---------
def verificar_admin(func):
    async def wrapper(update, context):
        admin_id = int(os.getenv('ADMIN_CHAT_ID', '0'))
        if update.effective_chat.id != admin_id:
            await update.message.reply_text("❌ Acesso negado. Apenas o admin pode usar este bot.")
            return
        return await func(update, context)
    return wrapper

# --------- HANDLERS PRINCIPAIS ---------
@verificar_admin
async def start(update, context):
    nome_admin = update.effective_user.first_name
    try:
        db = DatabaseManager()
        total_clientes = len(db.listar_clientes())
    except:
        total_clientes = 0
    mensagem = f"""🤖 *Bot de Gestão de Clientes*

Olá *{nome_admin}!* 

✅ Sistema inicializado com sucesso!
📊 Total de clientes: {total_clientes}

Use os botões abaixo para navegar:
👥 *Listar Clientes* - Ver todos os clientes
➕ *Adicionar Cliente* - Cadastrar novo cliente
📊 *Relatórios* - Estatísticas do sistema
🔍 *Buscar Cliente* - Encontrar cliente específico
⚙️ *Configurações* - Configurar empresa
❓ *Ajuda* - Ajuda completa

🚀 Sistema 100% operacional!"""
    await update.message.reply_text(mensagem, parse_mode='Markdown', reply_markup=criar_teclado_principal())

# --------- CONTINUA... ---------
# --------- CONTINUAÇÃO DO BOT ---------
# (cadastro, listagem, confirmação etc)

@verificar_admin
async def iniciar_cadastro(update, context):
    await update.message.reply_text(
        "📝 *Cadastro de Novo Cliente*\n\n"
        "Vamos cadastrar um cliente passo a passo.\n\n"
        "**Passo 1/6:** Digite o *nome completo* do cliente:",
        parse_mode='Markdown',
        reply_markup=criar_teclado_cancelar())
    return NOME

async def receber_nome(update, context):
    if update.message.text == "❌ Cancelar":
        return await cancelar_cadastro(update, context)
    nome = update.message.text.strip()
    if len(nome) < 2:
        await update.message.reply_text(
            "❌ Nome muito curto. Digite um nome válido:",
            reply_markup=criar_teclado_cancelar())
        return NOME
    context.user_data['nome'] = nome
    await update.message.reply_text(
        f"✅ Nome: *{nome}*\n\n"
        "**Passo 2/6:** Digite o *telefone* (apenas números):\n\n"
        "*Exemplo:* 11999999999",
        parse_mode='Markdown',
        reply_markup=criar_teclado_cancelar())
    return TELEFONE

async def receber_telefone(update, context):
    if update.message.text == "❌ Cancelar":
        return await cancelar_cadastro(update, context)
    telefone = update.message.text.strip().replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
    if not telefone.isdigit() or len(telefone) < 10:
        await update.message.reply_text(
            "❌ Telefone inválido. Digite apenas números (ex: 11999999999):",
            reply_markup=criar_teclado_cancelar())
        return TELEFONE
    context.user_data['telefone'] = telefone
    await update.message.reply_text(
        f"✅ Telefone: *{telefone}*\n\n"
        "**Passo 3/6:** Escolha o *plano de duração*:\n\n"
        "Selecione uma das opções ou digite um plano personalizado:",
        parse_mode='Markdown',
        reply_markup=criar_teclado_planos())
    return PACOTE

async def receber_pacote(update, context):
    if update.message.text == "❌ Cancelar":
        return await cancelar_cadastro(update, context)
    texto = update.message.text.strip()
    # Planos predefinidos
    if texto == "📅 1 mês":
        pacote = "Plano 1 mês"
    elif texto == "📅 3 meses":
        pacote = "Plano 3 meses"
    elif texto == "📅 6 meses":
        pacote = "Plano 6 meses"
    elif texto == "📅 1 ano":
        pacote = "Plano 1 ano"
    elif texto == "✏️ Personalizado":
        await update.message.reply_text(
            "✏️ Digite o nome do seu plano personalizado:\n\n"
            "*Exemplos:* Netflix Premium, Disney+ 4K, Combo Streaming",
            parse_mode='Markdown',
            reply_markup=criar_teclado_cancelar())
        return PACOTE
    else:
        pacote = texto
        if len(pacote) < 2:
            await update.message.reply_text(
                "❌ Nome do pacote muito curto. Digite um nome válido:",
                reply_markup=criar_teclado_planos())
            return PACOTE
    context.user_data['pacote'] = pacote
    hoje = agora_br().replace(tzinfo=None)
    if "1 mês" in pacote:
        vencimento_auto = hoje + timedelta(days=30)
    elif "3 meses" in pacote:
        vencimento_auto = hoje + timedelta(days=90)
    elif "6 meses" in pacote:
        vencimento_auto = hoje + timedelta(days=180)
    elif "1 ano" in pacote:
        vencimento_auto = hoje + timedelta(days=365)
    else:
        vencimento_auto = hoje + timedelta(days=30)
    context.user_data['vencimento_auto'] = vencimento_auto.strftime('%Y-%m-%d')
    await update.message.reply_text(
        f"✅ Pacote: *{pacote}*\n\n"
        "**Passo 4/6:** Escolha o *valor mensal*:\n\n"
        "Selecione um valor ou digite um personalizado:",
        parse_mode='Markdown',
        reply_markup=criar_teclado_valores())
    return VALOR

async def receber_valor(update, context):
    if update.message.text == "❌ Cancelar":
        return await cancelar_cadastro(update, context)
    texto = update.message.text.strip()
    try:
        if texto == "💰 R$ 30,00": valor = 30.00
        elif texto == "💰 R$ 35,00": valor = 35.00
        elif texto == "💰 R$ 40,00": valor = 40.00
        elif texto == "💰 R$ 45,00": valor = 45.00
        elif texto == "💰 R$ 50,00": valor = 50.00
        elif texto == "💰 R$ 60,00": valor = 60.00
        elif texto == "💰 R$ 70,00": valor = 70.00
        elif texto == "💰 R$ 90,00": valor = 90.00
        elif texto == "💰 R$ 135,00": valor = 135.00
        elif texto == "✏️ Valor personalizado":
            await update.message.reply_text(
                "✏️ Digite o valor personalizado:\n\n"
                "*Exemplos:* 25.90, 85, 149.99",
                parse_mode='Markdown',
                reply_markup=criar_teclado_cancelar())
            return VALOR
        else:
            valor_str = texto.replace(',', '.').replace('R$', '').replace(' ', '')
            valor = float(valor_str)
            if valor <= 0: raise ValueError
    except Exception:
        await update.message.reply_text(
            "❌ Valor inválido. Digite um número válido (ex: 25.90):",
            reply_markup=criar_teclado_valores())
        return VALOR
    context.user_data['valor'] = valor
    await update.message.reply_text(
        f"✅ Valor: *R$ {valor:.2f}*\n\n"
        "**Passo 5/6:** Digite o *servidor*:\n\n"
        "*Exemplos:* Servidor 1, Premium Server, Fast Play",
        parse_mode='Markdown',
        reply_markup=criar_teclado_cancelar())
    return SERVIDOR

async def receber_servidor(update, context):
    if update.message.text == "❌ Cancelar":
        return await cancelar_cadastro(update, context)
    servidor = update.message.text.strip()
    if len(servidor) < 2:
        await update.message.reply_text(
            "❌ Nome do servidor muito curto. Digite um nome válido:",
            reply_markup=criar_teclado_cancelar())
        return SERVIDOR
    context.user_data['servidor'] = servidor
    vencimento_auto = context.user_data.get('vencimento_auto')
    if vencimento_auto:
        data_formatada = datetime.strptime(vencimento_auto, '%Y-%m-%d').strftime('%d/%m/%Y')
        await update.message.reply_text(
            f"✅ Servidor: *{servidor}*\n\n"
            f"**Passo 6/6:** *Data de vencimento*\n\n"
            f"📅 *Data automática calculada:* {data_formatada}\n\n"
            "Deseja usar esta data ou personalizar?",
            parse_mode='Markdown',
            reply_markup=criar_teclado_vencimento())
    else:
        await update.message.reply_text(
            f"✅ Servidor: *{servidor}*\n\n"
            "**Passo 6/6:** Digite a *data de vencimento*:\n\n"
            "*Formato:* AAAA-MM-DD\n"
            "*Exemplo:* 2025-03-15",
            parse_mode='Markdown',
            reply_markup=criar_teclado_cancelar())
    return VENCIMENTO

async def receber_vencimento(update, context):
    if update.message.text == "❌ Cancelar":
        return await cancelar_cadastro(update, context)
    texto = update.message.text.strip()
    if texto == "✅ Usar data automática":
        data_str = context.user_data.get('vencimento_auto')
        if not data_str:
            await update.message.reply_text(
                "❌ Erro: data automática não encontrada. Digite manualmente:",
                reply_markup=criar_teclado_cancelar())
            return VENCIMENTO
    elif texto == "📅 Data personalizada":
        await update.message.reply_text(
            "📅 Digite a data de vencimento personalizada:\n\n"
            "*Formato:* AAAA-MM-DD\n"
            "*Exemplo:* 2025-03-15",
            parse_mode='Markdown',
            reply_markup=criar_teclado_cancelar())
        return VENCIMENTO
    else:
        data_str = texto
        try:
            data_obj = datetime.strptime(data_str, '%Y-%m-%d')
            if data_obj < agora_br().replace(tzinfo=None):
                await update.message.reply_text(
                    "❌ Data não pode ser no passado. Digite uma data futura:",
                    reply_markup=criar_teclado_cancelar())
                return VENCIMENTO
        except ValueError:
            await update.message.reply_text(
                "❌ Data inválida. Use o formato AAAA-MM-DD (ex: 2025-03-15):",
                reply_markup=criar_teclado_vencimento())
            return VENCIMENTO
    context.user_data['vencimento'] = data_str
    data_obj = datetime.strptime(data_str, '%Y-%m-%d')
    dados = context.user_data
    data_formatada = data_obj.strftime('%d/%m/%Y')
    resumo = f"""📋 *CONFIRMAR CADASTRO*

📝 *Nome:* {dados['nome']}
📱 *Telefone:* {dados['telefone']}
📦 *Pacote:* {dados['pacote']}
💰 *Valor:* R$ {dados['valor']:.2f}
🖥️ *Servidor:* {dados['servidor']}
📅 *Vencimento:* {data_formatada}

Os dados estão corretos?"""
    await update.message.reply_text(resumo, parse_mode='Markdown', reply_markup=criar_teclado_confirmar())
    return CONFIRMAR

async def confirmar_cadastro(update, context):
    if update.message.text == "❌ Cancelar":
        return await cancelar_cadastro(update, context)
    elif update.message.text == "✏️ Editar":
        await update.message.reply_text(
            "✏️ *Qual campo deseja editar?*\n\n"
            "Digite o número:\n"
            "1 - Nome\n"
            "2 - Telefone\n"
            "3 - Pacote\n"
            "4 - Valor\n"
            "5 - Servidor\n"
            "6 - Vencimento",
            parse_mode='Markdown',
            reply_markup=criar_teclado_cancelar())
        return CONFIRMAR
    elif update.message.text == "✅ Confirmar":
        try:
            db = DatabaseManager()
            dados = context.user_data
            sucesso = db.adicionar_cliente(dados['nome'], dados['telefone'],
                                           dados['pacote'], dados['valor'],
                                           dados['vencimento'],
                                           dados['servidor'])
            if sucesso:
                data_formatada = datetime.strptime(
                    dados['vencimento'], '%Y-%m-%d').strftime('%d/%m/%Y')
                await update.message.reply_text(
                    f"✅ *CLIENTE CADASTRADO COM SUCESSO!*\n\n"
                    f"📝 {dados['nome']}\n"
                    f"📱 {dados['telefone']}\n"
                    f"📦 {dados['pacote']}\n"
                    f"💰 R$ {dados['valor']:.2f}\n"
                    f"🖥️ {dados['servidor']}\n"
                    f"📅 {data_formatada}\n\n"
                    "Cliente adicionado ao sistema!",
                    parse_mode='Markdown',
                    reply_markup=criar_teclado_principal())
            else:
                await update.message.reply_text(
                    "❌ Erro ao salvar cliente. Tente novamente.",
                    reply_markup=criar_teclado_principal())
            context.user_data.clear()
            return ConversationHandler.END
        except Exception as e:
            logger.error(f"Erro ao cadastrar cliente: {e}")
            await update.message.reply_text(
                "❌ Erro interno. Tente novamente mais tarde.",
                reply_markup=criar_teclado_principal())
            context.user_data.clear()
            return ConversationHandler.END
    # Edição manual por número
    try:
        opcao = int(update.message.text)
        if opcao == 1:
            await update.message.reply_text("Digite o novo nome:", reply_markup=criar_teclado_cancelar())
            return NOME
        elif opcao == 2:
            await update.message.reply_text("Digite o novo telefone:", reply_markup=criar_teclado_cancelar())
            return TELEFONE
        elif opcao == 3:
            await update.message.reply_text("Digite o novo pacote:", reply_markup=criar_teclado_cancelar())
            return PACOTE
        elif opcao == 4:
            await update.message.reply_text("Digite o novo valor:", reply_markup=criar_teclado_cancelar())
            return VALOR
        elif opcao == 5:
            await update.message.reply_text("Digite o novo servidor:", reply_markup=criar_teclado_cancelar())
            return SERVIDOR
        elif opcao == 6:
            await update.message.reply_text("Digite a nova data (AAAA-MM-DD):", reply_markup=criar_teclado_cancelar())
            return VENCIMENTO
    except ValueError:
        pass
    await update.message.reply_text(
        "❌ Opção inválida. Use os botões ou digite um número de 1 a 6:",
        reply_markup=criar_teclado_confirmar())
    return CONFIRMAR

async def cancelar_cadastro(update, context):
    context.user_data.clear()
    await update.message.reply_text("❌ Cadastro cancelado.", reply_markup=criar_teclado_principal())
    return ConversationHandler.END

# CONTINUA...
# --------- LISTAGEM E BUSCA DE CLIENTES ---------
@verificar_admin
async def listar_clientes(update, context):
    try:
        db = DatabaseManager()
        clientes = db.listar_clientes(ativo_apenas=False)
        if not clientes:
            await update.message.reply_text(
                "📋 Nenhum cliente cadastrado ainda.\n\n"
                "Use ➕ Adicionar Cliente para começar!",
                reply_markup=criar_teclado_principal())
            return
        # Ordenar por data de vencimento
        clientes_ordenados = []
        for cliente in clientes:
            try:
                vencimento = datetime.strptime(cliente['vencimento'], '%Y-%m-%d')
                cliente['vencimento_obj'] = vencimento
                cliente['dias_restantes'] = (vencimento - agora_br().replace(tzinfo=None)).days
                clientes_ordenados.append(cliente)
            except Exception as e:
                logger.error(f"Erro ao processar cliente {cliente}: {e}")
                continue
        clientes_ordenados.sort(key=lambda x: x['vencimento_obj'])
        total_clientes = len(clientes_ordenados)
        hoje = agora_br().replace(tzinfo=None)
        vencidos = len([c for c in clientes_ordenados if c['dias_restantes'] < 0])
        vencendo_hoje = len([c for c in clientes_ordenados if c['dias_restantes'] == 0])
        vencendo_breve = len([c for c in clientes_ordenados if 0 < c['dias_restantes'] <= 3])
        ativos = total_clientes - vencidos
        mensagem = f"""👥 *LISTA DE CLIENTES*

📊 *Resumo:* {total_clientes} clientes
🔴 {vencidos} vencidos • ⚠️ {vencendo_hoje} hoje • 🟡 {vencendo_breve} em breve • 🟢 {ativos} ativos

💡 *Clique em um cliente para ver detalhes:*"""
        keyboard = []
        for cliente in clientes_ordenados[:50]:
            dias_restantes = cliente['dias_restantes']
            vencimento = cliente['vencimento_obj']
            if dias_restantes < 0:
                status_emoji = "🔴"
            elif dias_restantes == 0:
                status_emoji = "⚠️"
            elif dias_restantes <= 3:
                status_emoji = "🟡"
            else:
                status_emoji = "🟢"
            nome_curto = cliente['nome'][:18] + "..." if len(cliente['nome']) > 18 else cliente['nome']
            botao_texto = f"{status_emoji} {nome_curto} - R${cliente['plano']:.0f} - {vencimento.strftime('%d/%m')}"
            keyboard.append([
                InlineKeyboardButton(botao_texto, callback_data=f"cliente_{cliente['id']}")
            ])
        if total_clientes > 50:
            mensagem += f"\n\n⚠️ *Mostrando primeiros 50 de {total_clientes} clientes*\nUse 🔍 Buscar Cliente para encontrar outros."
        keyboard.append([
            InlineKeyboardButton("🔄 Atualizar Lista", callback_data="atualizar_lista"),
            InlineKeyboardButton("📊 Relatório", callback_data="gerar_relatorio")
        ])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(mensagem, parse_mode='Markdown', reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Erro ao listar clientes: {e}")
        await update.message.reply_text("❌ Erro ao listar clientes!", reply_markup=criar_teclado_principal())

@verificar_admin
async def buscar_cliente(update, context):
    try:
        if not context.args:
            await update.message.reply_text(
                "❌ Por favor, informe o telefone!\n\n"
                "Exemplo: `/buscar 11999999999`",
                parse_mode='Markdown',
                reply_markup=criar_teclado_principal())
            return
        telefone = context.args[0]
        db = DatabaseManager()
        cliente = db.buscar_cliente_por_telefone(telefone)
        if not cliente:
            await update.message.reply_text(
                f"❌ Cliente com telefone {telefone} não encontrado.",
                reply_markup=criar_teclado_principal())
            return
        vencimento = datetime.strptime(cliente['vencimento'], '%Y-%m-%d')
        mensagem = f"""👤 *Cliente Encontrado*

📝 *Nome:* {cliente['nome']}
📱 *Telefone:* {cliente['telefone']}
📦 *Pacote:* {cliente['pacote']}
💰 *Valor:* R$ {cliente['plano']:.2f}
📅 *Vencimento:* {vencimento.strftime('%d/%m/%Y')}
🖥️ *Servidor:* {cliente['servidor']}"""
        await update.message.reply_text(mensagem, parse_mode='Markdown', reply_markup=criar_teclado_principal())
    except Exception as e:
        logger.error(f"Erro ao buscar cliente: {e}")
        await update.message.reply_text("❌ Erro ao buscar cliente!", reply_markup=criar_teclado_principal())

# --------- RELATÓRIO SIMPLES DE CLIENTES ---------
@verificar_admin
async def relatorio(update, context):
    try:
        db = DatabaseManager()
        clientes = db.listar_clientes(ativo_apenas=False)
        total_clientes = len(clientes)
        receita_total = sum(float(c['plano']) for c in clientes)
        hoje = agora_br().replace(tzinfo=None).strftime('%Y-%m-%d')
        vencendo_hoje = [c for c in clientes if str(c['vencimento']) == hoje]
        mensagem = f"""📊 *RELATÓRIO GERAL*

👥 Total de clientes: {total_clientes}
💰 Receita mensal: R$ {receita_total:.2f}
⚠️ Vencendo hoje: {len(vencendo_hoje)}

📅 Data: {agora_br().replace(tzinfo=None).strftime('%d/%m/%Y %H:%M')}"""
        await update.message.reply_text(mensagem, parse_mode='Markdown', reply_markup=criar_teclado_principal())
    except Exception as e:
        logger.error(f"Erro no relatório: {e}")
        await update.message.reply_text("❌ Erro ao gerar relatório!")

# --------- AJUDA ---------
@verificar_admin
async def help_cmd(update, context):
    mensagem = """🆘 *COMANDOS DISPONÍVEIS*

*Gestão de Clientes:*
/start - Iniciar o bot
/add - Adicionar cliente
/listar - Listar todos os clientes
/relatorio - Relatório geral
/buscar - Buscar cliente por telefone
/help - Esta ajuda

*Exemplo:*
`/add João Silva | 11999999999 | Netflix | 25.90 | 2025-03-15 | Servidor1`

🤖 Bot funcionando 24/7!"""
    await update.message.reply_text(mensagem, parse_mode='Markdown', reply_markup=criar_teclado_principal())

# --------- MAIN ---------
def main():
    token = os.getenv('BOT_TOKEN')
    admin_id = os.getenv('ADMIN_CHAT_ID')
    if not token:
        print("❌ BOT_TOKEN não configurado!")
        sys.exit(1)
    if not admin_id:
        print("❌ ADMIN_CHAT_ID não configurado!")
        sys.exit(1)
    print("🚀 Iniciando bot Telegram...")

    try:
        db = DatabaseManager()
        print("✅ Banco de dados PostgreSQL OK")
    except Exception as e:
        print(f"⚠️ Database: {e}")

    app = Application.builder().token(token).build()

    # ConversationHandler para cadastro escalonável
    cadastro_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^➕ Adicionar Cliente$"), iniciar_cadastro)
        ],
        states={
            NOME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_nome)],
            TELEFONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_telefone)],
            PACOTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_pacote)],
            VALOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_valor)],
            SERVIDOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_servidor)],
            VENCIMENTO: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_vencimento)],
            CONFIRMAR: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirmar_cadastro)]
        },
        fallbacks=[
            MessageHandler(filters.Regex("^❌ Cancelar$"), cancelar_cadastro),
            CommandHandler("cancel", cancelar_cadastro)
        ])

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("listar", listar_clientes))
    app.add_handler(CommandHandler("relatorio", relatorio))
    app.add_handler(CommandHandler("buscar", buscar_cliente))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(cadastro_handler)

    # Handler para o botão de listar clientes
    botoes_filter = filters.Regex(
        "^(👥 Listar Clientes|➕ Adicionar Cliente|📊 Relatórios|🔍 Buscar Cliente|❓ Ajuda)$"
    )
    app.add_handler(MessageHandler(botoes_filter, help_cmd), group=2)

    print("✅ Bot configurado com sucesso!")
    print(f"🔑 Admin ID: {admin_id}")
    print("🤖 Bot online e funcionando!")
    try:
        app.run_polling(drop_pending_updates=True)
    except KeyboardInterrupt:
        print("\n👋 Bot encerrado pelo usuário")
    except Exception as e:
        print(f"❌ Erro: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
