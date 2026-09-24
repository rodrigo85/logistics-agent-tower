"""
SQLAlchemy Relational Database Models for Logistics Control Tower.
Stores Customers, Orders, Fleet, Customer Dock Rules, and Dispatch Manifests.
"""

from datetime import datetime
from typing import List, Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    document_cnpj: Mapped[str] = mapped_column(String(20), unique=True)
    address: Mapped[str] = mapped_column(String(255))
    neighborhood: Mapped[str] = mapped_column(String(100), index=True)
    city: Mapped[str] = mapped_column(String(100), default="Itajaí")
    state: Mapped[str] = mapped_column(String(2), default="SC")
    zip_code: Mapped[str] = mapped_column(String(10))
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    contact_phone: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    dock_type: Mapped[str] = mapped_column(String(50), default="NIVEL_SOLO")
    max_vehicle_allowed: Mapped[str] = mapped_column(String(50), default="TOCO")

    rules: Mapped[List["CustomerRule"]] = relationship("CustomerRule", back_populates="customer", cascade="all, delete-orphan")
    orders: Mapped[List["Order"]] = relationship("Order", back_populates="customer")


class CustomerRule(Base):
    __tablename__ = "customer_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(Integer, ForeignKey("customers.id"), index=True)
    rule_category: Mapped[str] = mapped_column(String(50))  # ACCESS_RESTRICTION, COLD_CHAIN, DOCK_WINDOW, SECURITY
    content: Mapped[str] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(String(20), default="HIGH")

    customer: Mapped["Customer"] = relationship("Customer", back_populates="rules")


class Vehicle(Base):
    __tablename__ = "fleet"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vehicle_id: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    plate: Mapped[str] = mapped_column(String(10), unique=True)
    model: Mapped[str] = mapped_column(String(100))
    vehicle_type: Mapped[str] = mapped_column(String(30))  # VUC, TOCO, TRUCK
    max_weight_kg: Mapped[float] = mapped_column(Float)
    max_volume_m3: Mapped[float] = mapped_column(Float)
    has_refrigeration: Mapped[bool] = mapped_column(Boolean, default=False)
    driver_name: Mapped[str] = mapped_column(String(150))
    driver_phone: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    current_status: Mapped[str] = mapped_column(String(30), default="AVAILABLE")
    home_cd_id: Mapped[str] = mapped_column(String(50), default="CD-ITAJAI-SC01")


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_number: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    customer_id: Mapped[int] = mapped_column(Integer, ForeignKey("customers.id"), index=True)
    cd_id: Mapped[str] = mapped_column(String(50), default="CD-ITAJAI-SC01")
    weight_kg: Mapped[float] = mapped_column(Float)
    volume_m3: Mapped[float] = mapped_column(Float)
    cargo_type: Mapped[str] = mapped_column(String(30), default="dry")  # dry, refrigerated
    window_start: Mapped[str] = mapped_column(String(10))  # "07:30"
    window_end: Mapped[str] = mapped_column(String(10))    # "11:00"
    priority: Mapped[str] = mapped_column(String(30), default="STANDARD")  # VIP, STANDARD, HIGH_RISK_LOAD
    value_brl: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(30), default="PENDING")  # PENDING, ALLOCATED, DISPATCHED

    customer: Mapped["Customer"] = relationship("Customer", back_populates="orders")


class DispatchManifest(Base):
    __tablename__ = "dispatch_manifests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    manifest_id: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    cd_id: Mapped[str] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    total_orders: Mapped[int] = mapped_column(Integer)
    total_vehicles: Mapped[int] = mapped_column(Integer)
    total_weight_kg: Mapped[float] = mapped_column(Float)
    total_volume_m3: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(30))  # DISPATCHED, REJECTED
    human_verdict: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    human_feedback: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    manifest_payload_json: Mapped[str] = mapped_column(Text)
