"""
OGSL custom template helper function.

Consists of functions typically used within templates, but also
available to Controllers. This module is available to templates as 'h'.

"""

import copy
import json
import logging
import re
from collections import OrderedDict

# from ckantoolkit import h
import ckan.logic as logic
import ckan.model as model
import ckan.plugins as p
import ckan.plugins.toolkit as toolkit
import importlib_metadata as metadata
import jsonpickle
from ckan.common import config
from ckantoolkit import _, c, config

from ckanext.dcat.processors import RDFSerializer

log = logging.getLogger(__name__)

try:
    # CKAN >= 2.6
    from ckan.exceptions import HelperError
except ImportError:
    # CKAN < 2.6
    class HelperError(Exception):
        pass


get_action = logic.get_action


def composite_separator():
    """Return the composite field separator used by ckanext-scheming.

    ckanext-scheming uses a separator character to construct flat field names
    from composite (nested) fields. The default is '-' (hyphen), matching
    the hardcoded value in scheming's expand_form_composite().

    This can be overridden via the 'scheming.composite.separator' config setting.
    """
    return config.get("scheming.composite.separator", "-")


def load_json(j):
    try:
        new_val = json.loads(j)
    except Exception:
        new_val = j
    return new_val


def load_about_markdown():
    """
    Load about page content from markdown files.

    Supports multilingual markdown files via ckan.site_about_markdown_file config.

    Config format (JSON string):
    {"en": "/path/to/about_en.md", "fr": "/path/to/about_fr.md"}

    Returns:
        dict: Dictionary with language keys and markdown content, or None if not configured
    """
    markdown_file_config = config.get("ckan.site_about_markdown_file")

    if not markdown_file_config:
        return None

    try:
        # Parse the JSON config
        file_paths = load_json(markdown_file_config)

        if not isinstance(file_paths, dict):
            log.warning(
                "ckan.site_about_markdown_file must be a JSON object with language keys"
            )
            return None

        markdown_content = {}

        # Load markdown files for each language
        for lang, file_path in file_paths.items():
            if not file_path:
                continue

            try:
                with open(file_path, encoding="utf-8") as f:
                    markdown_content[lang] = f.read()
            except FileNotFoundError:
                log.error(f"About markdown file not found: {file_path}")
            except OSError as e:
                log.error(f"Error reading about markdown file {file_path}: {e}")

        return markdown_content if markdown_content else None

    except Exception as e:
        log.error(f"Error loading about markdown files: {e}")
        return None


# def get_organization_list(data_dict):
#     '''Returns a list of organizations.
#
#     :param id: the id or name of the organization
#     '''
#     # If a context of None is passed to the action function then the default context dict will be created
#     # All other parameters are optional and are set to their default value
#     # cf. http://docs.ckan.org/en/latest/extensions/plugins-toolkit.html#ckan.plugins.toolkit.ckan.plugins.toolkit.get_action
#     return toolkit.get_action('organization_list')(None, data_dict = data_dict)
#
# def get_organization_dict(id):
#     '''Returns the details of an organization.
#
#     :param id: the id or name of the organization
#     '''
#     # If a context of None is passed to the action function then the default context dict will be created
#     # All other parameters are optional and are set to their default value
#     # cf. http://docs.ckan.org/en/latest/api/index.html#ckan.logic.action.get.organization_show
#     return toolkit.get_action('organization_show')(None, data_dict = {'id': id})
#
# def get_organization_dict_extra(organization_dict, key, default=None):
#     '''Returns the value for the organization extra with the provided key.
#
#     If the key is not found, it returns a default value, which is None by
#     default.
#
#     :param organization_dict: dictized organization
#     :key: extra key to lookup
#     :default: default value returned if not found
#     '''
#     extras = organization_dict['extras'] if 'extras' in organization_dict else []
#
#     for extra in extras:
#         if extra['key'] == key:
#             return extra['value']
#
#     return default


# copied from dcat extension
def helper_available(helper_name):
    """
    Checks if a given helper name is available on `h`
    """
    try:
        getattr(toolkit.h, helper_name)
    except (AttributeError, HelperError):
        return False
    return True


def generate_doi_suffix():
    import random

    chars = [
        "a",
        "b",
        "c",
        "d",
        "e",
        "f",
        "g",
        "h",
        "j",
        "k",
        "m",
        "n",
        "p",
        "q",
        "r",
        "s",
        "t",
        "u",
        "v",
        "w",
        "x",
        "y",
        "z",
        "0",
        "1",
        "2",
        "3",
        "4",
        "5",
        "6",
        "7",
        "8",
        "9",
    ]
    str1 = "".join(random.SystemRandom().choice(chars) for _ in range(4))
    str2 = "".join(random.SystemRandom().choice(chars) for _ in range(4))
    return str1 + "-" + str2


def get_doi_authority_url():
    return toolkit.config.get("ckan.cioos.doi_authority_url", "https://doi.org/")


def get_doi_prefix():
    return toolkit.config.get("ckan.cioos.doi_prefix")


def get_datacite_org():
    return toolkit.config.get("ckan.cioos.datacite_org")


def get_datacite_test_mode():
    return toolkit.config.get("ckan.cioos.datacite_test_mode", "True")


def get_ra_extents_url():
    # './ckanext-cioos_theme/ckanext/cioos_theme/public/base/layers/pacific_RA.json'
    ra_file_url = toolkit.config.get("ckan.cioos.ra_json_file", "null")
    return ra_file_url


