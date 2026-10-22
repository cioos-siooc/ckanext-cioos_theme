"""CIOOS template helpers and shared functions (licences, URIs, DOIs, JSON)."""

import json
import re

import ckan.plugins.toolkit as toolkit
from ckantoolkit import config

from ckanext.dcat.processors import RDFSerializer


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


def get_doi_authority_url():
    return toolkit.config.get("ckan.cioos.doi_authority_url", "https://doi.org/")


def get_doi_prefix():
    return toolkit.config.get("ckan.cioos.doi_prefix")


def get_datacite_org():
    return toolkit.config.get("ckan.cioos.datacite_org")


def get_datacite_test_mode():
    return toolkit.config.get("ckan.cioos.datacite_test_mode", "True")


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


def cioos_structured_data(data_dict):
    toolkit.check_access("dcat_dataset_show", {}, data_dict)

    serializer = RDFSerializer(profiles=["schemaorg", "cioos_dcat"])

    output = serializer.serialize_dataset(data_dict, _format="jsonld")

    return output
