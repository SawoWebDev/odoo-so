"""Schema-aware access on top of OdooReadClient: logical names, fields_get intersection, batching."""
from __future__ import annotations

from typing import Any, Iterable

from ..odoo.client import OdooReadClient
from ..odoo.errors import OdooMissingModel
from .fieldmap import LOGICAL

CHUNK = 200


def chunked(seq: list, n: int = CHUNK):
    for i in range(0, len(seq), n):
        yield seq[i : i + n]


def or_domain(terms: list) -> list:
    """['|', t1, '|', t2, t3] for n terms; [] for none; [t] for one."""
    if not terms:
        return []
    return ["|"] * (len(terms) - 1) + list(terms)


class Rec:
    """One Odoo record addressed by logical field names."""

    def __init__(self, model: str, schema: "Schema", data: dict):
        self.model, self._s, self.data = model, schema, data

    @property
    def id(self) -> int:
        return self.data["id"]

    def has(self, logical: str) -> bool:
        a = self._s.pick(self.model, logical)
        return bool(a) and a in self.data

    def raw(self, logical: str) -> Any:
        a = self._s.pick(self.model, logical)
        return self.data.get(a) if a else None

    def m2o(self, logical: str) -> tuple[int | None, str]:
        v = self.raw(logical)
        if isinstance(v, (list, tuple)) and v:
            return v[0], (v[1] if len(v) > 1 else "")
        return None, ""

    def ids(self, logical: str) -> list[int]:
        v = self.raw(logical)
        return list(v) if isinstance(v, (list, tuple)) else []

    def text(self, logical: str) -> str:
        v = self.raw(logical)
        return "" if v is False or v is None else str(v)

    def num(self, logical: str) -> float | None:
        v = self.raw(logical)
        return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None

    def state_label(self, logical: str) -> str:
        a = self._s.pick(self.model, logical)
        v = self.data.get(a) if a else None
        return self._s.selection_label(self.model, a, v) if a else ""


class Schema:
    def __init__(self, client: OdooReadClient, fields_cache: dict[str, dict] | None = None):
        self.client = client
        self._fields: dict[str, dict] = fields_cache if fields_cache is not None else {}
        self._missing: set[str] = set()

    # -- fields_get --------------------------------------------------------------------------
    def fields(self, model: str) -> dict:
        if model in self._missing:
            raise OdooMissingModel(f"Model {model} is not available on this Odoo instance")
        if model not in self._fields:
            try:
                self._fields[model] = self.client.fields_get(model, ["string", "type", "relation", "selection"])
            except OdooMissingModel:
                self._missing.add(model)
                raise
        return self._fields[model]

    def has_model(self, model: str) -> bool:
        try:
            return bool(self.fields(model))
        except OdooMissingModel:
            return False

    def pick(self, model: str, logical: str) -> str | None:
        fields = self.fields(model)
        for cand in LOGICAL.get(model, {}).get(logical, []):
            if cand in fields:
                return cand
        return None

    def present(self, model: str, logicals: Iterable[str] | None = None) -> list[str]:
        wanted = list(logicals) if logicals is not None else list(LOGICAL.get(model, {}))
        out = [self.pick(model, lg) for lg in wanted]
        return sorted({a for a in out if a})

    def resolution(self, model: str) -> dict[str, str | None]:
        return {lg: self.pick(model, lg) for lg in LOGICAL.get(model, {})}

    def selection_label(self, model: str, actual: str, value: Any) -> str:
        if value in (False, None, ""):
            return ""
        for key, label in (self.fields(model).get(actual, {}).get("selection") or []):
            if key == value:
                return str(label)
        return str(value)

    # -- reads ---------------------------------------------------------------------------------
    def d(self, model: str, logical: str, op: str, value: Any) -> list:
        """Domain clause by logical name; [] when the field does not exist on this instance."""
        a = self.pick(model, logical)
        return [(a, op, value)] if a else []

    def search_read(self, model: str, domain: list, logicals: Iterable[str] | None = None, *,
                    limit: int | None = None, order: str | None = None) -> list[Rec]:
        fields = self.present(model, logicals)
        rows = self.client.search_read(model, domain, fields, limit=limit, order=order)
        return [Rec(model, self, r) for r in rows]

    def read(self, model: str, ids: list[int], logicals: Iterable[str] | None = None) -> list[Rec]:
        ids = sorted({i for i in ids if i})
        fields = self.present(model, logicals)
        out: list[Rec] = []
        for part in chunked(ids):
            out += [Rec(model, self, r) for r in self.client.read(model, part, fields)]
        return out

    def search_read_in(self, model: str, logical: str, ids: list[int], logicals: Iterable[str] | None = None,
                       extra: list | None = None, order: str | None = None) -> list[Rec]:
        """Batched `field in ids` lookup (one call per chunk, never one call per record)."""
        a = self.pick(model, logical)
        if not a or not ids:
            return []
        out: list[Rec] = []
        for part in chunked(sorted(set(ids))):
            out += self.search_read(model, [(a, "in", part)] + (extra or []), logicals, order=order)
        return out
