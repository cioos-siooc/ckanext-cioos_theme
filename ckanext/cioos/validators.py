"""Validators referenced by the CIOOS scheming schema (cioos-siooc-schema)."""

import json
import re

import ckan.lib.navl.dictization_functions as df
import ckan.plugins.toolkit as toolkit
from ckantoolkit import _

from ckanext.cioos.helpers import load_json
from ckanext.scheming.validation import scheming_validator

Invalid = df.Invalid


def populate_select(key, data, errors, langs, select_field, keyword_list):
    candidate_dict = {}
    # create dictionary from select choice list
    for x in toolkit.h.scheming_field_choices(select_field):
        candidate_dict[x["value"].lower()] = x["value"]
        for id in x.get("alternative_ids", []):
            candidate_dict[id.lower()] = x["value"]
        for lang in langs:
            if x["label"].get(lang):
                candidate_dict[x["label"][lang].lower()] = x["value"]
                # if clean_tags is true during harvesting then spaces will be
                # replaced by dash's by mung_tags
                candidate_dict[x["label"][lang].replace(" ", "-").lower()] = x["value"]

    d = json.loads(data.get(key, "[]"))
    # search for matching keywords in select choices dictionary
    for x in keyword_list:
        if isinstance(x, str):
            val = candidate_dict.get(x.lower(), "")
        elif isinstance(x, dict):
            val = candidate_dict.get(x["name"].lower(), "")
        else:
            val = candidate_dict.get(x, "")
        if val and val not in d:
            d.append(val)

    # why do we run this twice? double errors in list?
    if len(d) and "Select at least one" in errors[key]:
        errors[key].remove("Select at least one")
    if len(d) and "Select at least one" in errors[key]:
        errors[key].remove("Select at least one")

    data[key] = json.dumps(d)
    return data


# this validator tries to populate eov from keywords. It looks for any english
# keywords that match either the value or label in the choice list for the eov
# field and add's them to the eov field.
@scheming_validator
def clean_and_populate_eovs(field, schema):

    def validator(key, data, errors, context):
        if errors[key] and (
            "Select at least one" not in errors[key]
            or "Select at least one" not in errors[key]
        ):
            return

        select_field = toolkit.h.scheming_field_by_name(schema["dataset_fields"], "eov")
        langs = toolkit.h.fluent_form_languages(select_field, None, None, schema)

        keywords_main = data.get(("keywords",), {})
        if keywords_main:
            keyword_list = keywords_main.get("en", []) + keywords_main.get("fr", [])
        else:
            extras = data.get(("__extras",), {})
            keyword_list = extras.get("keywords-en", "").split(",") + extras.get(
                "keywords-fr", ""
            ).split(",")

        return populate_select(key, data, errors, langs, select_field, keyword_list)

    return validator


# this validator tries to populate ecv from keywords. It looks for any english
# or french keywords that match either the value or label in the choice list for the ecv
# field and add's them to the eov field.
@scheming_validator
def clean_and_populate_ecvs(field, schema):

    def validator(key, data, errors, context):

        if errors[key]:
            return

        select_field = toolkit.h.scheming_field_by_name(schema["dataset_fields"], "ecv")
        langs = toolkit.h.fluent_form_languages(select_field, None, None, schema)

        keywords_main = data.get(("keywords",), {})
        if keywords_main:
            keyword_list = keywords_main.get("en", []) + keywords_main.get("fr", [])
        else:
            extras = data.get(("__extras",), {})
            keyword_list = extras.get("keywords-en", "").split(",") + extras.get(
                "keywords-fr", ""
            ).split(",")

        return populate_select(key, data, errors, langs, select_field, keyword_list)

    return validator


@scheming_validator
def cioos_tag_name_validator(field, schema):

    def validator(value, context):
        tagname_match = re.compile(
            r"[\w\u00c0-\u018f\u0300-\u0315 .'’,;\\/\(\)-]*$", re.UNICODE
        )
        if not tagname_match.match(value):
            raise Invalid(
                _('Tag "%s" must be alphanumeric characters or symbols: -_.,;\'()')
                % (value)
            )
        return value

    return validator


@scheming_validator
def cioos_name_validator(field, schema):

    CIOOS_PACKAGE_NAME_MAX_LENGTH = 255
    name_match = re.compile(r"[a-z0-9_-]*$")

    def validator(value, context):
        """Return the given value if it's a valid name, otherwise raise Invalid.

        If it's a valid name, the given value will be returned unmodified.

        This function applies general validation rules for names of packages,
        groups, users, etc.

        Most schemas also have their own custom name validator function to apply
        custom validation rules after this function, for example a
        ``package_name_validator()`` to check that no package with the given name
        already exists.

        :raises ckan.lib.navl.dictization_functions.Invalid: if ``value`` is not
            a valid name

        """
        if not isinstance(value, str):
            raise Invalid(_("Names must be strings"))

        # check basic textual rules
        if value in ["new", "edit", "search"]:
            raise Invalid(_("That name cannot be used"))

        if len(value) < 2:
            raise Invalid(_("Must be at least %s characters long") % 2)
        if len(value) > CIOOS_PACKAGE_NAME_MAX_LENGTH:
            raise Invalid(
                _("Name must be a maximum of %i characters long")
                % CIOOS_PACKAGE_NAME_MAX_LENGTH
            )
        if not name_match.match(value):
            raise Invalid(
                _(
                    "Must be purely lowercase alphanumeric "
                    "(ascii) characters and these symbols: -_"
                )
            )
        return value

    return validator


@scheming_validator
def cioos_is_valid_range(field, schema):

    def validator(value, context):
        range = load_json(value)
        if (not range.get("begin") and range.get("end")) or (
            range.get("end") and range["end"] < range["begin"]
        ):
            raise Invalid(
                _('Invalid value "%r". Valid ranges must contain begin <= end values')
                % (value)
            )
        return value

    return validator
