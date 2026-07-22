"""ddpa_cei2json online mode (mode 3): serve + search + filter CEI metadata.

A :class:`SharedIndexMicroservice` (owned prefix ``cei``) that reduces an FSDB slice into RAM
at load time: it reads every charter's ``CH.cei2json.pred.json`` (produced by the offline mode)
and builds, aligned to the shared sorted charter index,

* two substring/regex text indexes (:class:`StandoffStrIdx`) over abstracts and tenors,
* a per-charter date span (as sortable ``YYYYMMDD`` ints) for date-range filtering,
* a location facet (place name -> charter positions) for location filtering.

It then exposes single-item and scope views plus combined text + date + location search. The
contract routes (``/cei/health`` ``/cei/info`` ``/cei/register`` ``/cei/health_report``,
``/cei/basket``), Swagger, sibling discovery and ``run()`` are inherited from the base class.
Nothing is written back into the FSDB.
"""
from __future__ import annotations

import json
from collections import defaultdict

import numpy as np
from flask import jsonify, request

from fargv import deep_dataclass
from fsdb import Charter, Fond
from ddp_util import create_pagers
from ddp_util.config_ms import DdpMsConfigs
from ddp_microservices import scope
from ddp_microservices.microservice import SharedIndexMicroservice

from .fsdb_standoff import StandoffStrIdx

#: the offline per-charter output this service indexes (CH.<app>.<what>.json).
CEI2JSON_FILENAME = "CH.cei2json.pred.json"


@deep_dataclass
class MsCei2Json(DdpMsConfigs.Microservice):
    """Config for the cei2json serving microservice (parsed with suite_root=DdpMsConfigs)."""

    ms_id: int = 6                         # port = base_port + ms_id -> 5006 by default
    route_prefix: str = "cei"
    launch_cmd: str = "ddpa_cei2json_serve"
    icon: str = "static/icon_cei2json.svg"  # served at /cei/icon.ico (favicon + topnav box)
    filename: str = CEI2JSON_FILENAME
    "per-charter offline output to index."
    page_itemcount: int = 25
    "default results per page for scope/search listings."


# --- date helpers: ISO <-> sortable YYYYMMDD int, with year-only widening ----------------

def _iso_to_int(iso):
    """``"1255-07-14"`` -> ``12550714``; falsy -> 0."""
    if not iso:
        return 0
    return int(iso.replace("-", ""))


def _int_to_iso(value):
    """``12550714`` -> ``"1255-07-14"``; 0 -> None."""
    if not value:
        return None
    s = f"{value:08d}"
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}"


def _bound_to_int(text, *, high):
    """Parse a filter bound (``"YYYY"``, ``"YYYY-MM"`` or ``"YYYY-MM-DD"``) to a YYYYMMDD int.
    Missing month/day widen to the start (``high=False``) or end (``high=True``) of the period."""
    if not text:
        return None
    parts = text.strip().split("-")
    try:
        year = int(parts[0])
    except ValueError:
        return None
    month = int(parts[1]) if len(parts) > 1 else (12 if high else 1)
    day = int(parts[2]) if len(parts) > 2 else (31 if high else 1)
    return year * 10000 + month * 100 + day


