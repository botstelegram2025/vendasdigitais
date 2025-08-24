"""Template management handlers for the Telegram bot"""

import logging
from datetime import datetime
from sqlalchemy import or_
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from services.database_service import db_service
from models import User, MessageTemplate

logger = logging.getLogger(__name__)

# ------------ Helpers -----------------

def _user_from_session(session, tg_user_id: int) -> User | None:
    return session.query(User).filter_by(telegram_id=str(tg_user_id)).first()

def _user_templates(session, user_id: int, active_only: bool = False):
    q = session.query(MessageTemplate).filter(MessageTemplate.user_id == user_id)
    if active_only:
        q = q.filter(MessageTemplate.is_active.is_(True))
    return q.order_by(MessageTemplate.name.asc()).all()

def _global_templates(session, active_only: bool = False):
    q = session.query(MessageTemplate).filter(MessageTemplate.user_id.is_(None))
    if active_only:
        q = q.filter(MessageTemplate.is_active.is_(True))
    return q.order_by(MessageTemplate.name.asc()).all()

def _get_template_with_fallback(session, user_id: int, template_id: int) -> MessageTemplate | None:
    """Busca template do usuário pelo id; se não for do usuário, tenta global com mesmo id."""
    tpl = session.query(MessageTemplate).filter_by(id=template_id, user_id=user_id).first()
    if tpl:
        return tpl
    # fallback: global com esse id (caso tenha vindo da lista de seleção que mostrou globais)
    return session.query(MessageTemplate).filter_by(id=template_id).filter(MessageTemplate.user_id.is_(None)).first()

# ------------ Handlers -----------------

