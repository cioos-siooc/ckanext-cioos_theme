"""Find the collections a dataset belongs to, from its own aggregation-info.

A dataset belongs to a collection when one of its aggregation-info entries has
initiative-type "collection". That entry's identifier gives the collection UUID
and its name gives the collection title (EN/FR).

The collection UUID is stored with its prefix, e.g. ca-cioos_<uuid>, the same
value as in the collection's catalogue URL.
"""

import json
import logging
import re

log = logging.getLogger(__name__)

UUID_PATTERN = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
UUID_RE = re.compile(UUID_PATTERN, re.IGNORECASE)

# A UUID, with the prefix in front of it if there is one (ca-cioos_ or ca.cioos_).
PREFIXED_UUID_RE = re.compile(
    r"(?:([0-9a-z.-]+)_)?(" + UUID_PATTERN + ")", re.IGNORECASE
)

# Prefix used when a link has a UUID with no prefix. CIOOS records always use ca.cioos.
DEFAULT_PREFIX = "ca-cioos"


def _decode(value):
    """Decode a JSON string; return any other value unchanged."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


def find_uuid(text):
    """Return the first UUID in text, lower-cased, or None.

    Only the 8-4-4-4-12 form with hyphens is found. A UUID written without
    hyphens is ignored on purpose: other IDs (e.g. MD5 hashes) look the same.
    """
    match = UUID_RE.search(text or "")
    return match.group(0).lower() if match else None


def find_collection(text):
    """Return (uuid, collection UUID with prefix) from a link, or (None, None).

    Examples:
    - "https://.../dataset/ca-cioos_<uuid>" -> "ca-cioos_<uuid>"
    - "ca.cioos_<uuid>"                      -> "ca-cioos_<uuid>"  ("." becomes "-")
    - "<uuid>" (no prefix)                   -> "ca-cioos_<uuid>"  (assumes CIOOS)
    - "https://.../dataset/ca-gc-dfo-mpo-cnodc-cndoc_<uuid>" keeps its own prefix
    """
    match = PREFIXED_UUID_RE.search(text or "")
    if not match:
        return None, None
    prefix, uuid = match.group(1), match.group(2).lower()
    prefix = prefix.lower().replace(".", "-") if prefix else DEFAULT_PREFIX
    return uuid, f"{prefix}_{uuid}"


def _names(value, fallback):
    """Return {"en": ..., "fr": ...}, each language falling back to the other."""
    value = _decode(value)
    if isinstance(value, dict):
        en = (value.get("en") or "").strip()
        fr = (value.get("fr") or "").strip()
    else:
        en = fr = (value or "").strip() if isinstance(value, str) else ""
    return {"en": en or fr or fallback, "fr": fr or en or fallback}


def extract_collections(aggregation_info, dataset_name=""):
    """Return the dataset's collections as a list of (collection UUID, {"en", "fr"} title).

    The collection UUID has its prefix, e.g. "ca-cioos_<uuid>".
    - aggregation_info: the dataset's aggregation-info (a list or a JSON string).
    - dataset_name: the dataset's own name, used to skip a link to itself.
    Links with no UUID (e.g. a DOI) are skipped and logged.
    The same collection linked twice is counted once.
    """
    entries = _decode(aggregation_info)
    if not isinstance(entries, list):
        return []

    own_uuid = find_uuid(dataset_name)
    collections = []
    seen = set()
    for item in entries:
        if not isinstance(item, dict) or item.get("initiative-type") != "collection":
            continue
        code = item.get("aggregate-dataset-identifier_code") or ""
        uuid, collection_id = find_collection(code)
        if not uuid:
            log.warning(
                "Dataset %s: collection link %r has no UUID; not indexed",
                dataset_name,
                code,
            )
            continue
        # Compare bare UUIDs, so "ca.cioos_<uuid>" and "ca-cioos_<uuid>" count as one.
        if uuid == own_uuid or uuid in seen:
            continue
        seen.add(uuid)
        title = _names(item.get("aggregate-dataset-name"), collection_id)
        collections.append((collection_id, title))
    return collections