def get_dataset_extents_url(q, fields, bbox_values, output=None):
    search_params = {
        "q": q,
        "fl": "spatial",
        "fq_list": [],
        "facet": "false",
        "rows": 1000,
    }

    clean_fields = [(i, '("%s")' % j) for i, j in fields]
    search_params["fq_list"] = search_params["fq_list"] + [
        "+%s" % ":".join(x) for x in clean_fields
    ]
    search_params["fq"] = "".join(search_params["fq_list"])
    del search_params["fq_list"]

    # search_params['output'] = 'geojson'
    if bbox_values:
        # ids = toolkit.get_action('spatial_query_geo')(data_dict={'bbox':bbox_values})
        search_params["bbox"] = bbox_values

    # Try known spatial API endpoints across ckanext-spatial versions
    endpoints = [
        "spatial_api.geo_package_search",
        "spatial_api.package_search",
        "spatial_api.geojson_package_search",
    ]
    for ep in endpoints:
        try:
            return toolkit.h.url_for(ep, register="dataset", **search_params)
        except Exception:
            continue
    # Fallback: return empty string to avoid BuildError at render time
    return ""


def merge_dict(d1, d2):
    return {**d1, **d2}


def get_license_def(id, url="", title=""):
    licenses = toolkit.get_action("license_list")()

    locales_offered = toolkit.config.get("ckan.locales_offered", [])
    if isinstance(locales_offered, str):
        locales_offered = locales_offered.split() if locales_offered.strip() else []
    default_locale = toolkit.config.get("ckan.locale_default") or (
        locales_offered[0] if locales_offered else "en"
    )
    lang = toolkit.h.lang() or default_locale

    # check for id first
    for license in licenses:
        if id.lower() == license["id"].lower() or id.lower() in [
            x.lower() for x in license.get("legacy_ids", [])
        ]:
            return {
                "license_id": license["id"],
                "license_url": license.get("url_" + lang, license["url"]),
                "license_title": license.get("title_" + lang, license["title"]),
            }

    # if that fails match on url or title next
    if url or title:
        for license in licenses:
            if url == license.get("url_" + lang, license["url"]):
                return {
                    "license_id": license["id"],
                    "license_url": license.get("url_" + lang, license["url"]),
                    "license_title": license.get("title_" + lang, license["title"]),
                }
            if title.lower() == license.get("title_" + lang, license["title"]).lower():
                return {
                    "license_id": license["id"],
                    "license_url": license.get("url_" + lang, license["url"]),
                    "license_title": license.get("title_" + lang, license["title"]),
                }
    return None


def get_fully_qualified_package_uri(pkg, uri_field, default_code_space=None):
    fqURI = []
    uris = pkg.get(uri_field)

    if not uris:
        # try to build out of flat fields
        uris = (
            [
                {
                    "authority": pkg.get(uri_field + "authority"),
                    "code-space": pkg.get(uri_field + "code-space"),
                    "code": pkg.get(uri_field + "code"),
                    "version": pkg.get(uri_field + "version"),
                }
            ]
            if pkg.get(uri_field + "code")
            else None
        )

    if not uris:
        return fqURI

    if isinstance(uris, dict):
        uris = [uris]

    for uri in uris:
        uri = toolkit.h.cioos_load_json(uri)
        if not uri:
            continue
        code_space = uri.get("code-space") or default_code_space
        code = uri.get("code")
        if isinstance(code, list):
            code = code[0]
        version = uri.get("version")
        if not code:
            continue
        if toolkit.h.is_url(code):
            fqURI.append(code)
            continue
        out_code = code
        if code_space not in out_code:
            out_code = code_space + "/" + out_code
        if not toolkit.h.is_url(out_code):
            out_code = "https://" + out_code

        fqURI.append(out_code)
    return fqURI


def get_package_relationships(pkg):
    # compare schema field, here called aggregation-info and
    # package relationships.
    relationships = pkg.get("aggregation-info", [])
    rels_from_schema = []
    for rel in relationships:
        comment = "/".join(
            filter(None, [rel.get("initiative-type"), rel.get("association-type")])
        )
        comment = re.sub(r"([A-Z])", r" \1", comment)
        comment = comment.title()

        rel_uri = rel.get("aggregate-dataset-identifier_code")
        rel_name = rel.get("aggregate-dataset-name")

        map_type = {
            "largerWorkCitation": "parent",
            "crossReference": "cross link",
            "dependency": "depends on",
            "revisionOf": "revision of",
            "series": "cross link",
            "isComposedOf": "child",
        }
        rel_type = map_type.get(rel.get("association-type"), "links to")

        if rel_uri and rel_name:
            rels_from_schema.append(
                {
                    "subject": pkg["name"],
                    "type": rel_type,
                    "object": {"title": rel_name, "url": rel_uri},
                    "comment": comment,
                }
            )
    return rels_from_schema


# the following functions have been depricated. use above function instead
# def get_package_relationships(pkg):
#     '''Returns the relationships of a package.

#     :param id: the id or name of the package
#     '''
#     rel = pkg.get('relationships_as_subject') + pkg.get('relationships_as_object')
#     b = []
#     for x in rel:
#         if x not in b:
#             b.append(x)
#     return b


# def print_package_relationship_type(type):
#     out = 'depends on'
#     if 'child' in type:
#         out = 'parent'
#     elif 'parent' in type:
#         out = 'child'
#     elif 'link' in type:
#         out = 'cross link'
#     return out


