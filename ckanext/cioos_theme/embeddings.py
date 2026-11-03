"""Text embeddings for semantic search ranking.

Vectors come from the `embeddings` compose service (Hugging Face
text-embeddings-inference) at ``ckan.cioos.embeddings_url``. The model is
multilingual, so English and French text share one vector space and a single
vector per dataset serves both UI languages.

Every failure is logged and returns None: callers then index the dataset
without a vector or rank the search lexically, so search never breaks
because the service is down or unset.
"""

import logging
import re
import time

import requests
import ckan.plugins.toolkit as toolkit

log = logging.getLogger(__name__)

# Seconds to wait for the service: short at query time (a user is waiting),
# longer when indexing (harvests and reindexes).
QUERY_TIMEOUT = 2
INDEX_TIMEOUT = 30
CONNECT_TIMEOUT = 1
# After a failure, skip the service for this many seconds (per process) so an
# outage costs one timeout, not one per search or per indexed dataset.
RETRY_AFTER = 60

_unavailable_until = 0.0

_CAMEL_CASE = re.compile(r"(?<=[a-z])(?=[A-Z])")


def embed(text, timeout):
    """Return the embedding of ``text`` as a list of floats, or None."""
    global _unavailable_until
    url = toolkit.config.get("ckan.cioos.embeddings_url")
    if not url or not text or time.monotonic() < _unavailable_until:
        return None
    try:
        response = requests.post(
            url.rstrip("/") + "/embed",
            json={"inputs": text, "truncate": True},
            timeout=(CONNECT_TIMEOUT, timeout),
        )
        response.raise_for_status()
        return response.json()[0]
    except (requests.RequestException, ValueError, LookupError) as err:
        _unavailable_until = time.monotonic() + RETRY_AFTER
        log.warning(
            "Embeddings service unavailable, searching and indexing without "
            "vectors for %ss: %s",
            RETRY_AFTER,
            err,
        )
        return None


def dataset_passage(data_dict):
    """Text embedded for a dataset, from the fields before_dataset_index derives.

    The model reads at most 128 tokens, so the short, high-signal fields come
    first and the abstract last (adapted from build_rich_document in
    cioos-siooc/cioos-search-engine).
    """

    def first(*values):
        return next((v for v in values if v and isinstance(v, str)), "")

    eovs = data_dict.get("eov") or []
    if isinstance(eovs, str):
        eovs = [eovs]
    parts = [
        first(data_dict.get("title_en"), data_dict.get("title_fr"), data_dict.get("title")),
        ", ".join(_CAMEL_CASE.sub(" ", eov).lower() for eov in eovs),
        ", ".join(data_dict.get("tags_en") or data_dict.get("tags_fr") or []),
        first(data_dict.get("organization_en"), data_dict.get("organization_fr")),
        first(data_dict.get("notes_en"), data_dict.get("notes_fr"), data_dict.get("notes")),
    ]
    return ". ".join(p for p in parts if p)
