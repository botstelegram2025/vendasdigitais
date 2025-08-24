from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from contextlib import contextmanager
import logging
from config import Config
from models import Base, User, Client, Subscription, MessageTemplate, MessageLog, SystemSettings

logger = logging.getLogger(__name__)

class DatabaseService:
    def __init__(self):
        self.engine = create_engine(
            Config.DATABASE_URL,
            pool_pre_ping=True,
            pool_recycle=300,
            echo=False
        )
        self.SessionLocal = scoped_session(sessionmaker(bind=self.engine))
        self.create_tables()
        self.create_default_templates()
    
    def create_tables(self):
        """Create all database tables"""
        try:
            Base.metadata.create_all(bind=self.engine)
            logger.info("Database tables created successfully")
        except Exception as e:
            logger.error(f"Error creating database tables: {e}")
            raise
    
    @contextmanager
    def get_session(self):
        """Get database session with automatic cleanup"""
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Database session error: {e}")
            raise
        finally:
            session.close()
    
    def create_default_templates(self):
        """Create default message templates"""
        default_templates = [
            {
                'name': 'Lembrete 2 dias antes',
                'template_type': 'reminder_2days',
                'subject': 'Lembrete: Vencimento em 2 dias',
                'content': 'Olá {client_name}! 👋\n\nEste é um lembrete amigável de que seu plano "{plan_name}" vencerá em 2 dias ({due_date}).\n\nValor: R$ {plan_price}\n\nPara renovar, entre em contato conosco.\n\nObrigado! 😊'
            },
            {
                'name': 'Lembrete 1 dia antes',
                'template_type': 'reminder_1day',
                'subject': 'Lembrete: Vencimento amanhã',
                'content': 'Olá {client_name}! ⏰\n\nSeu plano "{plan_name}" vence AMANHÃ ({due_date}).\n\nValor: R$ {plan_price}\n\nNão esqueça de renovar para continuar aproveitando nossos serviços!\n\nRenove agora! 🚀'
            },
            {
                'name': 'Lembrete no vencimento',
                'template_type': 'reminder_due',
                'subject': 'Vencimento hoje',
                'content': 'Olá {client_name}! 📅\n\nSeu plano "{plan_name}" vence HOJE ({due_date}).\n\nValor: R$ {plan_price}\n\nRenove agora para não perder o acesso aos nossos serviços.\n\nContate-nos para renovar! 💬'
            },
            {
                'name': 'Lembrete após vencimento',
                'template_type': 'reminder_overdue',
                'subject': 'Plano vencido',
                'content': 'Olá {client_name}! ⚠️\n\nSeu plano "{plan_name}" venceu ontem ({due_date}).\n\nValor: R$ {plan_price}\n\nRenove o quanto antes para reativar seus serviços.\n\nEstamos aqui para ajudar! 🤝'
            },
            {
                'name': 'Boas-vindas',
                'template_type': 'welcome',
                'subject': 'Bem-vindo!',
                'content': 'Olá {client_name}! 🎉\n\nSeja muito bem-vindo(a)!\n\nSeu plano "{plan_name}" está ativo e vence em {due_date}.\n\nValor: R$ {plan_price}\n\nEstamos muito felizes em tê-lo(a) conosco! 🌟'
            },
            {
                'name': 'Renovação',
                'template_type': 'renewal',
                'subject': 'Plano renovado com sucesso!',
                'content': 'Olá {client_name}! ✅\n\nSeu plano "{plan_name}" foi renovado com sucesso!\n\nNovo vencimento: {due_date}\nValor: R$ {plan_price}\n\nObrigado pela confiança! Continue aproveitando nossos serviços. 🚀'
            }
        ]
        
        with self.get_session() as session:
            for template_data in default_templates:
                existing = session.query(MessageTemplate).filter_by(
                    template_type=template_data['template_type']
                ).first()
                
                if not existing:
                    template = MessageTemplate(**template_data)
                    session.add(template)
                    logger.info(f"Created default template: {template_data['name']}")

# Global database service instance
db_service = DatabaseService()
