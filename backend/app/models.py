"""App database. Holds app data only (guideline rule 3): never a mirror of Odoo data, never credentials."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AppUser(Base):
    __tablename__ = "app_user"
    odoo_uid: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    odoo_login: Mapped[str] = mapped_column(String(255), index=True)
    display_name: Mapped[str] = mapped_column(String(255), default="")
    app_role: Mapped[str] = mapped_column(String(32), default="viewer")  # viewer | printer | template_admin
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Template(Base):
    __tablename__ = "template"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(64), default="general")
    format: Mapped[str] = mapped_column(String(16))  # html | docx | pdf_overlay | zpl
    size: Mapped[str] = mapped_column(String(32), default="A6")
    orientation: Mapped[str] = mapped_column(String(16), default="portrait")
    scope: Mapped[str] = mapped_column(String(16), default="line")  # so | line | lot | package
    default_calc_mode: Mapped[int] = mapped_column(Integer, default=1)
    active: Mapped[bool] = mapped_column(Boolean, default=False)
    active_version_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # version used for new prints
    versions: Mapped[list["TemplateVersion"]] = relationship(
        back_populates="template", order_by="TemplateVersion.version", cascade="all, delete-orphan"
    )


class TemplateVersion(Base):
    """Immutable once created. Old versions stay usable for reprints."""

    __tablename__ = "template_version"
    __table_args__ = (UniqueConstraint("template_id", "version"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    template_id: Mapped[int] = mapped_column(ForeignKey("template.id"))
    version: Mapped[int] = mapped_column(Integer)
    file_ref: Mapped[str] = mapped_column(String(512))  # relative to STORAGE_DIR
    original_filename: Mapped[str] = mapped_column(String(255), default="")
    # size/orientation/scope/default_calc_mode are copied here so an old version renders as it did.
    size: Mapped[str] = mapped_column(String(32), default="A6")
    orientation: Mapped[str] = mapped_column(String(16), default="portrait")
    scope: Mapped[str] = mapped_column(String(16), default="line")
    default_calc_mode: Mapped[int] = mapped_column(Integer, default=1)
    uploaded_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    template: Mapped[Template] = relationship(back_populates="versions")
    mappings: Mapped[list["TemplateMapping"]] = relationship(
        back_populates="version", cascade="all, delete-orphan", order_by="TemplateMapping.id"
    )


class TemplateMapping(Base):
    __tablename__ = "template_mapping"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    template_version_id: Mapped[int] = mapped_column(ForeignKey("template_version.id"))
    placeholder: Mapped[str] = mapped_column(String(255))
    catalog_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    overflow_rule: Mapped[str] = mapped_column(String(16), default="wrap")  # wrap | shrink | truncate
    optional: Mapped[bool] = mapped_column(Boolean, default=False)
    version: Mapped[TemplateVersion] = relationship(back_populates="mappings")


class FieldCatalog(Base):
    __tablename__ = "field_catalog"
    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    label: Mapped[str] = mapped_column(String(255))
    group: Mapped[str] = mapped_column(String(32))
    source_path: Mapped[str] = mapped_column(String(255))
    type: Mapped[str] = mapped_column(String(16))  # text | number | date | image | barcode
    scope: Mapped[str] = mapped_column(String(16))  # so | line | lot | package
    selectable: Mapped[bool] = mapped_column(Boolean, default=True)
    aliases: Mapped[list] = mapped_column(JSON, default=list)


class Preset(Base):
    __tablename__ = "preset"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    owner_uid: Mapped[int] = mapped_column(Integer, index=True)
    shared: Mapped[bool] = mapped_column(Boolean, default=False)
    selection_json: Mapped[dict] = mapped_column(JSON, default=dict)


class PrintJob(Base):
    __tablename__ = "print_job"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    so_name: Mapped[str] = mapped_column(String(64), index=True)
    template_version_id: Mapped[int] = mapped_column(ForeignKey("template_version.id"))
    selection_json: Mapped[dict] = mapped_column(JSON, default=dict)
    overrides_json: Mapped[dict] = mapped_column(JSON, default=dict)
    calculated_json: Mapped[dict] = mapped_column(JSON, default=dict)  # original calc, before overrides
    options_json: Mapped[dict] = mapped_column(JSON, default=dict)  # calc mode, toggles
    copies: Mapped[int] = mapped_column(Integer, default=1)
    layout: Mapped[dict] = mapped_column(JSON, default=dict)
    printer: Mapped[str] = mapped_column(String(128), default="")
    snapshot_ref: Mapped[str] = mapped_column(String(512), default="")  # exact values rendered, for reprint
    output_format: Mapped[str] = mapped_column(String(8), default="pdf")
    user_uid: Mapped[int] = mapped_column(Integer, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    version: Mapped[TemplateVersion] = relationship()


class AuditEvent(Base):
    __tablename__ = "audit_event"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_uid: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    event: Mapped[str] = mapped_column(String(32), index=True)  # login | login_failed | search | upload | print
    so_name: Mapped[str] = mapped_column(String(64), default="")
    detail: Mapped[str] = mapped_column(String(512), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