# def get_package_relationship_reverse_type(type):
#     return PackageRelationship.reverse_type(type)


# def get_package_title(id):
#     '''Returns the title of a package.

#     :param id: the id or name of the package
#     '''
#     try:
#         pkg = toolkit.get_action('package_show')(None, data_dict={'id': id})
#     except Exception as e:
#         return None
#     return toolkit.h.get_translated(pkg, 'title')


def _merge_lists(key, list1, list2):
    merged = {}
    for item in list1 + list2:
        if item[key] in merged:
            merged[item[key]].update(item)
        else:
            merged[item[key]] = item
    return [v for (k, v) in merged.items()]


def cioos_get_eovs(show_all=False):
    """Return a list of eov's in a similar format to the facet list
    If show_all is true then the complete list of eov's is returned. The name
    and display_name fields are updated from the eoc choices list as found in
    ckanext-scheming. If show_all is false only the eov's returned as part of
    the active facet list are returned.

    param show_all: display all eov fields or only the ones that are currently
                    active.
    """
    schema = toolkit.h.scheming_get_dataset_schema("dataset")
    choices = []
    # needed to make get_facet_items_dict work
    toolkit.h.cioos_get_facets(package_type="dataset", facet_list=["eov"])
    search_facets = getattr(toolkit.c, "search_facets", {}) or {}
    eov = search_facets.get("eov", {}).get("items", [])
    if not eov:
        eov = toolkit.h.get_facet_items_dict("eov", limit=None, exclude_active=False)

    try:
        # retreave a copy of the choices list for the eov field
        choices = copy.deepcopy(
            toolkit.h.scheming_field_choices(
                toolkit.h.scheming_field_by_name(schema["dataset_fields"], "eov")
            )
        )
        # make choices list more facet like
        for x in choices:
            x["name"] = x["value"]
            x["display_name"] = x["label"]
    except:
        pass

    if show_all:
        # TODO: could this be improved?
        output = _merge_lists("name", eov, choices)
    else:
        lookup = {x["name"]: x for x in eov}
        for x in choices:
            if x["name"] in lookup:
                lookup[x["name"]].update(x)
        output = list(lookup.values())

    for x in output:
        # set count to zero for eov's not in facet list
        if "count" not in x:
            x["count"] = 0
        # generate icon file name if not set
        if "icon" not in x:
            x["icon"] = "icon-" + x["name"].lower() + ".png"
    return output


def cioos_count_datasets():
    """Return a count of datasets"""
    user = logic.get_action("get_site_user")({"model": model, "ignore_auth": True}, {})
    context = {"model": model, "session": model.Session, "user": user["name"]}
    # Get a list of all the site's datasets from CKAN, no need to return actual data
    datasets = logic.get_action("package_search")(context, {"fl": "id", "rows": "0"})
    return datasets["count"]


_CENTROID_CACHE = {"key": None, "value": None}


def _centroid_and_bbox_from_spatial(spatial_str):
    """Compute centroid + bbox from a GeoJSON `spatial` value.

    Returns ([lon, lat], [west, south, east, north]) or (None, None) on failure.
    Points return a degenerate bbox (the point's coords repeated).
    """
    try:
        geom = json.loads(spatial_str) if isinstance(spatial_str, str) else spatial_str
    except (TypeError, ValueError):
        return None, None
    if not geom:
        return None, None
    gtype = geom.get("type")
    coords = geom.get("coordinates")
    if not coords:
        return None, None
    try:
        if gtype == "Point":
            lon, lat = coords[0], coords[1]
            if not (-180 <= lon <= 180 and -90 <= lat <= 90):
                return None, None
            return (
                [round(lon, 4), round(lat, 4)],
                [round(lon, 4), round(lat, 4), round(lon, 4), round(lat, 4)],
            )
        # Flatten arbitrarily nested coordinate arrays to leaf [lon, lat] pairs.
        stack = [coords]
        xs, ys = [], []
        while stack:
            node = stack.pop()
            if (
                isinstance(node, (list, tuple))
                and len(node) >= 2
                and isinstance(node[0], (int, float))
                and isinstance(node[1], (int, float))
            ):
                xs.append(node[0])
                ys.append(node[1])
            elif isinstance(node, (list, tuple)):
                stack.extend(node)
        if not xs:
            return None, None
        west, east = min(xs), max(xs)
        south, north = min(ys), max(ys)
        lon = (west + east) / 2.0
        lat = (south + north) / 2.0
        if not (-180 <= lon <= 180 and -90 <= lat <= 90):
            return None, None
        return (
            [round(lon, 4), round(lat, 4)],
            [round(west, 4), round(south, 4), round(east, 4), round(north, 4)],
        )
    except (TypeError, ValueError, IndexError):
        return None, None


def _centroid_from_spatial(spatial_str):
    """Back-compat wrapper — returns just the centroid."""
    centroid, _bbox = _centroid_and_bbox_from_spatial(spatial_str)
    return centroid


def _extract_spatial_from_pkg(pkg):
    """Find the GeoJSON spatial value on a package_search result, regardless
    of whether ckanext-spatial promoted it to a top-level Solr field, kept it
    as a flattened extra, or left it inside the `extras` list."""
    for key in ("extras_spatial", "spatial"):
        val = pkg.get(key)
        if val:
            return val
    for extra in pkg.get("extras", []) or []:
        if extra.get("key") == "spatial" and extra.get("value"):
            return extra["value"]
    return None


