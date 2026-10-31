import enum
from typing import List, Optional, TYPE_CHECKING
from sqlalchemy import Boolean, Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.organization import Organization
    from app.models.customer import Customer
    from app.models.token import PasswordResetToken


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    STAFF = "staff"
    CUSTOMER = "customer"


class User(Base, TimestampMixin):
    """
    User entity representing an authenticated account within a specific organization.
    """
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("organization_id", "email", name="uq_users_organization_email"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, index=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role_enum", native_enum=False),
        default=UserRole.CUSTOMER,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationships
    organization: Mapped["Organization"] = relationship("Organization", back_populates="users")
    customer_profile: Mapped[Optional["Customer"]] = relationship(
        "Customer",
        back_populates="user",
        uselist=False,
    )
    password_reset_tokens: Mapped[List["PasswordResetToken"]] = relationship(
        "PasswordResetToken",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email='{self.email}', role='{self.role}', org_id={self.organization_id})>"