class Cei2JsonMicroservice(SharedIndexMicroservice):
    """CEI metadata service: full-text search over abstracts/tenors + date/location filtering.

    Launch (if not running):  ddpa_cei2json_serve
    """

    config_class = MsCei2Json
    GLOBAL_ROUTE_PREFIX = "cei"
    LAUNCH_CMD = "ddpa_cei2json_serve"
    # Hand-off view types this service can RECEIVE (it serves /cei/<view>/<value>): a charter, a
    # fond, an archive, and its own home. The page-level charter_list/charter_ranking markers below
    # are the on-screen view-model, not descriptor hand-off targets, so they are NOT advertised.
    VIEWS = ("charter", "fond", "archive", "root")
    index_class = None                            # charter-only shared index
    filepattern = CEI2JSON_FILENAME               # presence mask -> charters carrying our output

    # ---- load-time reduction into RAM ----------------------------------------------------
    def load(self):
        super().load()                            # builds self.index (+ presence_mask over filepattern)
        idx = self.index
        n = len(idx)
        verbose = getattr(self.cfg, "verbosity", 0)

        self.date_start = np.zeros(n, dtype=np.int64)   # YYYYMMDD span start; 0 -> unknown
        self.date_end = np.zeros(n, dtype=np.int64)
        self.has_date = np.zeros(n, dtype=bool)
        self.location_of = [None] * n                   # per-position place name or None
        abstracts: dict[str, str] = {}                  # md5 -> abstract (non-empty only)
        tenors: dict[str, str] = {}                     # md5 -> tenor
        loc_positions: dict[str, list] = defaultdict(list)

        if idx.presence_mask is not None:
            positions = np.nonzero(idx.presence_mask)[0].tolist()
        else:
            positions = range(n)

        for pos in positions:
            pos = int(pos)
            md5 = idx.id_of(pos)
            path = idx.charter_path(pos) / self.cfg.filename
            try:
                rec = json.loads(path.read_text())
            except (OSError, ValueError):
                continue
            date = rec.get("date")
            if date and date.get("start"):
                self.date_start[pos] = _iso_to_int(date["start"])
                self.date_end[pos] = _iso_to_int(date.get("end") or date["start"])
                self.has_date[pos] = True
            loc = rec.get("location")
            if loc:
                self.location_of[pos] = loc
                loc_positions[loc].append(pos)
            if rec.get("abstract"):
                abstracts[md5] = rec["abstract"]
            if rec.get("tenor"):
                tenors[md5] = rec["tenor"]

        self.abstracts = abstracts
        self.tenors = tenors
        self.location_facet = {k: np.array(sorted(v), dtype=np.int64) for k, v in loc_positions.items()}
        self.abstract_idx = StandoffStrIdx.from_md5dict(abstracts)
        self.tenor_idx = StandoffStrIdx.from_md5dict(tenors)
        if verbose >= 1:
            print(f"[cei2json] indexed {len(abstracts)} abstracts, {len(tenors)} tenors, "
                  f"{int(self.has_date.sum())} dated, {len(self.location_facet)} locations "
                  f"over {n} charters.", flush=True)

    # ---- filter primitives: each returns a bool mask (length n) over sorted positions ----
    def _date_mask(self):
        """``?from=`` / ``?to=`` (YYYY[-MM[-DD]]); a charter matches if its span overlaps the range."""
        lo = _bound_to_int(request.args.get("from"), high=False)
        hi = _bound_to_int(request.args.get("to"), high=True)
        if lo is None and hi is None:
            return np.ones(len(self.index), dtype=bool)
        lo = 0 if lo is None else lo
        hi = 99999999 if hi is None else hi
        return self.has_date & (self.date_start <= hi) & (self.date_end >= lo)

    def _location_mask(self):
        """``?location=`` exact place name and/or ``?location_contains=`` case-insensitive substring."""
        exact = request.args.get("location")
        contains = request.args.get("location_contains")
        if not exact and not contains:
            return np.ones(len(self.index), dtype=bool)
        mask = np.zeros(len(self.index), dtype=bool)
        if exact:
            rows = self.location_facet.get(exact)
            if rows is not None:
                mask[rows] = True
        if contains:
            needle = contains.lower()
            for name, rows in self.location_facet.items():
                if needle in name.lower():
                    mask[rows] = True
        return mask

    def _meta_mask(self):
        """date ∧ location — the metadata filter. Basket scope is applied separately via scope.apply."""
        return self._date_mask() & self._location_mask()

    # ---- entity masks + per-request stats + breadcrumb ----------------------------------
    def _fond_mask(self, fond_md5):
        mask = np.zeros(len(self.index), dtype=bool)
        rows = self.index.fond_to_charter_idx.get(fond_md5)
        if rows is not None:
            mask[rows] = True
        return mask

    def _archive_mask(self, archive_id):
        mask = np.zeros(len(self.index), dtype=bool)
        rows = self.index.archive_to_charter_idx.get(archive_id)
        if rows is not None:
            mask[rows] = True
        return mask

    def _archive_of_fond(self, fond_md5):
        key = fond_md5.encode("ascii")
        fpos = int(np.searchsorted(self.index.fond_id, key))
        if fpos >= len(self.index.fond_id) or self.index.fond_id[fpos] != key:
            return None
        return self.index.archive_id[self.index.fond_to_archive_idx[fpos]].decode("ascii")

    def _stats(self, mask):
        """Per-request corpus stats over the charters selected by `mask`. 'charter' == abstract⊕tenor."""
        n_abs = n_ten = abs_chars = ten_chars = 0
        abs_set, ten_set = set(), set()
        for pos in np.nonzero(mask)[0]:
            md5 = self.index.id_of(int(pos))
            a = self.abstracts.get(md5)
            t = self.tenors.get(md5)
            if a:
                n_abs += 1; abs_chars += len(a); abs_set.update(a)
            if t:
                n_ten += 1; ten_chars += len(t); ten_set.update(t)
        charter_set = abs_set | ten_set
        return {
            "charters": int(mask.sum()),
            "with_abstract": n_abs, "with_tenor": n_ten,
            "abstract_chars": abs_chars, "tenor_chars": ten_chars,
            "abstract_charset_len": len(abs_set), "tenor_charset_len": len(ten_set),
            "charter_charset_len": len(charter_set),
            "abstract_charset": "".join(sorted(abs_set)),
            "tenor_charset": "".join(sorted(ten_set)),
            "charter_charset": "".join(sorted(charter_set)),
        }

    def _breadcrumb(self, archive_id=None, fond_md5=None, charter_md5=None):
        """Up-to-4-crumb trail [(label, href), …]; last crumb is current (href None). Captions are
        compact tails from fsdb.Fond/Charter; the root crumb is a home glyph."""
        p = f"/{self.route_prefix}"
        crumbs = [("🏠", f"{p}/")]
        if archive_id:
            crumbs.append((archive_id, f"{p}/archive/{archive_id}"))
        if fond_md5:
            crumbs.append((self._fond_caption(archive_id, fond_md5), f"{p}/fond/{fond_md5}"))
        if charter_md5:
            crumbs.append((self._charter_caption(archive_id, fond_md5, charter_md5), f"{p}/charter/{charter_md5}"))
        label, _ = crumbs[-1]
        crumbs[-1] = (label, None)          # current node -> plain text
        return crumbs

    def _fond_caption(self, archive_id, fond_md5):
        try:
            return Fond(self.index.fsdb_root / archive_id / fond_md5).atom_id.rstrip("/").rsplit("/", 1)[-1]
        except Exception:
            return fond_md5[:10]

    def _charter_caption(self, archive_id, fond_md5, charter_md5):
        try:
            sig = Charter(str(self.index.fsdb_root / archive_id / fond_md5 / charter_md5)).archival_signature
            return sig.rstrip("/").rsplit("/", 1)[-1]
        except Exception:
            return charter_md5[:10]

    def _st_image_src(self):
        """``(available, prefix)`` for Static's IIIF thumbnails. ``available`` is False when no live
        Static (`st`) sibling is known -> the view shows a 'no image service' note. ``prefix`` is
        the URL base the template prepends to ``/st/iiif/…``: **empty** behind a single-origin proxy
        (root-relative, so it resolves against the current origin -- the gateway/tunnel) or Static's
        **absolute** ``base_url`` when proxyless. NEVER return the loopback base_url behind a proxy:
        that points at each viewer's own machine (127.0.0.1)."""
        st = next((s for s in self.siblings if s.get("prefix") == "st"), None)
        if st is None:
            return (False, "")
        return (True, (st.get("base_url") or "") if self.absolute_links else "")

    # ---- serialisation helpers -----------------------------------------------------------
    def _charter_brief(self, pos):
        """A small JSON-able summary for one charter position (for list/search responses)."""
        md5 = self.index.id_of(pos)
        date = None
        if self.has_date[pos]:
            date = {"start": _int_to_iso(int(self.date_start[pos])), "end": _int_to_iso(int(self.date_end[pos]))}
        return {"md5": md5, "date": date, "location": self.location_of[pos],
                "abstract": self.abstracts.get(md5)}

    def _paged(self, ordered, total):
        """(skip, count) from the request + a create_pagers tuple, applied to an ordered list."""
        skip = request.args.get("skip", 0, type=int)
        count = request.args.get("count", self.cfg.page_itemcount, type=int)
        pagers = create_pagers(total, skip, count)
        return ordered[skip:skip + count], skip, count, pagers

    @staticmethod
    def _base_query():
        """Current query string minus skip/count, urlencoded — a stable base for paging links."""
        from urllib.parse import urlencode
        return urlencode([(k, v) for k, v in request.args.items(multi=True) if k not in ("skip", "count")])

    # ---- routes (all under /cei/) --------------------------------------------------------
    def register_routes(self):
        super().register_routes()                 # /cei/basket + /cei/basket/db
        app = self.app
        p = f"/{self.route_prefix}"
        # scope wiring (app.extensions["ddp_ms"]) and the IndexMismatch->409 handler are now
        # inherited from DidipMicroservice -- no local copies needed.

        @app.route(f"{p}/", methods=["GET", "POST"])
        def home():
            """Landing page: whole-slice stats (scope-aware) + a search/filter form (root view).
            ---
            responses:
              200: {description: landing page}
            """
            stats = {"charters": len(self.index), "abstracts": len(self.abstracts),
                     "tenors": len(self.tenors), "dated": int(self.has_date.sum()),
                     "locations": len(self.location_facet)}
            res = scope.apply(np.ones(len(self.index), dtype=bool))
            if request.args.get("format") == "json":
                return jsonify({**stats, "scope": {"active": res.active, "in_scope": res.in_scope,
                                                   "total": res.total, "index_hash": scope.index_hash}})
            return self.render("cei_home.html", stats=stats, scope=res,
                               crumbs=self._breadcrumb(), viewed_root=True)

        @app.route(f"{p}/locations")
        def locations():
            """Location facet: place name -> charter count, optionally filtered by substring.
            ---
            responses:
              200: {description: facet listing}
            """
            needle = (request.args.get("contains") or "").lower()
            facet = sorted(((name, int(len(rows))) for name, rows in self.location_facet.items()
                            if needle in name.lower()), key=lambda kv: (-kv[1], kv[0]))
            if request.args.get("format") == "json":
                return jsonify({"total": len(facet), "locations": [{"name": n, "count": c} for n, c in facet]})
            return self.render("cei_locations.html", facet=facet, needle=needle)

        @app.route(f"{p}/filter", methods=["GET", "POST"])
        def filter_charters():
            """Metadata filter (date ∧ location), intersected with the active basket scope, ordered
            by date, paged (scope view).
            ---
            parameters:
              - {name: from, in: query, type: string, description: "start bound YYYY[-MM[-DD]]"}
              - {name: to, in: query, type: string, description: "end bound YYYY[-MM[-DD]]"}
              - {name: location, in: query, type: string}
              - {name: location_contains, in: query, type: string}
              - {name: scope, in: query, type: string, description: "compact basket (or POST body)"}
              - {name: skip, in: query, type: integer}
              - {name: count, in: query, type: integer}
            responses:
              200: {description: matching charters}
              409: {description: scope references a stale index}
            """
            res = scope.apply(self._meta_mask())
            positions = np.nonzero(res.mask)[0]
            # order by date (undated sink to the end via a large sentinel), stable on md5 order.
            key = np.where(self.has_date[positions], self.date_start[positions], 99999999)
            positions = positions[np.argsort(key, kind="stable")].tolist()
            total = len(positions)
            page, skip, count, pagers = self._paged(positions, total)
            items = [self._charter_brief(int(pos)) for pos in page]
            if request.args.get("format") == "json":
                return jsonify({"total": total, "skip": skip, "count": count,
                                "ids": [it["md5"] for it in items], "items": items,
                                "scope": {"active": res.active, "in_scope": res.in_scope,
                                          "total": res.total, "index_hash": scope.index_hash}})
            return self.render("cei_list.html", items=items, total=total, skip=skip, count=count,
                               pagers=pagers, paging_base_url=f"{p}/filter", base_query=self._base_query(),
                               scope=res, crumbs=self._breadcrumb(),
                               viewed_charter_list=" ".join(it["md5"] for it in items), title="Filter")

        @app.route(f"{p}/search/<field>/<path:pattern>", methods=["GET", "POST"])
        def search(field, pattern):
            """Substring/regex search over abstracts / tenors, intersected with the metadata filter.

            ``field`` is ``abstract``, ``tenor`` or ``all``. Results are ranked by match count and
            each carries a text snippet. Combine with ?from/to/location/scope params + skip/count.
            ---
            responses:
              200: {description: ranked matches}
              404: {description: unknown field}
            """
            indexes = {"abstract": [self.abstract_idx], "tenor": [self.tenor_idx],
                       "all": [self.abstract_idx, self.tenor_idx]}.get(field)
            if indexes is None:
                return jsonify({"error": f"unknown field {field!r} (use abstract|tenor|all)"}), 404
            res = scope.apply(self._meta_mask())     # basket scope ∧ date ∧ location -> allowed set
            allowed = res.mask
            hits: dict[str, dict] = {}
            for stand in indexes:
                for md5, span in stand.find(pattern):
                    md5 = str(md5)
                    pos = self.index.position_of(md5)
                    if pos < 0 or not allowed[pos]:
                        continue
                    entry = hits.get(md5)
                    if entry is None:
                        snippet = stand.get_tttf(md5, (span[0] - 30, span[1] + 30))
                        hits[md5] = {"md5": md5, "score": 1, "snippet": snippet}
                    else:
                        entry["score"] += 1
            ranked = sorted(hits.values(), key=lambda h: (-h["score"], h["md5"]))
            total = len(ranked)
            page, skip, count, pagers = self._paged(ranked, total)
            items = []
            for hit in page:
                brief = self._charter_brief(self.index.position_of(hit["md5"]))
                brief.update(score=hit["score"], snippet=hit["snippet"])
                items.append(brief)
            if request.args.get("format") == "json":
                return jsonify({"total": total, "skip": skip, "count": count,
                                "ids": [it["md5"] for it in items],
                                "scores": [it["score"] for it in items], "items": items,
                                "scope": {"active": res.active, "in_scope": res.in_scope,
                                          "total": res.total, "index_hash": scope.index_hash}})
            return self.render("cei_list.html", items=items, total=total, skip=skip, count=count,
                               pagers=pagers, paging_base_url=f"{p}/search/{field}/{pattern}",
                               base_query=self._base_query(), scope=res, crumbs=self._breadcrumb(),
                               viewed_charter_ranking=" ".join(it["md5"] for it in items),
                               title=f"Search {field}: {pattern}")

        @app.route(f"{p}/archive/<archive_id>", methods=["GET", "POST"])
        def archive_view(archive_id):
            """Archive statistics over its charters (scope-aware), an Archive hand-off view.
            ---
            responses:
              200: {description: archive stats}
              404: {description: unknown archive}
            """
            if archive_id not in self.index.archive_to_charter_idx:
                return jsonify({"error": f"unknown archive {archive_id}"}), 404
            res = scope.apply(self._archive_mask(archive_id))
            stats = self._stats(res.mask)
            if request.args.get("format") == "json":
                return jsonify({"archive": archive_id, "stats": stats,
                                "scope": {"active": res.active, "in_scope": res.in_scope,
                                          "total": res.total, "index_hash": scope.index_hash}})
            return self.render("cei_stats.html", kind="Archive", entity_id=archive_id, stats=stats,
                               scope=res, crumbs=self._breadcrumb(archive_id=archive_id),
                               viewed_archive=archive_id)

        @app.route(f"{p}/fond/<fond_md5>", methods=["GET", "POST"])
        def fond_view(fond_md5):
            """Fond statistics over its charters (scope-aware), a Fond hand-off view.
            ---
            responses:
              200: {description: fond stats}
              404: {description: unknown fond}
            """
            if fond_md5 not in self.index.fond_to_charter_idx:
                return jsonify({"error": f"unknown fond {fond_md5}"}), 404
            archive_id = self._archive_of_fond(fond_md5)
            res = scope.apply(self._fond_mask(fond_md5))
            stats = self._stats(res.mask)
            if request.args.get("format") == "json":
                return jsonify({"fond": fond_md5, "archive": archive_id, "stats": stats,
                                "scope": {"active": res.active, "in_scope": res.in_scope,
                                          "total": res.total, "index_hash": scope.index_hash}})
            return self.render("cei_stats.html", kind="Fond",
                               entity_id=self._fond_caption(archive_id, fond_md5), stats=stats, scope=res,
                               crumbs=self._breadcrumb(archive_id=archive_id, fond_md5=fond_md5),
                               viewed_fond=fond_md5)

        @app.route(f"{p}/charter/<md5>")
        def charter_view(md5):
            """Single charter view: CEI metadata + image strip + sibling hand-off. Scope does NOT
            apply to a single-item view (the `scope` proxy is never touched here).
            ---
            responses:
              200: {description: charter page}
              404: {description: unknown charter}
            """
            pos = self.index.position_of(md5)
            if pos < 0:
                return jsonify({"error": f"unknown charter {md5}"}), 404
            date = None
            if self.has_date[pos]:
                date = {"start": _int_to_iso(int(self.date_start[pos])), "end": _int_to_iso(int(self.date_end[pos]))}
            record = {"md5": md5, "date": date, "location": self.location_of[pos],
                      "abstract": self.abstracts.get(md5), "tenor": self.tenors.get(md5)}
            if request.args.get("format") == "json":
                return jsonify(record)
            archive_id, fond_md5, _ = self.index.charter_relpath(pos).split("/")
            try:
                charter = Charter(path=str(self.index.charter_path(pos)))
                signature = charter.archival_signature
                image_ids = getattr(charter, "guessed_imageid_order", None) or charter.image_ids
            except Exception:
                signature, image_ids = None, []
            st_available, st_base = self._st_image_src()
            return self.render("cei_charter.html", record=record, signature=signature,
                               image_ids=image_ids, st_available=st_available, st_base=st_base, sibling_md5=md5,
                               crumbs=self._breadcrumb(archive_id=archive_id, fond_md5=fond_md5, charter_md5=md5),
                               viewed_charter=md5)


def serve_cli_main():
    """``ddpa_cei2json_serve`` entry point: build the service and serve it."""
    Cei2JsonMicroservice().run()


if __name__ == "__main__":
    serve_cli_main()
