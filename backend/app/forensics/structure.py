"""Generator fingerprints: how a genuine file from a given producer is *built*, learned from real samples.

A forger can keep the /Producer string, fonts and layout, but re-saving through another library
changes low-level syntax (line endings, xref form, dictionary spacing, object streams). We learn
the set of values each generator produces from genuine public samples and report deviations.
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from ..config import DATA

PROFILE_PATH = DATA / "generator_profiles.json"


def features(raw: bytes) -> dict:
    head = raw[:16]
    m = re.match(rb"%PDF-(\d\.\d)", head)
    obj_heads = re.findall(rb"\d+ 0 obj(\r\n|\r|\n| )", raw[:400000])
    eol = Counter(x.decode("latin1").replace("\r", "CR").replace("\n", "LF").replace(" ", "SP") for x in obj_heads)
    spaced = len(re.findall(rb"<< /", raw[:400000])) + len(re.findall(rb"<<\n/", raw[:400000]))
    compact = len(re.findall(rb"<</", raw[:400000]))
    return {
        "version": m.group(1).decode() if m else "?",
        "obj_eol": eol.most_common(1)[0][0] if eol else "?",
        "xref": "stream" if b"/Type/XRef" in raw or b"/Type /XRef" in raw else "table",
        "objstm": b"/ObjStm" in raw,
        "has_id": b"/ID" in raw[-4096:] or b"/ID[" in raw or b"/ID [" in raw,
        "dict_style": "compact" if compact > spaced * 2 else ("spaced" if spaced > compact * 2 else "mixed"),
        "xmp": b"<x:xmpmeta" in raw or b"/Metadata" in raw,
    }


def build_profiles(samples: list[tuple[str, bytes]]) -> dict:
    """samples: (producer, raw) of files believed genuine & unmodified."""
    prof: dict[str, dict] = defaultdict(lambda: {"n": 0, "values": defaultdict(Counter)})
    for producer, raw in samples:
        p = prof[producer]
        p["n"] += 1
        for k, v in features(raw).items():
            p["values"][k][str(v)] += 1
    out = {k: {"n": v["n"], "values": {f: dict(c) for f, c in v["values"].items()}} for k, v in prof.items()}
    PROFILE_PATH.write_text(json.dumps(out, indent=2), "utf-8")
    return out


def load_profiles() -> dict:
    return json.loads(PROFILE_PATH.read_text("utf-8")) if PROFILE_PATH.exists() else {}


def compare(producer: str, raw: bytes, profiles: dict | None = None) -> dict | None:
    profiles = profiles if profiles is not None else load_profiles()
    prof = profiles.get(producer)
    if not prof or prof["n"] < 3:
        return None
    f = features(raw)
    deviations = []
    for k, v in f.items():
        seen = prof["values"].get(k, {})
        share = seen.get(str(v), 0) / prof["n"]
        dominant = max(seen.values()) / prof["n"] if seen else 0
        # A feature is evidence only if genuine files from this generator agree on it (>= 90%);
        # features that vary among genuine files (e.g. dict spacing in Oracle letters) are ignored.
        if share < 0.05 and dominant >= 0.90:
            expected = max(seen, key=seen.get) if seen else "?"
            deviations.append({"feature": k, "observed": str(v), "expected": expected,
                               "expected_share": round(seen.get(expected, 0) / prof["n"], 2)})
    return {"producer": producer, "samples": prof["n"], "features": f, "deviations": deviations}
