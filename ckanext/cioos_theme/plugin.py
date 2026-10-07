import logging
import string

import ckan.plugins as plugins
import ckan.plugins.toolkit as toolkit
from ckan.lib.plugins import DefaultTranslation
from ckantoolkit import _, g
from flask import Blueprint
from shapely.geometry import shape
from six.moves.urllib.parse import urlparse

import ckanext.cioos_theme.cli as cli
import ckanext.cioos_theme.helpers as cioos_helpers
from ckanext.scheming.validation import scheming_validator

log = logging.getLogger(__name__)


contact_email = toolkit.config.get("cioos.contact_email", "info@cioos.ca")
organizations_info_text = toolkit.config.get(
    "cioos.organizations_info_text",
    {
        "en": "CKAN Organizations are used to create, manage and publish collections of datasets. Users can have different roles within an Organization, depending on their level of authorisation to create, edit and publish.",
        "fr": "Les Organisations CKAN sont utilisées pour créer, gérer et publier des collections de jeux de données. Les utilisateurs peuvent avoir différents rôles au sein d'une Organisation, en fonction de leur niveau d'autorisation pour créer, éditer et publier.",
    },
)

group_info_text = toolkit.config.get(
    "cioos.group_info_text",
    {
        "resorg": {
            "en": "You can use CKAN Responsible Organizations to create and manage collections of datasets. In this case, a dataset is assigned to each organization that has been identified as contributing to, retains ownership of, or responsible for the data in the dataset.",
            "fr": "Vous pouvez utiliser les organisations responsables de CKAN pour créer et gérer des collections d'ensembles de données. Dans ce cas, un ensemble de données est attribué à chaque organisation qui a été identifiée comme contribuant, conservant la propriété ou responsable des données de l'ensemble de données.",
        },
        "group": {
            "en": "You can use CKAN Groups to create and manage collections of datasets. This could be to catalogue datasets for a particular project or team, or on a particular theme, or as a very simple way to help people find and search your own published datasets.",
            "fr": "Vous pouvez utiliser les groupes CKAN pour créer et gérer des collections d'ensembles de données. Il peut s'agir de cataloguer des ensembles de données pour un projet ou une équipe particulière, ou sur un thème particulier, ou encore d'un moyen très simple d'aider les gens à trouver et à rechercher vos propres ensembles de données publiés.",
        },
    },
)


def geojson_to_bbox(o):
    return shape(o).bounds


@scheming_validator
def fluent_field_default(field, schema):

    def validator(key, data, errors, context):
        if not data[key]:
            # field is blank, populate with default value
            data[key] = {}
            lang_list = toolkit.h.fluent_form_languages()
            for lang in lang_list:
                data[key][lang] = ""

        elif not data[key].startswith("{"):
            # its a string, need to format as a json object
            new_dict = {}
            lang_list = toolkit.h.fluent_form_languages()
            for lang in lang_list:
                new_dict[lang] = data[key]
            data[key] = new_dict
        # we should now have a json object so nothing left to do.
        return data

    return validator


def url_validator_with_port(key, data, errors, context):
    """Checks that the provided value (if it is present) is a valid URL, accepts port numbers in URL"""

    url = data.get(key, None)
    if not url:
        return

    try:
        pieces = urlparse(url)
        if (
            all([pieces.scheme, pieces.netloc])
            and set(pieces.netloc) <= set(string.ascii_letters + string.digits + "-.:")
            and pieces.scheme in ["http", "https"]
        ):
            return
    except ValueError:
        # url is invalid
        pass
    errors[key].append(_("Please provide a valid URL"))


def render_schemamap():
    return toolkit.render("schemamap.html")


def render_basic_package_view(id):
    pkg = toolkit.get_action("package_show")(data_dict={"id": id})
    return toolkit.render("package/basic.html", extra_vars={"pkg_dict": pkg})


def cioos_home_index():
    if g.userobj and not g.userobj.email:
        url = toolkit.h.url_for(controller="user", action="edit")
        msg = _(
            'Please <a href="%s">update your profile</a> and add your email address. '
        ) % url + _(
            "%s uses your email address if you need to reset your password."
        ) % toolkit.config.get("ckan.site_title")
        toolkit.h.flash_notice(msg, allow_html=True)
    return toolkit.render("home/index.html", extra_vars={})


