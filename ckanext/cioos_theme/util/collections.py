"""Collection links read from a dataset's own aggregation-info.

A dataset belongs to a collection when one of its aggregation-info entries
(ISO 19115 MD_AssociatedResource) has initiative-type "collection". The entry's
identifier carries the collection's UUID (bare, as a catalogue URL, or as a
dataset name such as ca-cioos_<uuid>) and its name carries the collection's
title. Only the dataset's own metadata is read, so the collection dataset
does not need to exist, or be indexed, first.
"""

import json
import logging
import re

log = logging.getLogger(__name__)

UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE
)


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

    Only the hyphenated 8-4-4-4-12 form is recognised, wherever it appears
    (bare, upper case, urn:uuid:, {braces}, ca-cioos_ / ca.cioos_ prefixes, URLs).
    A UUID written without hyphens (32 hex digits) is not matched on purpose:
    MD5 hashes and other IDs look the same, so matching them could index
    something that isn't a collection. Such links are skipped and logged.
    If the text holds several UUIDs, only the first is returned.
    """
    match = UUID_RE.search(text or "")
    return match.group(0).lower() if match else None


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
    """List the collections a dataset belongs to, as (uuid, {"en", "fr"}) tuples.

    aggregation_info is the dataset's aggregation-info value (a list, or a JSON
    string of one). dataset_name is the dataset's own name; a link to its own
    UUID is ignored. Entries whose identifier holds no UUID (e.g. a DOI) are
    skipped with a warning. Each collection appears once, in first-seen order.
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
        uuid = find_uuid(code)
        if not uuid:
            log.warning(
                "Dataset %s: collection link %r has no UUID; not indexed",
                dataset_name,
                code,
            )
            continue
        if uuid == own_uuid or uuid in seen:
            continue
        seen.add(uuid)
        collections.append((uuid, _names(item.get("aggregate-dataset-name"), uuid)))
    return collections
