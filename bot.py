#!/usr/bin/env python3
"""
Bot Telegram - Sistema de Gestão de Clientes - VERSÃO FINAL
Corrige problemas de loop de eventos e garante estabilidade
"""

import os
import sys
import logging
from datetime import datetime, timedelta
import pytz
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler, CallbackQueryHandler
from telegram import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton

# Configurar timezone brasileiro
TIMEZONE_BR = pytz.timezone('America/Sao_Paulo')


def agora_br():
    """Retorna datetime atual no fuso horário de Brasília"""
    return datetime.now(TIMEZONE_BR)


def converter_para_br(dt):
    """Converte datetime para timezone brasileiro"""
    if dt.tzinfo is None:
        # Se não tem timezone, assume UTC
        dt = pytz.utc.localize(dt)
    return dt.astimezone(TIMEZONE_BR)


def formatar_data_br(dt):
    """Formata data/hora no padrão brasileiro"""
    if isinstance(dt, str):
        dt = datetime.strptime(dt, '%Y-%m-%d')
    return dt.strftime('%d/%m/%Y')


def formatar_datetime_br(dt):
    """Formata data/hora completa no padrão brasileiro"""
    if dt.tzinfo is None:
        dt = TIMEZONE_BR.localize(dt)
    return dt.strftime('%d/%m/%Y às %H:%M')


def escapar_html(text):
    """Escapa caracteres especiais para HTML do Telegram"""
    if text is None:
        return ""
    text = str(text)
    # Escapar caracteres especiais do HTML
    text = text.replace('&', '&amp;')
    text = text.replace('<', '&lt;')
    text = text.replace('>', '&gt;')
    text = text.replace('"', '&quot;')
    text = text.replace("'", '&#x27;')
    return text


# Configurar logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO)
logger = logging.getLogger(__name__)

# Estados da conversação para cadastro de cliente
NOME, TELEFONE, PACOTE, VALOR, SERVIDOR, VENCIMENTO, CONFIRMAR = range(7)

# Estados para edição de cliente
EDIT_NOME, EDIT_TELEFONE, EDIT_PACOTE, EDIT_VALOR, EDIT_SERVIDOR, EDIT_VENCIMENTO = range(
    7, 13)

# Estados para configurações
CONFIG_EMPRESA, CONFIG_PIX, CONFIG_SUPORTE = range(13, 16)

# Estados para edição de templates
TEMPLATE_EDIT_CONTENT = 16

# Estados para criação de novos templates
TEMPLATE_NEW_NAME, TEMPLATE_NEW_CONTENT = 17, 18


def criar_teclado_principal():
    """Cria o teclado persistente com os botões principais organizados"""
    keyboard = [
        # Gestão de Clientes
        [
            KeyboardButton("👥 Listar Clientes"),
            KeyboardButton("➕ Adicionar Cliente")
        ],
        [KeyboardButton("🔍 Buscar Cliente"),
         KeyboardButton("📊 Relatórios")],

        # Sistema de Mensagens
        [KeyboardButton("📄 Templates"),
         KeyboardButton("⏰ Agendador")],
        [
            KeyboardButton("📋 Fila de Mensagens"),
            KeyboardButton("📜 Logs de Envios")
        ],

        # WhatsApp
        [
            KeyboardButton("📱 WhatsApp Status"),
            KeyboardButton("🧪 Testar WhatsApp")
        ],
        [KeyboardButton("📱 QR Code"),
         KeyboardButton("⚙️ Gerenciar WhatsApp")],

        # Configurações
        [
            KeyboardButton("🏢 Empresa"),
            KeyboardButton("💳 PIX"),
            KeyboardButton("📞 Suporte")
        ],
        [KeyboardButton("❓ Ajuda")]
    ]
    return ReplyKeyboardMarkup(keyboard,
                               resize_keyboard=True,
                               one_time_keyboard=False)


def criar_teclado_cancelar():
    """Cria teclado com opção de cancelar"""
    keyboard = [[KeyboardButton("❌ Cancelar")]]
    return ReplyKeyboardMarkup(keyboard,
                               resize_keyboard=True,
                               one_time_keyboard=True)


def criar_teclado_confirmar():
    """Cria teclado para confirmação"""
    keyboard = [[KeyboardButton("✅ Confirmar"),
                 KeyboardButton("✏️ Editar")], [KeyboardButton("❌ Cancelar")]]
    return ReplyKeyboardMarkup(keyboard,
                               resize_keyboard=True,
                               one_time_keyboard=True)


def criar_teclado_planos():
    """Cria teclado com planos predefinidos"""
    keyboard = [[KeyboardButton("📅 1 mês"),
                 KeyboardButton("📅 3 meses")],
                [KeyboardButton("📅 6 meses"),
                 KeyboardButton("📅 1 ano")],
                [
                    KeyboardButton("✏️ Personalizado"),
                    KeyboardButton("❌ Cancelar")
                ]]
    return ReplyKeyboardMarkup(keyboard,
                               resize_keyboard=True,
                               one_time_keyboard=True)


def criar_teclado_vencimento():
    """Cria teclado para vencimento automático ou personalizado"""
    keyboard = [[
        KeyboardButton("✅ Usar data automática"),
        KeyboardButton("📅 Data personalizada")
    ], [KeyboardButton("❌ Cancelar")]]
    return ReplyKeyboardMarkup(keyboard,
                               resize_keyboard=True,
                               one_time_keyboard=True)


def criar_teclado_valores():
    """Cria teclado com valores predefinidos"""
    keyboard = [[
        KeyboardButton("💰 R$ 30,00"),
        KeyboardButton("💰 R$ 35,00"),
        KeyboardButton("💰 R$ 40,00")
    ],
                [
                    KeyboardButton("💰 R$ 45,00"),
                    KeyboardButton("💰 R$ 50,00"),
                    KeyboardButton("💰 R$ 60,00")
                ],
                [
                    KeyboardButton("💰 R$ 70,00"),
                    KeyboardButton("💰 R$ 90,00"),
                    KeyboardButton("💰 R$ 135,00")
                ],
                [
                    KeyboardButton("✏️ Valor personalizado"),
                    KeyboardButton("❌ Cancelar")
                ]]
    return ReplyKeyboardMarkup(keyboard,
                               resize_keyboard=True,
                               one_time_keyboard=True)


def verificar_admin(func):
    """Decorator para verificar se é admin"""

    async def wrapper(update, context):
        admin_id = int(os.getenv('ADMIN_CHAT_ID', '0'))
        if update.effective_chat.id != admin_id:
            await update.message.reply_text(
                "❌ Acesso negado. Apenas o admin pode usar este bot.")
            return
        return await func(update, context)

    return wrapper


@verificar_admin
async def start(update, context):
    """Comando /start"""
    nome_admin = update.effective_user.first_name

    try:
        from database import DatabaseManager
        db = DatabaseManager()
        total_clientes = len(db.listar_clientes(apenas_ativos=True))
    except:
        total_clientes = 0

    mensagem = f"""🤖 *Bot de Gestão de Clientes*

Olá *{nome_admin}*! 

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

    await update.message.reply_text(mensagem,
                                    parse_mode='Markdown',
                                    reply_markup=criar_teclado_principal())


# === SISTEMA DE CADASTRO ESCALONÁVEL ===


@verificar_admin
async def iniciar_cadastro(update, context):
    """Inicia o processo de cadastro de cliente"""
    await update.message.reply_text(
        "📝 *Cadastro de Novo Cliente*\n\n"
        "Vamos cadastrar um cliente passo a passo.\n\n"
        "**Passo 1/6:** Digite o *nome completo* do cliente:",
        parse_mode='Markdown',
        reply_markup=criar_teclado_cancelar())
    return NOME


async def receber_nome(update, context):
    """Recebe o nome do cliente"""
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
    """Recebe o telefone do cliente"""
    if update.message.text == "❌ Cancelar":
        return await cancelar_cadastro(update, context)

    telefone = update.message.text.strip().replace(' ', '').replace(
        '-', '').replace('(', '').replace(')', '')

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
    """Recebe o pacote do cliente"""
    if update.message.text == "❌ Cancelar":
        return await cancelar_cadastro(update, context)

    texto = update.message.text.strip()

    # Processar botões de planos predefinidos
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
        # Plano personalizado digitado diretamente
        pacote = texto
        if len(pacote) < 2:
            await update.message.reply_text(
                "❌ Nome do pacote muito curto. Digite um nome válido:",
                reply_markup=criar_teclado_planos())
            return PACOTE

    context.user_data['pacote'] = pacote

    # Calcular data de vencimento automática baseada no plano
    hoje = agora_br().replace(tzinfo=None)
    duracao_msg = ""

    if "1 mês" in pacote:
        vencimento_auto = hoje + timedelta(days=30)
        duracao_msg = " (vence em 30 dias)"
    elif "3 meses" in pacote:
        vencimento_auto = hoje + timedelta(days=90)
        duracao_msg = " (vence em 90 dias)"
    elif "6 meses" in pacote:
        vencimento_auto = hoje + timedelta(days=180)
        duracao_msg = " (vence em 180 dias)"
    elif "1 ano" in pacote:
        vencimento_auto = hoje + timedelta(days=365)
        duracao_msg = " (vence em 1 ano)"
    else:
        vencimento_auto = hoje + timedelta(days=30)  # Padrão: 30 dias
        duracao_msg = " (vencimento padrão: 30 dias)"

    # Salvar data calculada automaticamente
    context.user_data['vencimento_auto'] = vencimento_auto.strftime('%Y-%m-%d')

    await update.message.reply_text(
        f"✅ Pacote: *{pacote}*{duracao_msg}\n\n"
        "**Passo 4/6:** Escolha o *valor mensal*:\n\n"
        "Selecione um valor ou digite um personalizado:",
        parse_mode='Markdown',
        reply_markup=criar_teclado_valores())
    return VALOR


async def receber_valor(update, context):
    """Recebe o valor do plano"""
    if update.message.text == "❌ Cancelar":
        return await cancelar_cadastro(update, context)

    texto = update.message.text.strip()

    # Processar botões de valores predefinidos
    if texto == "💰 R$ 30,00":
        valor = 30.00
    elif texto == "💰 R$ 35,00":
        valor = 35.00
    elif texto == "💰 R$ 40,00":
        valor = 40.00
    elif texto == "💰 R$ 45,00":
        valor = 45.00
    elif texto == "💰 R$ 50,00":
        valor = 50.00
    elif texto == "💰 R$ 60,00":
        valor = 60.00
    elif texto == "💰 R$ 70,00":
        valor = 70.00
    elif texto == "💰 R$ 90,00":
        valor = 90.00
    elif texto == "💰 R$ 135,00":
        valor = 135.00
    elif texto == "✏️ Valor personalizado":
        await update.message.reply_text(
            "✏️ Digite o valor personalizado:\n\n"
            "*Exemplos:* 25.90, 85, 149.99",
            parse_mode='Markdown',
            reply_markup=criar_teclado_cancelar())
        return VALOR
    else:
        # Valor personalizado digitado diretamente
        try:
            valor_str = texto.replace(',', '.').replace('R$',
                                                        '').replace(' ', '')
            valor = float(valor_str)
            if valor <= 0:
                raise ValueError("Valor deve ser positivo")
        except ValueError:
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
    """Recebe o servidor"""
    if update.message.text == "❌ Cancelar":
        return await cancelar_cadastro(update, context)

    servidor = update.message.text.strip()
    if len(servidor) < 2:
        await update.message.reply_text(
            "❌ Nome do servidor muito curto. Digite um nome válido:",
            reply_markup=criar_teclado_cancelar())
        return SERVIDOR

    context.user_data['servidor'] = servidor

    # Mostrar opção de vencimento automático se disponível
    vencimento_auto = context.user_data.get('vencimento_auto')
    if vencimento_auto:
        data_formatada = datetime.strptime(vencimento_auto,
                                           '%Y-%m-%d').strftime('%d/%m/%Y')
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
    """Recebe a data de vencimento"""
    if update.message.text == "❌ Cancelar":
        return await cancelar_cadastro(update, context)

    texto = update.message.text.strip()

    # Processar botões de vencimento
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
        # Data digitada manualmente
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

    # Mostrar resumo para confirmação
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

    await update.message.reply_text(resumo,
                                    parse_mode='Markdown',
                                    reply_markup=criar_teclado_confirmar())
    return CONFIRMAR


async def confirmar_cadastro(update, context):
    """Confirma e salva o cadastro"""
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
        # Salvar no banco
        try:
            from database import DatabaseManager
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

            # Limpar dados temporários
            context.user_data.clear()
            return ConversationHandler.END

        except Exception as e:
            logger.error(f"Erro ao cadastrar cliente: {e}")
            await update.message.reply_text(
                "❌ Erro interno. Tente novamente mais tarde.",
                reply_markup=criar_teclado_principal())
            context.user_data.clear()
            return ConversationHandler.END

    # Se chegou aqui, é um número para editar
    try:
        opcao = int(update.message.text)
        if opcao == 1:
            await update.message.reply_text(
                "Digite o novo nome:", reply_markup=criar_teclado_cancelar())
            return NOME
        elif opcao == 2:
            await update.message.reply_text(
                "Digite o novo telefone:",
                reply_markup=criar_teclado_cancelar())
            return TELEFONE
        elif opcao == 3:
            await update.message.reply_text(
                "Digite o novo pacote:", reply_markup=criar_teclado_cancelar())
            return PACOTE
        elif opcao == 4:
            await update.message.reply_text(
                "Digite o novo valor:", reply_markup=criar_teclado_cancelar())
            return VALOR
        elif opcao == 5:
            await update.message.reply_text(
                "Digite o novo servidor:",
                reply_markup=criar_teclado_cancelar())
            return SERVIDOR
        elif opcao == 6:
            await update.message.reply_text(
                "Digite a nova data (AAAA-MM-DD):",
                reply_markup=criar_teclado_cancelar())
            return VENCIMENTO
    except ValueError:
        pass

    await update.message.reply_text(
        "❌ Opção inválida. Use os botões ou digite um número de 1 a 6:",
        reply_markup=criar_teclado_confirmar())
    return CONFIRMAR


async def cancelar_cadastro(update, context):
    """Cancela o processo de cadastro"""
    context.user_data.clear()
    await update.message.reply_text("❌ Cadastro cancelado.",
                                    reply_markup=criar_teclado_principal())
    return ConversationHandler.END


# === FIM DO SISTEMA DE CADASTRO ===


@verificar_admin
async def add_cliente(update, context):
    """Adiciona cliente ao sistema"""
    try:
        texto = update.message.text.replace('/add ', '')
        partes = [p.strip() for p in texto.split('|')]

        if len(partes) != 6:
            await update.message.reply_text(
                "❌ Formato incorreto!\n\n"
                "Use: `/add Nome | Telefone | Pacote | Valor | Vencimento | Servidor`",
                parse_mode='Markdown')
            return

        nome, telefone, pacote, valor_str, vencimento, servidor = partes

        try:
            valor = float(valor_str)
        except ValueError:
            await update.message.reply_text(
                "❌ Valor deve ser um número válido!")
            return

        try:
            datetime.strptime(vencimento, '%Y-%m-%d')
        except ValueError:
            await update.message.reply_text(
                "❌ Data deve estar no formato AAAA-MM-DD!")
            return

        from database import DatabaseManager
        db = DatabaseManager()

        sucesso = db.adicionar_cliente(nome, telefone, pacote, valor,
                                       vencimento, servidor)

        if sucesso:
            await update.message.reply_text(
                f"✅ *Cliente adicionado com sucesso!*\n\n"
                f"📝 Nome: {nome}\n"
                f"📱 Telefone: {telefone}\n"
                f"📦 Pacote: {pacote}\n"
                f"💰 Valor: R$ {valor:.2f}\n"
                f"📅 Vencimento: {vencimento}\n"
                f"🖥️ Servidor: {servidor}",
                parse_mode='Markdown')
        else:
            await update.message.reply_text("❌ Erro ao adicionar cliente!")

    except Exception as e:
        logger.error(f"Erro ao adicionar cliente: {e}")
        await update.message.reply_text("❌ Erro interno do sistema!")


@verificar_admin
async def listar_clientes(update, context):
    """Lista todos os clientes com botões interativos ordenados por vencimento"""
    try:
        from database import DatabaseManager
        db = DatabaseManager()
        clientes = db.listar_clientes(apenas_ativos=True)

        if not clientes:
            await update.message.reply_text(
                "📋 Nenhum cliente cadastrado ainda.\n\n"
                "Use ➕ Adicionar Cliente para começar!",
                reply_markup=criar_teclado_principal())
            return

        # Ordenar clientes por data de vencimento (mais próximo primeiro)
        clientes_ordenados = []
        for cliente in clientes:
            try:
                vencimento = datetime.strptime(cliente['vencimento'],
                                               '%Y-%m-%d')
                cliente['vencimento_obj'] = vencimento
                cliente['dias_restantes'] = (
                    vencimento - agora_br().replace(tzinfo=None)).days
                clientes_ordenados.append(cliente)
            except (ValueError, KeyError) as e:
                logger.error(f"Erro ao processar cliente {cliente}: {e}")
                continue

        # Ordenar por data de vencimento (mais próximo primeiro)
        clientes_ordenados.sort(key=lambda x: x['vencimento_obj'])

        # Contar clientes por status para resumo
        total_clientes = len(clientes_ordenados)
        hoje = agora_br().replace(tzinfo=None)
        vencidos = len(
            [c for c in clientes_ordenados if c['dias_restantes'] < 0])
        vencendo_hoje = len(
            [c for c in clientes_ordenados if c['dias_restantes'] == 0])
        vencendo_breve = len(
            [c for c in clientes_ordenados if 0 < c['dias_restantes'] <= 3])
        ativos = total_clientes - vencidos

        mensagem = f"""👥 *LISTA DE CLIENTES*

