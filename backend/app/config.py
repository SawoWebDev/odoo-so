"""Application settings. Everything environment-specific comes from env vars, nothing is hard-coded."""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore", case_sensitive=False)

    # Odoo
    odoo_url: str = ""
    odoo_db: str = ""
    odoo_transport: str = "auto"  # auto | jsonrpc | xmlrpc | json2
    odoo_verify_ssl: bool = True
    odoo_timeout_s: float = 30.0

    # App
    database_url: str = "sqlite:///./dev.db"
    redis_url: str = ""  # empty -> in-process session store (dev/tests only)
    app_secret_key: str = "dev-only-secret-change-me"
    storage_dir: str = "./storage"

    # Sessions / security
    session_idle_seconds: int = 1800
    cookie_secure: bool = False
    login_max_fails: int = 5
    login_lockout_seconds: int = 900
    initial_admin_logins: str = ""
    default_role: str = "printer"

    # Resolver
    cache_ttl_seconds: int = 120

    # Label PDFs. Folders to read are added on the "Label files" tab as a URL. A URL can only point inside what is
    # mounted into the container:
    #   LABEL_MOUNT_DIR  where the network share (or a local folder) is mounted in the container
    #   LABEL_SHARE      the network share that is mounted there, e.g. //172.16.0.4/Marketing  (so that
    #                    file://172.16.0.4/Marketing/00%20MASTERLIST/... maps to LABEL_MOUNT_DIR/00 MASTERLIST/...)
    label_mount_dir: str = "/labels"
    label_share: str = ""
    # Address of the share bridge (backend/scripts/share_bridge.py) running on the Windows PC. When set, the folders
    # are read through it with the PC's own access to the share: no mounted folder and no share password.
    # Docker Desktop: http://host.docker.internal:8765
    share_bridge_url: str = ""
    # Optional: a folder added automatically (once) when no folder has been added yet. Any form of URL / path works.
    label_default_location: str = ""
    # When one item code has several PDFs, folders containing the first matching word here are preferred as the
    # default. Comma separated, case-insensitive, e.g. "Box Stickers,Individual".
    label_folder_priority: str = ""
    # Only transfers that leave from this stock location are offered as a "Reference" (Odoo's source location, e.g.
    # "PL1/Output" or one of its sub-locations). Empty = every transfer of the order.
    reference_source_location: str = "PL1/Output"
    label_max_mb: int = 150  # larger PDFs can be viewed or printed alone but are not merged or kept in the snapshot

    @property
    def admin_logins(self) -> set[str]:
        return {x.strip().lower() for x in self.initial_admin_logins.split(",") if x.strip()}

    @property
    def folder_priority(self) -> list[str]:
        return [x.strip().lower() for x in self.label_folder_priority.split(",") if x.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
