from datetime import datetime, date

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, TimestampMixin


class _UnifiedMixin(TimestampMixin):
    """所有统一表共享的溯源字段"""

    source_system: Mapped[str] = mapped_column(String(50), nullable=False)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    source_data_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UnifiedCustomer(Base, _UnifiedMixin):
    __tablename__ = "unified_customers"
    __table_args__ = (
        UniqueConstraint("source_system", "external_id", name="uq_customers_source_external"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    company: Mapped[str | None] = mapped_column(String(200), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    industry: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str | None] = mapped_column(String(50), nullable=True)


class UnifiedOrder(Base, _UnifiedMixin):
    __tablename__ = "unified_orders"
    __table_args__ = (
        UniqueConstraint("source_system", "external_id", name="uq_orders_source_external"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_number: Mapped[str] = mapped_column(String(100), nullable=False)
    order_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    customer_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_amount: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(10), nullable=True)
    status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    order_date: Mapped[date | None] = mapped_column(Date, nullable=True)


class UnifiedProduct(Base, _UnifiedMixin):
    __tablename__ = "unified_products"
    __table_args__ = (
        UniqueConstraint("source_system", "external_id", name="uq_products_source_external"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    sku: Mapped[str | None] = mapped_column(String(100), nullable=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(20), nullable=True)
    status: Mapped[str | None] = mapped_column(String(50), nullable=True)


class UnifiedInventory(Base, _UnifiedMixin):
    __tablename__ = "unified_inventory"
    __table_args__ = (
        UniqueConstraint("source_system", "external_id", name="uq_inventory_source_external"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    warehouse: Mapped[str | None] = mapped_column(String(100), nullable=True)
    quantity: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    available_quantity: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(20), nullable=True)


class UnifiedProject(Base, _UnifiedMixin):
    __tablename__ = "unified_projects"
    __table_args__ = (
        UniqueConstraint("source_system", "external_id", name="uq_projects_source_external"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    priority: Mapped[str | None] = mapped_column(String(20), nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    owner: Mapped[str | None] = mapped_column(String(100), nullable=True)


class UnifiedContact(Base, _UnifiedMixin):
    __tablename__ = "unified_contacts"
    __table_args__ = (
        UniqueConstraint("source_system", "external_id", name="uq_contacts_source_external"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    company: Mapped[str | None] = mapped_column(String(200), nullable=True)
    department: Mapped[str | None] = mapped_column(String(100), nullable=True)
    position: Mapped[str | None] = mapped_column(String(100), nullable=True)