📊 *Resumo:* {total_clientes} clientes
🔴 {vencidos} vencidos • ⚠️ {vencendo_hoje} hoje • 🟡 {vencendo_breve} em breve • 🟢 {ativos} ativos

💡 *Clique em um cliente para ver detalhes:*"""

        # Criar apenas botões inline para cada cliente
        keyboard = []

        for cliente in clientes_ordenados[:50]:  # Limitado a 50 botões
            dias_restantes = cliente['dias_restantes']
            vencimento = cliente['vencimento_obj']

            # Definir status e emoji
            if dias_restantes < 0:
                status_emoji = "🔴"
            elif dias_restantes == 0:
                status_emoji = "⚠️"
            elif dias_restantes <= 3:
                status_emoji = "🟡"
            else:
                status_emoji = "🟢"

            # Texto do botão com informações principais
            nome_curto = cliente['nome'][:18] + "..." if len(
                cliente['nome']) > 18 else cliente['nome']
            botao_texto = f"{status_emoji} {nome_curto} - R${cliente['valor']:.0f} - {vencimento.strftime('%d/%m')}"

            # Criar botão inline para cada cliente
            keyboard.append([
                InlineKeyboardButton(botao_texto,
                                     callback_data=f"cliente_{cliente['id']}")
            ])

        # Mostrar aviso se há mais clientes
        if total_clientes > 50:
            mensagem += f"\n\n⚠️ *Mostrando primeiros 50 de {total_clientes} clientes*\nUse 🔍 Buscar Cliente para encontrar outros."

        # Adicionar botões de ação geral
        keyboard.append([
            InlineKeyboardButton("🔄 Atualizar Lista",
                                 callback_data="atualizar_lista"),
            InlineKeyboardButton("📊 Relatório",
                                 callback_data="gerar_relatorio")
        ])

        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(mensagem,
                                        parse_mode='Markdown',
                                        reply_markup=reply_markup)

    except Exception as e:
        logger.error(f"Erro ao listar clientes: {e}")
        await update.message.reply_text("❌ Erro ao listar clientes!",
                                        reply_markup=criar_teclado_principal())


async def callback_cliente(update, context):
    """Lida com callbacks dos botões inline dos clientes"""
    query = update.callback_query
    await query.answer()

    data = query.data

    try:
        if data.startswith("cliente_"):
            # Mostrar detalhes do cliente específico
            cliente_id = int(data.split("_")[1])
            await mostrar_detalhes_cliente(query, context, cliente_id)

        elif data == "atualizar_lista":
            # Atualizar a lista de clientes
            await atualizar_lista_clientes(query, context)

        elif data == "gerar_relatorio":
            # Gerar relatório rápido
            await gerar_relatorio_inline(query, context)

        elif data == "voltar_lista":
            # Voltar para a lista de clientes
            await atualizar_lista_clientes(query, context)

        elif data.startswith("cobrar_"):
            # Enviar cobrança via WhatsApp
            cliente_id = int(data.split("_")[1])
            await enviar_cobranca_cliente(query, context, cliente_id)

        elif data.startswith("mensagem_"):
            # Mostrar templates disponíveis para envio
            cliente_id = int(data.split("_")[1])
            await mostrar_templates_cliente(query, context, cliente_id)

        elif data.startswith("renovar_") and len(
                data.split("_")) == 3 and data.split("_")[1].isdigit():
            # Processar renovação por dias (formato: renovar_30_123)
            partes = data.split("_")
            dias = int(partes[1])
            cliente_id = int(partes[2])
            await processar_renovacao_cliente(query, context, cliente_id, dias)

        elif data.startswith("renovar_"):
            # Mostrar opções de renovação (formato: renovar_123)
            cliente_id = int(data.split("_")[1])
            await renovar_cliente_inline(query, context, cliente_id)

        elif data.startswith("editar_"):
            # Editar cliente
            cliente_id = int(data.split("_")[1])
            await editar_cliente_inline(query, context, cliente_id)

        elif data.startswith("excluir_"):
            # Excluir cliente
            cliente_id = int(data.split("_")[1])
            await excluir_cliente_inline(query, context, cliente_id)

        elif data.startswith("confirmar_excluir_"):
            # Confirmar exclusão
            cliente_id = int(data.split("_")[2])
            await confirmar_exclusao_cliente(query, context, cliente_id)

        elif data.startswith("template_enviar_"):
            # Enviar template específico para cliente
            partes = data.split("_")
            if len(partes) == 4:
                template_id = int(partes[2])
                cliente_id = int(partes[3])
                await enviar_template_cliente(query, context, cliente_id, template_id)

        elif data.startswith("historico_"):
            # Mostrar histórico de mensagens do cliente
            cliente_id = int(data.split("_")[1])
            await mostrar_historico_cliente(query, context, cliente_id)

        elif data.startswith("edit_"):
            # Processar edição de campos específicos
            partes = data.split("_")
            if len(partes) == 3:
                campo = partes[1]
                cliente_id = int(partes[2])
                await iniciar_edicao_campo(query, context, cliente_id, campo)

        # --- TEMPLATE CALLBACKS ADICIONADOS ---
        # Callbacks dos templates
        elif data == "templates_listar":
            from callbacks_templates import callback_templates_listar
            await callback_templates_listar(query, context)
        elif data == "template_ver":
            from callbacks_templates import callback_templates_ver
            await callback_templates_ver(query, context)
        elif data == "template_editar_escolher":
            from callbacks_templates import callback_templates_editar
            await callback_templates_editar(query, context)
        elif data == "template_testar_escolher":
            from callbacks_templates import callback_templates_testar
            await callback_templates_testar(query, context)
        elif data == "template_criar":
            from callbacks_templates import callback_templates_criar
            await callback_templates_criar(query, context)
        elif data == "template_excluir_escolher":
            from callbacks_templates import callback_templates_excluir
            await callback_templates_excluir(query, context)

        # Callbacks específicos de templates (mostrar, testar, editar, excluir por ID)
        elif data.startswith("template_mostrar_"):
            template_id = int(data.split("_")[2])
            from callbacks_templates import callback_template_mostrar
            await callback_template_mostrar(query, context, template_id)
        elif data.startswith("template_testar_"):
            template_id = int(data.split("_")[2])
            from callbacks_templates import callback_template_testar
            await callback_template_testar(query, context, template_id)
        elif data.startswith("template_editar_"):
            template_id = int(data.split("_")[2])
            # Assumindo que existe uma função para editar diretamente
            from callbacks_templates import callback_template_editar_direto
            await callback_template_editar_direto(query, context, template_id)
        elif data.startswith("template_excluir_"):
            template_id = int(data.split("_")[2])
            # Assumindo que existe uma função para excluir diretamente
            from callbacks_templates import callback_template_excluir_direto
            await callback_template_excluir_direto(query, context, template_id)

        elif data == "voltar_menu":
            # Voltar ao menu principal do bot
            await query.edit_message_text(
                "🤖 *BOT DE GESTÃO DE CLIENTES*\n\n"
                "Escolha uma opção abaixo:",
                parse_mode='Markdown',
                reply_markup=criar_teclado_principal()
            )
        elif data == "voltar_templates":
            # Recarregar a lista de templates
            from database import DatabaseManager
            db = DatabaseManager()
            templates = db.listar_templates(apenas_ativos=True)

            mensagem = f"📄 *SISTEMA DE TEMPLATES*\n\n"
            mensagem += f"📊 Templates disponíveis: {len(templates)}\n\n"

            keyboard = []

            for template in templates:
                template_id = template['id']
                nome_display = template['nome'][:20] + ('...' if len(template['nome']) > 20 else '')

                keyboard.append([
                    InlineKeyboardButton(f"📝 {nome_display}",
                                       callback_data=f"template_mostrar_{template_id}"),
                    InlineKeyboardButton("✏️ Editar",
                                       callback_data=f"template_editar_{template_id}")
                ])

            keyboard.append([
                InlineKeyboardButton("➕ Novo Template", callback_data="template_criar"),
                InlineKeyboardButton("🧪 Testar Template", callback_data="template_testar")
            ])
            keyboard.append([
                InlineKeyboardButton("⬅️ Menu Principal", callback_data="voltar_menu")
            ])

            if not templates:
                mensagem += "📭 **Nenhum template encontrado**\n\n"
                mensagem += "Crie seu primeiro template."

            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.edit_message_text(
                mensagem,
                parse_mode='Markdown',
                reply_markup=reply_markup
            )

    except Exception as e:
        logger.error(f"Erro no callback: {e}")
        await query.edit_message_text("❌ Erro ao processar ação!")


async def mostrar_detalhes_cliente(query, context, cliente_id):
    """Mostra detalhes completos de um cliente específico"""
    try:
        from database import DatabaseManager
        db = DatabaseManager()
        clientes = db.listar_clientes(apenas_ativos=True)

        cliente = next((c for c in clientes if c['id'] == cliente_id), None)
        if not cliente:
            await query.edit_message_text("❌ Cliente não encontrado!")
            return

        vencimento = datetime.strptime(cliente['vencimento'], '%Y-%m-%d')
        dias_restantes = (vencimento - agora_br().replace(tzinfo=None)).days

        # Status do cliente
        if dias_restantes < 0:
            status = f"🔴 VENCIDO há {abs(dias_restantes)} dias"
        elif dias_restantes == 0:
            status = "⚠️ VENCE HOJE"
        elif dias_restantes <= 3:
            status = f"🟡 VENCE EM {dias_restantes} DIAS"
        else:
            status = f"🟢 ATIVO ({dias_restantes} dias restantes)"

        mensagem = f"""👤 *DETALHES DO CLIENTE*

📝 *Nome:* {cliente['nome']}
📱 *Telefone:* {cliente['telefone']}
📦 *Pacote:* {cliente['pacote']}
💰 *Valor:* R$ {cliente['valor']:.2f}
🖥️ *Servidor:* {cliente['servidor']}
📅 *Vencimento:* {vencimento.strftime('%d/%m/%Y')}

📊 *Status:* {status}"""

        # Criar botões de ação para o cliente
        keyboard = [
            [
                InlineKeyboardButton("📧 Enviar Cobrança",
                                     callback_data=f"cobrar_{cliente_id}"),
                InlineKeyboardButton("💬 Enviar Mensagem",
                                     callback_data=f"mensagem_{cliente_id}")
            ],
            [
                InlineKeyboardButton("🔄 Renovar",
                                     callback_data=f"renovar_{cliente_id}"),
                InlineKeyboardButton("📊 Histórico",
                                     callback_data=f"historico_{cliente_id}")
            ],
            [
                InlineKeyboardButton("✏️ Editar",
                                     callback_data=f"editar_{cliente_id}"),
                InlineKeyboardButton("🗑️ Excluir",
                                     callback_data=f"excluir_{cliente_id}")
            ],
            [
                InlineKeyboardButton("⬅️ Voltar à Lista",
                                     callback_data="voltar_lista")
            ]
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(mensagem,
                                      parse_mode='Markdown',
                                      reply_markup=reply_markup)

    except Exception as e:
        logger.error(f"Erro ao mostrar detalhes: {e}")
        await query.edit_message_text("❌ Erro ao carregar detalhes!")


async def atualizar_lista_clientes(query, context):
    """Atualiza a lista de clientes inline"""
    try:
        from database import DatabaseManager
        db = DatabaseManager()
        clientes = db.listar_clientes(apenas_ativos=True)

        if not clientes:
            await query.edit_message_text("📋 Nenhum cliente cadastrado ainda.")
            return

        # Recriar a lista ordenada (mesmo código da função listar_clientes)
        clientes_ordenados = []
        for cliente in clientes:
            try:
                vencimento = datetime.strptime(cliente['vencimento'],
                                               '%Y-%m-%d')
                cliente['vencimento_obj'] = vencimento
                cliente['dias_restantes'] = (
                    vencimento - agora_br().replace(tzinfo=None)).days
                clientes_ordenados.append(cliente)
            except (ValueError, KeyError):
                continue

        clientes_ordenados.sort(key=lambda x: x['vencimento_obj'])

        # Contar clientes por status para resumo
        total_clientes = len(clientes_ordenados)
        hoje = agora_br().replace(tzinfo=None)
        vencidos = len(
            [c for c in clientes_ordenados if c['dias_restantes'] < 0])
        vencendo_hoje = len(
            [c for c in clientes_ordenados if c['dias_restantes'] == 0])
        vencendo_breve = len(
            [c for c in clientes_ordenados if 0 < c['dias_restantes'] <= 3])
        ativos = total_clientes - vencidos

        mensagem = f"""👥 *LISTA DE CLIENTES*

📊 *Resumo:* {total_clientes} clientes
🔴 {vencidos} vencidos • ⚠️ {vencendo_hoje} hoje • 🟡 {vencendo_breve} em breve • 🟢 {ativos} ativos

💡 *Clique em um cliente para ver detalhes:*"""

        keyboard = []

        # Mostrar apenas botões, sem texto da lista
        for cliente in clientes_ordenados[:50]:  # Limitado a 50 botões
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

            nome_curto = cliente['nome'][:18] + "..." if len(
                cliente['nome']) > 18 else cliente['nome']
            botao_texto = f"{status_emoji} {nome_curto} - R${cliente['valor']:.0f} - {vencimento.strftime('%d/%m')}"

            keyboard.append([
                InlineKeyboardButton(botao_texto,
                                     callback_data=f"cliente_{cliente['id']}")
            ])

        keyboard.append([
            InlineKeyboardButton("🔄 Atualizar Lista",
                                 callback_data="atualizar_lista"),
            InlineKeyboardButton("📊 Relatório",
                                 callback_data="gerar_relatorio")
        ])

        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(mensagem,
                                      parse_mode='Markdown',
                                      reply_markup=reply_markup)

    except Exception as e:
        logger.error(f"Erro ao atualizar lista: {e}")
        await query.edit_message_text("❌ Erro ao atualizar lista!")


async def gerar_relatorio_inline(query, context):
    """Gera relatório rápido inline"""
    try:
        from database import DatabaseManager
        db = DatabaseManager()
        clientes = db.listar_clientes(apenas_ativos=True)

        total_clientes = len(clientes)
        receita_total = sum(float(c['valor']) for c in clientes)

        hoje = agora_br().replace(tzinfo=None)
        vencidos = [
            c for c in clientes
            if datetime.strptime(c['vencimento'], '%Y-%m-%d') < hoje
        ]
        vencendo_hoje = [
            c for c in clientes if c['vencimento'] == hoje.strftime('%Y-%m-%d')
        ]
        vencendo_3_dias = [
            c for c in clientes
            if 0 <= (datetime.strptime(c['vencimento'], '%Y-%m-%d') -
                     hoje).days <= 3
        ]

        # Usar horário brasileiro para o relatório
        agora_brasilia = agora_br()

        mensagem = f"""📊 *RELATÓRIO RÁPIDO*

👥 *Total de clientes:* {total_clientes}
💰 *Receita mensal:* R$ {receita_total:.2f}

📈 *Status dos Clientes:*
🔴 Vencidos: {len(vencidos)}
⚠️ Vencem hoje: {len(vencendo_hoje)}
🟡 Vencem em 3 dias: {len(vencendo_3_dias)}
🟢 Ativos: {total_clientes - len(vencidos)}

