"""
SmartGuard AI — SQLAlchemy Declarative Base
All models import Base from this module so Alembic can discover them.
"""
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Project-wide SQLAlchemy declarative base."""
    pass