async def templates_edit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mostra opções para editar (apenas templates do usuário)."""
    if not update.callback_query:
        return

    query = update.callback_query
    await query.answer()
    user = query.from_user

    try:
        with db_service.get_session() as session:
            db_user = _user_from_session(session, user.id)
            if not db_user or not db_user.is_active:
                await query.edit_message_text("❌ Conta inativa.")
                return

            with session.no_autoflush:
                templates = _user_templates(session, db_user.id, active_only=False)

            if not templates:
                await query.edit_message_text(
                    "❌ Nenhum template encontrado para sua conta.\n\n"
                    "Você pode criar um novo template ou importar um global.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("➕ Criar Template", callback_data="create_template_menu")],
                        [InlineKeyboardButton("📥 Importar Globais", callback_data="import_global_templates")],
                        [InlineKeyboardButton("🔙 Voltar", callback_data="templates_menu")],
                    ])
                )
                return

            text = "✏️ *Editar Template*\n\n📋 Selecione o template para editar:"
            keyboard = []
            for template in templates:
                status = "✅" if template.is_active else "❌"
                keyboard.append([
                    InlineKeyboardButton(
                        f"{status} {template.name}",
                        callback_data=f"edit_template_{template.id}"
                    )
                ])

            keyboard.append([InlineKeyboardButton("🔙 Voltar", callback_data="templates_menu")])
            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Error showing edit templates: {e}")
        await query.edit_message_text("❌ Erro ao carregar templates.")

async def templates_create_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menu de criação de templates (somente do usuário)."""
    if not update.callback_query:
        return

    query = update.callback_query
    await query.answer()

    text = """➕ *Criar Novo Template*

🔧 *Tipos disponíveis:*

📋 *Variáveis que você pode usar:*
• {nome} - Nome do cliente
• {plano} - Nome do plano
• {valor} - Valor em R$
• {vencimento} - Data de vencimento
• {servidor} - Servidor do cliente
• {informacoes_extras} - Informações extras

📝 *Escolha o tipo de template:*"""

    keyboard = [
        [InlineKeyboardButton("Boas-vindas", callback_data="create_template_welcome")],
        [InlineKeyboardButton("Lembrete 2 dias", callback_data="create_template_reminder_2_days")],
        [InlineKeyboardButton("Lembrete 1 dia", callback_data="create_template_reminder_1_day")],
        [InlineKeyboardButton("Vencimento hoje", callback_data="create_template_reminder_due_date")],
        [InlineKeyboardButton("Em atraso", callback_data="create_template_reminder_overdue")],
        [InlineKeyboardButton("Renovação", callback_data="create_template_renewal")],
        [InlineKeyboardButton("🔙 Voltar", callback_data="templates_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def show_template_selection_for_client(update: Update, context: ContextTypes.DEFAULT_TYPE, client_id: int):
    """Mostra templates ativos do usuário e, se não houver, inclui globais como fallback para envio."""
    query = update.callback_query
    user = query.from_user

    try:
        with db_service.get_session() as session:
            db_user = _user_from_session(session, user.id)
            if not db_user or not db_user.is_active:
                await query.edit_message_text("❌ Conta inativa.")
                return

            with session.no_autoflush:
                user_templates = _user_templates(session, db_user.id, active_only=True)
                global_templates = _global_templates(session, active_only=True) if not user_templates else []

            templates = user_templates or global_templates

            if not templates:
                await query.edit_message_text(
                    "❌ Nenhum template ativo encontrado.\n\nCrie templates primeiro!",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔙 Voltar", callback_data=f"view_client_{client_id}")]
                    ])
                )
                return

            prefix = "" if user_templates else "🌐 "
            text = "📱 *Enviar Mensagem*\n\n📋 Selecione o template para usar:"
            keyboard = []
            for template in templates:
                keyboard.append([
                    InlineKeyboardButton(
                        f"{prefix}📝 {template.name}",
                        callback_data=f"send_template_{template.id}_{client_id}"
                    )
                ])

            keyboard.append([InlineKeyboardButton("🔙 Voltar", callback_data=f"view_client_{client_id}")])
            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Error showing template selection: {e}")
        await query.edit_message_text("❌ Erro ao carregar templates.")

async def send_template_to_client_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Envia o template escolhido (prioriza do usuário; se não, usa global)."""
    if not update.callback_query:
        return

    query = update.callback_query
    await query.answer()
    user = query.from_user

    try:
        parts = query.data.split('_')
        template_id = int(parts[2])
        client_id = int(parts[3])

        with db_service.get_session() as session:
            from models import Client, MessageLog
            from services.whatsapp_service import whatsapp_service
            from main import replace_template_variables  # mantém seu helper

            db_user = _user_from_session(session, user.id)
            if not db_user or not db_user.is_active:
                await query.edit_message_text("❌ Conta inativa.")
                return

            with session.no_autoflush:
                # 1) tenta do usuário
                template = session.query(MessageTemplate).filter_by(
                    id=template_id, user_id=db_user.id
                ).first()
                # 2) fallback: global
                if not template:
                    template = session.query(MessageTemplate).filter(
                        MessageTemplate.id == template_id,
                        MessageTemplate.user_id.is_(None),
                        MessageTemplate.is_active.is_(True)
                    ).first()

                client = session.query(Client).filter_by(
                    id=client_id, user_id=db_user.id
                ).first()

            if not template or not client:
                await query.edit_message_text("❌ Template ou cliente não encontrado.")
                return

            message_content = replace_template_variables(template.content, client)
            result = whatsapp_service.send_message(client.phone_number, message_content)

            log = MessageLog(
                user_id=db_user.id,
                client_id=client.id,
                template_id=template.id,
                message_content=message_content,
                sent_at=datetime.utcnow(),
                status='sent' if result.get('success') else 'failed',
                error_message=None if result.get('success') else result.get('error', 'Unknown error')
            )
            session.add(log)
            session.commit()

            if result.get('success'):
                await query.edit_message_text(
                    f"✅ **Mensagem enviada com sucesso!**\n\n"
                    f"📱 **Cliente:** {client.name}\n"
                    f"📝 **Template:** {template.name}\n"
                    f"📞 **Número:** {client.phone_number}\n\n"
                    f"📄 **Mensagem enviada:**\n{message_content}",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔙 Voltar", callback_data=f"view_client_{client_id}")]
                    ]),
                    parse_mode='Markdown'
                )
            else:
                await query.edit_message_text(
                    f"❌ **Falha ao enviar mensagem**\n\n"
                    f"📱 **Cliente:** {client.name}\n"
                    f"📞 **Número:** {client.phone_number}\n"
                    f"❌ **Erro:** {result.get('error', 'Erro desconhecido')}\n\n"
                    f"🔧 Verifique se o WhatsApp está conectado.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔙 Voltar", callback_data=f"view_client_{client_id}")]
                    ]),
                    parse_mode='Markdown'
                )

    except Exception as e:
        logger.error(f"Error sending template message: {e}")
        await query.edit_message_text("❌ Erro ao enviar mensagem.")

async def edit_template_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Edição de um template (apenas do usuário)."""
    if not update.callback_query:
        return

    query = update.callback_query
    await query.answer()
    user = query.from_user

    try:
        template_id = int(query.data.split('_')[2])

        with db_service.get_session() as session:
            db_user = _user_from_session(session, user.id)
            if not db_user or not db_user.is_active:
                await query.edit_message_text("❌ Conta inativa.")
                return

            with session.no_autoflush:
                template = session.query(MessageTemplate).filter_by(
                    id=template_id, user_id=db_user.id
                ).first()

            if not template:
                await query.edit_message_text("❌ Template não encontrado (ou é global e não pode ser editado).")
                return

            status = "✅ Ativo" if template.is_active else "❌ Inativo"

            text = f"""✏️ *Editar Template*

📝 *Nome:* {template.name}
🏷️ *Tipo:* {template.template_type}
📊 *Status:* {status}

📄 *Conteúdo atual:*
{template.content}

🔧 *O que deseja fazer?*"""

            keyboard = [
                [InlineKeyboardButton("📝 Editar Conteúdo", callback_data=f"edit_content_{template.id}")],
                [InlineKeyboardButton("🔄 Ativar/Desativar", callback_data=f"toggle_template_{template.id}")],
                [InlineKeyboardButton("🗑️ Excluir Template", callback_data=f"delete_template_{template.id}")],
                [InlineKeyboardButton("🔙 Voltar", callback_data="templates_edit")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Error editing template: {e}")
        await query.edit_message_text("❌ Erro ao carregar template para edição.")

async def edit_content_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Edição do conteúdo (apenas do usuário)."""
    if not update.callback_query:
        return

    query = update.callback_query
    await query.answer()
    user = query.from_user

    try:
        template_id = int(query.data.split('_')[2])

        with db_service.get_session() as session:
            db_user = _user_from_session(session, user.id)
            if not db_user or not db_user.is_active:
                await query.edit_message_text("❌ Conta inativa.")
                return

            with session.no_autoflush:
                template = session.query(MessageTemplate).filter_by(
                    id=template_id, user_id=db_user.id
                ).first()

            if not template:
                await query.edit_message_text("❌ Template não encontrado.")
                return

            text = f"""📝 *Editar Conteúdo*

🏷️ *Template:* {template.name}

📄 *Conteúdo atual:*
{template.content}

🔧 *Variáveis disponíveis:*
• {{nome}} - Nome do cliente
• {{plano}} - Nome do plano
• {{valor}} - Valor em R$
• {{vencimento}} - Data de vencimento
• {{servidor}} - Servidor do cliente
• {{informacoes_extras}} - Informações extras

📝 Digite o novo conteúdo para este template:"""

            reply_markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ Cancelar", callback_data=f"edit_template_{template.id}")]
            ])

            context.user_data['editing_template_id'] = template_id
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Error starting content edit: {e}")
        await query.edit_message_text("❌ Erro ao iniciar edição de conteúdo.")

async def delete_template_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Exclusão (apenas do usuário)."""
    if not update.callback_query:
        return

    query = update.callback_query
    await query.answer()
    user = query.from_user

    try:
        template_id = int(query.data.split('_')[2])

        with db_service.get_session() as session:
            db_user = _user_from_session(session, user.id)
            if not db_user or not db_user.is_active:
                await query.edit_message_text("❌ Conta inativa.")
                return

            with session.no_autoflush:
                template = session.query(MessageTemplate).filter_by(
                    id=template_id, user_id=db_user.id
                ).first()

            if not template:
                await query.edit_message_text("❌ Template não encontrado.")
                return

            text = f"""🗑️ *Excluir Template*

📝 *Template:* {template.name}
🏷️ *Tipo:* {template.template_type}

⚠️ *ATENÇÃO:* Esta ação é irreversível!

📄 *Conteúdo:*
{template.content[:100]}...

❓ Tem certeza que deseja excluir este template?"""

            reply_markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("🗑️ Confirmar Exclusão", callback_data=f"confirm_delete_{template.id}")],
                [InlineKeyboardButton("❌ Cancelar", callback_data=f"edit_template_{template.id}")]
            ])

            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Error showing delete confirmation: {e}")
        await query.edit_message_text("❌ Erro ao carregar confirmação de exclusão.")