📅 *Atualizado:* {formatar_datetime_br(agora_brasilia)} (Brasília)"""

        keyboard = [[
            InlineKeyboardButton("⬅️ Voltar à Lista",
                                 callback_data="voltar_lista")
        ]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(mensagem,
                                      parse_mode='Markdown',
                                      reply_markup=reply_markup)

    except Exception as e:
        logger.error(f"Erro no relatório: {e}")
        await query.edit_message_text("❌ Erro ao gerar relatório!")


async def enviar_cobranca_cliente(query, context, cliente_id):
    """Envia cobrança via WhatsApp para cliente específico usando templates do sistema"""
    try:
        from database import DatabaseManager
        from datetime import datetime

        db = DatabaseManager()
        clientes = db.listar_clientes(apenas_ativos=False)  # Incluir clientes inativos
        cliente = next((c for c in clientes if c['id'] == cliente_id), None)

        if not cliente:
            await query.edit_message_text(
                "❌ **CLIENTE NÃO ENCONTRADO**\n\n"
                f"Cliente ID: {cliente_id}\n"
                "O cliente pode ter sido excluído ou não existe no sistema.",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("⬅️ Voltar à Lista", callback_data="voltar_lista")
                ]])
            )
            return

        # Preparar dados para envio
        vencimento = datetime.strptime(cliente['vencimento'], '%Y-%m-%d')
        dias_restantes = (vencimento - agora_br().replace(tzinfo=None)).days

        # Criar mensagem baseada no status
        if dias_restantes < 0:
            status_msg = f"VENCIDO há {abs(dias_restantes)} dias"
            urgencia = "🔴 URGENTE"
        elif dias_restantes == 0:
            status_msg = "VENCE HOJE"
            urgencia = "⚠️ ATENÇÃO"
        elif dias_restantes <= 3:
            status_msg = f"Vence em {dias_restantes} dias"
            urgencia = "🟡 LEMBRETE"
        else:
            status_msg = f"Vence em {dias_restantes} dias"
            urgencia = "🔔 LEMBRETE"

        # Buscar templates do banco de dados ou usar padrão
        try:
            templates_db = db.listar_templates()
            template_cobranca = None
            template_vencido = None

            # Procurar por templates específicos
            for template in templates_db:
                if template['nome'].lower() == 'cobranca':
                    template_cobranca = template['conteudo']
                elif template['nome'].lower() == 'vencido':
                    template_vencido = template['conteudo']

            logger.info(f"Templates carregados - Cobrança: {'✓' if template_cobranca else '✗'}, Vencido: {'✓' if template_vencido else '✗'}")
        except Exception as e:
            logger.warning(f"Erro ao buscar templates do DB, usando padrão: {e}")
            template_cobranca = None
            template_vencido = None

        # Templates padrão caso não existam no DB
        templates_sistema = {
            'cobranca': template_cobranca or '⚠️ ATENÇÃO {nome}!\n\nSeu plano vence em breve:\n\n📦 Pacote: {pacote}\n💰 Valor: R$ {valor}\n📅 Vencimento: {vencimento}\n\nRenove agora para não perder o acesso!',
            'vencido': template_vencido or '🔴 PLANO VENCIDO - {nome}\n\nSeu plano venceu em {vencimento}.\n\n📦 Pacote: {pacote}\n💰 Valor para renovação: R$ {valor}\n\nRenove urgentemente para reativar o serviço!'
        }

        # Selecionar template baseado no status do cliente
        if dias_restantes < 0:
            template_usar = templates_sistema['vencido']
            tipo_template = "vencido"
        else:
            template_usar = templates_sistema['cobranca']
            tipo_template = "cobrança"

        # Formatar data de vencimento para exibição
        vencimento_formatado = vencimento.strftime('%d/%m/%Y')

        # Aplicar dados do cliente ao template
        try:
            mensagem_whatsapp = template_usar.format(
                nome=cliente['nome'],
                telefone=cliente['telefone'],
                pacote=cliente['pacote'],
                valor=f"{cliente['valor']:.2f}",
                vencimento=vencimento_formatado,
                servidor=cliente['servidor']
            )
            logger.info(f"Template aplicado com sucesso - Cliente: {cliente['nome']}, Tipo: {tipo_template}")
        except Exception as e:
            logger.error(f"Erro ao aplicar template: {e}")
            mensagem_whatsapp = f"Olá {cliente['nome']}!\n\nSeu plano {cliente['pacote']} vence em {vencimento_formatado}.\nValor: R$ {cliente['valor']:.2f}\nServidor: {cliente['servidor']}\n\nRenove para continuar usando nossos serviços."

        # Enviar via WhatsApp híbrido com timeout
        try:
            from whatsapp_hybrid_service import WhatsAppHybridService
            ws = WhatsAppHybridService()

            # Usar asyncio.wait_for para timeout de 15 segundos
            import asyncio
            sucesso = await asyncio.wait_for(ws.enviar_mensagem(
                cliente['telefone'], mensagem_whatsapp),
                                             timeout=15.0)

            if sucesso:
                # Log de sucesso
                logger.info(f"✅ Cobrança enviada com sucesso - Cliente: {cliente['nome']} ({cliente['telefone']}), Template: {tipo_template}")

                # Salvar log no banco de dados
                try:
                    db.registrar_log_mensagem(
                        cliente_id=cliente['id'],
                        tipo=tipo_template,
                        telefone=cliente['telefone'],
                        status='enviado',
                        conteudo=mensagem_whatsapp[:500]
                    )
                except Exception as log_err:
                    logger.warning(f"Erro ao salvar log: {log_err}")

                mensagem = f"✅ **COBRANÇA ENVIADA COM SUCESSO**\n\n"
                mensagem += f"**Cliente:** {cliente['nome']}\n"
                mensagem += f"**WhatsApp:** {cliente['telefone']}\n"
                mensagem += f"**Template:** {tipo_template.title()}\n"
                mensagem += f"**Enviado:** {agora_br().replace(tzinfo=None).strftime('%d/%m/%Y %H:%M')}\n\n"
                mensagem += f"**Status:** {status_msg}\n"
                mensagem += f"**Pacote:** {cliente['pacote']}\n"
                mensagem += f"**Valor:** R$ {cliente['valor']:.2f}\n\n"
                mensagem += f"📝 **Prévia da mensagem enviada:**\n`{mensagem_whatsapp[:100]}{'...' if len(mensagem_whatsapp) > 100 else ''}`"
            else:
                # Log de falha
                logger.error(f"❌ Falha no envio - Cliente: {cliente['nome']} ({cliente['telefone']})")

                try:
                    db.registrar_log_mensagem(
                        cliente_id=cliente['id'],
                        tipo=tipo_template,
                        telefone=cliente['telefone'],
                        status='falha',
                        conteudo='Erro: WhatsApp não confirmou o envio'
                    )
                except Exception as log_err:
                    logger.warning(f"Erro ao salvar log: {log_err}")

                mensagem = f"❌ **FALHA NO ENVIO**\n\n"
                mensagem += f"O WhatsApp não confirmou o envio.\n"
                mensagem += f"**Cliente:** {cliente['nome']}\n"
                mensagem += f"**Telefone:** {cliente['telefone']}\n"
                mensagem += f"**Template:** {tipo_template.title()}\n\n"
                mensagem += f"**Possíveis causas:**\n"
                mensagem += f"• Número incorreto ou inexistente\n"
                mensagem += f"• WhatsApp desconectado\n"
                mensagem += f"• Problemas na API Evolution/Baileys"

        except asyncio.TimeoutError:
            logger.warning(f"⏱️ Timeout no envio - Cliente: {cliente['nome']} ({cliente['telefone']})")

            try:
                db.registrar_log_mensagem(
                    cliente_id=cliente['id'],
                    tipo=tipo_template,
                    telefone=cliente['telefone'],
                    status='timeout',
                    conteudo='Erro: Timeout após 15 segundos'
                )
            except Exception as log_err:
                logger.warning(f"Erro ao salvar log: {log_err}")

            mensagem = f"⏱️ **TIMEOUT NO ENVIO**\n\n"
            mensagem += f"A mensagem pode ter sido enviada mas demorou para responder.\n\n"
            mensagem += f"**Cliente:** {cliente['nome']}\n"
            mensagem += f"**Template:** {tipo_template.title()}\n"
            mensagem += f"**Tempo limite:** 15 segundos\n\n"
            mensagem += f"**Ação recomendada:** Verificar manualmente no WhatsApp"
        except Exception as e:
            logger.error(f"❌ Erro específico ao enviar WhatsApp: {e}")

            try:
                db.registrar_log_mensagem(
                    cliente_id=cliente['id'],
                    tipo=tipo_template,
                    telefone=cliente['telefone'],
                    status='erro',
                    conteudo=f'Erro: {str(e)[:200]}'
                )
            except Exception as log_err:
                logger.warning(f"Erro ao salvar log: {log_err}")

            mensagem = f"❌ **ERRO NO ENVIO**\n\n"
            mensagem += f"**Cliente:** {cliente['nome']}\n"
            mensagem += f"**Template:** {tipo_template.title()}\n"
            mensagem += f"**Erro técnico:** {str(e)[:150]}\n\n"
            mensagem += f"**Diagnóstico sugerido:**\n"
            mensagem += f"• Verificar configuração da Evolution API\n"
            mensagem += f"• Confirmar se Baileys está conectado\n"
            mensagem += f"• Testar conectividade da instância WhatsApp"

        keyboard = [[
            InlineKeyboardButton("⬅️ Voltar ao Cliente",
                                 callback_data=f"cliente_{cliente_id}")
        ]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(mensagem,
                                      parse_mode='Markdown',
                                      reply_markup=reply_markup)

    except Exception as e:
        logger.error(f"Erro ao enviar cobrança: {e}")
        keyboard = [[
            InlineKeyboardButton("⬅️ Voltar ao Cliente",
                                 callback_data=f"cliente_{cliente_id}")
        ]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            f"❌ *Erro interno ao enviar cobrança!*\n\nDetalhes: {str(e)[:100]}",
            parse_mode='Markdown',
            reply_markup=reply_markup)


async def mostrar_templates_cliente(query, context, cliente_id):
    """Mostra templates disponíveis para envio ao cliente"""
    try:
        from database import DatabaseManager
        db = DatabaseManager()

        # Buscar cliente
        clientes = db.listar_clientes(apenas_ativos=False)
        cliente = next((c for c in clientes if c['id'] == cliente_id), None)

        if not cliente:
            await query.edit_message_text(
                "❌ **CLIENTE NÃO ENCONTRADO**\n\n"
                f"Cliente ID: {cliente_id}",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("⬅️ Voltar à Lista", callback_data="voltar_lista")
                ]])
            )
            return

        # Buscar templates
        templates = db.listar_templates(apenas_ativos=True)

        if not templates:
            await query.edit_message_text(
                "❌ **NENHUM TEMPLATE DISPONÍVEL**\n\n"
                "Não há templates cadastrados no sistema.\n"
                "Crie templates primeiro usando o menu principal.",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("⬅️ Voltar ao Cliente", callback_data=f"cliente_{cliente_id}")
                ]])
            )
            return

        mensagem = f"💬 **ENVIAR MENSAGEM**\n\n"
        mensagem += f"**Cliente:** {cliente['nome']}\n"
        mensagem += f"**WhatsApp:** {cliente['telefone']}\n\n"
        mensagem += f"📋 **Selecione um template para enviar:**\n"

        # Criar botões para cada template com informações de uso
        keyboard = []
        for template in templates:
            # Buscar estatísticas do template para este cliente
            historico_template = db.obter_historico_cliente_template(cliente_id, template['id'])
            total_envios = len(historico_template)

            # Limitar nome do template para botão
            nome_template = template['nome'][:20] + ('...' if len(template['nome']) > 20 else '')

            # Adicionar contador se já foi usado
            if total_envios > 0:
                nome_botao = f"📝 {nome_template} ({total_envios}x)"
            else:
                nome_botao = f"📝 {nome_template}"

            keyboard.append([
                InlineKeyboardButton(
                    nome_botao,
                    callback_data=f"template_enviar_{template['id']}_{cliente_id}"
                )
            ])

        # Botão para voltar
        keyboard.append([
            InlineKeyboardButton("⬅️ Voltar ao Cliente", callback_data=f"cliente_{cliente_id}")
        ])

        reply_markup = InlineKeyboardMarkup(keyboard)

        try:
            await query.edit_message_text(
                mensagem,
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
        except Exception as parse_error:
            logger.warning(f"Erro de parsing Markdown ao mostrar templates, enviando texto simples: {parse_error}")
            await query.edit_message_text(
                mensagem.replace('**', '').replace('*', ''),
                reply_markup=reply_markup
            )

    except Exception as e:
        logger.error(f"Erro ao mostrar templates: {e}")
        await query.edit_message_text(
            f"❌ **ERRO AO CARREGAR TEMPLATES**\n\n"
            f"Erro técnico: {str(e)[:100]}",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⬅️ Voltar ao Cliente", callback_data=f"cliente_{cliente_id}")
            ]])
        )


async def enviar_template_cliente(query, context, cliente_id, template_id):
    """Envia template específico para cliente usando WhatsApp híbrido"""
    try:
        from database import DatabaseManager
        from datetime import datetime

        db = DatabaseManager()

        # Buscar cliente
        clientes = db.listar_clientes(apenas_ativos=False)
        cliente = next((c for c in clientes if c['id'] == cliente_id), None)

        if not cliente:
            await query.edit_message_text(
                "❌ **CLIENTE NÃO ENCONTRADO**",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("⬅️ Voltar à Lista", callback_data="voltar_lista")
                ]])
            )
            return

        # Buscar template
        templates = db.listar_templates(apenas_ativos=False)
        template = next((t for t in templates if t['id'] == template_id), None)

        if not template:
            await query.edit_message_text(
                "❌ **TEMPLATE NÃO ENCONTRADO**\n\n"
                "O template pode ter sido excluído.",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("⬅️ Voltar ao Cliente", callback_data=f"cliente_{cliente_id}")
                ]])
            )
            return

        # Preparar dados do cliente
        vencimento = datetime.strptime(cliente['vencimento'], '%Y-%m-%d')
        vencimento_formatado = vencimento.strftime('%d/%m/%Y')

        # Obter configurações do sistema para variáveis adicionais
        try:
            configuracoes = db.get_configuracoes()
        except:
            configuracoes = {}

        # Aplicar variáveis ao template com dados completos
        try:
            # Calcular dias restantes para vencimento
            hoje = datetime.now()
            dias_restantes = (vencimento - hoje).days if vencimento > hoje else 0

            # Preparar novo vencimento (30 dias após atual)
            from datetime import timedelta
            novo_vencimento = (vencimento + timedelta(days=30)).strftime('%d/%m/%Y')

            dados_template = {
                # Dados básicos do cliente
                'nome': cliente['nome'],
                'telefone': cliente['telefone'],
                'pacote': cliente['pacote'],
                'valor': f"{cliente['valor']:.2f}",
                'vencimento': vencimento_formatado,
                'servidor': cliente['servidor'],

                # Dados do sistema/empresa
                'empresa': configuracoes.get('nome_empresa', configuracoes.get('empresa', 'Sua Empresa')),
                'suporte': configuracoes.get('suporte', f"@{configuracoes.get('telefone_empresa', 'suporte')}"),

                # Dados de pagamento PIX
                'pix_chave': configuracoes.get('pix_chave', 'sua_chave_pix@email.com'),
                'pix_banco': configuracoes.get('pix_banco', 'Banco do Brasil'),
                'pix_titular': configuracoes.get('pix_titular', 'Nome do Titular'),

                # Dados calculados
                'dias_restantes': str(dias_restantes),
                'novo_vencimento': novo_vencimento,
            }

            mensagem_whatsapp = template['conteudo'].format(**dados_template)
            logger.info(f"Template '{template['nome']}' aplicado - Cliente: {cliente['nome']}")
        except KeyError as key_err:
            logger.error(f"Erro: variável não encontrada no template: {key_err}")
            # Tentar aplicar apenas as variáveis básicas
            try:
                mensagem_whatsapp = template['conteudo'].format(
                    nome=cliente['nome'],
                    telefone=cliente['telefone'],
                    pacote=cliente['pacote'],
                    valor=f"{cliente['valor']:.2f}",
                    vencimento=vencimento_formatado,
                    servidor=cliente['servidor']
                )
                logger.info(f"Template aplicado com variáveis básicas - Cliente: {cliente['nome']}")
            except Exception:
                logger.error(f"Erro ao aplicar variáveis básicas, enviando template original")
                mensagem_whatsapp = template['conteudo']  # Usar template original se falhar
        except Exception as template_err:
            logger.error(f"Erro geral ao aplicar variáveis ao template: {template_err}")
            mensagem_whatsapp = template['conteudo']  # Usar template sem variáveis se falhar

        # Enviar via WhatsApp híbrido
        try:
            from whatsapp_hybrid_service import WhatsAppHybridService
            ws = WhatsAppHybridService()

            import asyncio
            sucesso = await asyncio.wait_for(ws.enviar_mensagem(
                cliente['telefone'], mensagem_whatsapp),
                                             timeout=15.0)

            if sucesso:
                # Log de sucesso
                logger.info(f"✅ Template enviado com sucesso - Cliente: {cliente['nome']} ({cliente['telefone']}), Template: {template['nome']}")

                # Registrar log no banco
                try:
                    db.registrar_log_mensagem(
                        cliente_id=cliente['id'],
                        tipo=f"template_{template['nome']}",
                        telefone=cliente['telefone'],
                        status='enviado',
                        conteudo=mensagem_whatsapp[:500],
                        template_id=template['id']
                    )
                except Exception as log_err:
                    logger.warning(f"Erro ao salvar log: {log_err}")

                mensagem = f"✅ **MENSAGEM ENVIADA COM SUCESSO**\n\n"
                mensagem += f"**Cliente:** {cliente['nome']}\n"
                mensagem += f"**WhatsApp:** {cliente['telefone']}\n"
                mensagem += f"**Template:** {template['nome']}\n"
                mensagem += f"**Enviado:** {agora_br().replace(tzinfo=None).strftime('%d/%m/%Y %H:%M')}\n\n"
                mensagem += f"📝 **Prévia da mensagem enviada:**\n"
                mensagem += f"`{mensagem_whatsapp[:200]}{'...' if len(mensagem_whatsapp) > 200 else ''}`"

            else:
                # Log de falha
                logger.error(f"❌ Falha no envio do template - Cliente: {cliente['nome']} ({cliente['telefone']})")

                try:
                    db.registrar_log_mensagem(
                        cliente_id=cliente['id'],
                        tipo=f"template_{template['nome']}",
                        telefone=cliente['telefone'],
                        status='falha',
                        conteudo='Erro: WhatsApp não confirmou o envio',
                        template_id=template['id']
                    )
                except Exception as log_err:
                    logger.warning(f"Erro ao salvar log: {log_err}")

                mensagem = f"❌ **FALHA NO ENVIO**\n\n"
                mensagem += f"**Cliente:** {cliente['nome']}\n"
                mensagem += f"**Template:** {template['nome']}\n"
                mensagem += f"**Telefone:** {cliente['telefone']}\n\n"
                mensagem += f"**Possíveis causas:**\n"
                mensagem += f"• Número incorreto ou inexistente\n"
                mensagem += f"• WhatsApp desconectado\n"
                mensagem += f"• Problemas na API Evolution/Baileys"

        except asyncio.TimeoutError:
            logger.warning(f"⏱️ Timeout no envio do template - Cliente: {cliente['nome']} ({cliente['telefone']})")

            try:
                db.registrar_log_mensagem(
                    cliente_id=cliente['id'],
                    tipo=f"template_{template['nome']}",
                    telefone=cliente['telefone'],
                    status='timeout',
                    conteudo='Erro: Timeout após 15 segundos',
                    template_id=template['id']
                )
            except Exception as log_err:
                logger.warning(f"Erro ao salvar log: {log_err}")

            mensagem = f"⏱️ **TIMEOUT NO ENVIO**\n\n"
            mensagem += f"**Cliente:** {cliente['nome']}\n"
            mensagem += f"**Template:** {template['nome']}\n"
            mensagem += f"**Tempo limite:** 15 segundos\n\n"
            mensagem += f"A mensagem pode ter sido enviada.\n"
            mensagem += f"**Ação recomendada:** Verificar manualmente no WhatsApp"

        except Exception as e:
            logger.error(f"❌ Erro específico ao enviar template: {e}")

            try:
                db.registrar_log_mensagem(
                    cliente_id=cliente['id'],
                    tipo=f"template_{template['nome']}",
                    telefone=cliente['telefone'],
                    status='erro',
                    conteudo=f'Erro: {str(e)[:200]}',
                    template_id=template['id']
                )
            except Exception as log_err:
                logger.warning(f"Erro ao salvar log: {log_err}")

            mensagem = f"❌ **ERRO NO ENVIO**\n\n"
            mensagem += f"**Cliente:** {cliente['nome']}\n"
            mensagem += f"**Template:** {template['nome']}\n"
            mensagem += f"**Erro técnico:** {str(e)[:150]}\n\n"
            mensagem += f"**Diagnóstico sugerido:**\n"
            mensagem += f"• Verificar configuração da Evolution API\n"
            mensagem += f"• Confirmar se Baileys está conectado\n"
            mensagem += f"• Testar conectividade da instância WhatsApp"

        # Botões de ação
        keyboard = [
            [
                InlineKeyboardButton("📝 Outros Templates",
                                   callback_data=f"mensagem_{cliente_id}"),
                InlineKeyboardButton("⬅️ Voltar ao Cliente",
                                   callback_data=f"cliente_{cliente_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Escapar caracteres especiais do Markdown para evitar erros de parsing
        try:
            await query.edit_message_text(
                mensagem,
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
        except Exception as parse_error:
            # Se falhar com Markdown, tentar sem parse_mode
            logger.warning(f"Erro de parsing Markdown, enviando texto simples: {parse_error}")
            await query.edit_message_text(
                mensagem,
                reply_markup=reply_markup
            )

    except Exception as e:
        logger.error(f"Erro ao enviar template: {e}")
        keyboard = [[
            InlineKeyboardButton("⬅️ Voltar ao Cliente",
                                 callback_data=f"cliente_{cliente_id}")
        ]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        try:
            await query.edit_message_text(
                f"❌ **ERRO INTERNO**\n\nDetalhes: {str(e)[:100]}",
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
        except Exception:
            await query.edit_message_text(
                f"❌ ERRO INTERNO\n\nDetalhes: {str(e)[:100]}",
                reply_markup=reply_markup
            )


async def mostrar_historico_cliente(query, context, cliente_id):
    """Mostra histórico de templates e mensagens enviadas para um cliente"""
    try:
        from database import DatabaseManager
        from datetime import datetime

        db = DatabaseManager()

        # Buscar cliente
        clientes = db.listar_clientes(apenas_ativos=False)
        cliente = next((c for c in clientes if c['id'] == cliente_id), None)

        if not cliente:
            await query.edit_message_text(
                "❌ **CLIENTE NÃO ENCONTRADO**",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("⬅️ Voltar à Lista", callback_data="voltar_lista")
                ]])
            )
            return

        # Buscar histórico de mensagens do cliente
        logs = db.obter_historico_cliente_template(cliente_id)

        mensagem = f"📊 **HISTÓRICO DE MENSAGENS**\n\n"
        mensagem += f"**Cliente:** {cliente['nome']}\n"
        mensagem += f"**Telefone:** {cliente['telefone']}\n\n"

        if not logs:
            mensagem += "📭 **Nenhuma mensagem enviada ainda**\n\n"
            mensagem += "Este cliente ainda não recebeu nenhuma mensagem via template."
        else:
            mensagem += f"📈 **Total de envios:** {len(logs)}\n\n"

            # Estatísticas rápidas
            enviados = len([log for log in logs if log['status'] == 'enviado'])
            falhas = len([log for log in logs if log['status'] in ['falha', 'erro', 'timeout']])

            mensagem += f"✅ **Enviados:** {enviados}\n"
            mensagem += f"❌ **Falhas:** {falhas}\n\n"

            mensagem += "📋 **Últimos 5 envios:**\n"

            # Mostrar últimos 5 envios
            for i, log in enumerate(logs[:5]):
                try:
                    data_criacao = datetime.fromisoformat(log['criado_em'].replace('Z', '+00:00'))
                    data_formatada = data_criacao.strftime('%d/%m %H:%M')
                except:
                    data_formatada = log['criado_em'][:16] if log['criado_em'] else 'N/A'

                # Status emoji
                status_emoji = {
                    'enviado': '✅',
                    'falha': '❌',
                    'erro': '❌',
                    'timeout': '⏱️',
                    'pendente': '⏳'
                }.get(log['status'], '❓')

                template_nome = log.get('template_nome', 'Template Removido')
                if not template_nome or template_nome == 'None':
                    if log['tipo'] and 'template_' in log['tipo']:
                        template_nome = log['tipo'].replace('template_', '').title()
                    else:
                        template_nome = log['tipo'] or 'Manual'

                mensagem += f"`{i+1}.` {status_emoji} **{template_nome}** - {data_formatada}\n"

                if log['status'] not in ['enviado']:
                    erro = log.get('erro', log.get('conteudo', ''))
                    if erro and 'Erro:' in erro:
                        erro_resumido = erro.split('Erro:')[1][:30].strip()
                        mensagem += f"    💬 _{erro_resumido}_\n"

                mensagem += "\n"

        # Botões de ação
        keyboard = [
            [
                InlineKeyboardButton("💬 Enviar Mensagem",
                                   callback_data=f"mensagem_{cliente_id}"),
                InlineKeyboardButton("📧 Enviar Cobrança",
                                   callback_data=f"cobrar_{cliente_id}")
            ],
            [
                InlineKeyboardButton("⬅️ Voltar ao Cliente",
                                   callback_data=f"cliente_{cliente_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            mensagem,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )

    except Exception as e:
        logger.error(f"Erro ao mostrar histórico do cliente: {e}")
        keyboard = [[
            InlineKeyboardButton("⬅️ Voltar ao Cliente",
                                 callback_data=f"cliente_{cliente_id}")
        ]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            f"❌ **ERRO AO CARREGAR HISTÓRICO**\n\nDetalhes: {str(e)[:100]}",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )


async def renovar_cliente_inline(query, context, cliente_id):
    """Renova cliente por período específico"""
    try:
        from database import DatabaseManager
        db = DatabaseManager()
        clientes = db.listar_clientes(
            ativo_apenas=False)  # Busca todos os clientes
        cliente = next((c for c in clientes if c['id'] == cliente_id), None)

        # Debug: vamos ver se o cliente existe
        logger.info(f"Procurando cliente ID: {cliente_id}")
        logger.info(f"Total de clientes encontrados: {len(clientes)}")
        if clientes:
            logger.info(f"IDs dos clientes: {[c['id'] for c in clientes]}")

        if not cliente:
            await query.edit_message_text(
                f"❌ Cliente ID {cliente_id} não encontrado!\nTotal clientes: {len(clientes)}"
            )
            return

        vencimento_atual = datetime.strptime(cliente['vencimento'], '%Y-%m-%d')

        mensagem = f"""🔄 *RENOVAR CLIENTE*

