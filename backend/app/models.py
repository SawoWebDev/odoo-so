"""App database: app roles, the saved list of label PDFs, the print log and the audit log.
Never a mirror of Odoo data, never credentials."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

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


class LabelLocation(Base):
    """A folder of label PDFs that was added on the Label files tab (as a URL)."""

    __tablename__ = "label_location"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    url: Mapped[str] = mapped_column(String(1024))  # exactly what was typed
    folder: Mapped[str] = mapped_column(String(1024), unique=True)  # where it is inside the container
    added_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LabelFile(Base):
    """One label PDF: its name and where it is. Looked up here (not on the disk) when matching item codes and when
    previewing or printing. `status` turns "missing" when a check finds the file renamed, moved or deleted."""

    __tablename__ = "label_file"
    __table_args__ = (UniqueConstraint("location_id", "rel_path"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("label_location.id", ondelete="CASCADE"), index=True)
    rel_path: Mapped[str] = mapped_column(String(1024))  # below the location's folder, forward slashes
    url: Mapped[str | None] = mapped_column(String(2048), nullable=True)  # the file's own address, e.g. file://server/share/...
    name: Mapped[str] = mapped_column(String(512), index=True)
    folder: Mapped[str] = mapped_column(String(1024), default="")  # rel_path without the file name
    code_key: Mapped[str] = mapped_column(String(255), index=True)  # item code this file is for (upper case)
    exact: Mapped[bool] = mapped_column(Boolean, default=True)  # False = name has a suffix like " -No BG"
    size: Mapped[int] = mapped_column(BigInteger, default=0)
    status: Mapped[str] = mapped_column(String(16), default="ok", index=True)  # ok | missing
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_checked: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LabelRequest(Base):
    """Someone asked for the label file of an item code (the order line had none). One open request per code; it is
    solved and closed as soon as a label file for that code is saved in the list."""

    __tablename__ = "label_request"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code_key: Mapped[str] = mapped_column(String(255), index=True)  # item code, upper case
    item_code: Mapped[str] = mapped_column(String(255))
    product_name: Mapped[str] = mapped_column(String(512), default="")
    so_name: Mapped[str] = mapped_column(String(64), default="")
    requested_by: Mapped[int] = mapped_column(Integer, index=True)
    requested_by_name: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    status: Mapped[str] = mapped_column(String(16), default="open", index=True)  # open | solved
    kind: Mapped[str] = mapped_column(String(16), default="missing", index=True)  # missing (no file) | change (file exists)
    note: Mapped[str] = mapped_column(String(1000), default="")  # what was asked for (change requests)
    # How many label files the item code must have before this request is done: the count when it was asked, plus the
    # requests already waiting ahead of it, plus one. 0 = an old request without a count.
    expected: Mapped[int] = mapped_column(Integer, default=0)
    baseline: Mapped[int] = mapped_column(Integer, default=0)  # label files the code had when it was asked
    solved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    file_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    file_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    file_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)  # the link of the file that solved it


class LabelPrintJob(Base):
    """One print / export. `items_json` lists every PDF used: line, item code, where it was, its SHA-256 and size.
    A copy of each file is kept by hash so a reprint is identical even if the file changes or disappears later."""

    __tablename__ = "label_print_job"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    so_name: Mapped[str] = mapped_column(String(64), index=True)
    user_uid: Mapped[int] = mapped_column(Integer, index=True)
    items_json: Mapped[list] = mapped_column(JSON, default=list)
    copies: Mapped[int] = mapped_column(Integer, default=1)
    printer: Mapped[str] = mapped_column(String(128), default="")
    reprint_of: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AppSetting(Base):
    """Small admin-edited settings (JSON text per key), e.g. the email setup for label requests."""

    __tablename__ = "app_setting"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")


class AuditEvent(Base):
    __tablename__ = "audit_event"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_uid: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    event: Mapped[str] = mapped_column(String(32), index=True)  # login | search | print | reprint | label_*
    so_name: Mapped[str] = mapped_column(String(64), default="")
    detail: Mapped[str] = mapped_column(String(512), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