def cioos_get_dataset_centroids(max_rows=15000, force_refresh=False):
    """Return a JSON string of dataset centroids for the home-page filter map.

    Output shape (positional, to keep the payload small for 10k+ points):
        [[name, title, lon, lat, [west, south, east, north]], ...]
    The bbox is included so the client can render the dataset's spatial
    extent on click without a follow-up fetch.

    Cache invalidation:
      - Dataset count change (add/delete) — keyed on Solr `numFound`.
      - Explicit invalidation via `cioos_invalidate_dataset_centroids()`,
        called from IPackageController after_dataset_create/update/delete
        hooks so edits to `spatial` on existing datasets propagate
        immediately.

    Pass `force_refresh=True` to bypass the cache (e.g. from a CLI command).
    """
    user = logic.get_action("get_site_user")({"model": model, "ignore_auth": True}, {})
    context = {"model": model, "session": model.Session, "user": user["name"]}

    # Get total count first (cheap, just for cache keying). No spatial filter
    # here — Solr field naming for the spatial extra varies between CKAN
    # versions and we'd rather over-fetch + filter in Python than miss rows.
    try:
        head = logic.get_action("package_search")(
            context, {"fl": "id", "rows": "0"}
        )
    except Exception:
        log.exception("centroids: package_search count failed")
        return "[]"
    count = head.get("count", 0)

    cached = _CENTROID_CACHE
    if (
        not force_refresh
        and cached["key"] == count
        and cached["value"] is not None
    ):
        return cached["value"]

    # CKAN caps `package_search` at `ckan.search.rows_max` (default 1000) and
    # silently strips post-processed fields like `spatial` when `fl` is set,
    # so we paginate full-record fetches.
    page_size = 1000
    target = min(count, max_rows)
    points = []
    skipped_no_spatial = 0
    skipped_bad_geom = 0
    start = 0
    while start < target:
        try:
            result = logic.get_action("package_search")(
                context,
                {"rows": str(min(page_size, target - start)), "start": str(start)},
            )
        except Exception:
            log.exception("centroids: package_search page start=%d failed", start)
            return cached["value"] if cached["value"] is not None else "[]"
        results = result.get("results", []) or []
        if not results:
            break
        for pkg in results:
            spatial = _extract_spatial_from_pkg(pkg)
            if not spatial:
                skipped_no_spatial += 1
                continue
            c, bbox = _centroid_and_bbox_from_spatial(spatial)
            if c is None:
                skipped_bad_geom += 1
                continue
            # Title may be a fluent dict ({en: ..., fr: ...}) on this site;
            # render in the active language and fall back to the slug.
            raw_title = pkg.get("title") or pkg.get("name") or ""
            try:
                title = toolkit.h.scheming_language_text(raw_title) or raw_title
            except Exception:
                title = raw_title if isinstance(raw_title, str) else pkg.get("name") or ""
            points.append([pkg.get("name"), title, c[0], c[1], bbox])
        start += len(results)

    log.info(
        "centroids: total=%d fetched=%d kept=%d no_spatial=%d bad_geom=%d",
        count, start, len(points), skipped_no_spatial, skipped_bad_geom,
    )

    # The template embeds this payload inside a single-quoted HTML attribute
    # (`data-module-points='...'`). json.dumps does not escape `'`, so a title
    # containing an apostrophe ("Newfoundland's …") would terminate the
    # attribute early and silently break the centroid layer (the hex layer is
    # unaffected because its payload is purely numeric/hex IDs). Encode `'` as
    # a numeric entity — the browser decodes it back to `'` before the JSON is
    # parsed in JS, so the round-trip is lossless.
    payload = json.dumps(points, separators=(",", ":")).replace("'", "&#39;")
    _CENTROID_CACHE["key"] = count
    _CENTROID_CACHE["value"] = payload
    return payload


def cioos_invalidate_dataset_centroids():
    """Invalidate the centroid cache. Safe to call from IPackageController hooks."""
    _CENTROID_CACHE["key"] = None
    _CENTROID_CACHE["value"] = None


# ── Hex-bin density layer ─────────────────────────────────────────
# Server-side aggregation of every dataset's spatial footprint into Uber
# H3 cells. The browser rebuilds the cell polygons from `cellToBoundary`
# (single source of truth — same vertex set used for the map render and
# for the click-through `ext_geometry` URL).
#
# Resolution and color ramp are deployment-tunable via env vars (see
# `cioos_get_hexmap_config`) so non-Canada-wide deployments can crank up
# the resolution without a code change.
_HEXBIN_CACHE = {"key": None, "value": None}

try:
    import h3 as _h3
except ImportError:  # pragma: no cover — extension still imports without h3
    _h3 = None