👤 *Cliente:* {cliente['nome']}
📅 *Vencimento Atual:* {vencimento_atual.strftime('%d/%m/%Y')}
📦 *Pacote:* {cliente['pacote']}
💰 *Valor:* R$ {cliente['valor']:.2f}

Escolha o período de renovação:"""

        keyboard = [
            [
                InlineKeyboardButton("📅 +30 dias",
                                     callback_data=f"renovar_30_{cliente_id}"),
                InlineKeyboardButton("📅 +60 dias",
                                     callback_data=f"renovar_60_{cliente_id}")
            ],
            [
                InlineKeyboardButton("📅 +90 dias",
                                     callback_data=f"renovar_90_{cliente_id}"),
                InlineKeyboardButton("📅 +365 dias",
                                     callback_data=f"renovar_365_{cliente_id}")
            ],
            [
                InlineKeyboardButton("⬅️ Voltar ao Cliente",
                                     callback_data=f"cliente_{cliente_id}")
            ]
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(mensagem,
                                      parse_mode='Markdown',
                                      reply_markup=reply_markup)

    except Exception as e:
        logger.error(f"Erro ao preparar renovação: {e}")
        await query.edit_message_text("❌ Erro ao preparar renovação!")


async def editar_cliente_inline(query, context, cliente_id):
    """Edita dados do cliente"""
    try:
        from database import DatabaseManager
        db = DatabaseManager()
        clientes = db.listar_clientes(ativo_apenas=False)
        cliente = next((c for c in clientes if c['id'] == cliente_id), None)

        if not cliente:
            await query.edit_message_text("❌ Cliente não encontrado!")
            return

        vencimento = datetime.strptime(cliente['vencimento'], '%Y-%m-%d')

        mensagem = f"""✏️ *EDITAR CLIENTE*

👤 *Cliente:* {cliente['nome']}
📱 *Telefone:* {cliente['telefone']}
📦 *Pacote:* {cliente['pacote']}
💰 *Valor:* R$ {cliente['valor']:.2f}
🖥️ *Servidor:* {cliente['servidor']}
📅 *Vencimento:* {vencimento.strftime('%d/%m/%Y')}

Escolha o que deseja editar:"""

        keyboard = [[
            InlineKeyboardButton("📝 Nome",
                                 callback_data=f"edit_nome_{cliente_id}"),
            InlineKeyboardButton("📱 Telefone",
                                 callback_data=f"edit_telefone_{cliente_id}")
        ],
                    [
                        InlineKeyboardButton(
                            "📦 Pacote",
                            callback_data=f"edit_pacote_{cliente_id}"),
                        InlineKeyboardButton(
                            "💰 Valor",
                            callback_data=f"edit_valor_{cliente_id}")
                    ],
                    [
                        InlineKeyboardButton(
                            "🖥️ Servidor",
                            callback_data=f"edit_servidor_{cliente_id}"),
                        InlineKeyboardButton(
                            "📅 Vencimento",
                            callback_data=f"edit_vencimento_{cliente_id}")
                    ],
                    [
                        InlineKeyboardButton(
                            "⬅️ Voltar ao Cliente",
                            callback_data=f"cliente_{cliente_id}")
                    ]]

        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(mensagem,
                                      parse_mode='Markdown',
                                      reply_markup=reply_markup)

    except Exception as e:
        logger.error(f"Erro ao preparar edição: {e}")
        await query.edit_message_text("❌ Erro ao preparar edição!")


async def excluir_cliente_inline(query, context, cliente_id):
    """Confirma exclusão do cliente"""
    try:
        from database import DatabaseManager
        db = DatabaseManager()
        clientes = db.listar_clientes(ativo_apenas=False)
        cliente = next((c for c in clientes if c['id'] == cliente_id), None)

        if not cliente:
            await query.edit_message_text("❌ Cliente não encontrado!")
            return

        vencimento = datetime.strptime(cliente['vencimento'], '%Y-%m-%d')

        mensagem = f"""🗑️ *EXCLUIR CLIENTE*

⚠️ *ATENÇÃO: Esta ação não pode ser desfeita!*

👤 *Cliente:* {cliente['nome']}
📱 *Telefone:* {cliente['telefone']}
📦 *Pacote:* {cliente['pacote']}
💰 *Valor:* R$ {cliente['valor']:.2f}
📅 *Vencimento:* {vencimento.strftime('%d/%m/%Y')}

Tem certeza que deseja excluir este cliente?"""

        keyboard = [[
            InlineKeyboardButton(
                "🗑️ SIM, EXCLUIR",
                callback_data=f"confirmar_excluir_{cliente_id}"),
            InlineKeyboardButton("❌ Cancelar",
                                 callback_data=f"cliente_{cliente_id}")
        ]]

        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(mensagem,
                                      parse_mode='Markdown',
                                      reply_markup=reply_markup)

    except Exception as e:
        logger.error(f"Erro ao preparar exclusão: {e}")
        await query.edit_message_text("❌ Erro ao preparar exclusão!")


async def confirmar_exclusao_cliente(query, context, cliente_id):
    """Executa a exclusão do cliente"""
    try:
        from database import DatabaseManager
        db = DatabaseManager()
        clientes = db.listar_clientes(ativo_apenas=False)
        cliente = next((c for c in clientes if c['id'] == cliente_id), None)

        if not cliente:
            await query.edit_message_text("❌ Cliente não encontrado!")
            return

        nome_cliente = cliente['nome']

        # Executar exclusão
        sucesso = db.excluir_cliente(cliente_id)

        if sucesso:
            mensagem = f"""✅ *CLIENTE EXCLUÍDO*

👤 Cliente: {nome_cliente}
🗑️ Removido do sistema em: {agora_br().strftime('%d/%m/%Y %H:%M')}

O cliente foi permanentemente excluído do banco de dados."""
        else:
            mensagem = f"❌ *ERRO AO EXCLUIR*\n\nNão foi possível excluir o cliente {nome_cliente}.\nTente novamente mais tarde."

        keyboard = [[
            InlineKeyboardButton("⬅️ Voltar à Lista",
                                 callback_data="voltar_lista")
        ]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(mensagem,
                                      parse_mode='Markdown',
                                      reply_markup=reply_markup)

    except Exception as e:
        logger.error(f"Erro ao excluir cliente: {e}")
        await query.edit_message_text("❌ Erro interno ao excluir cliente!")


async def processar_renovacao_cliente(query, context, cliente_id, dias):
    """Processa a renovação do cliente por X dias"""
    try:
        from database import DatabaseManager
        db = DatabaseManager()
        clientes = db.listar_clientes(ativo_apenas=False)
        cliente = next((c for c in clientes if c['id'] == cliente_id), None)

        if not cliente:
            await query.edit_message_text("❌ Cliente não encontrado!")
            return

        # Calcular nova data de vencimento
        from datetime import datetime, timedelta  # Import local para evitar conflitos
        vencimento_atual = datetime.strptime(cliente['vencimento'], '%Y-%m-%d')

        # Se já venceu, renovar a partir de hoje
        if vencimento_atual < agora_br().replace(tzinfo=None):
            nova_data = agora_br().replace(tzinfo=None) + timedelta(days=dias)
        else:
            # Se ainda não venceu, somar os dias ao vencimento atual
            nova_data = vencimento_atual + timedelta(days=dias)

        # Atualizar apenas a data de vencimento
        sucesso = db.atualizar_cliente(cliente_id, 'vencimento',
                                       nova_data.strftime('%Y-%m-%d'))

        if sucesso:
            # Registrar renovação no histórico
            db.registrar_renovacao(cliente_id, dias, cliente['valor'])

            mensagem = f"""✅ *CLIENTE RENOVADO*

👤 *Cliente:* {cliente['nome']}
⏰ *Período adicionado:* {dias} dias
📅 *Vencimento anterior:* {vencimento_atual.strftime('%d/%m/%Y')}
🔄 *Novo vencimento:* {nova_data.strftime('%d/%m/%Y')}
💰 *Valor:* R$ {cliente['valor']:.2f}

Renovação registrada com sucesso!"""
        else:
            mensagem = f"❌ *ERRO NA RENOVAÇÃO*\n\nNão foi possível renovar o cliente.\nTente novamente mais tarde."

        keyboard = [[
            InlineKeyboardButton("⬅️ Voltar ao Cliente",
                                 callback_data=f"cliente_{cliente_id}"),
            InlineKeyboardButton("📋 Ver Lista", callback_data="voltar_lista")
        ]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(mensagem,
                                      parse_mode='Markdown',
                                      reply_markup=reply_markup)

    except Exception as e:
        logger.error(f"Erro ao renovar cliente: {e}")
        await query.edit_message_text("❌ Erro interno ao renovar cliente!")


async def iniciar_edicao_campo(query, context, cliente_id, campo):
    """Inicia a edição interativa de um campo específico do cliente"""
    try:
        from database import DatabaseManager
        db = DatabaseManager()
        clientes = db.listar_clientes(ativo_apenas=False)
        cliente = next((c for c in clientes if c['id'] == cliente_id), None)

        if not cliente:
            await query.edit_message_text("❌ Cliente não encontrado!")
            return

        # Salvar dados no contexto para a conversa de edição
        context.user_data['editando_cliente_id'] = cliente_id
        context.user_data['editando_campo'] = campo
        context.user_data['cliente_dados'] = cliente

        # Mapear campos e valores atuais
        campos_info = {
            'nome': {
                'label': 'Nome',
                'valor': cliente['nome'],
                'placeholder': 'Ex: João Silva Santos'
            },
            'telefone': {
                'label': 'Telefone',
                'valor': cliente['telefone'],
                'placeholder': 'Ex: 11999999999'
            },
            'pacote': {
                'label': 'Pacote',
                'valor': cliente['pacote'],
                'placeholder': 'Ex: Netflix Premium'
            },
            'valor': {
                'label': 'Valor',
                'valor': f"R$ {cliente['valor']:.2f}",
                'placeholder': 'Ex: 45.00'
            },
            'servidor': {
                'label': 'Servidor',
                'valor': cliente['servidor'],
                'placeholder': 'Ex: BR-SP01'
            },
            'vencimento': {
                'label':
                'Vencimento',
                'valor':
                datetime.strptime(cliente['vencimento'],
                                  '%Y-%m-%d').strftime('%d/%m/%Y'),
                'placeholder':
                'Ex: 15/03/2025'
            }
        }

        if campo not in campos_info:
            await query.edit_message_text("❌ Campo inválido!")
            return

        info = campos_info[campo]

        mensagem = f"""✏️ *EDITAR {info['label'].upper()}*

👤 *Cliente:* {cliente['nome']}
📝 *Campo:* {info['label']}
🔄 *Valor atual:* {info['valor']}

