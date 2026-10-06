class OdooError(Exception):
    """Base class for anything that goes wrong talking to Odoo. Messages never contain credentials."""


class ForbiddenOdooMethod(OdooError):
    """Raised when code tries to call anything outside the read-only allow-list (guideline rule 1)."""


class OdooConnectionError(OdooError):
    """Network failure, timeout, or a server that does not speak the expected protocol."""


class OdooAuthError(OdooError):
    """Bad login / password / API key."""


class OdooAccessError(OdooError):
    """The logged-in user is not allowed to read this model or record (Odoo AccessError)."""


class OdooMissingModel(OdooError):
    """The model does not exist on this instance (module not installed)."""
