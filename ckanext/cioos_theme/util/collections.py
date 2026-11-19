"""Find the collections a dataset belongs to, from its own aggregation-info.

A dataset belongs to a collection when one of its aggregation-info entries has
initiative-type "collection". That entry's identifier gives the collection ID
and its name gives the collection title (EN/FR).

The collection ID is:
- the DOI, if the link is a DOI, e.g. 10.60622/v6nn-kw50
- otherwise the collection UUID with its prefix, e.g. ca-cioos_<uuid>, the same
  value as in the collection's catalogue URL.
A DOI link and a UUID link to the same collection give two different IDs; both
have the same title, so they show as one entry in the Collections facet.
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

# A DOI (10.<registrant>/<suffix>), bare or written as doi:..., https://doi.org/...
# or https://dx.doi.org/...
DOI_RE = re.compile(
    r"^(?:doi:|https?://(?:dx\.)?doi\.org/)?(10\.\d{4,9}/\S+)$", re.IGNORECASE
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

    Only the 8-4-4-4-12 form with hyphens is found. A UUID written without
    hyphens is ignored on purpose: other IDs (e.g. MD5 hashes) look the same.
    """
    match = UUID_RE.search(text or "")
    return match.group(0).lower() if match else None


def find_doi(text):
    """Return the DOI in text, lower-cased and without doi: / https://doi.org/, or None.

    DOIs are not case-sensitive, so lower-casing lets different spellings match.
    """
    match = DOI_RE.match((text or "").strip())
    return match.group(1).lower() if match else None


def find_collection(text):
    """Return (key, collection ID) from a link, or (None, None).

    A DOI is checked first, then a UUID. The key is used to spot the same
    collection linked twice (the DOI, or the bare UUID).

    Examples:
    - "https://doi.org/10.60622/v6nn-kw50"   -> "10.60622/v6nn-kw50"
    - "doi:10.60622/v6nn-kw50"               -> "10.60622/v6nn-kw50"
    - "https://.../dataset/ca-cioos_<uuid>" -> "ca-cioos_<uuid>"
    - "ca.cioos_<uuid>"                      -> "ca-cioos_<uuid>"  ("." becomes "-")
    - "<uuid>" (no prefix)                   -> "ca-cioos_<uuid>"  (assumes CIOOS)
    - "https://.../dataset/ca-gc-dfo-mpo-cnodc-cndoc_<uuid>" keeps its own prefix
    """
    doi = find_doi(text)
    if doi:
        return doi, doi

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
    """Return the dataset's collections as a list of (collection ID, {"en", "fr"} title).

    The collection ID is a DOI (e.g. "10.60622/v6nn-kw50") or a collection UUID
    with its prefix (e.g. "ca-cioos_<uuid>"); see find_collection.
    - aggregation_info: the dataset's aggregation-info (a list or a JSON string).
    - dataset_name: the dataset's own name, used to skip a link to itself.
    Links with neither a DOI nor a UUID (e.g. an ERDDAP URL) are skipped and logged.
    The same collection linked twice in the same form is counted once.
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
        key, collection_id = find_collection(code)
        if not key:
            log.warning(
                "Dataset %s: collection link %r has no DOI or UUID; not indexed",
                dataset_name,
                code,
            )
            continue
        # Compare keys (DOI or bare UUID), so "ca.cioos_<uuid>" and "ca-cioos_<uuid>"
        # count as one. A link to the dataset's own UUID is skipped.
        if key == own_uuid or key in seen:
            continue
        seen.add(key)
        title = _names(item.get("aggregate-dataset-name"), collection_id)
        collections.append((collection_id, title))
    return collections