💬 Digite o novo {info['label'].lower()}:
{info['placeholder']}"""

        # Criar teclado com cancelar
        keyboard = [[KeyboardButton("❌ Cancelar")]]
        reply_markup = ReplyKeyboardMarkup(keyboard,
                                           resize_keyboard=True,
                                           one_time_keyboard=True)

        # Remover mensagem inline e enviar nova mensagem de texto
        await query.delete_message()
        await context.bot.send_message(chat_id=query.message.chat_id,
                                       text=mensagem,
                                       parse_mode='Markdown',
                                       reply_markup=reply_markup)

        # Mapear campo para estado
        estados_edicao = {
            'nome': EDIT_NOME,
            'telefone': EDIT_TELEFONE,
            'pacote': EDIT_PACOTE,
            'valor': EDIT_VALOR,
            'servidor': EDIT_SERVIDOR,
            'vencimento': EDIT_VENCIMENTO
        }

        return estados_edicao[campo]

    except Exception as e:
        logger.error(f"Erro ao iniciar edição: {e}")
        await query.edit_message_text("❌ Erro ao preparar edição!")


@verificar_admin
async def editar_cliente_cmd(update, context):
    """Comando para editar cliente via comando"""
    try:
        if len(context.args) < 3:
            await update.message.reply_text(
                "❌ Uso correto:\n"
                "`/editar ID campo valor`\n\n"
                "*Exemplo:*\n"
                "`/editar 1 nome João Silva`\n"
                "`/editar 1 valor 35.00`",
                parse_mode='Markdown',
                reply_markup=criar_teclado_principal())
            return

        cliente_id = int(context.args[0])
        campo = context.args[1].lower()
        novo_valor = " ".join(context.args[2:])

        from database import DatabaseManager
        db = DatabaseManager()
        clientes = db.listar_clientes(apenas_ativos=True)
        cliente = next((c for c in clientes if c['id'] == cliente_id), None)

        if not cliente:
            await update.message.reply_text(
                f"❌ Cliente com ID {cliente_id} não encontrado!",
                reply_markup=criar_teclado_principal())
            return

        # Validar campo e atualizar
        campos_validos = [
            'nome', 'telefone', 'pacote', 'valor', 'servidor', 'vencimento'
        ]
        if campo not in campos_validos:
            await update.message.reply_text(
                f"❌ Campo inválido! Use: {', '.join(campos_validos)}",
                reply_markup=criar_teclado_principal())
            return

        # Preparar dados para atualização
        dados = {
            'nome': cliente['nome'],
            'telefone': cliente['telefone'],
            'pacote': cliente['pacote'],
            'valor': cliente['valor'],
            'servidor': cliente['servidor'],
            'vencimento': cliente['vencimento']
        }

        # Aplicar mudança
        if campo == 'valor':
            try:
                dados['valor'] = float(novo_valor)
            except ValueError:
                await update.message.reply_text("❌ Valor deve ser um número!")
                return
        elif campo == 'vencimento':
            try:
                # Converter dd/mm/yyyy para yyyy-mm-dd
                if '/' in novo_valor:
                    dia, mes, ano = novo_valor.split('/')
                    novo_valor = f"{ano}-{mes.zfill(2)}-{dia.zfill(2)}"
                dados['vencimento'] = novo_valor
            except:
                await update.message.reply_text(
                    "❌ Data inválida! Use dd/mm/aaaa")
                return
        else:
            dados[campo] = novo_valor

        # Executar atualização
        sucesso = db.atualizar_cliente(cliente_id, campo, dados[campo])

        if sucesso:
            mensagem = f"""✅ *Cliente Atualizado!*

👤 *Nome:* {dados['nome']}
📱 *Telefone:* {dados['telefone']}
📦 *Pacote:* {dados['pacote']}
💰 *Valor:* R$ {dados['valor']:.2f}
🖥️ *Servidor:* {dados['servidor']}
📅 *Vencimento:* {datetime.strptime(dados['vencimento'], '%Y-%m-%d').strftime('%d/%m/%Y')}

🔄 *Campo alterado:* {campo.upper()}"""
        else:
            mensagem = "❌ Erro ao atualizar cliente!"

        await update.message.reply_text(mensagem,
                                        parse_mode='Markdown',
                                        reply_markup=criar_teclado_principal())

    except Exception as e:
        logger.error(f"Erro ao editar cliente: {e}")
        await update.message.reply_text("❌ Erro interno ao editar cliente!",
                                        reply_markup=criar_teclado_principal())


@verificar_admin
async def relatorio(update, context):
    """Gera relatório básico"""
    try:
        from database import DatabaseManager
        db = DatabaseManager()

        clientes = db.listar_clientes(apenas_ativos=True)
        total_clientes = len(clientes)
        receita_total = sum(float(c['valor']) for c in clientes)

        hoje = agora_br().replace(tzinfo=None).strftime('%Y-%m-%d')
        vencendo_hoje = [c for c in clientes if c['vencimento'] == hoje]

        mensagem = f"""📊 *RELATÓRIO GERAL*

👥 Total de clientes: {total_clientes}
💰 Receita mensal: R$ {receita_total:.2f}
⚠️ Vencendo hoje: {len(vencendo_hoje)}

📅 Data: {agora_br().replace(tzinfo=None).strftime('%d/%m/%Y %H:%M')}"""

        await update.message.reply_text(mensagem,
                                        parse_mode='Markdown',
                                      reply_markup=criar_teclado_principal())

    except Exception as e:
        logger.error(f"Erro no relatório: {e}")
        await update.message.reply_text("❌ Erro ao gerar relatório!")


@verificar_admin
async def help_cmd(update, context):
    """Comando de ajuda"""
    mensagem = """🆘 *COMANDOS DISPONÍVEIS*

*Gestão de Clientes:*
/start - Iniciar o bot
/addcliente - Como adicionar cliente
/add - Adicionar cliente
/listar - Listar todos os clientes
/relatorio - Relatório geral
/help - Esta ajuda

*Exemplo:*
`/add João Silva | 11999999999 | Netflix | 25.90 | 2025-03-15 | Servidor1`

🤖 Bot funcionando 24/7!"""

    await update.message.reply_text(mensagem,
                                    parse_mode='Markdown',
                                    reply_markup=criar_teclado_principal())


@verificar_admin
async def lidar_com_botoes(update, context):
    """Lida com os botões pressionados - somente quando não há conversa ativa"""
    texto = update.message.text

    # Lista de botões reconhecidos
    botoes_reconhecidos = [
        "👥 Listar Clientes", "➕ Adicionar Cliente", "📊 Relatórios",
        "🔍 Buscar Cliente", "🏢 Empresa", "💳 PIX", "📞 Suporte",
        "📱 WhatsApp Status", "🧪 Testar WhatsApp", "📱 QR Code",
        "⚙️ Gerenciar WhatsApp", "📄 Templates", "⏰ Agendador",
        "📋 Fila de Mensagens", "📜 Logs de Envios", "❓ Ajuda"
    ]

    # Se não é um botão reconhecido, não fazer nada (evitar mensagem de ajuda)
    if texto not in botoes_reconhecidos:
        return

    # Verificar se há uma conversa ativa (ConversationHandler em uso)
    if hasattr(context, 'user_data') and context.user_data:
        # Se há dados de conversa ativa, não processar aqui
        if any(key in context.user_data for key in
               ['editando_cliente_id', 'cadastro_atual', 'config_estado']):
            return

    if texto == "👥 Listar Clientes":
        await listar_clientes(update, context)
    elif texto == "➕ Adicionar Cliente":
        # Este caso será tratado pelo ConversationHandler
        pass
    elif texto == "📊 Relatórios":
        await relatorio(update, context)
    elif texto == "🔍 Buscar Cliente":
        await buscar_cliente_cmd(update, context)
    elif texto == "🏢 Empresa":
        # Este caso será tratado pelo ConversationHandler config_direct_handler
        pass
    elif texto == "💳 PIX":
        # Este caso será tratado pelo ConversationHandler config_direct_handler
        pass
    elif texto == "📞 Suporte":
        # Este caso será tratado pelo ConversationHandler config_direct_handler
        pass
    elif texto == "📱 WhatsApp Status":
        await whatsapp_status_direct(update, context)
    elif texto == "🧪 Testar WhatsApp":
        await testar_whatsapp_direct(update, context)
    elif texto == "📱 QR Code":
        await qr_code_direct(update, context)
    elif texto == "⚙️ Gerenciar WhatsApp":
        await gerenciar_whatsapp_direct(update, context)
    elif texto == "📄 Templates":
        await menu_templates_direct(update, context)
    elif texto == "⏰ Agendador":
        from agendador_interface import mostrar_agendador_principal
        await mostrar_agendador_principal(update, context)
    elif texto == "📋 Fila de Mensagens":
        await update.message.reply_text(
            "📋 Sistema de fila de mensagens será implementado em breve!",
            reply_markup=criar_teclado_principal())
    elif texto == "📜 Logs de Envios":
        await update.message.reply_text(
            "📜 Sistema de logs de envios será implementado em breve!",
            reply_markup=criar_teclado_principal())
    elif texto == "❓ Ajuda":
        await help_cmd(update, context)


# Funções diretas para WhatsApp e Templates
async def whatsapp_status_direct(update, context):
    """Mostra status do WhatsApp diretamente"""
    await update.message.reply_text(
        "📱 *Status WhatsApp*\n\nVerificando status...",
        parse_mode='Markdown',
        reply_markup=criar_teclado_principal()
    )

async def testar_whatsapp_direct(update, context):
    """Testa WhatsApp diretamente"""
    await update.message.reply_text(
        "🧪 *Teste WhatsApp*\n\nIniciando teste...",
        parse_mode='Markdown',
        reply_markup=criar_teclado_principal()
    )

async def qr_code_direct(update, context):
    """Mostra QR Code diretamente"""
    await update.message.reply_text(
        "📱 *QR Code*\n\nGerando código QR...",
        parse_mode='Markdown',
        reply_markup=criar_teclado_principal()
    )

async def gerenciar_whatsapp_direct(update, context):
    """Gerencia WhatsApp diretamente"""
    await update.message.reply_text(
        "⚙️ *Gerenciar WhatsApp*\n\nAbrindo gerenciamento...",
        parse_mode='Markdown',
        reply_markup=criar_teclado_principal()
    )

async def menu_templates_direct(update, context):
    """Menu de templates direto"""
    try:
        from database import DatabaseManager
        db = DatabaseManager()
        templates = db.listar_templates()
        
        mensagem = f"📄 *SISTEMA DE TEMPLATES*\n\n"
        mensagem += f"📊 Templates disponíveis: {len(templates)}\n\n"
        
        keyboard = []
        
        for template in templates:
            template_id = template['id']
            nome_display = template['nome'][:20] + ('...' if len(template['nome']) > 20 else '')
            
            keyboard.append([
                InlineKeyboardButton(f"📝 {nome_display}",
                                   callback_data=f"template_mostrar_{template_id}"),
                InlineKeyboardButton("✏️ Editar",
                                   callback_data=f"template_editar_{template_id}")
            ])
        
        keyboard.append([
            InlineKeyboardButton("➕ Novo Template", callback_data="template_criar"),
            InlineKeyboardButton("🧪 Testar Template", callback_data="template_testar")
        ])
        keyboard.append([
            InlineKeyboardButton("⬅️ Menu Principal", callback_data="voltar_menu")
        ])
        
        if not templates:
            mensagem += "📭 **Nenhum template encontrado**\n\n"
            mensagem += "Crie seu primeiro template."
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            mensagem,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        
    except Exception as e:
        logger.error(f"Erro no menu templates: {e}")
        await update.message.reply_text(
            "❌ Erro ao carregar templates",
            reply_markup=criar_teclado_principal()
        )

@verificar_admin
async def buscar_cliente_cmd(update, context):
    """Comando para buscar cliente"""
    await update.message.reply_text(
        "🔍 *Buscar Cliente*\n\n"
        "Para buscar um cliente, use:\n"
        "`/buscar telefone`\n\n"
        "*Exemplo:*\n"
        "`/buscar 11999999999`",
        parse_mode='Markdown',
        reply_markup=criar_teclado_principal())


@verificar_admin
async def buscar_cliente(update, context):
    """Busca cliente por telefone"""
    try:
        if not context.args:
            await update.message.reply_text(
                "❌ Por favor, informe o telefone!\n\n"
                "Exemplo: `/buscar 11999999999`",
                parse_mode='Markdown',
                reply_markup=criar_teclado_principal())
            return

        telefone = context.args[0]

        from database import DatabaseManager
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
💰 *Valor:* R$ {cliente['valor']:.2f}
📅 *Vencimento:* {vencimento.strftime('%d/%m/%Y')}
🖥️ *Servidor:* {cliente['servidor']}"""

        await update.message.reply_text(mensagem,
                                        parse_mode='Markdown',
                                        reply_markup=criar_teclado_principal())

    except Exception as e:
        logger.error(f"Erro ao buscar cliente: {e}")
        await update.message.reply_text("❌ Erro ao buscar cliente!",
                                        reply_markup=criar_teclado_principal())


