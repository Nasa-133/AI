from sqlalchemy import Boolean, Column, DateTime, Integer, MetaData, Table, Text, Uuid

metadata = MetaData(schema="identity")

users = Table(
    "users",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("email", Text, nullable=False, unique=True),
    Column("password_hash", Text, nullable=False),
    Column("mfa_secret_encrypted", Text),
    Column("mfa_enabled", Boolean, nullable=False),
    Column("failed_login_count", Integer, nullable=False),
    Column("locked_until", DateTime(timezone=True)),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

tenants = Table(
    "tenants",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("name", Text, nullable=False),
    Column("timezone", Text, nullable=False),
    Column("base_currency", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

memberships = Table(
    "memberships",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("tenant_id", Uuid, nullable=False),
    Column("user_id", Uuid, nullable=False),
    Column("role", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

sessions = Table(
    "sessions",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("token_hash", Text, nullable=False, unique=True),
    Column("user_id", Uuid, nullable=False),
    Column("tenant_id", Uuid, nullable=False),
    Column("mfa_verified", Boolean, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
)
