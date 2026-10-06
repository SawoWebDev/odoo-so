"""Application settings. Everything environment-specific comes from env vars, nothing is hard-coded."""
from __future__ import annotations

import json
from functools import lru_cache

from pydantic import field_validator
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
    bom_depth: int = 2
    cache_ttl_seconds: int = 120
    # Odoo stores weight/volume in the units configured under Inventory settings; multiply to get kg / m3. [VERIFY]
    weight_factor_to_kg: float = 1.0
    volume_factor_to_m3: float = 1.0

    # Labels
    default_label_size: str = "A6"
    max_upload_mb: int = 15
    render_timeout_seconds: int = 20
    printers: dict[str, str] = {}

    @field_validator("printers", mode="before")
    @classmethod
    def _parse_printers(cls, v):
        if isinstance(v, str):
            v = v.strip()
            return json.loads(v) if v else {}
        return v or {}

    @property
    def admin_logins(self) -> set[str]:
        return {x.strip().lower() for x in self.initial_admin_logins.split(",") if x.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()