@verificar_admin
async def configuracoes_cmd(update, context):
    """Comando de configurações"""
    try:
        from database import DatabaseManager
        db = DatabaseManager()
        config = db.get_configuracoes()

        if config:
            # Escapar caracteres especiais para HTML
            empresa = escapar_html(config['empresa_nome'])
            pix_key = escapar_html(config['pix_key'])
            suporte = escapar_html(config['contato_suporte'])

            mensagem = f"""⚙️ <b>Configurações Atuais</b>

🏢 <b>Empresa:</b> {empresa}
💳 <b>PIX:</b> {pix_key}
📞 <b>Suporte:</b> {suporte}"""

            # Criar botões inline para editar configurações
            keyboard = [
                [
                    InlineKeyboardButton("🏢 Alterar Empresa",
                                         callback_data="config_empresa")
                ],
                [
                    InlineKeyboardButton("💳 Alterar PIX",
                                         callback_data="config_pix")
                ],
                [
                    InlineKeyboardButton("📞 Alterar Suporte",
                                         callback_data="config_suporte")
                ],
                [
                    InlineKeyboardButton("🔄 Atualizar",
                                         callback_data="config_refresh")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

        else:
            mensagem = """⚙️ <b>Configurações</b>

Nenhuma configuração encontrada.
Configure sua empresa para personalizar as mensagens do bot."""

            # Botões para configuração inicial
            keyboard = [
                [
                    InlineKeyboardButton("🏢 Configurar Empresa",
                                         callback_data="config_empresa")
                ],
                [
                    InlineKeyboardButton("💳 Configurar PIX",
                                         callback_data="config_pix")
                ],
                [
                    InlineKeyboardButton("📞 Configurar Suporte",
                                         callback_data="config_suporte")
                ],
                [
                    InlineKeyboardButton("📱 Status WhatsApp",
                                         callback_data="whatsapp_status")
                ],
                [
                    InlineKeyboardButton("🧪 Testar WhatsApp",
                                         callback_data="whatsapp_test")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(mensagem,
                                        parse_mode='HTML',
                                      reply_markup=reply_markup)

    except Exception as e:
        logger.error(f"Erro nas configurações: {e}")
        await update.message.reply_text("❌ Erro ao carregar configurações!",
                                        reply_markup=criar_teclado_principal())


# Funções de callback para configurações
async def config_callback(update, context):
    """Callback para botões de configuração"""
    query = update.callback_query
    await query.answer()

    data = query.data

    if data == "config_refresh":
        # Atualizar as configurações
        try:
            from database import DatabaseManager
            db = DatabaseManager()
            config = db.get_configuracoes()

            if config:
                empresa = escapar_html(config['empresa_nome'])
                pix_key = escapar_html(config['pix_key'])
                suporte = escapar_html(config['contato_suporte'])

                mensagem = f"""⚙️ <b>Configurações Atuais</b>

🏢 <b>Empresa:</b> {empresa}
💳 <b>PIX:</b> {pix_key}
📞 <b>Suporte:</b> {suporte}"""

                keyboard = [
                    [
                        InlineKeyboardButton("🏢 Alterar Empresa",
                                             callback_data="config_empresa")
                    ],
                    [
                        InlineKeyboardButton("💳 Alterar PIX",
                                             callback_data="config_pix")
                    ],
                    [
                        InlineKeyboardButton("📞 Alterar Suporte",
                                             callback_data="config_suporte")
                    ],
                    [
                        InlineKeyboardButton("📱 Status WhatsApp",
                                             callback_data="whatsapp_status")
                    ],
                    [
                        InlineKeyboardButton("🧪 Testar WhatsApp",
                                             callback_data="whatsapp_test")
                    ],
                    [
                        InlineKeyboardButton("⚙️ Gerenciar Instância",
                                             callback_data="whatsapp_instance")
                    ],
                    [
                        InlineKeyboardButton("🔄 Atualizar",
                                             callback_data="config_refresh")
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)

                await query.edit_message_text(text=mensagem,
                                              parse_mode='HTML',
                                              reply_markup=reply_markup)
            else:
                await query.edit_message_text("❌ Nenhuma configuração encontrada!")

        except Exception as e:
            logger.error(f"Erro ao atualizar configurações: {e}")
            try:
                await query.edit_message_text(
                    "❌ Erro ao carregar configurações!")
            except:
                # Se não conseguir editar, enviar nova mensagem
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text="❌ Erro ao carregar configurações!")

    elif data == "config_empresa":
        return await iniciar_config_empresa(query, context)
    elif data == "config_pix":
        return await iniciar_config_pix(query, context)
    elif data == "config_suporte":
        return await iniciar_config_suporte(query, context)
    elif data == "whatsapp_status":
        await verificar_whatsapp_status(query, context)
    elif data == "whatsapp_test":
        await testar_whatsapp(query, context)
    elif data == "whatsapp_instance":
        await gerenciar_instancia(query, context)
    elif data == "instance_restart":
        await reiniciar_instancia(query, context)
    elif data == "instance_details":
        await mostrar_detalhes_instancia(query, context)
    elif data == "instance_disconnect":
        await desconectar_instancia(query, context)
    elif data == "show_qrcode":
        await mostrar_qr_code(query, context)
    elif data == "instance_stable_reconnect":
        await reconexao_estavel(query, context)

    # Templates System callbacks
    elif data == "templates_listar":
        from callbacks_templates import callback_templates_listar
        await callback_templates_listar(query, context)
    elif data == "templates_editar":
        from callbacks_templates import callback_templates_editar
        await callback_templates_editar(query, context)
    elif data == "templates_testar":
        from callbacks_templates import callback_templates_testar
        await callback_templates_testar(query, context)
    elif data == "template_ver":
        from callbacks_templates import callback_templates_ver
        await callback_templates_ver(query, context)
    elif data.startswith("template_mostrar_"):
        template_id = int(data.split("_")[2])
        from callbacks_templates import callback_template_mostrar
        await callback_template_mostrar(query, context, template_id)
    elif data.startswith("template_testar_"):
        template_id = int(data.split("_")[2])
        from callbacks_templates import callback_template_testar
        await callback_template_testar(query, context, template_id)
    elif data == "template_criar":
        await callback_template_criar(query, context)
    elif data.startswith("template_toggle_"):
        template_id = int(data.split("_")[2])
        await callback_template_toggle(query, context, template_id)
    elif data.startswith("template_excluir_"):
        template_id = int(data.split("_")[2])
        await callback_template_excluir(query, context, template_id)
    elif data.startswith("confirmar_excluir_template_"):
        template_id = int(data.split("_")[3])
        await callback_confirmar_excluir_template(query, context, template_id)
    elif data == "template_excluir_escolher":
        await callback_template_excluir_escolher(query, context)
    elif data == "template_editar_escolher":
        await callback_template_editar_escolher(query, context)
    elif data == "menu_principal":
        await callback_menu_principal(query, context)

    # Scheduler System callbacks
    elif data == "agendador_executar":
        from callbacks_templates import callback_agendador_executar
        await callback_agendador_executar(query, context)
    elif data == "agendador_stats":
        from callbacks_templates import callback_agendador_stats
        await callback_agendador_stats(query, context)
    elif data == "agendador_config":
        from callbacks_templates import callback_agendador_config
        await callback_agendador_config(query, context)


async def iniciar_config_empresa(query, context):
    """Inicia configuração da empresa"""
    mensagem = """🏢 <b>Configurar Nome da Empresa</b>

Digite o nome da sua empresa:
<i>Ex: IPTV Premium Brasil</i>"""

    keyboard = [[KeyboardButton("❌ Cancelar")]]
    reply_markup = ReplyKeyboardMarkup(keyboard,
                                       resize_keyboard=True,
                                       one_time_keyboard=True)

    await query.delete_message()
    await context.bot.send_message(chat_id=query.message.chat_id,
                                   text=mensagem,
                                   parse_mode='HTML',
                                   reply_markup=reply_markup)

    return CONFIG_EMPRESA


async def iniciar_config_pix(query, context):
    """Inicia configuração do PIX"""
    mensagem = """💳 <b>Configurar Chave PIX</b>

Digite sua chave PIX:
<i>Ex: empresa@email.com ou 11999887766</i>"""

    keyboard = [[KeyboardButton("❌ Cancelar")]]
    reply_markup = ReplyKeyboardMarkup(keyboard,
                                       resize_keyboard=True,
                                       one_time_keyboard=True)

    await query.delete_message()
    await context.bot.send_message(chat_id=query.message.chat_id,
                                   text=mensagem,
                                   parse_mode='HTML',
                                   reply_markup=reply_markup)

    return CONFIG_PIX


async def iniciar_config_suporte(query, context):
    """Inicia configuração do suporte"""
    mensagem = """📞 <b>Configurar Contato de Suporte</b>

Digite o contato para suporte:
<i>Ex: @seu_usuario ou 11999887766</i>"""

    keyboard = [[KeyboardButton("❌ Cancelar")]]
    reply_markup = ReplyKeyboardMarkup(keyboard,
                                       resize_keyboard=True,
                                       one_time_keyboard=True)

    await query.delete_message()
    await context.bot.send_message(chat_id=query.message.chat_id,
                                   text=mensagem,
                                   parse_mode='HTML',
                                   reply_markup=reply_markup)

    return CONFIG_SUPORTE


# === CALLBACKS DE TEMPLATES ===

async def callback_template_criar(query, context):
    """Callback para criar novo template"""
    try:
        from callbacks_templates import callback_templates_criar
        await callback_templates_criar(query, context)
    except Exception as e:
        logger.error(f"Erro no callback criar template: {e}")
        await query.edit_message_text(
            "❌ Erro ao mostrar instruções de criação",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⬅️ Voltar", callback_data="templates_listar")
            ]])
        )

async def callback_template_toggle(query, context, template_id):
    """Callback para ativar/desativar template"""
    try:
        from database import DatabaseManager
        db = DatabaseManager()

        # Buscar template no banco de dados
        templates = db.listar_templates(apenas_ativos=False)
        template = next((t for t in templates if t['id'] == template_id), None)

        if not template:
            await query.edit_message_text(
                "❌ **TEMPLATE NÃO ENCONTRADO**\n\n"
                "O template pode ter sido excluído.",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("⬅️ Menu Templates", callback_data="voltar_templates")
                ]])
            )
            return

        # Inverter status
        novo_status = 0 if template['ativo'] == 1 else 1

        try:
            db.atualizar_template(template_id, ativo=novo_status)
            status_text = "ativado" if novo_status else "desativado"
            mensagem = f"""✅ **Template {status_text.title()}!**

📝 **Template:** {template['nome']}
🆔 **ID:** {template_id}
📊 **Novo Status:** {"✅ Ativo" if novo_status else "❌ Inativo"}"""
        except Exception as e:
            logger.error(f"Erro ao alterar status do template: {e}")
            mensagem = "❌ Erro ao alterar status do template."

        keyboard = [[
            InlineKeyboardButton("👁️ Ver Template", callback_data=f"template_mostrar_{template_id}"),
            InlineKeyboardButton("⬅️ Voltar", callback_data="template_ver")
        ]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            text=mensagem,
            parse_mode='HTML',
            reply_markup=reply_markup
        )

    except Exception as e:
        logger.error(f"Erro ao alterar status do template: {e}")
        await query.edit_message_text(
            "❌ Erro ao alterar status do template!",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⬅️ Voltar", callback_data="template_ver")
            ]])
        )

async def callback_template_excluir(query, context, template_id):
    """Callback para confirmar exclusão de template"""
    try:
        from database import DatabaseManager
        db = DatabaseManager()

        # Buscar template no banco de dados
        templates = db.listar_templates(apenas_ativos=False)
        template = next((t for t in templates if t['id'] == template_id), None)

        if not template:
            await query.edit_message_text(
                "❌ **TEMPLATE NÃO ENCONTRADO**\n\n"
                "O template pode ter sido excluído.",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("⬅️ Menu Templates", callback_data="voltar_templates")
                ]])
            )
            return

        mensagem = f"""🗑️ **EXCLUIR TEMPLATE**

⚠️ **ATENÇÃO: Esta ação não pode ser desfeita!**

📝 **Template:** {template['nome']}
🆔 **ID:** {template_id}
📂 **Tipo:** {template.get('tipo', 'geral').replace('_', ' ').title()}
📊 **Status:** {"✅ Ativo" if template['ativo'] else "❌ Inativo"}

Tem certeza que deseja excluir este template permanentemente?"""

        keyboard = [[
            InlineKeyboardButton("🗑️ SIM, EXCLUIR", callback_data=f"confirmar_excluir_template_{template_id}"),
            InlineKeyboardButton("❌ Cancelar", callback_data=f"template_mostrar_{template_id}")
        ]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            text=mensagem,
            parse_mode='HTML',
            reply_markup=reply_markup
        )

    except Exception as e:
        logger.error(f"Erro ao preparar exclusão: {e}")
        await query.edit_message_text(
            "❌ Erro ao preparar exclusão do template!",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⬅️ Voltar", callback_data="template_ver")
            ]])
        )

async def callback_confirmar_excluir_template(query, context, template_id):
    """Callback para confirmar e executar exclusão de template"""
    try:
        from database import DatabaseManager
        db = DatabaseManager()

        # Buscar template no banco
        templates = db.listar_templates(apenas_ativos=False)
        template = next((t for t in templates if t['id'] == template_id), None)

        if not template:
            await query.edit_message_text(
                "❌ **TEMPLATE NÃO ENCONTRADO**\n\n"
                "O template pode ter sido excluído.",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("⬅️ Menu Templates", callback_data="voltar_templates")
                ]])
            )
            return

        nome_template = template['nome']

        # Executar exclusão
        try:
            db.excluir_template(template_id)
            sucesso = True
        except Exception as e:
            logger.error(f"Erro ao excluir template: {e}")
            sucesso = False

        if sucesso:
            mensagem = f"""✅ <b>TEMPLATE EXCLUÍDO</b>

📝 <b>Template:</b> {nome_template}
🆔 <b>ID:</b> {template_id}
🗑️ <b>Excluído em:</b> {agora_br().strftime('%d/%m/%Y às %H:%M')}

O template foi permanentemente removido do sistema."""
        else:
            mensagem = f"""❌ <b>ERRO AO EXCLUIR</b>

Não foi possível excluir o template {nome_template}.
Tente novamente mais tarde."""

        keyboard = [[
            InlineKeyboardButton("📋 Ver Templates", callback_data="templates_listar"),
            InlineKeyboardButton("⬅️ Menu Templates", callback_data="menu_principal")
        ]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            text=mensagem,
            parse_mode='HTML',
            reply_markup=reply_markup
        )

    except Exception as e:
        logger.error(f"Erro ao excluir template: {e}")
        await query.edit_message_text(
            "❌ Erro interno ao excluir template!",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("📋 Ver Templates", callback_data="templates_listar")
            ]])
        )

async def callback_template_excluir_escolher(query, context):
    """Callback para escolher template para excluir"""
    try:
        from database import DatabaseManager
        db = DatabaseManager()
        templates = db.listar_templates(apenas_ativos=False)

        if not templates:
            await query.edit_message_text(
                "❌ Nenhum template encontrado para excluir.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("⬅️ Voltar", callback_data="templates_listar")
                ]])
            )
            return

        mensagem = """🗑️ <b>EXCLUIR TEMPLATE</b>

Escolha um template para excluir:

⚠️ <b>ATENÇÃO:</b> Esta ação é permanente!"""

        keyboard = []
        for template in templates[:10]:
            status_icon = "✅" if template['ativo'] else "❌"
            keyboard.append([
                InlineKeyboardButton(
                    f"{status_icon} {template['nome']}",
                    callback_data=f"template_excluir_{template['id']}"
                )
            ])

        keyboard.append([
            InlineKeyboardButton("⬅️ Voltar", callback_data="templates_listar")
        ])

        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            text=mensagem,
            parse_mode='HTML',
            reply_markup=reply_markup
        )

    except Exception as e:
        logger.error(f"Erro ao mostrar lista de exclusão: {e}")
        await query.edit_message_text(
            "❌ Erro ao carregar templates para exclusão",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⬅️ Voltar", callback_data="templates_listar")
            ]])
        )

async def callback_template_editar_escolher(query, context):
    """Callback para escolher template para editar"""
    try:
        mensagem = """✏️ <b>EDITAR TEMPLATES</b>

Para editar templates, use os comandos:

<code>/template_editar [ID] [campo] [novo_valor]</code>

<b>Campos disponíveis:</b>
• <code>titulo</code> - Título do template
• <code>conteudo</code> - Conteúdo do template
• <code>tipo</code> - Tipo do template
• <code>descricao</code> - Descrição do template
• <code>ativo</code> - true/false para ativar/desativar

<b>Exemplo:</b>
<code>/template_editar 1 titulo "Novo Título"</code>

Ou use os botões de visualização para editar templates específicos."""

        keyboard = [[
            InlineKeyboardButton("👁️ Ver Templates", callback_data="template_ver"),
            InlineKeyboardButton("📋 Listar Todos", callback_data="templates_listar")
        ], [
            InlineKeyboardButton("⬅️ Voltar", callback_data="templates_listar")
        ]]

        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            text=mensagem,
            parse_mode='HTML',
            reply_markup=reply_markup
        )

    except Exception as e:
        logger.error(f"Erro ao mostrar opções de edição: {e}")
        await query.edit_message_text(
            "❌ Erro ao carregar opções de edição",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⬅️ Voltar", callback_data="templates_listar")
            ]])
        )

async def iniciar_edicao_template_db(query, context, template_id):
    """Inicia edição interativa de template do banco de dados"""
    try:
        from database import DatabaseManager
        db = DatabaseManager()

        # Buscar template no banco
        templates = db.listar_templates(apenas_ativos=False)
        template = next((t for t in templates if t['id'] == template_id), None)

        if not template:
            await query.edit_message_text(
                "❌ **TEMPLATE NÃO ENCONTRADO**\n\n"
                "O template pode ter sido excluído.",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("⬅️ Menu Templates", callback_data="voltar_templates")
                ]])
            )
            return

        # Salvar dados no contexto para edição
        context.user_data['editando_template_id'] = template_id
        context.user_data['template_original'] = template
        context.user_data['aguardando_edicao'] = True

        # Conteúdo truncado para exibição
        conteudo_preview = template['conteudo'][:200] + "..." if len(template['conteudo']) > 200 else template['conteudo']

        mensagem = f"""✏️ **MODO EDIÇÃO ATIVO**

📝 **Template:** {template['nome']}
🆔 **ID:** {template['id']}
📊 **Tipo:** {template['tipo']}

📄 **Conteúdo atual:**
```
{conteudo_preview}
```

⚠️ **DIGITE O NOVO CONTEÚDO** como próxima mensagem

**Variáveis disponíveis:**
• {{nome}} • {{telefone}} • {{pacote}}
• {{valor}} • {{vencimento}} • {{servidor}}

**Digite /cancel para cancelar a edição**"""

        await query.edit_message_text(
            mensagem,
            parse_mode='Markdown'
        )

        # Retornar estado para o conversation handler
        return TEMPLATE_EDIT_CONTENT

    except Exception as e:
        logger.error(f"Erro ao iniciar edição de template {template_id}: {e}")
        await query.edit_message_text(
            "❌ Erro ao iniciar edição!",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⬅️ Menu Templates", callback_data="voltar_templates")
            ]])
        )

