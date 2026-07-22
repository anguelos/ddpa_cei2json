"""ddpa_cei2json offline mode (mode 2 — the map).

Pure per-charter map over an FSDB: read each charter's ``CH.cei.xml`` and write one
``CH.cei2json.pred.json`` next to it. Idempotent and resumable (existing outputs are
skipped by the harness; writes are atomic). No cross-charter state.
"""

import json
import os
import sys
import time
import traceback

import fargv
from fsdb import CharterFargvConfig, generate_charter_paths

from .cei_extract import cei_to_dict
from .version import __version__

#: provenance stamped into every output (app namespace + code version).
PROVENANCE = f"app:cei2json,version:{__version__}"


@fargv.deep_dataclass
class Config(CharterFargvConfig):
    """Extract CEI metadata (date span, location, abstract, tenor) into one JSON per charter."""

    output_replace: str = "/CH.cei2json.pred.json"
    "Suffix that names the output; leading '/' keeps it charter-level (CH.<app>.<what>.json)."
    cei_filename: str = "CH.cei.xml"
    "The CEI XML file inside each charter directory."
    resume_on_exception: bool = True
    "Log and skip charters that fail to parse instead of aborting the whole run."
    verbosity: int = fargv.FargvInt(0, short_name="v", is_count_switch=True)
    "-v final summary, -vv tqdm bar, -vvv per-skip debug from the harness."


def _atomic_write_json(path: str, obj: dict) -> None:
    """Write JSON to a temp file in the same dir, then os.replace — no truncated outputs."""
    tmp = f"{path}.tmp.{os.getpid()}"
    with open(tmp, "w") as f:
        json.dump(obj, f, ensure_ascii=False)
    os.replace(tmp, path)


def main():
    cfg, _ = fargv.parse(Config)
    pairs = generate_charter_paths(cfg, generate_output=True, verbosity=cfg.verbosity)
    if cfg.verbosity >= 2:
        from tqdm import tqdm
        pairs = tqdm(pairs, desc="cei2json")
    processed = failed = 0
    t = time.time()
    for charter_path, output_path in pairs:
        cei_path = os.path.join(charter_path, cfg.cei_filename)
        try:
            record = cei_to_dict(cei_path)
            record["user"] = PROVENANCE
            _atomic_write_json(output_path, record)
            processed += 1
        except Exception:
            failed += 1
            print(f"cei2json_offline: failed on {charter_path}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            if not cfg.resume_on_exception:
                sys.exit(1)
    if cfg.verbosity >= 1:
        print(f"cei2json_offline: {processed} written, {failed} failed in {time.time() - t:.3g}s.", file=sys.stderr)


if __name__ == "__main__":
    main()