def _h3_cells_for_geom(geom, resolution):
    """Return the set of H3 cell IDs that cover a GeoJSON geometry.

    - Point     → single cell containing the point.
    - Polygon   / MultiPolygon → all cells whose centers fall inside (h3 v4
      `geo_to_cells`), plus boundary cells via `polygon_to_cells_experimental`
      when available (so a small polygon never returns the empty set).
    - Anything else (LineString etc.) → centroid of the bbox as a fallback.

    Defensive against malformed coords; returns an empty set on failure.
    """
    if _h3 is None:
        return set()
    try:
        gtype = geom.get("type")
        coords = geom.get("coordinates")
        if not gtype or coords is None:
            return set()

        if gtype == "Point":
            lon, lat = coords[0], coords[1]
            if not (-180 <= lon <= 180 and -90 <= lat <= 90):
                return set()
            return {_h3.latlng_to_cell(lat, lon, resolution)}

        if gtype in ("Polygon", "MultiPolygon"):
            # h3 v4 expects a GeoJSON-like dict via `LatLngPoly` / `geo_to_cells`.
            # Use the high-level `geo_to_cells(geometry, res)` which accepts
            # GeoJSON-like dicts directly. Fallback to bbox if the call fails
            # (e.g. self-intersecting ring rejected by h3).
            try:
                cells = _h3.geo_to_cells(geom, resolution)
                if cells:
                    return set(cells)
            except Exception:
                pass

        # Fallback: bbox center → single cell. Keeps the dataset visible
        # on the map even when its geometry is unparseable by h3.
        _c, bbox = _centroid_and_bbox_from_spatial(json.dumps(geom))
        if not bbox:
            return set()
        west, south, east, north = bbox
        lon = (west + east) / 2.0
        lat = (south + north) / 2.0
        return {_h3.latlng_to_cell(lat, lon, resolution)}
    except Exception:
        log.exception("hexbins: cell computation failed for geom type=%s", geom.get("type"))
        return set()


def cioos_get_hexmap_config():
    """Return the deployment-tunable hex-map config dict for the template.

    Read from CKAN config (env-mapped via ckanext-envvars):
      ckanext.cioos.hexmap.resolution   default 3
      ckanext.cioos.hexmap.color_low    default '#f3f0ec' (cream)
      ckanext.cioos.hexmap.color_high   default '#152f37' (navy)
      ckanext.cioos.hexmap.color_steps  default 5
      ckanext.cioos.hexmap.opacity      default 0.75
      ckanext.cioos.hexmap.stroke       default '#152f37'
    """
    def _cfg(key, default, cast=str):
        val = config.get("ckanext.cioos.hexmap." + key, default)
        try:
            return cast(val)
        except (TypeError, ValueError):
            return default

    # Color resolution order (highest priority first):
    #   1. color_stops  — explicit comma-separated multi-stop palette
    #                     e.g. "#fff7bc,#fec44f,#d95f0e"
    #   2. color_preset — named built-in palette resolved client-side
    #                     (e.g. "viridis", "ylgnbu", "ylorrd", "cioos")
    #   3. color_low + color_high — legacy two-color ramp
    color_stops_raw = _cfg("color_stops", "")
    color_stops = [s.strip() for s in color_stops_raw.split(",") if s.strip()] if color_stops_raw else None

    # Custom percentile breakpoints (in (0, 1)). When set, overrides the
    # uniform 1/N split derived from `color_steps`. Lets deployments push
    # bin boundaries into the tail (e.g. 0.5,0.8,0.95,0.99 reserves the
    # accent for only the top 1% of cells). Implicitly determines bin
    # count: N quantiles → N+1 bins, palette is built with steps=N+1.
    quantiles_raw = _cfg("color_quantiles", "")
    color_quantiles = []
    if quantiles_raw:
        for tok in quantiles_raw.split(","):
            try:
                q = float(tok.strip())
                if 0.0 < q < 1.0:
                    color_quantiles.append(q)
            except (TypeError, ValueError):
                continue
        color_quantiles = sorted(set(color_quantiles))

    # `accent_color` (optional) overrides the topmost quantile bin's color
    # as a post-processing step — sidesteps gradient-interpolation muddiness
    # and guarantees the densest cells always pop with a fixed accent.
    # Empty string disables the override entirely (pure gradient).
    accent_raw = _cfg("accent_color", "#d97c4a")
    accent_color = accent_raw if accent_raw else None

    return {
        "resolution": _cfg("resolution", 3, int),
        "color_preset": _cfg("color_preset", "cioos"),
        "color_stops": color_stops,
        "color_quantiles": color_quantiles,
        "accent_color": accent_color,
        "color_low": _cfg("color_low", "#f3f0ec"),
        "color_high": _cfg("color_high", "#152f37"),
        "color_steps": _cfg("color_steps", 7, int),
        "color_scale": _cfg("color_scale", "log"),
        "opacity": _cfg("opacity", 0.75, float),
        "stroke": _cfg("stroke", "#152f37"),
    }


