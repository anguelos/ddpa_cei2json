"""Generic, request-scoped basket scope — a cei prototype of a didipcv base-class mechanism.

`scope` is a lazy, ``request``-like object: it parses the basket scope of the current request
ONCE (from ``?scope=`` for small baskets, or the POST body ``scope`` for large ones), resolves
it against the service's :class:`fsdb.shared_index.FSDBSharedIndex` into a numpy bool mask over
the sorted charter universe, and caches it on ``flask.g``. A route that never touches ``scope``
never parses it (so single-item / meta routes pay nothing).

Belongs in ``ddp_microservices.SharedIndexMicroservice`` so every DiDip app inherits it; kept
here as a local prototype that moves to the base verbatim (routes then just change the import).
The service must publish its index for the proxy to reach:
``self.app.extensions["ddp_ms"] = self`` (done in ``register_routes``).
"""
from __future__ import annotations

import json

import numpy as np
from flask import current_app, g, request
from werkzeug.local import LocalProxy

from fsdb.shared_index import IndexMismatch  # noqa: F401  (receive_basket raises it -> 409)


class ScopeResult:
    """Outcome of intersecting a route's candidate charter set with the active scope."""

    __slots__ = ("mask", "in_scope", "total", "active")

    def __init__(self, mask, in_scope, total, active):
        self.mask = mask            # bool[N]: candidate ∩ active-scope
        self.in_scope = int(in_scope)
        self.total = int(total)     # candidate size before scoping
        self.active = bool(active)

    @property
    def note(self) -> str:
        if self.active:
            return f"{self.in_scope} of {self.total} charters in scope"
        return f"{self.total} charter{'' if self.total == 1 else 's'}"


class Scope:
    """Resolved basket scope for one request: a charter-aligned bool mask + helpers.

    Charter-level only on the wire (the compact basket has no image encoding); ``images`` is a
    projection through the index's charter->image map and needs an image-aware index.
    """

    def __init__(self, index):
        self._index = index
        self._charters = None       # bool[N] once resolved; stays None when no scope is present
        self._resolved = False
        self._active = False

    def _resolve(self):
        if self._resolved:
            return
        self._resolved = True
        raw = request.args.get("scope")
        if raw is None and request.method in ("POST", "PUT"):
            body = request.get_json(silent=True)
            raw = body.get("scope") if isinstance(body, dict) else None
        if not raw:
            return
        basket = json.loads(raw) if isinstance(raw, str) else raw
        self._charters = self._index.receive_basket(basket)   # bool[N]; IndexMismatch -> 409
        self._active = True

    @property
    def active(self) -> bool:
        self._resolve()
        return self._active

    @property
    def index_hash(self) -> str:
        return self._index.index_hash

    @property
    def charters(self) -> np.ndarray:
        """bool[N_charter] over the sorted charter universe (all-True when no scope is active)."""
        self._resolve()
        if self._charters is None:
            return np.ones(len(self._index), dtype=bool)
        return self._charters

    @property
    def images(self) -> np.ndarray:
        """bool[N_image] derived from the charter mask (needs an FSDBSharedImageIndex)."""
        idx = self._index
        if not hasattr(idx, "charter_to_image_idx"):
            raise TypeError("scope.images requires an image-aware index (FSDBSharedImageIndex)")
        self._resolve()
        mask = np.zeros(idx.n_images, dtype=bool)
        if self._charters is None:
            mask[:] = True
            return mask
        for pos in np.nonzero(self._charters)[0]:
            rows = idx.charter_to_image_idx.get(idx.id_of(int(pos)))
            if rows is not None and len(rows):
                mask[rows] = True
        return mask

    def apply(self, candidate) -> ScopeResult:
        """Intersect a candidate charter bool mask with the active scope (the per-route one-liner)."""
        candidate = np.asarray(candidate, dtype=bool)
        total = int(candidate.sum())
        self._resolve()
        if self._charters is None:
            return ScopeResult(candidate, total, total, active=False)
        scoped = candidate & self._charters
        return ScopeResult(scoped, int(scoped.sum()), total, active=True)


def _current_scope() -> Scope:
    s = getattr(g, "_ddp_scope", None)
    if s is None:
        s = Scope(current_app.extensions["ddp_ms"].index)
        g._ddp_scope = s
    return s


#: request-like proxy — ``from ddp_cei.scope import scope; scope.apply(mask)``.
scope = LocalProxy(_current_scope)
