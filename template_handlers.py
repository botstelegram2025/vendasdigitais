"""Template management handlers for the Telegram bot"""

import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from services.database_service import db_service
from models import User, MessageTemplate

logger = logging.getLogger(__name__)

async def templates_edit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show template edit options"""
    if not update.callback_query:
        return
        
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    
    try:
        with db_service.get_session() as session:
            db_user = session.query(User).filter_by(telegram_id=str(user.id)).first()
            
            if not db_user or not db_user.is_active:
                await query.edit_message_text("❌ Conta inativa.")
                return
            
            # Get all templates for user
            templates = session.query(MessageTemplate).filter_by(user_id=db_user.id).all()
            
            if not templates:
                await query.edit_message_text(
                    "❌ Nenhum template encontrado.\n\nCrie templates primeiro!",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔙 Voltar", callback_data="templates_menu")]
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
    """Show template creation options"""
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
    """Show template selection for sending message to a specific client"""
    query = update.callback_query
    user = query.from_user
    
    try:
        with db_service.get_session() as session:
            db_user = session.query(User).filter_by(telegram_id=str(user.id)).first()
            
            if not db_user or not db_user.is_active:
                await query.edit_message_text("❌ Conta inativa.")
                return
            
            # Get all active templates for user
            templates = session.query(MessageTemplate).filter_by(
                user_id=db_user.id,
                is_active=True
            ).all()
            
            if not templates:
                await query.edit_message_text(
                    "❌ Nenhum template ativo encontrado.\n\nCrie templates primeiro!",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔙 Voltar", callback_data=f"view_client_{client_id}")]
                    ])
                )
                return
            
            text = f"📱 *Enviar Mensagem*\n\n📋 Selecione o template para usar:"
            
            keyboard = []
            for template in templates:
                keyboard.append([
                    InlineKeyboardButton(
                        f"📝 {template.name}",
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
    """Send selected template to client"""
    if not update.callback_query:
        return
        
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    
    try:
        # Extract template_id and client_id from callback data
        parts = query.data.split('_')
        template_id = int(parts[2])
        client_id = int(parts[3])
        
        with db_service.get_session() as session:
            from models import Client
            from services.whatsapp_service import whatsapp_service
            
            db_user = session.query(User).filter_by(telegram_id=str(user.id)).first()
            
            if not db_user or not db_user.is_active:
                await query.edit_message_text("❌ Conta inativa.")
                return
            
            # Get template and client
            template = session.query(MessageTemplate).filter_by(
                id=template_id,
                user_id=db_user.id
            ).first()
            
            client = session.query(Client).filter_by(
                id=client_id,
                user_id=db_user.id
            ).first()
            
            if not template or not client:
                await query.edit_message_text("❌ Template ou cliente não encontrado.")
                return
            
            # Replace variables in template
            from main import replace_template_variables
            message_content = replace_template_variables(template.content, client)
            
            # Send WhatsApp message
            result = whatsapp_service.send_message(client.phone_number, message_content)
            
            if result['success']:
                # Log the message
                from models import MessageLog
                message_log = MessageLog(
                    user_id=db_user.id,
                    client_id=client.id,
                    template_id=template.id,
                    message_content=message_content,
                    sent_at=datetime.utcnow(),
                    status='sent'
                )
                session.add(message_log)
                session.commit()
                
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
                # Log failed message
                message_log = MessageLog(
                    user_id=db_user.id,
                    client_id=client.id,
                    template_id=template.id,
                    message_content=message_content,
                    sent_at=datetime.utcnow(),
                    status='failed',
                    error_message=result.get('error', 'Unknown error')
                )
                session.add(message_log)
                session.commit()
                
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
    """Handle individual template edit"""
    if not update.callback_query:
        return
        
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    
    try:
        # Extract template ID from callback data
        template_id = int(query.data.split('_')[2])
        
        with db_service.get_session() as session:
            db_user = session.query(User).filter_by(telegram_id=str(user.id)).first()
            
            if not db_user or not db_user.is_active:
                await query.edit_message_text("❌ Conta inativa.")
                return
            
            # Get template
            template = session.query(MessageTemplate).filter_by(
                id=template_id, 
                user_id=db_user.id
            ).first()
            
            if not template:
                await query.edit_message_text("❌ Template não encontrado.")
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
    """Handle template content editing"""
    if not update.callback_query:
        return
        
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    
    try:
        # Extract template ID from callback data
        template_id = int(query.data.split('_')[2])
        
        with db_service.get_session() as session:
            db_user = session.query(User).filter_by(telegram_id=str(user.id)).first()
            
            if not db_user or not db_user.is_active:
                await query.edit_message_text("❌ Conta inativa.")
                return
            
            # Get template
            template = session.query(MessageTemplate).filter_by(
                id=template_id, 
                user_id=db_user.id
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
            
            keyboard = [
                [InlineKeyboardButton("❌ Cancelar", callback_data=f"edit_template_{template.id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Store template ID in context for next message
            context.user_data['editing_template_id'] = template_id
            
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
            
    except Exception as e:
        logger.error(f"Error starting content edit: {e}")
        await query.edit_message_text("❌ Erro ao iniciar edição de conteúdo.")

async def delete_template_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle template deletion"""
    if not update.callback_query:
        return
        
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    
    try:
        # Extract template ID from callback data
        template_id = int(query.data.split('_')[2])
        
        with db_service.get_session() as session:
            db_user = session.query(User).filter_by(telegram_id=str(user.id)).first()
            
            if not db_user or not db_user.is_active:
                await query.edit_message_text("❌ Conta inativa.")
                return
            
            # Get template
            template = session.query(MessageTemplate).filter_by(
                id=template_id, 
                user_id=db_user.id
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
            
            keyboard = [
                [InlineKeyboardButton("🗑️ Confirmar Exclusão", callback_data=f"confirm_delete_{template.id}")],
                [InlineKeyboardButton("❌ Cancelar", callback_data=f"edit_template_{template.id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
            
    except Exception as e:
        logger.error(f"Error showing delete confirmation: {e}")
        await query.edit_message_text("❌ Erro ao carregar confirmação de exclusão.")