def cioos_get_dataset_hexbins(resolution=None, max_rows=15000, force_refresh=False):
    """Return a JSON string of H3 hex-bin counts for the home-page map.

    Output shape (positional, compact):
        [[cell_id, count], ...]

    `cell_id` is an H3 v4 string ID; the client converts it to a polygon
    via `h3-js`'s `cellToBoundary`. `count` is the number of datasets whose
    `spatial` footprint touches that cell.

    Cache invalidation:
      - Keyed on (Solr numFound, resolution) so changing resolution
        forces a rebuild without touching the centroid cache.
      - `cioos_invalidate_dataset_hexbins()` from IPackageController hooks.
    """
    if _h3 is None:
        log.warning("hexbins: h3 package not installed — returning empty payload")
        return "[]"

    if resolution is None:
        resolution = cioos_get_hexmap_config()["resolution"]

    user = logic.get_action("get_site_user")({"model": model, "ignore_auth": True}, {})
    context = {"model": model, "session": model.Session, "user": user["name"]}

    try:
        head = logic.get_action("package_search")(context, {"fl": "id", "rows": "0"})
    except Exception:
        log.exception("hexbins: package_search count failed")
        return "[]"
    count = head.get("count", 0)

    cache_key = (count, resolution)
    cached = _HEXBIN_CACHE
    if (
        not force_refresh
        and cached["key"] == cache_key
        and cached["value"] is not None
    ):
        return cached["value"]

    page_size = 1000
    target = min(count, max_rows)
    cell_counts = {}
    skipped_no_spatial = 0
    skipped_no_cells = 0
    start = 0
    while start < target:
        try:
            result = logic.get_action("package_search")(
                context,
                {"rows": str(min(page_size, target - start)), "start": str(start)},
            )
        except Exception:
            log.exception("hexbins: package_search page start=%d failed", start)
            return cached["value"] if cached["value"] is not None else "[]"
        results = result.get("results", []) or []
        if not results:
            break
        for pkg in results:
            spatial = _extract_spatial_from_pkg(pkg)
            if not spatial:
                skipped_no_spatial += 1
                continue
            try:
                geom = json.loads(spatial) if isinstance(spatial, str) else spatial
            except (TypeError, ValueError):
                skipped_no_cells += 1
                continue
            cells = _h3_cells_for_geom(geom, resolution)
            if not cells:
                skipped_no_cells += 1
                continue
            # +1 per cell — a dataset spanning N cells contributes to all N.
            for cell in cells:
                cell_counts[cell] = cell_counts.get(cell, 0) + 1
        start += len(results)

    payload_list = [[cell, n] for cell, n in cell_counts.items()]
    log.info(
        "hexbins: total=%d fetched=%d cells=%d no_spatial=%d no_cells=%d res=%d",
        count, start, len(payload_list), skipped_no_spatial, skipped_no_cells, resolution,
    )

    payload = json.dumps(payload_list, separators=(",", ":"))
    _HEXBIN_CACHE["key"] = cache_key
    _HEXBIN_CACHE["value"] = payload
    return payload


def cioos_invalidate_dataset_hexbins():
    """Invalidate the hex-bin cache. Safe to call from IPackageController hooks."""
    _HEXBIN_CACHE["key"] = None
    _HEXBIN_CACHE["value"] = None


def cioos_count_resorgs(group_type="resorg"):
    """Return a count of CIOOS responsible-organization groups."""
    user = logic.get_action("get_site_user")({"model": model, "ignore_auth": True}, {})
    context = {"model": model, "session": model.Session, "user": user["name"]}
    try:
        groups = logic.get_action("group_list")(context, {"type": group_type, "all_fields": False})
        return len(groups or [])
    except Exception:
        return 0


def cioos_count_projects(facet_field="projects"):
    """Return the number of distinct projects across all datasets.

    `projects` is a multi-value field on packages indexed in Solr; this
    counts the unique facet values rather than calling group_list (it
    isn't a group type in CIOOS).
    """
    user = logic.get_action("get_site_user")({"model": model, "ignore_auth": True}, {})
    context = {"model": model, "session": model.Session, "user": user["name"]}
    try:
        result = logic.get_action("package_search")(
            context,
            {
                "rows": 0,
                "facet.field": '["%s"]' % facet_field,
                "facet.limit": -1,
                "facet.mincount": 1,
            },
        )
        facets = result.get("search_facets") or result.get("facets") or {}
        items = facets.get(facet_field, {})
        if isinstance(items, dict):
            items = items.get("items", [])
        return len(items or [])
    except Exception:
        return 0


def cioos_get_resorgs(group_type="resorg", limit=None):
    """Return CIOOS responsible-organization groups with logos and dataset counts.

    Sorted by package_count descending. Used by the home page's "Browse by
    Organization" section to deep-link into each group's canonical page.
    """
    user = logic.get_action("get_site_user")({"model": model, "ignore_auth": True}, {})
    context = {"model": model, "session": model.Session, "user": user["name"]}
    try:
        groups = logic.get_action("group_list")(
            context,
            {
                "type": group_type,
                "all_fields": True,
                "include_extras": True,
                "include_dataset_count": True,
                "sort": "package_count desc",
            },
        ) or []
    except Exception:
        return []
    groups = [g for g in groups if (g.get("package_count") or 0) > 0]
    if limit:
        groups = groups[:limit]
    return groups


def cioos_get_projects(facet_field="projects", limit=None):
    """Return distinct project facet values with dataset counts.

    Sorted by count descending. Used by the home page's "Browse by Project"
    section to deep-link into a filtered dataset search.
    """
    user = logic.get_action("get_site_user")({"model": model, "ignore_auth": True}, {})
    context = {"model": model, "session": model.Session, "user": user["name"]}
    try:
        result = logic.get_action("package_search")(
            context,
            {
                "rows": 0,
                "facet.field": '["%s"]' % facet_field,
                "facet.limit": -1,
                "facet.mincount": 1,
            },
        )
    except Exception:
        return []
    facets = result.get("search_facets") or result.get("facets") or {}
    items = facets.get(facet_field, {})
    if isinstance(items, dict):
        items = items.get("items", [])
    items = sorted(items or [], key=lambda x: x.get("count", 0), reverse=True)
    if limit:
        items = items[:limit]
    return items


def cioos_datasets():
    """Return a list of the datasets"""

    user = logic.get_action("get_site_user")({"model": model, "ignore_auth": True}, {})
    context = {"model": model, "session": model.Session, "user": user["name"]}
    # Get a list of all the site's datasets from CKAN
    datasets = logic.get_action("package_search")(context, {"fl": "id"})
    return datasets