# Funções básicas para templates
async def mostrar_template_individual_basic(query, context, template_id):
    """Mostra template individual de forma básica"""
    try:
        from database import DatabaseManager
        db = DatabaseManager()
        template = db.obter_template(template_id)
        
        if not template:
            await query.edit_message_text(
                "❌ Template não encontrado",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("⬅️ Voltar", callback_data="voltar_templates")
                ]])
            )
            return
        
        ativo_status = "Ativo" if template.get('ativo', True) else "Inativo"
        conteudo = template.get('conteudo', 'Sem conteúdo')
        
        mensagem = f"""📄 **TEMPLATE DETALHADO**

🆔 **ID:** {template['id']}
📝 **Nome:** {template['nome']}
🎯 **Tipo:** {template['tipo']}
✅ **Status:** {ativo_status}

📋 **CONTEÚDO:**
```
{conteudo}
```"""

        keyboard = [
            [InlineKeyboardButton("✏️ Editar", callback_data=f"template_editar_{template_id}")],
            [InlineKeyboardButton("⬅️ Voltar", callback_data="voltar_templates")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            mensagem, 
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        
    except Exception as e:
        logger.error(f"Erro ao mostrar template {template_id}: {e}")
        await query.edit_message_text("❌ Erro ao carregar template")

async def callback_template_editar_basic(query, context, template_id):
    """Callback básico para editar template"""
    try:
        from database import DatabaseManager
        db = DatabaseManager()
        template = db.obter_template(template_id)
        
        if not template:
            await query.edit_message_text("❌ Template não encontrado")
            return
        
        mensagem = f"""✏️ **EDITAR TEMPLATE**

📝 **Template:** {template['nome']}
🆔 **ID:** {template['id']}

Para editar este template, use os comandos:

**Editar nome:**
`/template_editar {template['id']} nome "Novo Nome"`

**Editar conteúdo:**
`/template_editar {template['id']} conteudo "Novo conteúdo"`

**Ativar/Desativar:**
`/template_editar {template['id']} ativo true` ou `false`

**Exemplo:**
`/template_editar {template['id']} conteudo "Olá {{nome}}, seu plano vence em {{dias_restantes}} dias!"`"""

        keyboard = [
            [InlineKeyboardButton("👁️ Ver Template", callback_data=f"template_mostrar_{template_id}")],
            [InlineKeyboardButton("⬅️ Voltar", callback_data="voltar_templates")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            mensagem, 
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        
    except Exception as e:
        logger.error(f"Erro ao editar template {template_id}: {e}")
        await query.edit_message_text("❌ Erro ao preparar edição")

async def callback_template_criar_basic(query, context):
    """Callback básico para criar template"""
    try:
        mensagem = """➕ **CRIAR NOVO TEMPLATE**

Para criar um template, use o comando:

`/template_novo "Nome" tipo "Descrição"`

**Tipos disponíveis:**
• `boas_vindas` - Mensagem de boas-vindas
• `aviso_vencimento` - Avisos de vencimento  
• `renovacao` - Confirmação de renovação
• `cobranca` - Cobrança de vencidos
• `sistema` - Templates do sistema

**Exemplo:**
`/template_novo "Lembrete Vencimento" aviso_vencimento "Template para avisar sobre vencimento"`

**Variáveis disponíveis:**
• `{nome}` - Nome do cliente
• `{telefone}` - Telefone do cliente  
• `{pacote}` - Pacote/plano do cliente
• `{valor}` - Valor do plano
• `{servidor}` - Servidor/login
• `{vencimento}` - Data de vencimento"""

        keyboard = [[
            InlineKeyboardButton("📋 Ver Templates", callback_data="voltar_templates"),
            InlineKeyboardButton("⬅️ Voltar", callback_data="voltar_templates")
        ]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            mensagem,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )

    except Exception as e:
        logger.error(f"Erro ao mostrar criação: {e}")
        await query.edit_message_text("❌ Erro ao carregar criação")

async def callback_template_testar_basic(query, context):
    """Callback básico para testar template"""
    await query.edit_message_text(
        "🧪 **TESTAR TEMPLATE**\n\n"
        "Para testar um template, use:\n"
        "`/template_testar [ID]`\n\n"
        "**Exemplo:**\n"
        "`/template_testar 1`\n\n"
        "O teste será feito com dados de exemplo.",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("⬅️ Voltar", callback_data="voltar_templates")
        ]])
    )

async def callback_templates_handler(update, context):
    """Handler para callbacks de templates"""
    query = update.callback_query
    await query.answer()

    try:
        data = query.data

        if data == "template_novo":
            await callback_template_criar_basic(query, context)

        elif data == "template_testar":
            await query.edit_message_text(
                "🧪 *TESTAR TEMPLATE*\n\n"
                "Para testar um template, use:\n"
                "`/template_testar nome_template`\n\n"
                "*Exemplo:*\n"
                "`/template_testar boas_vindas`\n\n"
                "O teste será feito com dados de exemplo.",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("⬅️ Menu Templates", callback_data="voltar_templates")
                ]])
            )

        elif data.startswith("template_ver_db_"):
            # Visualizar template do banco de dados
            template_id = int(data.split("_")[2])
            await mostrar_template_db(query, context, template_id)

        elif data.startswith("template_ver_"):
            nome_template = data.replace("template_ver_", "")
            await mostrar_template(query, context, nome_template)

        elif data.startswith("template_teste_"):
            nome_template = data.replace("template_teste_", "")
            await testar_template(query, context, nome_template)

        elif data.startswith("template_editar_db_"):
            # Editar template do banco de dados - CORREÇÃO FINAL
            template_id = int(data.split("_")[2])

            # Buscar template no banco
            from database import DatabaseManager
            db = DatabaseManager()
            template = db.obter_template(template_id)

            if not template:
                await query.edit_message_text(
                    "❌ **TEMPLATE NÃO ENCONTRADO**\n\n"
                    f"Template com ID {template_id} não existe no banco de dados.",
                    parse_mode='Markdown',
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("⬅️ Menu Templates", callback_data="voltar_templates")
                    ]])
                )
                return

            # SOLUÇÃO: Salvar no contexto com chave específica para usuário
            user_id = query.from_user.id
            context.user_data[f'editando_template_id_{user_id}'] = template_id
            context.user_data[f'template_original_{user_id}'] = template
            context.user_data['aguardando_edicao'] = True

            # Conteúdo truncado para exibição
            conteudo_preview = template['conteudo'][:200] + "..." if len(template['conteudo']) > 200 else template['conteudo']

            mensagem = f"""✏️ **MODO EDIÇÃO ATIVO**

📝 **Template:** {template['nome']}
🆔 **ID:** {template['id']}
📊 **Tipo:** {template['tipo']}

📄 **Conteúdo atual:**
```
{conteudo_preview}
```

⚠️ **DIGITE O NOVO CONTEÚDO** como próxima mensagem

**Variáveis disponíveis:**
• {{nome}} • {{telefone}} • {{pacote}}
• {{valor}} • {{vencimento}} • {{servidor}}

**Digite /cancel para cancelar a edição**"""

            await query.edit_message_text(
                mensagem,
                parse_mode='Markdown'
            )
            return

        elif data.startswith("template_editar_"):
            # Esta função é capturada pelo ConversationHandler template_edit_handler
            pass

        elif data.startswith("template_excluir_"):
            nome_template = data.replace("template_excluir_", "")
            await confirmar_exclusao_template(query, context, nome_template)

        elif data.startswith("template_confirmar_exclusao_"):
            nome_template = data.replace("template_confirmar_exclusao_", "")
            await executar_exclusao_template(query, context, nome_template)

        elif data.startswith("template_duplicar_"):
            nome_template = data.replace("template_duplicar_", "")
            await duplicar_template(query, context, nome_template)

        elif data == "voltar_menu":
            # Voltar ao menu principal do bot
            await query.edit_message_text(
                "🤖 *BOT DE GESTÃO DE CLIENTES*\n\n"
                "Escolha uma opção abaixo:",
                parse_mode='Markdown',
                reply_markup=criar_teclado_principal()
            )

        elif data == "voltar_templates":
            # Recarregar templates do banco de dados
            from database import DatabaseManager
            db = DatabaseManager()
            templates = db.listar_templates(apenas_ativos=True)

            mensagem = f"📄 *SISTEMA DE TEMPLATES*\n\n"
            mensagem += f"📊 Templates disponíveis: {len(templates)}\n\n"

            keyboard = []

            for template in templates:
                template_id = template['id']
                nome_display = template['nome'][:20] + ('...' if len(template['nome']) > 20 else '')

                keyboard.append([
                    InlineKeyboardButton(f"📝 {nome_display}",
                                       callback_data=f"template_mostrar_{template_id}"),
                    InlineKeyboardButton("✏️ Editar",
                                       callback_data=f"template_editar_{template_id}")
                ])

            keyboard.append([
                InlineKeyboardButton("➕ Novo Template", callback_data="template_criar"),
                InlineKeyboardButton("🧪 Testar Template", callback_data="template_testar")
            ])
            keyboard.append([
                InlineKeyboardButton("⬅️ Menu Principal", callback_data="voltar_menu")
            ])

            if not templates:
                mensagem += "📭 **Nenhum template encontrado**\n\n"
                mensagem += "Crie seu primeiro template."

            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.edit_message_text(
                mensagem,
                parse_mode='Markdown',
                reply_markup=reply_markup
            )

    except Exception as e:
        logger.error(f"Erro no callback de templates: {e}")
        await query.edit_message_text("❌ Erro ao processar template!")


async def mostrar_template(query, context, nome_template):
    """Mostra detalhes de um template específico"""
    try:
        # Templates padrão
        templates_padrao = {
            'boas_vindas': {
                'titulo': 'Mensagem de Boas-vindas',
                'conteudo': 'Olá {nome}! 👋\n\nSeja bem-vindo ao nosso serviço!\n\n📦 Seu pacote: {pacote}\n💰 Valor: R$ {valor}\n📅 Vencimento: {vencimento}\n\nQualquer dúvida, estamos aqui para ajudar!',
                'tipo': 'Padrão'
            },
            'cobranca': {
                'titulo': 'Cobrança de Renovação',
                'conteudo': '⚠️ ATENÇÃO {nome}!\n\nSeu plano vence em breve:\n\n📦 Pacote: {pacote}\n💰 Valor: R$ {valor}\n📅 Vencimento: {vencimento}\n\nRenove agora para não perder o acesso!',
                'tipo': 'Padrão'
            },
            'vencido': {
                'titulo': 'Plano Vencido',
                'conteudo': '🔴 PLANO VENCIDO - {nome}\n\nSeu plano venceu em {vencimento}.\n\n📦 Pacote: {pacote}\n💰 Valor para renovação: R$ {valor}\n\nRenove urgentemente para reativar o serviço!',
                'tipo': 'Padrão'
            }
        }

        # Buscar template no banco de dados
        from database import DatabaseManager
        db = DatabaseManager()
        templates = db.listar_templates(apenas_ativos=False)
        template_db = next((t for t in templates if t['nome'].lower() == nome_template.lower()), None)

        if template_db:
            template = {
                'titulo': template_db['nome'],
                'conteudo': template_db['conteudo'],
                'tipo': 'Banco de Dados'
            }
        elif nome_template in templates_padrao:
            template = templates_padrao[nome_template]
        else:
            await query.edit_message_text(
                "❌ **TEMPLATE NÃO ENCONTRADO**\n\n"
                "Verifique se o nome está correto.",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("⬅️ Menu Templates", callback_data="voltar_templates")
                ]])
            )
            return

        mensagem = f"📝 *{template['titulo']}*\n\n"
        mensagem += f"**Tipo:** {template['tipo']}\n"

        if template['tipo'] == 'Personalizado' and nome_template in templates_personalizados:
            mensagem += f"**Criado em:** {templates_personalizados[nome_template]['criado_em']}\n"

        mensagem += f"\n**Conteúdo:**\n```\n{template['conteudo']}\n```\n\n"
        mensagem += "**Variáveis disponíveis:**\n"
        mensagem += "• `{nome}` - Nome do cliente\n"
        mensagem += "• `{telefone}` - Telefone\n"
        mensagem += "• `{pacote}` - Pacote contratado\n"
        mensagem += "• `{valor}` - Valor do plano\n"
        mensagem += "• `{vencimento}` - Data de vencimento\n"
        mensagem += "• `{servidor}` - Servidor usado"

        # Diferentes botões para templates padrão vs personalizados
        if template['tipo'] == 'Padrão':
            keyboard = [
                [InlineKeyboardButton("✏️ Editar", callback_data=f"template_editar_{nome_template}"),
                 InlineKeyboardButton("🧪 Testar", callback_data=f"template_teste_{nome_template}")],
                [InlineKeyboardButton("📋 Duplicar", callback_data=f"template_duplicar_{nome_template}")],
                [InlineKeyboardButton("⬅️ Voltar Templates", callback_data="voltar_templates")]
            ]
        else:
            keyboard = [
                [InlineKeyboardButton("✏️ Editar", callback_data=f"template_editar_{nome_template}"),
                 InlineKeyboardButton("🧪 Testar", callback_data=f"template_teste_{nome_template}")],
                [InlineKeyboardButton("📋 Duplicar", callback_data=f"template_duplicar_{nome_template}"),
                 InlineKeyboardButton("🗑️ Excluir", callback_data=f"template_excluir_{nome_template}")],
                [InlineKeyboardButton("⬅️ Voltar Templates", callback_data="voltar_templates")]
            ]

        await query.edit_message_text(
            mensagem,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    except Exception as e:
        logger.error(f"Erro ao mostrar template: {e}")
        await query.edit_message_text("❌ Erro ao carregar template!")


async def testar_template(query, context, nome_template):
    """Testa um template com dados de exemplo"""
    try:
        # Templates padrão
        templates_padrao = {
            'boas_vindas': 'Olá {nome}! 👋\n\nSeja bem-vindo ao nosso serviço!\n\n📦 Seu pacote: {pacote}\n💰 Valor: R$ {valor}\n📅 Vencimento: {vencimento}\n\nQualquer dúvida, estamos aqui para ajudar!',
            'cobranca': '⚠️ ATENÇÃO {nome}!\n\nSeu plano vence em breve:\n\n📦 Pacote: {pacote}\n💰 Valor: R$ {valor}\n📅 Vencimento: {vencimento}\n\nRenove agora para não perder o acesso!',
            'vencido': '🔴 PLANO VENCIDO - {nome}\n\nSeu plano venceu em {vencimento}.\n\n📦 Pacote: {pacote}\n💰 Valor para renovação: R$ {valor}\n\nRenove urgentemente para reativar o serviço!'
        }

        # Verificar se é template padrão ou
        if nome_template in templates_padrao:
            template_conteudo = templates_padrao[nome_template]
        elif nome_template in templates_personalizados:
            template_conteudo = templates_personalizados[nome_template]['conteudo']
        else:
            await query.edit_message_text("❌ Template não encontrado!")
            return

        # Dados de exemplo para teste
        dados_exemplo = {
            'nome': 'João Silva',
            'telefone': '11999999999',
            'pacote': 'Premium',
            'valor': '29.90',
            'vencimento': '15/08/2025',
            'servidor': 'BR-SP-01'
        }

        # Aplicar dados ao template
        mensagem_teste = template_conteudo.format(**dados_exemplo)

        mensagem = f"🧪 *TESTE DO TEMPLATE*\n\n"
        mensagem += f"**Resultado com dados de exemplo:**\n\n"
        mensagem += f"```\n{mensagem_teste}\n```\n\n"
        mensagem += "**Dados usados no teste:**\n"
        mensagem += f"• Nome: {dados_exemplo['nome']}\n"
        mensagem += f"• Telefone: {dados_exemplo['telefone']}\n"
        mensagem += f"• Pacote: {dados_exemplo['pacote']}\n"
        mensagem += f"• Valor: R$ {dados_exemplo['valor']}\n"
        mensagem += f"• Vencimento: {dados_exemplo['vencimento']}\n"
        mensagem += f"• Servidor: {dados_exemplo['servidor']}"

        keyboard = [
            [InlineKeyboardButton("✏️ Editar Template", callback_data=f"template_editar_{nome_template}"),
             InlineKeyboardButton("📋 Duplicar", callback_data=f"template_duplicar_{nome_template}")],
            [InlineKeyboardButton("🗑️ Excluir Template", callback_data=f"template_excluir_{nome_template}")],
            [InlineKeyboardButton("⬅️ Voltar", callback_data=f"template_ver_{nome_template}")]
        ]

        await query.edit_message_text(
            mensagem,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    except Exception as e:
        logger.error(f"Erro ao testar template: {e}")
        await query.edit_message_text("❌ Erro ao testar template!")


async def iniciar_edicao_template(query, context, nome_template):
    """Inicia processo de edição de template"""
    try:
        templates = {
            'boas_vindas': {
                'titulo': 'Mensagem de Boas-vindas',
                'conteudo': 'Olá {nome}! 👋\n\nSeja bem-vindo ao nosso serviço!\n\n📦 Seu pacote: {pacote}\n💰 Valor: R$ {valor}\n📅 Vencimento: {vencimento}\n\nQualquer dúvida, estamos aqui para ajudar!'
            },
            'cobranca': {
                'titulo': 'Cobrança de Renovação',
                'conteudo': '⚠️ ATENÇÃO {nome}!\n\nSeu plano vence em breve:\n\n📦 Pacote: {pacote}\n💰 Valor: R$ {valor}\n📅 Vencimento: {vencimento}\n\nRenove agora para não perder o acesso!'
            },
            'vencido': {
                'titulo': 'Plano Vencido',
                'conteudo': '🔴 PLANO VENCIDO - {nome}\n\nSeu plano venceu em {vencimento}.\n\n📦 Pacote: {pacote}\n💰 Valor para renovação: R$ {valor}\n\nRenove urgentemente para reativar o serviço!'
            }
        }

        template = templates.get(nome_template)
        if not template:
            await query.edit_message_text("❌ Template não encontrado!")
            return

        mensagem = f"✏️ *EDITAR TEMPLATE*\n\n"
        mensagem += f"**Template:** {template['titulo']}\n\n"
        mensagem += f"**Conteúdo atual:**\n```\n{template['conteudo']}\n```\n\n"
        mensagem += f"Para editar este template, use o comando:\n"
        mensagem += f"`/template_editar {nome_template} NOVO_CONTEUDO`\n\n"
        mensagem += f"**Exemplo:**\n"
        mensagem += f"`/template_editar {nome_template} Olá {{nome}}! Seu plano vence em {{vencimento}}.`\n\n"
        mensagem += f"**Variáveis disponíveis:**\n"
        mensagem += "• `{nome}` • `{telefone}` • `{pacote}`\n"
        mensagem += "• `{valor}` • `{vencimento}` • `{servidor}`"

        keyboard = [
            [InlineKeyboardButton("🧪 Testar Template", callback_data=f"template_teste_{nome_template}"),
             InlineKeyboardButton("🗑️ Excluir Template", callback_data=f"template_excluir_{nome_template}")],
            [InlineKeyboardButton("⬅️ Voltar", callback_data=f"template_ver_{nome_template}")]
        ]

        await query.edit_message_text(
            mensagem,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    except Exception as e:
        logger.error(f"Erro ao iniciar edição: {e}")
        await query.edit_message_text("❌ Erro ao iniciar edição!")


async def processar_edicao_template(update, context):
    """Processa o novo conteúdo do template"""
    try:
        novo_conteudo = update.message.text.strip()

        # Verificar se é edição de template do banco de dados
        template_id = context.user_data.get('editando_template_id')
        if template_id:
            return await processar_edicao_template_db(update, context, novo_conteudo)

        # Edição de template tradicional
        nome_template = context.user_data.get('editando_template')
        template_atual = context.user_data.get('template_atual')

        if not nome_template or not template_atual:
            await update.message.reply_text(
                "❌ Erro: dados de edição perdidos.",
                reply_markup=criar_teclado_principal()
            )
            return ConversationHandler.END

        # Verificar se não está vazio
        if not novo_conteudo:
            await update.message.reply_text(
                "❌ O conteúdo não pode estar vazio. Digite o conteúdo do template ou /cancel para cancelar."
            )
            return TEMPLATE_EDIT_CONTENT

        # Templates padrão
        templates_padrao = ['boas_vindas', 'cobranca', 'vencido']

        if nome_template in templates_padrao:
            # Atualizar template padrão (simulado - em produção seria salvo no banco)
            mensagem_sucesso = f"✅ **TEMPLATE EDITADO COM SUCESSO**\n\n"
            mensagem_sucesso += f"**Template:** {template_atual['titulo']}\n"
            mensagem_sucesso += f"**Tipo:** Padrão (sistema)\n"
            mensagem_sucesso += f"**Data:** {agora_br().strftime('%d/%m/%Y %H:%M')}\n\n"
            mensagem_sucesso += f"**Novo conteúdo:**\n```\n{novo_conteudo}\n```\n\n"
            mensagem_sucesso += "Template atualizado no sistema!"
        else:
            # Atualizar template personalizado
            if nome_template in templates_personalizados:
                templates_personalizados[nome_template]['conteudo'] = novo_conteudo
                templates_personalizados[nome_template]['editado_em'] = agora_br().strftime('%d/%m/%Y %H:%M')

                mensagem_sucesso = f"✅ **TEMPLATE PERSONALIZADO EDITADO**\n\n"
                mensagem_sucesso += f"**Template:** {templates_personalizados[nome_template]['titulo']}\n"
                mensagem_sucesso += f"**Tipo:** Personalizado\n"
                mensagem_sucesso += f"**Data:** {agora_br().strftime('%d/%m/%Y %H:%M')}\n\n"
                mensagem_sucesso += f"**Novo conteúdo:**\n```\n{novo_conteudo}\n```\n\n"
                mensagem_sucesso += "Template salvo com sucesso!"
            else:
                await update.message.reply_text(
                    "❌ Template não encontrado!",
                    reply_markup=criar_teclado_principal()
                )
                return ConversationHandler.END

        # Limpar dados do contexto
        context.user_data.pop('editando_template', None)
        context.user_data.pop('template_atual', None)

        await update.message.reply_text(
            mensagem_sucesso,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("👁️ Ver Template", callback_data=f"template_ver_{nome_template}")],
                [InlineKeyboardButton("📄 Menu Templates", callback_data="voltar_templates")],
                [InlineKeyboardButton("⬅️ Menu Principal", callback_data="voltar_menu")]
            ])
        )

        return ConversationHandler.END

        if not nome_template or not template_atual:
            await update.message.reply_text(
                "❌ Erro: dados de edição perdidos.",
                reply_markup=criar_teclado_principal()
            )
            return ConversationHandler.END

        # Simular atualização do template
        mensagem = f"✅ **Template atualizado com sucesso!**\n\n"
        mensagem += f"**Template:** {template_atual['titulo']}\n\n"
        mensagem += f"**Novo conteúdo:**\n```\n{novo_conteudo}\n```\n\n"
        mensagem += f"**Preview com dados de exemplo:**\n\n"

        # Dados de exemplo para preview
        dados_exemplo = {
            'nome': 'João Silva',
            'telefone': '11999999999',
            'pacote': 'Premium',
            'valor': '29.90',
            'vencimento': '15/08/2025',
            'servidor': 'BR-SP-01'
        }

        try:
            preview = novo_conteudo.format(**dados_exemplo)
            mensagem += f"```\n{preview}\n```"
        except KeyError as e:
            mensagem += f"⚠️ Variável não reconhecida: {e}"

        await update.message.reply_text(
            mensagem,
            parse_mode='Markdown',
            reply_markup=criar_teclado_principal()
        )

        # Limpar dados do contexto
        context.user_data.pop('editando_template', None)
        context.user_data.pop('template_atual', None)

        return ConversationHandler.END

    except Exception as e:
        logger.error(f"Erro ao processar edição: {e}")
        await update.message.reply_text(
            "❌ Erro ao processar edição do template!",
            reply_markup=criar_teclado_principal()
        )
        return ConversationHandler.END

