import logging
from copy import deepcopy

import ckan.plugins as plugins
import ckan.plugins.toolkit as toolkit
import lxml.etree as ET
from ckan.lib.plugins import DefaultTranslation
from ckan.logic import NotFound

import ckanext.cioos.cli as cli
import ckanext.cioos.helpers as cioos_helpers
import ckanext.cioos.logic as logic
import ckanext.cioos.validators as validators
import ckanext.cioos.views as views
from ckanext.scheming.helpers import scheming_language_text

helpers = cioos_helpers
log = logging.getLogger(__name__)
# Kept under the theme's historical logger name: fail2ban filters match it.
log_auth = logging.getLogger("ckanext.cioos_theme.plugin.auth")


show_responsible_organizations = toolkit.asbool(
    toolkit.config.get("cioos.show_responsible_organizations_facet", "True")
)

hide_organization_in_dataset_sidebar = toolkit.asbool(
    toolkit.config.get("ckan.hide_organization_in_dataset_sidebar", False)
)


class CioosPlugin(plugins.SingletonPlugin, DefaultTranslation):
    """CIOOS catalogue domain logic, independent of the theme (ADR 0002)."""

    plugins.implements(plugins.ITranslation)
    plugins.implements(plugins.IConfigurer)
    plugins.implements(plugins.IConfigDeclaration)
    plugins.implements(plugins.ITemplateHelpers)
    plugins.implements(plugins.IFacets)
    plugins.implements(plugins.IPackageController, inherit=True)
    plugins.implements(plugins.IOrganizationController, inherit=True)
    plugins.implements(plugins.IValidators)
    plugins.implements(plugins.IAuthenticator)
    plugins.implements(plugins.IClick)
    plugins.implements(plugins.IBlueprint)
    plugins.implements(plugins.IActions)

    all_groups_dict_by_name = None

    # IActions

    def get_actions(self):
        return {
            "dcat_dataset_show": logic.dcat_dataset_show,
            "spatial_query_geo": logic.spatial_query_geo,
            "spatial_query_geo_package_search": logic.spatial_query_geo_package_search,
        }

    # IConfigDeclaration

    def declare_config_options(self, declaration, key):
        declaration.declare(key.cioos.show_responsible_organizations_facet, "True")
        declaration.declare(key.ckan.cioos.exclude_facets, "[]")
        declaration.declare(key.ckan.cioos.doi_authority_url, "https://doi.org/")
        declaration.declare(key.ckan.cioos.doi_prefix, "")
        declaration.declare(key.ckan.cioos.datacite_org, "")
        declaration.declare(key.ckan.cioos.datacite_test_mode, "True")

    # IConfigurer

    def update_config(self, config_):
        toolkit.add_template_directory(config_, "templates")

    # IClick

    def get_commands(self):
        return cli.get_commands()

    # IBlueprint

    def get_blueprint(self):
        return views.get_blueprint()

    # ITemplateHelpers

    def get_helpers(self):
        return {
            "cioos_load_json": helpers.load_json,
            "cioos_get_package_relationships": helpers.get_package_relationships,
            "cioos_get_doi_authority_url": helpers.get_doi_authority_url,
            "cioos_get_doi_prefix": helpers.get_doi_prefix,
            "cioos_get_datacite_org": helpers.get_datacite_org,
            "cioos_get_datacite_test_mode": helpers.get_datacite_test_mode,
            "cioos_group_contacts": self.group_by_ind_or_org,
            "cioos_get_fully_qualified_package_uri": helpers.get_fully_qualified_package_uri,
            "cioos_get_license_def": helpers.get_license_def,
            "cioos_structured_data": helpers.cioos_structured_data,
            "composite_separator": helpers.composite_separator,
            "scheming_composite_separator": helpers.composite_separator,
        }

    # IValidators

    def get_validators(self):
        return {
            "cioos_clean_and_populate_eovs": validators.clean_and_populate_eovs,
            "cioos_clean_and_populate_ecvs": validators.clean_and_populate_ecvs,
            "cioos_tag_name_validator": validators.cioos_tag_name_validator,
            "cioos_name_validator": validators.cioos_name_validator,
            "cioos_is_valid_range": validators.cioos_is_valid_range,
        }

    # IOrganizationController

    def read(self, entity):
        pass

    def create(self, entity):
        # Organizations created without a translated title get the plain title
        # in both languages. IPackageController.create shares this method, so
        # ignore packages.
        if not getattr(entity, "is_organization", False):
            return entity
        if hasattr(entity, "title_translated"):
            if entity.title_translated == "{}" or not entity.title_translated:
                toolkit.get_action("organization_patch")(
                    data_dict={
                        "id": entity.id,
                        "title": entity.title,
                        "title_translated": '{"en":"%s", "fr":"%s"}'
                        % (entity.title, entity.title),
                    }
                )
        return entity

    def edit(self, entity):
        pass

    def delete(self, entity):
        pass

    # IAuthenticator

    def authenticate(self, identity):
        """Authenticate a user identity.

        Required by IAuthenticator in CKAN 2.10+.
        Returns None to allow other authenticators to handle authentication.
        """
        return None

    def identify(self):
        try:
            remote_addr = toolkit.request.headers["X-Forwarded-For"]
        except KeyError:
            remote_addr = toolkit.request.remote_addr

        log_auth.info(
            "Request by %s for %s from %s",
            toolkit.request.remote_user,
            toolkit.request.url,
            remote_addr,
        )
        # Note: Do not reset g.user/g.userobj here - let CKAN's default authenticator handle it
        return

    def identify_user(self, user_id=None):
        """Allow CKAN core auth middleware to continue with default auth flow.

        CKAN 2.12 calls ``identify_user`` on IAuthenticator plugins during
        request preprocessing. Returning None indicates this plugin does not
        authenticate the current request.
        """
        return None

    def login(self, error=None):
        try:
            remote_addr = toolkit.request.headers["X-Forwarded-For"]
        except KeyError:
            remote_addr = toolkit.request.remote_addr
        log_auth.info("Login attempt from %s", remote_addr)
        return

    def logout(self):
        try:
            remote_addr = toolkit.request.headers["X-Forwarded-For"]
        except KeyError:
            remote_addr = toolkit.request.remote_addr
        log_auth.info("Logout by %s from %s", toolkit.request.remote_user, remote_addr)
        return

    def abort(self, status_code, detail, headers, comment):
        """Handle an abort."""
        try:
            remote_addr = toolkit.request.headers["X-Forwarded-For"]
        except KeyError:
            remote_addr = toolkit.request.remote_addr
        log_auth.info(
            'Blocked request to %s with status %s becouse "%s" from %s',
            toolkit.request.url,
            status_code,
            detail,
            remote_addr,
        )
        return (status_code, detail, headers, comment)

    # IFacets

    def dataset_facets(self, facets_dict, package_type):
        """Modify and return the facets_dict for the dataset search page.

        :param facets_dict: the search facets as currently specified
        :type facets_dict: OrderedDict

        :param package_type: the package type that these facets apply to
        :type package_type: string

        :returns: the updated facets_dict
        :rtype: OrderedDict

        """
        self._update_facets(facets_dict, package_type, None)
        return facets_dict

    def group_facets(self, facets_dict, group_type, package_type):
        """Modify and return the facets_dict for a group's page.

        :param facets_dict: the search facets as currently specified
        :type facets_dict: OrderedDict

        :param group_type: the group type that these facets apply to
        :type group_type: string

        :param package_type: the package type that these facets apply to
        :type package_type: string

        :returns: the updated facets_dict
        :rtype: OrderedDict

        """
        self._update_facets(facets_dict, package_type, group_type)
        return facets_dict

    def organization_facets(self, facets_dict, organization_type, package_type):
        """Modify and return the facets_dict for an organization's page.

        :param facets_dict: the search facets as currently specified
        :type facets_dict: OrderedDict

        :param organization_type: the organization type that these facets apply
        :type organization_type: string

        :param package_type: the package type that these facets apply to
        :type package_type: string

        :returns: the updated facets_dict
        :rtype: OrderedDict
        """
        self._update_facets(facets_dict, package_type, organization_type)
        return facets_dict

    def _update_facets(self, facets_dict, package_type, group_type):
        """
            Add facet themes
        :param facets_dict:
        :return:
        """

        # populate search_extras global if any were used
        search_extras = {}
        for param, value in toolkit.request.args.items():
            if (
                param not in ["q", "page", "sort"]
                and len(value)
                and param.startswith("ext_")
            ):
                search_extras[param] = value
        toolkit.c.search_extras = search_extras

        if (
            "themes" not in facets_dict
            or "eov" not in facets_dict
            or "ecv" not in facets_dict
            or "responsible_organizations" not in facets_dict
            or "projects" not in facets_dict
            or "resource-type" not in facets_dict
            or "resorg_groups" not in facets_dict
        ):
            ordered_dict = facets_dict.copy()
            facets_dict.clear()

            facets_dict["eov"] = toolkit._("Ocean Variables")
            facets_dict["ecv"] = toolkit._("Climate Variables")
            if show_responsible_organizations:
                facets_dict["resorg_groups" + "_" + self.lang()] = toolkit._(
                    "Responsible Organization"
                )
            if not hide_organization_in_dataset_sidebar:
                facets_dict["organization" + "_" + self.lang()] = toolkit._(
                    "Organization"
                )
            facets_dict["harvest_source_title"] = toolkit._("Metadata Harvested From")
            facets_dict["tags" + "_" + self.lang()] = toolkit._("Tags")
            facets_dict["projects"] = toolkit._("Projects")
            facets_dict["resource-type"] = toolkit._("Resource Type")

            # add any facets we may have missed
            for key, value in ordered_dict.items():
                if key not in facets_dict:
                    facets_dict[key] = value

        # remove unneeded facet
        facets_to_hide = cioos_helpers.load_json(
            toolkit.config.get("ckan.cioos.exclude_facets", "[]")
        ) + ["groups", "organization", "tags"]
        log.debug("facets_to_hide: %r", facets_to_hide)
        for f in facets_to_hide:
            if f in facets_dict:
                facets_dict.pop(f)

        return facets_dict

    # IPackageController

    # modfiey tags, keywords, and eov fields so that they properly index
    def before_dataset_index(self, data_dict):
        try:
            data_type = data_dict.get("type")
            if data_type != "dataset":
                return data_dict

            try:
                tags_dict = cioos_helpers.load_json(data_dict.get("keywords", "{}"))
            except Exception as err:
                log.error(data_dict.get("id", "NO ID"))
                log.error(type(err))
                log.error("error:%s, keywords:%r", err, data_dict.get("keywords", "{}"))
                tags_dict = {"en": [], "fr": []}

            # update tag list by language
            data_dict["tags_en"] = tags_dict.get("en", [])
            data_dict["tags_fr"] = tags_dict.get("fr", [])
            data_dict["tags"] = data_dict["tags_en"] + data_dict["tags_fr"]

            # update citation by language
            citation_dict = cioos_helpers.load_json(data_dict.get("citation", "{}"))
            data_dict["citation_en"] = citation_dict.get("en", [])
            data_dict["citation_fr"] = citation_dict.get("fr", [])

            # update translation method fields by language
            ttm_dict = cioos_helpers.load_json(
                data_dict.get("title_translation_method", "{}")
            )
            data_dict["title_translation_method_en"] = ttm_dict.get("en", [])
            data_dict["title_translation_method_fr"] = ttm_dict.get("fr", [])

            ntm_dict = cioos_helpers.load_json(
                data_dict.get("notes_translation_method", "{}")
            )
            data_dict["notes_translation_method_en"] = ntm_dict.get("en", [])
            data_dict["notes_translation_method_fr"] = ntm_dict.get("fr", [])

            ktm_dict = cioos_helpers.load_json(
                data_dict.get("keywords_translation_method", "{}")
            )
            data_dict["keywords_translation_method_en"] = ktm_dict.get("en", [])
            data_dict["keywords_translation_method_fr"] = ktm_dict.get("fr", [])

            # split xml in harvest_document_content into french and englsih fields for indexing
            hdc = data_dict.get("harvest_document_content")
            if hdc:
                try:
                    namespaces = {
                        "lan": "http://standards.iso.org/iso/19115/-3/lan/1.0",
                        "mdb": "http://standards.iso.org/iso/19115/-3/mdb/2.0",
                        "gmd": "http://www.isotc211.org/2005/gmd",
                    }

                    root = ET.fromstring(hdc)

                    default_lang = root.xpath(
                        "./mdb:defaultLocale/lan:PT_Locale/lan:language/lan:LanguageCode/@codeListValue|./gmd:language/gmd:LanguageCode/@codeListValue",
                        namespaces=namespaces,
                    )
                    if default_lang:
                        default_lang = default_lang[0]

                    root_fr = ET.Element("fr")
                    root_en = ET.Element("en")
                    if default_lang in ["eng", "en"]:
                        for locale in root.xpath(
                            ".//lan:LocalisedCharacterString[@locale='#fr' or @locale='#FR']|.//gmd:LocalisedCharacterString[@locale='#fr' or @locale='#FR']",
                            namespaces=namespaces,
                        ):
                            root_fr.append(deepcopy(locale))
                            locale.getparent().remove(locale)
                        root_en = deepcopy(root)
                    elif default_lang in ["fra", "fr"]:
                        for locale in root.xpath(
                            ".//lan:LocalisedCharacterString[@locale='#en' or @locale='#EN']|.//gmd:LocalisedCharacterString[@locale='#en' or @locale='#EN']",
                            namespaces=namespaces,
                        ):
                            root_en.append(deepcopy(locale))
                            locale.getparent().remove(locale)
                        root_fr = deepcopy(root)
                    else:
                        log.error(
                            "No default language set in xml document. can not split document into language fields"
                        )

                    data_dict["harvest_document_content_en"] = ET.strip_tags(
                        root_en, "*", "*"
                    )
                    data_dict["harvest_document_content_fr"] = ET.strip_tags(
                        root_fr, "*", "*"
                    )
                except ET.XMLSyntaxError as err:
                    log.error(err)

            # update organization list by language
            org_id = data_dict.get("owner_org")
            if org_id:
                org_details = toolkit.get_action("organization_show")(
                    data_dict={
                        "id": org_id,
                        "include_datasets": False,
                        "include_dataset_count": False,
                        "include_extras": True,
                        "include_users": False,
                        "include_groups": False,
                        "include_tags": False,
                        "include_followers": False,
                    }
                )
                org_title = org_details.get("title_translated", {})
                data_dict["organization_en"] = org_title.get("en", "")
                data_dict["organization_fr"] = org_title.get("fr", "")

            try:
                title = cioos_helpers.load_json(data_dict.get("title_translated", "{}"))
                data_dict["title_en"] = title.get("en", [])
                data_dict["title_fr"] = title.get("fr", [])
            except Exception as err:
                log.error(err)

            try:
                title = cioos_helpers.load_json(data_dict.get("notes_translated", "{}"))
                data_dict["notes_en"] = title.get("en", [])
                data_dict["notes_fr"] = title.get("fr", [])
            except Exception as err:
                log.error(err)

            try:
                if not self.all_groups_dict_by_name:
                    self.all_groups_dict_by_name = self.get_all_groups("group", "name")

                for name in data_dict.get("groups", []):
                    if name.startswith("resorg"):
                        data_dict["resorg_groups"] = name
                        group_title = self.all_groups_dict_by_name[name].get(
                            "title_translated", {}
                        )
                        data_dict["resorg_groups_en"] = group_title.get("en", "")
                        data_dict["resorg_groups_fr"] = group_title.get("fr", "")

            except Exception as err:
                log.error(err)

            # create temporal extent index.
            # Composite field path: temporal-extent is a JSON string {"begin": ..., "end": ...}
            # Fallback path: harvested datasets may store temporal-extent-begin / temporal-extent-end
            # as separate extras (the harvester flattened the composite before storing).
            te = data_dict.get("temporal-extent", "{}")
            temporal_extent = cioos_helpers.load_json(te) if te else {}
            if isinstance(temporal_extent, list):
                temporal_extent = temporal_extent[0]
            temporal_extent_begin = temporal_extent.get("begin") or data_dict.get(
                "temporal-extent-begin"
            )
            temporal_extent_end = temporal_extent.get("end") or data_dict.get(
                "temporal-extent-end"
            )
            if temporal_extent_begin:
                data_dict["temporal-extent-begin"] = temporal_extent_begin
            if temporal_extent_end:
                data_dict["temporal-extent-end"] = temporal_extent_end
            # If end is not set then we will still include these dataset in temporal searches by giving them an end time of 'NOW'
            if temporal_extent_begin:
                data_dict["temporal-extent-range"] = (
                    "["
                    + temporal_extent_begin
                    + " TO "
                    + (temporal_extent_end or "*")
                    + "]"
                )

            # create vertical extent index
            ve = data_dict.get("vertical-extent", "{}")
            if ve:
                vertical_extent = cioos_helpers.load_json(ve)
                if isinstance(vertical_extent, list):
                    vertical_extent = vertical_extent[0]
                vertical_extent_min = vertical_extent.get("min")
                vertical_extent_max = vertical_extent.get("max")
                if vertical_extent_min:
                    data_dict["vertical-extent-min"] = vertical_extent_min
                if vertical_extent_max:
                    data_dict["vertical-extent-max"] = vertical_extent_max

            # eov is multi select so it is a json list rather then a python list
            if data_dict.get("eov"):
                data_dict["eov"] = cioos_helpers.load_json(data_dict["eov"])

            # ecv is multi select so it is a json list rather then a python list
            if data_dict.get("ecv"):
                data_dict["ecv"] = cioos_helpers.load_json(data_dict["ecv"])

            for res in data_dict.get("resources", []):
                res_name = cioos_helpers.load_json(res.get("name", "{}"))
                if (
                    res_name
                    and isinstance(res_name, dict)
                    and not res.get("name_translated")
                ):
                    res["name_translated"] = res_name
                resource_description = cioos_helpers.load_json(
                    res.get("description", "{}")
                )
                if (
                    resource_description
                    and isinstance(resource_description, dict)
                    and not res.get("description_translated")
                ):
                    res["description_translated"] = resource_description

            if data_dict.get("projects"):
                data_dict["projects"] = cioos_helpers.load_json(
                    data_dict.get("projects")
                )
        except Exception as e:
            log.exception(e)
            raise e
        return data_dict

    # group a list of dictionaries based on individual-name or organization-name keys
    def group_by_ind_or_org(self, dict_list):
        from collections import OrderedDict, defaultdict

        out = []
        dict_out = {}

        # create dictionary of grouped dictionaries where the keys are ind. name + org. name
        # and the values are dictionaries. The values ob sub dictionary keys are lists of all
        # the values found when merging the the original list of dictionaries.
        #
        # example output:
        # {'René MANGA_Agence Mamu Innu Kaikusseht (AMIK)': defaultdict( < class 'list' > , {
        #   'contact-info_email': ['enviro2@l-amik.ca', 'enviro2@l-amik.ca'],
        #   'contact-info_online-resource': ['', ''],
        #   'individual-name': ['René MANGA', 'René MANGA'],
        #   'individual-uri_authority': ['', 'orcid.org'],
        #   'individual-uri_code': ['https://orcid.org/0000-0003-4718-4962', 'https://orcid.org//0000-0003-4718-4962'],
        #   'individual-uri_code-space': ['', ''],
        #   'individual-uri_version': ['', ''],
        #   'organisation-name': ['Agence Mamu Innu Kaikusseht (AMIK)', 'Agence Mamu Innu Kaikusseht (AMIK)'],
        #   'role': ['custodian', 'rightsHolder']
        # }),...}
        for d in dict_list:
            group_value = (
                d.get("individual-name", "") + "_" + d.get("organisation-name", "")
            )
            if not dict_out.get(group_value):
                dict_out[group_value] = defaultdict(list)
            for key, value in d.items():
                if isinstance(value, list):
                    dict_out[group_value][key] = dict_out[group_value][key] + value
                else:
                    dict_out[group_value][key].append(value)

        # convert the above dictionary of default dictionary classes into a
        # dictionary of regular dictionaries classes
        # example output
        # {'René MANGA_Agence Mamu Innu Kaikusseht (AMIK)': {...
        for d in dict_list:
            group_value = (
                d.get("individual-name", "") + "_" + d.get("organisation-name", "")
            )
            dict_out[group_value] = dict(dict_out[group_value])

        # remove duplicate entries in value lists and convert to strings if only one value remaining
        for k1, v1 in dict_out.items():
            for k, v in v1.items():
                v1[k] = list(OrderedDict.fromkeys(v))
                if len(v1[k]) == 1:
                    v1[k] = v1[k][0]
                if isinstance(v1[k], list):
                    v1[k] = list(filter(None, v1[k]))  # remove empty strings from list
                    if len(v1[k]) == 1:
                        v1[k] = v1[k][0]
            out.append(v1)
        return out

    # handle custom temporal range search facet
    def before_dataset_search(self, search_params):
        if toolkit.request:
            lang = toolkit.h.lang()
            search_params["qf"] = "name^4 title_%s^4 tags_%s^2 text_%s text" % (
                lang,
                lang,
                lang,
            )

        extras = search_params.get("extras", {})
        search_params["fq_list"] = search_params.get("fq_list", [])

        # Temporal extent range filter
        begin = extras.get("ext_year_begin", "*")
        end = extras.get("ext_year_end", "*")
        if begin != "*" or end != "*":
            show_null_range = extras.get("ext_show_empty_range", "false")
            if show_null_range == "true":
                search_params["fq_list"].append(
                    f"+(temporal-extent-range:[{begin} TO {end}] OR (*:* NOT temporal-extent-range:[* TO *]))"
                )
            else:
                search_params["fq_list"].append(
                    f"+temporal-extent-range:[{begin} TO {end}]"
                )

        # Metadata date range filters (ext_created_begin/end, ext_modified_begin/end)
        for field, solr_field in [
            ("created", "metadata_created"),
            ("modified", "metadata_modified"),
        ]:
            b = extras.get(f"ext_{field}_begin", "")
            e = extras.get(f"ext_{field}_end", "")
            if b or e:
                search_params["fq_list"].append(
                    f"+{solr_field}:[{b + 'T00:00:00Z' if b else '*'} TO {e + 'T23:59:59Z' if e else '*'}]"
                )

        return search_params

    def populate_schema_select_display_name(self, search_facets, field_name):
        facet_field = search_facets[field_name]
        items = facet_field.get("items")
        if not items:
            return items or []
        schema = toolkit.h.scheming_get_dataset_schema("dataset")
        fields = schema["dataset_fields"]
        field = toolkit.h.scheming_field_by_name(fields, field_name)
        if not field:
            return None
        choices = toolkit.h.scheming_field_choices(field)
        new_values = []
        for item in items:
            for ch in choices:
                if ch["value"] == item["name"]:
                    item["display_name"] = toolkit.h.scheming_language_text(
                        ch.get("label", item["name"])
                    )
                    cat = ch.get("category", "")
                    if cat:
                        item["category"] = cat
                    subcat = ch.get("subcatagory", "")
                    if subcat:
                        item["subcategory"] = subcat
            new_values.append(item)
        return new_values

    def get_all_groups(self, action_type, key="id", groups=None):
        group_list = []
        limit = 25
        offset = 0
        schema_list = toolkit.get_action("scheming_%s_schema_list" % action_type)()
        schema_types = list(dict.fromkeys(schema_list + [action_type]))
        groups_dict = {}
        if groups:
            groups_dict = {"groups": groups}

        for type in schema_types:
            while True:
                # need to turn off dataset_count here as it causes a recursive loop with package_search
                res = toolkit.get_action("%s_list" % action_type)(
                    data_dict={
                        "type": type,
                        "limit": limit,
                        "offset": offset,
                        "all_fields": True,
                        "include_dataset_count": False,
                        "include_extras": True,
                        "include_users": False,
                        "include_groups": False,
                        "include_tags": False,
                        **groups_dict,
                    }
                )
                if not res:
                    break
                group_list = group_list + res
                offset = offset + limit
        return {x[key]: x for x in group_list}

    def get_group(self, type, id):
        # need to turn off dataset_count, users and groups here as it causes a recursive loop
        try:
            group = toolkit.get_action("%s_show" % type)(
                data_dict={
                    "id": id,
                    "include_datasets": False,
                    "include_dataset_count": False,
                    "include_extras": True,
                    "include_users": False,
                    "include_groups": False,
                    "include_tags": False,
                    "include_followers": False,
                }
            )
        except NotFound:
            log.warning("Group or Organization %s not found", id)
            return None
        return group

    # update eov search facets with keys from choices list in the scheming extension schema
    # format search results for consistant json output
    # add organization extra fields to results
    def after_dataset_search(self, search_results, search_params):
        org_dict = {}
        group_dict = {}
        group_dict_by_name = {}

        # no need to do all this if not returning data anyway
        if search_params.get("rows") == 0:
            return search_results

        try:
            search_results["search_facets"]["eov"]["items"] = (
                self.populate_schema_select_display_name(
                    search_results["search_facets"], "eov"
                )
            )
        except:
            pass

        try:
            search_results["search_facets"]["ecv"]["items"] = (
                self.populate_schema_select_display_name(
                    search_results["search_facets"], "ecv"
                )
            )
        except:
            pass

        try:
            items = search_results["search_facets"]["license_id"]["items"]
            if items:
                new_license_items = []
                for item in items:
                    license = toolkit.h.cioos_get_license_def(item["name"], None, None)
                    if license:
                        item["display_name"] = license["license_title"]
                    new_license_items.append(item)
                search_results["search_facets"]["license_id"]["items"] = (
                    new_license_items
                )
        except:
            pass

        try:
            items = search_results["search_facets"]["resorg_groups"]["items"]
            # move group call here so it is only run if needed
            group_dict = self.get_all_groups("group")
            group_dict_by_name = {v["name"]: v for k, v in group_dict.items()}
            if items:
                new_resorg_items = []
                for item in items:
                    item["display_name"] = group_dict_by_name[item["name"]][
                        "display_name"
                    ]
                    new_resorg_items.append(item)
                search_results["search_facets"]["resorg_groups"]["items"] = (
                    new_resorg_items
                )
        except:
            pass

        groups = search_results["search_facets"].get("groups", {})
        # convert string encoded json to json objects for translated fields
        # package_search with filters uses solr index values which are strings
        # this is inconsistant with package data which is returned as json objects
        # by the package_show and package_search end points whout filters applied
        for i, result in enumerate(search_results.get("results", [])):
            try:
                if (
                    toolkit.request.path == "/dataset/"
                    or toolkit.request.path == "/dataset"
                ) and search_params["fl"] == "id validated_data_dict":
                    fields_to_keep = [
                        "title_translated",
                        "notes_translated",
                        "resources",
                        "state",
                        "dataset_type",
                        "type",
                        "name",
                        "private",
                        "unique-resource-identifier-full",
                    ]
                    result = {k: v for k, v in result.items() if k in fields_to_keep}
                    try:
                        result["notes_translated"]["en"] = result["notes_translated"][
                            "en"
                        ][:200]
                        result["notes_translated"]["fr"] = result["notes_translated"][
                            "fr"
                        ][:200]
                    except:
                        pass
            except:
                pass

            # Update group list
            groups = result.get("groups")
            if groups:
                # if there are groups to update and the group dict has not been populated, fetch it
                if not group_dict:
                    group_dict = self.get_all_groups("group")
                new_group_list = []
                for group in groups:
                    new_group_list.append(group_dict.get(group["id"], group))
                if new_group_list:
                    result["groups"] = new_group_list

            if result.get("cited-responsible-party"):
                result["cited-responsible-party"] = self.group_by_ind_or_org(
                    result.get("cited-responsible-party")
                )
            if result.get("metadata-point-of-contact"):
                result["metadata-point-of-contact"] = self.group_by_ind_or_org(
                    result.get("metadata-point-of-contact")
                )

            # fluent output validators set title and notes to the default language on package_show
            # doing the same here so the output is consistent
            title = result.get("title_translated")
            if title:
                result["title_translated"] = cioos_helpers.load_json(title)
                if isinstance(result["title_translated"], dict):
                    result["title"] = scheming_language_text(
                        result["title_translated"],
                        toolkit.config.get("ckan.locale_default", "en"),
                    )

            notes = result.get("notes_translated")
            if notes:
                result["notes_translated"] = cioos_helpers.load_json(notes)
                if isinstance(result["notes_translated"], dict):
                    result["notes"] = scheming_language_text(
                        result["notes_translated"],
                        toolkit.config.get("ckan.locale_default", "en"),
                    )

            for res in result.get("resources", []):
                res_name = cioos_helpers.load_json(res.get("name_translated", "{}"))
                if res_name and isinstance(res_name, dict):
                    res["name"] = scheming_language_text(
                        res_name, toolkit.config.get("ckan.locale_default", "en")
                    )
                resource_description = cioos_helpers.load_json(
                    res.get("description_translated", "{}")
                )
                if resource_description and isinstance(resource_description, dict):
                    res["description"] = scheming_language_text(
                        resource_description,
                        toolkit.config.get("ckan.locale_default", "en"),
                    )

            # convert the rest of the strings from json
            for field in [
                "keywords",
                "temporal-extent",
                "unique-resource-identifier-full",
                "vertical-extent",
                "dataset-reference-date",
                "metadata-reference-date",
                "metadata-point-of-contact",
                "cited-responsible-party",
                "projects",
            ]:
                tmp = result.get(field)
                if tmp:
                    result[field] = cioos_helpers.load_json(tmp)

            # update organization object while we are at it
            org_id = result.get("owner_org")
            if org_id:
                # if org id and org dict has not been populated, fetch it
                if not org_dict:
                    org_dict = self.get_all_groups("organization")
                org_details = org_dict.get(org_id, {})
                organization = result.get("organization", {})
                if organization or org_details:
                    new_org_dict = {**organization, **org_details}
                    result["organization"] = new_org_dict
                else:
                    log.warn("No org details for owner_org %s", org_id)

            search_results["results"][i] = result
        return search_results

    # add organization extras to organization object in package.
    # this will make the show and search endpoints look the same
    def after_dataset_show(self, context, package_dict):
        if toolkit.request and toolkit.request.path.startswith("/dataset/"):
            try:
                del package_dict["harvest_document_content"]
            except:
                pass
        org_id = package_dict.get("owner_org")
        data_type = package_dict.get("type")

        if org_id and (data_type == "dataset" or data_type == "harvest"):
            org_details = self.get_group("organization", org_id)
            if org_details:
                package_org = package_dict["organization"]
                new_org = {**package_org, **org_details}
                if new_org:
                    package_dict["organization"] = new_org

        if data_type == "harvest":
            return package_dict

        # Update group list
        # TODO since groups are split into there own page do we need this? might still be used during indexing?
        groups = package_dict.get("groups")
        if groups:
            group_dict = self.get_all_groups(
                "group", groups=[x["name"] for x in groups]
            )
            new_group_list = []
            for group in groups:
                new_group_list.append(group_dict.get(group["id"], group))
            if new_group_list:
                package_dict["groups"] = new_group_list

        if package_dict.get("cited-responsible-party"):
            package_dict["cited-responsible-party"] = self.group_by_ind_or_org(
                package_dict.get("cited-responsible-party")
            )
        if package_dict.get("metadata-point-of-contact"):
            package_dict["metadata-point-of-contact"] = self.group_by_ind_or_org(
                package_dict.get("metadata-point-of-contact")
            )

        result = package_dict
        title = result.get("title_translated")
        if title:
            result["title_translated"] = cioos_helpers.load_json(title)
        notes = result.get("notes_translated")
        if notes:
            result["notes_translated"] = cioos_helpers.load_json(notes)

        # convert the rest of the strings from json
        for field in [
            "keywords",
            "temporal-extent",
            "unique-resource-identifier-full",
            "vertical-extent",
            "dataset-reference-date",
            "metadata-reference-date",
            "metadata-point-of-contact",
            "cited-responsible-party",
            "projects",
        ]:
            tmp = result.get(field)
            if tmp:
                result[field] = cioos_helpers.load_json(tmp)
        package_dict = result

        # Update package relationships with package name
        ras = package_dict["relationships_as_subject"]
        for rel in ras:
            if rel.get("__extras"):
                id = rel["__extras"]["object_package_id"]
                result = toolkit.get_action("package_search")(
                    context, data_dict={"q": "id:%s" % id, "fl": "name"}
                )
                if result["results"]:
                    rel["__extras"]["object_package_name"] = result["results"][0][
                        "name"
                    ]
                rel["__extras"]["subject_package_name"] = package_dict["name"]
            else:
                id = rel["object_package_id"]
                result = toolkit.get_action("package_search")(
                    context, data_dict={"q": "id:%s" % id, "fl": "name"}
                )
                if result["results"]:
                    rel["object_package_name"] = result["results"][0]["name"]
                rel["subject_package_name"] = package_dict["name"]

        rao = package_dict["relationships_as_object"]
        for rel in rao:
            if rel.get("__extras"):
                rel["__extras"]["object_package_name"] = package_dict["name"]
                id = rel["__extras"]["subject_package_id"]
                result = toolkit.get_action("package_search")(
                    context, data_dict={"q": "id:%s" % id, "fl": "name"}
                )
                if result["results"]:
                    rel["__extras"]["subject_package_name"] = result["results"][0][
                        "name"
                    ]
            else:
                rel["object_package_name"] = package_dict["name"]
                id = rel["subject_package_id"]
                result = toolkit.get_action("package_search")(
                    context, data_dict={"q": "id:%s" % id, "fl": "name"}
                )
                if result["results"]:
                    rel["subject_package_name"] = result["results"][0]["name"]
        return package_dict

    def lang(self):
        return toolkit.h.lang()