def cioos_schema_field_map():
    import inspect

    import jinja2

    import ckanext.spatial.model as spatial_model

    # map spatial key to schema field_name {'spatial': 'schema'}
    map = {
        "title": "title_translated",
        "abstract": "notes_translated",
        "guid": "name",
        "keywords": ["keywords", "eov"],
        "bbox": [
            "bbox-north-lat",
            "bbox-south-lat",
            "bbox-east-long",
            "bbox-west-long",
        ],
        "license_id": "use-constraints",
    }

    schema = toolkit.h.scheming_get_dataset_schema("dataset")
    doc = spatial_model.ISODocument("<xml></xml>")

    # load classes, we have to pre load class defenitions and later update them
    # vecouse pickle dosn't do it properly. Might be becouse our isodocument
    # class is so large
    classes = inspect.getmembers(spatial_model, inspect.isclass)
    classes_pickled = json.loads(jsonpickle.encode(classes, unpicklable=False))
    class_dict = {}
    for x in classes_pickled:
        class_dict[x[0]] = x[1]
        class_ = getattr(spatial_model, x[0])
        try:
            instanse = class_(None)
        except Exception:
            try:
                instanse = class_()
            except Exception:
                instanse = class_("<xml></xml>")

        class_dict[x[0]]["class"] = jsonpickle.encode(instanse)

    # Dataset
    fields = schema["dataset_fields"]
    j = jsonpickle.encode(doc.elements)
    isodoc_dict = json.loads(j)
    output = cioos_schema_field_map_parent(
        fields, isodoc_dict, class_dict, map, "Dataset Fields"
    )

    # Resources
    resource_fields_schema = [
        {
            "field_name": "resource_fields",
            "repeating_subfields": schema["resource_fields"],
        }
    ]
    j = jsonpickle.encode(
        [x for x in doc.elements if isinstance(x, spatial_model.ISOResourceLocator)],
        unpicklable=False,
    )
    isodoc_dict = json.loads(j)
    resource_locator = [x for x in isodoc_dict if x["name"] == "resource-locator"]

    map = {"resource-locator": "resource_fields"}

    output = output + cioos_schema_field_map_parent(
        resource_fields_schema, resource_locator, class_dict, map, "Resource Fields"
    )
    return jinja2.Markup(output)


# process any first level fields in the isodocument
def cioos_schema_field_map_parent(fields, isodoc_dict, class_dict, mapkey, caption):
    output = (
        """<table class="table table-bordered table-condensed">
        <caption>"""
        + caption
        + """</caption>
        <thead>
            <tr>
                <th style="width:40px;">Req</th>
                <th style="width:200px;">Schema Name</th>
                <th style="width:200px;">Harvest Name</th>
                <th style="width:40px;">N</th>
                <th style="width:100px;">Description</th>
                <th>XML Path</th>

            </tr>
        </thead><tbody>"""
    )
    matched_schema_fields = []

    # loop through spatial harvester isodocument fields
    for item in isodoc_dict:
        # get class name of entry in spatial harvester class
        (objpath, delimiter, objtype) = item.get("py/object", "").rpartition(".")
        # update class with pre determined definition if appropreit
        if (
            objtype != "ISOElement"
            and item.get("elements")
            and objtype.startswith("ISO")
        ):
            class_json_def = json.loads(class_dict.get(objtype, {}).get("class", "{}"))
            elem = class_json_def.get("elements", [])
            item["elements"] = elem

        # get the search paths for the current item
        sp = item["search_paths"]
        if isinstance(item["search_paths"], list):
            sp = "<br/>".join(item["search_paths"])

        # map item name to a new name if it is entered in the mapkey dictinary
        search_item = mapkey.get(item["name"], item["name"])

        # get ckan schema field with the same name, if it exists
        field = toolkit.h.scheming_field_by_name(fields, search_item)
        # the mapkey fields could be a list as sometimes more then one ckan
        # schema field maps to a spatial harvest field
        if isinstance(search_item, list):
            fn = []
            fl = []
            for x in search_item:
                field = toolkit.h.scheming_field_by_name(fields, x)
                fn.append(field["field_name"])
                fl.append(toolkit.h.scheming_language_text(field.get("label", "")))
                matched_schema_fields.append(field["field_name"])
            field = {}
            field["field_name"] = ",<br/>".join(fn)
            field["label"] = ",<br/>".join(fl)

        schema_name = ""
        schema_label = ""
        schema_help = ""
        subfields = None
        required = ""

        if field:
            schema_name = field["field_name"]
            schema_label = (
                " (" + toolkit.h.scheming_language_text(field.get("label", "")) + ")"
            )
            schema_help = field.get("help_text", "")
            subfields = field.get("repeating_subfields")
            if field.get("required"):
                required = '<span class="required">*</span>'
            matched_schema_fields.append(schema_name)

        output = (
            output
            + "<tr><td>"
            + required
            + "</td><td>"
            + schema_name
            + schema_label
            + "</td><td>"
            + item["name"]
            + "</td><td>"
            + item["multiplicity"]
            + "</td><td>"
            + schema_help
            + "</td><td>"
            + sp
            + "</td></tr>"
        )
        (output_new, matched_schema_fields) = cioos_schema_field_map_child(
            subfields, None, item.get("elements"), "", 1, matched_schema_fields
        )
        output = output + output_new

    # add any fields in schema that have not found a match in spatial harvest
    for field in fields:
        if field["field_name"] not in matched_schema_fields:
            schema_name = field["field_name"]
            schema_label = (
                " (" + toolkit.h.scheming_language_text(field.get("label", "")) + ")"
            )
            matched_schema_fields.append(schema_name)
            required = ""
            if field.get("required"):
                required = '<span class="required">*</span>'
            output = (
                output
                + "<tr><td>"
                + required
                + "</td><td>"
                + schema_name
                + schema_label
                + "</td><td></td><td></td><td></td><td></td></tr>"
            )
    return output + "</tbody></table>"


