from datetime import datetime, timezone
from typing import TYPE_CHECKING
from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base

if TYPE_CHECKING:
    from app.models.user import User


class PasswordResetToken(Base):
    """
    Stores cryptographic hashes of password reset tokens.
    Plaintext tokens are never stored in the database.
    """
    __tablename__ = "password_reset_tokens"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="password_reset_tokens")

    @property
    def is_expired(self) -> bool:
        now = datetime.now(timezone.utc)
        if self.expires_at.tzinfo is None:
            # Handle naive datetime comparisons gracefully
            return datetime.utcnow() > self.expires_at
        return now > self.expires_at

    def __repr__(self) -> str:
        return f"<PasswordResetToken(id={self.id}, user_id={self.user_id}, is_used={self.is_used})>"

