"""SQLAlchemy declarative base.

Every ORM model imports `Base` from here so Alembic's autogenerate sees
one unified metadata graph. Lives in its own module to break the import
cycle: env.py needs Base, models need Base, services need models.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
