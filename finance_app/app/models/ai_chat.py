"""AI Chat message model — persists conversation history with the Groq advisor."""
from datetime import datetime
from ..extensions import db


class AiChatMessage(db.Model):
    """Stores individual messages between the user and the AI financial advisor.

    Persisted so the user can return to the conversation and the LLM
    has access to recent context across page reloads.
    """
    __tablename__ = 'ai_chat_messages'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey('users.user_id'), nullable=False
    )
    role = db.Column(db.String(20), nullable=False)   # 'user' or 'assistant'
    content = db.Column(db.Text, nullable=False)
    tokens_used = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Index for efficient chronological per-user queries
    __table_args__ = (
        db.Index('idx_ai_chat_user_time', 'user_id', 'created_at'),
    )

    def to_dict(self):
        return {
            'role': self.role,
            'content': self.content,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        preview = (self.content or '')[:40]
        return f'<AiChatMessage {self.id} [{self.role}]: {preview}...>'