class Cioos_ThemePlugin(plugins.SingletonPlugin, DefaultTranslation):
    plugins.implements(plugins.ITranslation)
    plugins.implements(plugins.IConfigurer)
    plugins.implements(plugins.IConfigDeclaration)
    plugins.implements(plugins.ITemplateHelpers)
    plugins.implements(plugins.IValidators)
    plugins.implements(plugins.IClick)
    plugins.implements(plugins.IBlueprint)

    # IConfigDeclaration

    def declare_config_options(self, declaration, key):
        # CIOOS theme custom config options
        declaration.declare(key.ckan.site_heading, "")
        declaration.declare(key.ckan.site_logo_translated, "")
        declaration.declare(key.ckan.site_home_url, "")
        declaration.declare(key.ckan.exclude_eov_category, "")
        declaration.declare(key.ckan.exclude_eov, "")
        declaration.declare(key.ckan.eov_icon_base_path, "/base/images/eov-icons-svg/")
        declaration.declare(key.ckan.header_file_name, "")
        declaration.declare(key.ckan.footer_file_name, "")
        declaration.declare(key.ckan.site_about_markdown_file, "")
        declaration.declare(key.ckan.show_social_in_dataset_sidebar, "false")
        declaration.declare(key.ckan.hide_organization_in_breadcrumb, "false")
        declaration.declare(key.ckan.hide_organization_in_dataset_sidebar, "false")
        declaration.declare(key.ckan.show_harvested_from_in_dataset_sidebar, "true")
        declaration.declare(key.ckan.show_language_picker_in_top_bar, "true")
        declaration.declare(key.ckan.show_language_picker_in_menu, "true")

        # CIOOS specific config options (cioos.* namespace)
        declaration.declare(key.cioos.contact_email, "info@cioos.ca")
        declaration.declare(key.cioos.organizations_info_text, "{}")
        declaration.declare(key.cioos.group_info_text, "{}")

        # CKAN CIOOS config options (ckan.cioos.* namespace)
        declaration.declare(key.ckan.cioos.ra_css_path, "")
        declaration.declare(key.ckan.cioos.ra_json_file, "null")

        # Lang option used in templates
        declaration.declare(key.lang, "")

    # IClick
    def get_commands(self):
        return cli.get_commands()

    # IBlueprint
    def get_blueprint(self):
        blueprint = Blueprint("cioos_theme", self.__module__)
        rules = [
            ("/schemamap", "schemamap", render_schemamap),
            ("/dataset/<id>.basic", "package_basic", render_basic_package_view),
            ("/", "home", cioos_home_index),
        ]
        for rule in rules:
            blueprint.add_url_rule(*rule)

        return blueprint

    # IConfigurer

    def update_config(self, config_):
        toolkit.add_template_directory(config_, "templates")
        toolkit.add_public_directory(config_, "public")
        toolkit.add_resource("public", "ckanext-cioos_theme")

    def update_config_schema(self, schema):

        ignore_missing = toolkit.get_validator("ignore_missing")
        fluent_text = toolkit.get_validator("fluent_text")
        boolean_validator = toolkit.get_validator("boolean_validator")

        schema.update(
            {
                "ckan.site_title": [
                    ignore_missing,
                    fluent_field_default(None, None),
                    fluent_text(None, None),
                ],
                "ckan.site_heading": [
                    ignore_missing,
                    fluent_field_default(None, None),
                    fluent_text(None, None),
                ],
                "ckan.site_description": [
                    ignore_missing,
                    fluent_field_default(None, None),
                    fluent_text(None, None),
                ],
                "ckan.site_about": [
                    ignore_missing,
                    fluent_field_default(None, None),
                    fluent_text(None, None),
                ],
                "ckan.site_about_markdown_file": [ignore_missing],
                "ckan.site_intro_text": [
                    ignore_missing,
                    fluent_field_default(None, None),
                    fluent_text(None, None),
                ],
                "ckan.site_logo_translated": [
                    ignore_missing,
                    fluent_field_default(None, None),
                    fluent_text(None, None),
                ],
                "ckan.site_home_url": [ignore_missing, url_validator_with_port],
                "ckan.exclude_eov_category": [ignore_missing],
                "ckan.exclude_eov": [ignore_missing],
                "ckan.eov_icon_base_path": [ignore_missing],
                "ckan.header_file_name": [ignore_missing],
                "ckan.footer_file_name": [ignore_missing],
                "ckan.show_social_in_dataset_sidebar": [
                    ignore_missing,
                    boolean_validator,
                ],
                "ckan.hide_organization_in_breadcrumb": [
                    ignore_missing,
                    boolean_validator,
                ],
                "ckan.hide_organization_in_dataset_sidebar": [
                    ignore_missing,
                    boolean_validator,
                ],
                "ckan.show_harvested_from_in_dataset_sidebar": [
                    ignore_missing,
                    boolean_validator,
                ],
                "ckan.show_language_picker_in_top_bar": [
                    ignore_missing,
                    boolean_validator,
                ],
                "ckan.show_language_picker_in_menu": [
                    ignore_missing,
                    boolean_validator,
                ],
            }
        )
        return schema

    def get_additional_css_path(self):
        return toolkit.config.get("ckan.cioos.ra_css_path")

    def get_helpers(self):
        return {
            "cioos_organizations_info_text": lambda: organizations_info_text,
            "cioos_contact_email": lambda: contact_email,
            "cioos_group_info_text": lambda: group_info_text,
            "cioos_geojson_to_bbox": geojson_to_bbox,
            "cioos_get_facets": cioos_helpers.cioos_get_facets,
            "cioos_datasets": cioos_helpers.cioos_datasets,
            "cioos_count_datasets": cioos_helpers.cioos_count_datasets,
            "cioos_get_eovs": cioos_helpers.cioos_get_eovs,
            "cioos_get_locale_url": self.get_locale_url,
            "cioos_schema_field_map": cioos_helpers.cioos_schema_field_map,
            "cioos_get_additional_css_path": self.get_additional_css_path,
            "cioos_get_homepage_path": lambda: toolkit.config.get(
                "ckan.homepage_template", "home/default_home.html"
            ),
            "cioos_get_cfg": lambda key, default=None: toolkit.config.get(key, default),
            "cioos_get_cfg_bool": lambda key, default=False: toolkit.asbool(
                toolkit.config.get(key, default)
            ),
            "cioos_helper_available": cioos_helpers.helper_available,
            "cioos_version": cioos_helpers.cioos_version,
            "cioos_merge_dict": cioos_helpers.merge_dict,
            "cioos_get_dataset_extents_url": cioos_helpers.get_dataset_extents_url,
            "cioos_get_ra_extents_url": cioos_helpers.get_ra_extents_url,
            "cioos_get_extra_value": self._get_extra_value,
            "cioos_append_to_homepages": cioos_helpers.append_to_homepages,
            # Config access helpers
            "cioos_get_header_file_name": lambda: toolkit.config.get(
                "ckan.header_file_name", ""
            ),
            "cioos_get_footer_file_name": lambda: toolkit.config.get(
                "ckan.footer_file_name", ""
            ),
            "cioos_get_eov_icon_base_path": lambda: toolkit.config.get(
                "ckan.eov_icon_base_path", "/base/images/eov-icons-svg/"
            ),
            "cioos_get_exclude_eov": lambda: toolkit.config.get("ckan.exclude_eov", ""),
            "cioos_get_exclude_eov_category": lambda: toolkit.config.get(
                "ckan.exclude_eov_category", ""
            ),
            "cioos_show_social_in_dataset_sidebar": lambda: toolkit.asbool(
                toolkit.config.get("ckan.show_social_in_dataset_sidebar", False)
            ),
            "cioos_hide_organization_in_breadcrumb": lambda: toolkit.asbool(
                toolkit.config.get("ckan.hide_organization_in_breadcrumb", False)
            ),
            "cioos_hide_organization_in_dataset_sidebar": lambda: toolkit.asbool(
                toolkit.config.get("ckan.hide_organization_in_dataset_sidebar", False)
            ),
            "cioos_show_harvested_from_in_dataset_sidebar": lambda: toolkit.asbool(
                toolkit.config.get("ckan.show_harvested_from_in_dataset_sidebar", True)
            ),
            "cioos_show_language_picker_in_top_bar": lambda: toolkit.asbool(
                toolkit.config.get("ckan.show_language_picker_in_top_bar", True)
            ),
            "cioos_show_language_picker_in_menu": lambda: toolkit.asbool(
                toolkit.config.get("ckan.show_language_picker_in_menu", True)
            ),
            "cioos_load_about_markdown": cioos_helpers.load_about_markdown,
        }

    def get_validators(self):
        return {
            "cioos_fluent_field_default": fluent_field_default,
            "cioos_url_validator_with_port": url_validator_with_port,
        }

    def _get_extra_value(self, key, package_dict):
        for extra in package_dict.get("extras", []):
            if extra["key"] == key:
                return extra["value"]

    def get_locale_url(self, base_url, locale_urls):
        default_locale = toolkit.config.get(
            "ckan.locale_default", toolkit.config.get("ckan.locales_offered", ["en"])[0]
        )
        lang = toolkit.h.lang() or default_locale
        if base_url.endswith("/"):
            return base_url + locale_urls.get(lang)
        return base_url + "/" + locale_urls.get(lang)