# process any child elements of first level or lower isodocument fields.
def cioos_schema_field_map_child(
    schema_subfields,
    schema_parentfields,
    harvest_elements,
    path,
    indent,
    matched_schema_fields,
):
    output = ""
    if not harvest_elements:
        return output, matched_schema_fields
    if not isinstance(harvest_elements, list):
        return output, matched_schema_fields

    for item in harvest_elements:
        if not item or not item.get("name"):
            continue
        sp = item["search_paths"]
        if isinstance(item["search_paths"], list):
            sp = "<br/>".join(item["search_paths"])

        field = None
        if schema_subfields:
            field = toolkit.h.scheming_field_by_name(
                schema_subfields, item["name"]
            ) or toolkit.h.scheming_field_by_name(schema_subfields, path + item["name"])
        if not field and schema_parentfields:
            field = toolkit.h.scheming_field_by_name(
                schema_parentfields, item["name"]
            ) or toolkit.h.scheming_field_by_name(
                schema_parentfields, path + item["name"]
            )

        schema_name = ""
        schema_label = ""
        schema_help = ""
        subfields = None
        parentfields = schema_subfields
        required = ""

        if field:
            schema_name = field["field_name"]
            schema_label = (
                " (" + toolkit.h.scheming_language_text(field.get("label", "")) + ")"
            )
            schema_help = field.get("help_text", "")
            subfields = field.get("repeating_subfields")
            matched_schema_fields.append(schema_name)
            schema_name = '<i class="fa fa-angle-right"></i>' + schema_name
            if field.get("required"):
                required = '<span class="required">*</span>'

        harvest_name = ""
        if item["name"]:
            harvest_name = '<i class="fa fa-angle-right"></i>' + item["name"]

        output = (
            output
            + '<tr class="child'
            + str(indent)
            + '"><td>'
            + required
            + "</td><td>"
            + schema_name
            + schema_label
            + "</td><td>"
            + harvest_name
            + "</td><td>"
            + item["multiplicity"]
            + "</td><td>"
            + schema_help
            + "</td><td>"
            + sp
            + "</td></tr>"
        )
        (output_new, matched_schema_fields) = cioos_schema_field_map_child(
            subfields,
            parentfields,
            item.get("elements"),
            path + item["name"] + "_",
            indent + 1,
            matched_schema_fields,
        )
        output = output + output_new

    # outout any schema fields at this sublevel which do not have a match.
    if schema_subfields:
        for field in schema_subfields:
            if field["field_name"] not in matched_schema_fields:
                schema_name = field["field_name"]
                schema_label = (
                    " ("
                    + toolkit.h.scheming_language_text(field.get("label", ""))
                    + ")"
                )
                matched_schema_fields.append(schema_name)
                required = ""
                if field.get("required"):
                    required = '<span class="required">*</span>'
                output = (
                    output
                    + "<tr><td>"
                    + required
                    + "</td><td>"
                    + schema_name
                    + schema_label
                    + "</td><td></td><td></td><td></td><td></td></tr>"
                )
    return output, matched_schema_fields


def cioos_get_facets(package_type="dataset", facet_list=["ALL"]):
    """get all dataset for the given package type, including private ones.
    This function works similarly to code found in ckan/ckan/controllers/package.py
    in that it does a search of all datasets and populates the following
    globals for later use:
        c.facet_titles
        c.search_facets
    """
    facets = OrderedDict()

    default_facet_titles = {
        "organization": _("Organizations"),
        "groups": _("Groups"),
        "tags": _("Tags"),
        "res_format": _("Formats"),
        "license_id": _("Licenses"),
    }

    for facet in toolkit.h.facets():
        if facet in default_facet_titles:
            facets[facet] = default_facet_titles[facet]
        else:
            facets[facet] = facet

    # Facet titles
    for plugin in p.PluginImplementations(p.IFacets):
        facets = plugin.dataset_facets(facets, package_type)

    # filter facets if needed
    facets = {k: v for k, v in facets.items() if "ALL" in facet_list or k in facet_list}

    c.facet_titles = facets

    data_dict = {
        "facet.field": list(facets.keys()),
        "facet.limit": -1,
        "rows": 0,
        "include_private": toolkit.asbool(
            config.get("ckan.search.default_include_private", True)
        ),
    }

    context = {
        "model": model,
        "session": model.Session,
        "user": c.user,
        "for_view": True,
        "auth_user_obj": c.userobj,
    }

    query = get_action("package_search")(context, data_dict)
    c.search_facets = query["search_facets"]
    # return {
    #     'search': c.search_facets,
    #     'titles': c.facet_titles,
    # }


def cioos_version():
    """Return CIOOS version"""
    return metadata.version("ckanext.cioos_theme")


def append_to_homepages(homepages):
    homepages.append({"value": "4", "text": "CIOOS"})
    return homepages


def cioos_structured_data(data_dict):
    toolkit.check_access("dcat_dataset_show", {}, data_dict)

    serializer = RDFSerializer(profiles=["schemaorg", "cioos_dcat"])

    output = serializer.serialize_dataset(data_dict, _format="jsonld")

    return output
