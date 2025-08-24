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
        # ❌ NÃO rode seed no boot: evita user_id=None em coluna NOT NULL
        # self.create_default_templates()  # removido

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

    # ---------- NOVO: templates padrão como função util ----------
    @staticmethod
    def _default_templates():
        return [
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

    # ---------- NOVO: seed POR USUÁRIO ----------
    def create_default_templates_for_user(self, user_id: int) -> None:
        """
        Cria os templates padrão para um usuário específico.
        Use quando o usuário já existir (ex.: após /start).
        Mantém integridade quando message_templates.user_id é NOT NULL.
        """
        if not isinstance(user_id, int):
            raise ValueError("user_id inválido para seed de templates.")

        with self.get_session() as session:
            # evita flush prematuro caso exista objeto pendente
            with session.no_autoflush:
                for tpl in self._default_templates():
                    exists = (
                        session.query(MessageTemplate)
                        .filter_by(user_id=user_id, template_type=tpl['template_type'])
                        .first()
                    )
                    if not exists:
                        session.add(MessageTemplate(
                            user_id=user_id,
                            name=tpl['name'],
                            template_type=tpl['template_type'],
                            subject=tpl['subject'],
                            content=tpl['content'],
                            is_active=True
                        ))
                        logger.info(f"[seed] Default template criado para user_id={user_id}: {tpl['name']}")

    # ---------- (opcional) método legado desativado ----------
    def create_default_templates(self):
        """
        (Desativado) Não usar. O seed global sem user_id causava violação de NOT NULL.
        Mantenho o método apenas para evitar importações quebradas.
        """
        logger.warning("create_default_templates() está desativado. "
                       "Use create_default_templates_for_user(user_id).")


# Global database service instance
db_service = DatabaseService()