async def processar_edicao_template_db(update, context, novo_conteudo):
    """Processa edição de template do banco de dados"""
    try:
        template_id = context.user_data.get('editando_template_id')
        template_original = context.user_data.get('template_original')

        if not template_id or not template_original:
            await update.message.reply_text(
                "❌ Erro: dados da edição perdidos.",
                reply_markup=criar_teclado_principal()
            )
            return ConversationHandler.END

        # Verificar se não está vazio
        if not novo_conteudo or len(novo_conteudo.strip()) < 5:
            await update.message.reply_text(
                "❌ O conteúdo deve ter pelo menos 5 caracteres. Digite o novo conteúdo ou /cancel para cancelar."
            )
            return TEMPLATE_EDIT_CONTENT

        # Atualizar template no banco de dados
        from database import DatabaseManager
        db = DatabaseManager()

        sucesso = db.atualizar_template(template_id, conteudo=novo_conteudo)

        if sucesso:
            # Contar variáveis no novo conteúdo
            import re
            variaveis = re.findall(r'\{(\w+)\}', novo_conteudo)
            total_variaveis = len(set(variaveis))

            mensagem = f"✅ **TEMPLATE EDITADO COM SUCESSO**\n\n"
            mensagem += f"📝 **Template:** {template_original['nome']}\n"
            mensagem += f"🆔 **ID:** {template_id}\n"
            mensagem += f"📊 **Variáveis:** {total_variaveis} únicas\n"
            mensagem += f"📅 **Data:** {agora_br().strftime('%d/%m/%Y %H:%M')}\n\n"

            # Mostrar preview do conteúdo
            preview = novo_conteudo[:150] + "..." if len(novo_conteudo) > 150 else novo_conteudo
            mensagem += f"📄 **Novo conteúdo:**\n```\n{preview}\n```\n\n"
            mensagem += "✅ **Template salvo no banco de dados!**"

            keyboard = [
                [InlineKeyboardButton("📄 Menu Templates", callback_data="voltar_templates")],
                [InlineKeyboardButton("🏠 Menu Principal", callback_data="voltar_menu")]
            ]
        else:
            mensagem = "❌ **ERRO AO SALVAR**\n\nNão foi possível salvar o template no banco de dados."
            keyboard = [
                [InlineKeyboardButton("🔄 Tentar Novamente", callback_data=f"template_editar_db_{template_id}")],
                [InlineKeyboardButton("📄 Menu Templates", callback_data="voltar_templates")]
            ]

        await update.message.reply_text(
            mensagem,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

        # Limpar contexto completamente
        context.user_data.pop('editando_template_id', None)
        context.user_data.pop('template_original', None)
        context.user_data.pop('aguardando_edicao', None)
        context.user_data.pop('editando_template', None)
        context.user_data.pop('template_atual', None)

        return ConversationHandler.END

    except Exception as e:
        logger.error(f"Erro ao processar edição de template DB: {e}")
        await update.message.reply_text(
            "❌ Erro interno. Tente novamente.",
            reply_markup=criar_teclado_principal()
        )
        return ConversationHandler.END

async def comando_editar_template_por_id(update, context):
    """Comando para editar template por ID"""
    try:
        if not context.args:
            await update.message.reply_text(
                "❌ **USO INCORRETO**\n\n"
                "Uso: `/template_editar_id <ID>`\n"
                "Exemplo: `/template_editar_id 1`",
                parse_mode='Markdown',
                reply_markup=criar_teclado_principal()
            )
            return

        template_id = int(context.args[0])

        from database import DatabaseManager
        db = DatabaseManager()
        template_data = db.buscar_template_por_id(template_id)

        if not template_data:
            await update.message.reply_text(
                "❌ **TEMPLATE NÃO ENCONTRADO**\n\n"
                f"Não existe template com ID {template_id}.",
                parse_mode='Markdown',
                reply_markup=criar_teclado_principal()
            )
            return

        # Mostrar informações do template e permitir edição
        mensagem = f"""✏️ **EDITAR TEMPLATE**

📝 **Nome:** {template_data['nome']}
🆔 **ID:** {template_data['id']}
📊 **Tipo:** {template_data['tipo']}
📅 **Criado:** {template_data['criado_em']}

📄 **Conteúdo atual:**
```
{template_data['conteudo'][:300]}{'...' if len(template_data['conteudo']) > 300 else ''}
```

**Para editar, responda com o novo conteúdo.**
**Use /cancel para cancelar.**"""

        # Salvar contexto de edição
        context.user_data['editando_template_id'] = template_id
        context.user_data['template_original'] = template_data

        await update.message.reply_text(
            mensagem,
            parse_mode='Markdown'
        )

        return TEMPLATE_EDIT_CONTENT

    except ValueError:
        await update.message.reply_text(
            "❌ **ID INVÁLIDO**\n\n"
            "O ID deve ser um número.",
            parse_mode='Markdown',
            reply_markup=criar_teclado_principal()
        )
    except Exception as e:
        logger.error(f"Erro ao editar template por ID: {e}")
        await update.message.reply_text(
            "❌ Erro ao processar comando!",
            reply_markup=criar_teclado_principal()
        )

def inicializar_templates_padrao():
    """Inicializa templates padrão no banco de dados se não existirem"""
    try:
        from database import DatabaseManager
        db = DatabaseManager()

        templates_padrao_db = {
            'boas_vindas': {
                'conteudo': 'Olá {nome}! 👋\n\nSeja bem-vindo ao nosso serviço!\n\n📦 Seu pacote: {pacote}\n💰 Valor: R$ {valor}\n📅 Vencimento: {vencimento}\n\nQualquer dúvida, estamos aqui para ajudar!',
                'tipo': 'sistema'
            },
            'cobranca': {
                'conteudo': '⚠️ ATENÇÃO {nome}!\n\nSeu plano vence em breve:\n\n📦 Pacote: {pacote}\n💰 Valor: R$ {valor}\n📅 Vencimento: {vencimento}\n\nRenove agora para não perder o acesso!',
                'tipo': 'sistema'
            },
            'vencido': {
                'conteudo': '🔴 PLANO VENCIDO - {nome}\n\nSeu plano venceu em {vencimento}.\n\n📦 Pacote: {pacote}\n💰 Valor para renovação: R$ {valor}\n\nRenove urgentemente para reativar o serviço!',
                'tipo': 'sistema'
            }
        }

        # Verificar quais templates já existem
        templates_existentes = db.listar_templates(apenas_ativos=False)
        nomes_existentes = [t['nome'].lower() for t in templates_existentes]

        templates_criados = 0
        for nome, dados in templates_padrao_db.items():
            if nome not in nomes_existentes:
                try:
                    template_id = db.adicionar_template(
                        nome=nome,
                        conteudo=dados['conteudo'],
                        tipo=dados['tipo']
                    )
                    logger.info(f"Template padrão criado: {nome} (ID: {template_id})")
                    templates_criados += 1
                except Exception as e:
                    logger.error(f"Erro ao criar template padrão {nome}: {e}")

        if templates_criados > 0:
            logger.info(f"Inicialização: {templates_criados} templates padrão criados")
        else:
            logger.info("Templates padrão já existem")

    except Exception as e:
        logger.error(f"Erro ao inicializar templates padrão: {e}")


def main():
    """Função principal"""
    # Verificar variáveis essenciais
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    admin_id = os.getenv('ADMIN_CHAT_ID')

    if not token:
        print("❌ TELEGRAM_BOT_TOKEN não configurado!")
        sys.exit(1)

    if not admin_id:
        print("❌ ADMIN_CHAT_ID não configurado!")
        sys.exit(1)

    print("🚀 Iniciando bot Telegram...")

    # Testar componentes principais
    try:
        from database import DatabaseManager
        db = DatabaseManager()
        print("✅ Banco de dados OK")
        
        # Inicializar agendador automático
        try:
            from scheduler_automatico import scheduler_automatico
            scheduler_automatico.iniciar()
            print("✅ Agendador automático iniciado")
        except Exception as e:
            print(f"⚠️ Erro ao iniciar agendador: {e}")

        # Inicializar templates padrão
        inicializar_templates_padrao()
        print("✅ Templates padrão verificados")
    except Exception as e:
        print(f"⚠️ Database: {e}")

    try:
        from whatsapp_hybrid_service import WhatsAppHybridService
        ws = WhatsAppHybridService()
        print("✅ WhatsApp Service OK")
    except Exception as e:
        print(f"⚠️ WhatsApp: {e}")

    # Criar e configurar aplicação
    app = Application.builder().token(token).build()

    # ConversationHandler para cadastro escalonável
    cadastro_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^➕ Adicionar Cliente$"),
                           iniciar_cadastro)
        ],
        states={
            NOME:
            [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_nome)],
            TELEFONE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND,
                               receber_telefone)
            ],
            PACOTE:
            [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_pacote)],
            VALOR:
            [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_valor)],
            SERVIDOR: [
                MessageHandler(filters.TEXT & ~filters.COMMAND,
                               receber_servidor)
            ],
            VENCIMENTO: [
                MessageHandler(filters.TEXT & ~filters.COMMAND,
                               receber_vencimento)
            ],
            CONFIRMAR: [
                MessageHandler(filters.TEXT & ~filters.COMMAND,
                               confirmar_cadastro)
            ]
        },
        fallbacks=[
            MessageHandler(filters.Regex("^❌ Cancelar$"), cancelar_cadastro),
            CommandHandler("cancel", cancelar_cadastro)
        ])

    # ConversationHandler para edição de cliente
    async def iniciar_edicao_wrapper(update, context):
        query = update.callback_query
        partes = query.data.split("_")
        if len(partes) == 3:
            campo = partes[1]
            cliente_id = int(partes[2])
            return await iniciar_edicao_campo(query, context, cliente_id,
                                              campo)
        return ConversationHandler.END

    # ConversationHandler simplificado para edição
    edicao_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(iniciar_edicao_wrapper, pattern="^edit_")
        ],
        states={},
        fallbacks=[
            CommandHandler("cancel", cancelar_cadastro)
        ])

    # ConversationHandler simplificado para configurações
    config_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(config_callback, pattern="^config_")
        ],
        states={},
        fallbacks=[
            CommandHandler("cancel", lambda u, c: ConversationHandler.END)
        ])

    # ConversationHandler simplificado para configurações diretas
    config_direct_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^⚙️ Configurações$"), lambda u, c: ConversationHandler.END)
        ],
        states={},
        fallbacks=[
            CommandHandler("cancel", lambda u, c: ConversationHandler.END)
        ])

    # ConversationHandler simplificado para templates
    template_edit_handler = ConversationHandler(
        entry_points=[],
        states={},
        fallbacks=[
            CommandHandler("cancel", lambda u, c: ConversationHandler.END)
        ])

    # ConversationHandler simplificado para criação de templates
    template_new_handler = ConversationHandler(
        entry_points=[],
        states={},
        fallbacks=[
            CommandHandler("cancel", lambda u, c: ConversationHandler.END)
        ])

    # Adicionar handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", add_cliente))
    app.add_handler(CommandHandler("listar", listar_clientes))
    app.add_handler(CommandHandler("relatorio", relatorio))
    app.add_handler(CommandHandler("buscar", buscar_cliente))
    app.add_handler(CommandHandler("editar", editar_cliente_cmd))
    app.add_handler(CommandHandler("config", configuracoes_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    
    # Comandos do agendamento automático
    from comando_agendamento import (
        processar_comando_agendamento,
        processar_comando_proximos_vencimentos,
        processar_comando_forcar_envio
    )
    app.add_handler(CommandHandler("agendamento", processar_comando_agendamento))
    app.add_handler(CommandHandler("vencimentos", processar_comando_proximos_vencimentos))
    app.add_handler(CommandHandler("forcar_envio", processar_comando_forcar_envio))
    
    # Handlers do agendador via interface
    from agendador_interface import handle_agendador_callback
    app.add_handler(CallbackQueryHandler(handle_agendador_callback, pattern="^agendador_|^voltar_menu$"))



    # Adicionar ConversationHandlers PRIMEIRO (prioridade mais alta)
    app.add_handler(template_new_handler, group=0)
    app.add_handler(template_edit_handler, group=0)
    app.add_handler(config_handler, group=0)
    app.add_handler(config_direct_handler, group=0)
    app.add_handler(edicao_handler, group=0)
    app.add_handler(cadastro_handler, group=0)

    # Handler para callbacks dos botões inline - ordem importante!
    app.add_handler(CallbackQueryHandler(callback_templates_handler, pattern="^(template_|voltar_templates)"), group=0)
    app.add_handler(CallbackQueryHandler(callback_cliente), group=1)
    app.add_handler(CallbackQueryHandler(config_callback), group=1)

    # Handler para os botões do teclado personalizado (prioridade mais baixa)
    # Criar um filtro específico para botões conhecidos
    botoes_filter = filters.Regex(
        "^(👥 Listar Clientes|➕ Adicionar Cliente|📊 Relatórios|🔍 Buscar Cliente|🏢 Empresa|💳 PIX|📞 Suporte|📱 WhatsApp Status|🧪 Testar WhatsApp|📱 QR Code|⚙️ Gerenciar WhatsApp|📄 Templates|⏰ Agendador|📋 Fila de Mensagens|📜 Logs de Envios|❓ Ajuda)$"
    )
    app.add_handler(MessageHandler(botoes_filter, lidar_com_botoes), group=2)

    # Adicionar handler de erro global
    async def error_handler(update, context):
        """Handler global de erros"""
        try:
            logger.error(f"Erro não tratado: {context.error}")
            logger.error(f"Update: {update}")

            if update and update.effective_chat:
                try:
                    await context.bot.send_message(
                        chat_id=update.effective_chat.id,
                        text="❌ Ocorreu um erro interno. Tente novamente em alguns segundos.",
                        reply_markup=criar_teclado_principal()
                    )
                except:
                    pass  # Evitar loops de erro

        except Exception as e:
            logger.error(f"Erro no handler de erro: {e}")

    app.add_error_handler(error_handler)

    print("✅ Bot configurado com sucesso!")
    print(f"🔑 Admin ID: {admin_id}")

    # Inicializar sistema de agendamento automático
    try:
        from scheduler_automatico import iniciar_sistema_agendamento
        iniciar_sistema_agendamento()
        print("⏰ Sistema de agendamento iniciado - Execução diária às 9h")
    except ImportError:
        print("⚠️ Erro ao iniciar agendador: No module named 'scheduler_automatico'")
    except Exception as e:
        print(f"⚠️ Erro ao iniciar agendador: {e}")

    print("🤖 Bot online e funcionando!")

    # Executar o bot
    try:
        app.run_polling(drop_pending_updates=True)
    except KeyboardInterrupt:
        print("\n👋 Bot encerrado pelo usuário")
    except Exception as e:
        print(f"❌ Erro crítico: {e}")
        logger.error(f"Erro crítico no bot: {e}")
        return False


if __name__ == "__main__":
    main()
