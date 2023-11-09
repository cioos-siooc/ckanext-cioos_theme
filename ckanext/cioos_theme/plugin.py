# encoding: utf-8

import ckan.plugins as plugins
import ckan.plugins.toolkit as toolkit
import ckan.model as model
from ckan.views.dataset import GroupView
import ckanext.cioos_theme.helpers as cioos_helpers
import ckanext.cioos_theme.cli as cli
import ckanext.cioos_theme.util.package_relationships as pr
from ckanext.scheming.validation import scheming_validator
from ckanext.scheming.helpers import scheming_language_text
from ckan.logic import NotFound
from ckan.lib.plugins import DefaultTranslation
import ckan.model as model
from flask import Blueprint
import json
from shapely.geometry import shape
import logging
import ckan.lib.navl.dictization_functions as df
from ckantoolkit import g
from six.moves.urllib.parse import urlparse
import string
from ckantoolkit import _
import ckan.lib.base as base
import re
import time
from pyld import jsonld
import ckan.lib.munge as munge
import lxml.etree as ET
from copy import deepcopy

Invalid = df.Invalid

# import debugpy

StopOnError = df.StopOnError
missing = df.missing
log = logging.getLogger(__name__)
log_auth = logging.getLogger(__name__ + '.auth')

# debugpy.listen(('0.0.0.0', 5678))
# log.debug("Waiting for debugger attach")
# debugpy.wait_for_client()




show_responsible_organizations = toolkit.asbool(
    toolkit.config.get('cioos.show_responsible_organizations_facet', "True"))

hide_organization_in_dataset_sidebar = toolkit.asbool(
    toolkit.config.get('cioos.hide_organization_in_dataset_sidebar', "True"))

contact_email = toolkit.config.get('cioos.contact_email', "info@cioos.ca")
organizations_info_text = toolkit.config.get(
    'cioos.organizations_info_text',
    {
        "en": "CKAN Organizations are used to create, manage and publish collections of datasets. Users can have different roles within an Organization, depending on their level of authorisation to create, edit and publish.",
        "fr": u"Les Organisations CKAN sont utilisées pour créer, gérer et publier des collections de jeux de données. Les utilisateurs peuvent avoir différents rôles au sein d'une Organisation, en fonction de leur niveau d'autorisation pour créer, éditer et publier."
    }
)

group_info_text = toolkit.config.get(
    'cioos.group_info_text',
    {
    "resorg":{
        "en":"You can use CKAN Responsible Organizations to create and manage collections of datasets. In this case, a dataset is assigned to each organization that has been identified as contributing to, retains ownership of, or responsible for the data in the dataset.",
        "fr":"Vous pouvez utiliser les organisations responsables de CKAN pour créer et gérer des collections d'ensembles de données. Dans ce cas, un ensemble de données est attribué à chaque organisation qui a été identifiée comme contribuant, conservant la propriété ou responsable des données de l'ensemble de données."
    },
    "group": {
        "en": "You can use CKAN Groups to create and manage collections of datasets. This could be to catalogue datasets for a particular project or team, or on a particular theme, or as a very simple way to help people find and search your own published datasets.",
        "fr": u"Vous pouvez utiliser les groupes CKAN pour créer et gérer des collections d'ensembles de données. Il peut s'agir de cataloguer des ensembles de données pour un projet ou une équipe particulière, ou sur un thème particulier, ou encore d'un moyen très simple d'aider les gens à trouver et à rechercher vos propres ensembles de données publiés."
    }
    }
)





def geojson_to_bbox(o):
    return shape(o).bounds


def populate_select(key, data, errors, langs, select_field, keyword_list):
    candidate_dict = {}
    # create dictionary from select choice list
    for x in toolkit.h.scheming_field_choices(select_field):
        candidate_dict[x['value'].lower()] = x['value']
        for id in x.get('alternative_ids', []):
            candidate_dict[id.lower()] = x['value']
        for lang in langs:
            if x['label'].get(lang):
                candidate_dict[x['label'][lang].lower()] = x['value']
                # if clean_tags is true during harvesting then spaces will be
                # replaced by dash's by mung_tags
                candidate_dict[x['label'][lang].replace(' ', '-').lower()] = x['value']
    
    d = json.loads(data.get(key, '[]'))
    # search for matching keywords in select choices dictionary
    for x in keyword_list:
        if isinstance(x, str):
            val = candidate_dict.get(x.lower(), '')
        elif isinstance(x, dict):
            val = candidate_dict.get(x['name'].lower(), '')
        else:
            val = candidate_dict.get(x, '')
        if val and val not in d:
            d.append(val)

    # why do we run this twice? double errors in list?
    if len(d) and u'Select at least one' in errors[key]:
        errors[key].remove(u'Select at least one')
    if len(d) and 'Select at least one' in errors[key]:
        errors[key].remove('Select at least one')

    data[key] = json.dumps(d)
    return data

# IValidators

# this validator tries to populate eov from keywords. It looks for any english
# keywords that match either the value or label in the choice list for the eov
# field and add's them to the eov field.
@scheming_validator
def clean_and_populate_eovs(field, schema):

    def validator(key, data, errors, context):
        if errors[key] and (u'Select at least one' not in errors[key] or 'Select at least one' not in errors[key]):
            return

        select_field = toolkit.h.scheming_field_by_name(schema['dataset_fields'], 'eov')
        langs = toolkit.h.fluent_form_languages(select_field, None, None, schema)

        keywords_main = data.get(('keywords',), {})
        if keywords_main:
            keyword_list = keywords_main.get('en', []) + keywords_main.get('fr', [])
        else:
            extras = data.get(("__extras", ), {})
            keyword_list = extras.get('keywords-en', '').split(',') + extras.get('keywords-fr', '').split(',')

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

        select_field = toolkit.h.scheming_field_by_name(schema['dataset_fields'], 'ecv')
        langs = toolkit.h.fluent_form_languages(select_field, None, None, schema)

        keywords_main = data.get(('keywords',), {})
        if keywords_main:
            keyword_list = keywords_main.get('en', []) + keywords_main.get('fr', [])
        else:
            extras = data.get(("__extras", ), {})
            keyword_list = extras.get('keywords-en', '').split(',') + extras.get('keywords-fr', '').split(',')

        return populate_select(key, data, errors, langs, select_field, keyword_list)

    return validator


@scheming_validator
def fluent_field_default(field, schema):

    def validator(key, data, errors, context):
        if not data[key]:
            # field is blank, populate with default value
            data[key] = {}
            lang_list = toolkit.h.fluent_form_languages()
            for l in lang_list:
                data[key][l] = ''

        elif not data[key].startswith('{'):
            # its a string, need to format as a json object
            new_dict = {}
            lang_list = toolkit.h.fluent_form_languages()
            for l in lang_list:
                new_dict[l] = data[key]
            data[key] = new_dict
        # we should now have a json object so nothing left to do.
        return data
    return validator


def url_validator_with_port(key, data, errors, context):
    ''' Checks that the provided value (if it is present) is a valid URL, accepts port numbers in URL '''

    url = data.get(key, None)
    if not url:
        return

    try:
        pieces = urlparse(url)
        if all([pieces.scheme, pieces.netloc]) and \
           set(pieces.netloc) <= set(string.ascii_letters + string.digits + '-.:') and \
           pieces.scheme in ['http', 'https']:
            return
    except ValueError:
        # url is invalid
        pass
    errors[key].append(_('Please provide a valid URL'))


@scheming_validator
def cioos_tag_name_validator(field, schema):

    def validator(value, context):
        tagname_match = re.compile("[\w\u00C0-\u018F\u0300-\u0315 .'’,;\\/\(\)-]*$", re.UNICODE)
        if not tagname_match.match(value):
            raise Invalid(_('Tag "%s" must be alphanumeric characters or symbols: -_.,;\'()') % (value))
        return value
    return validator


@scheming_validator
def cioos_is_valid_range(field, schema):

    def validator(value, context):
        range = cioos_helpers.load_json(value)
        if (not range.get('begin') and range.get('end')) or (range.get('end') and range['end'] < range['begin']):
            raise Invalid(_('Invalid value "%r". Valid ranges must contain begin <= end values') % (value))
        return value
    return validator


def render_schemamap():
    return toolkit.render('schemamap.html')

def render_datacite_xml(id):
    context = {'model': model, 'session': model.Session,
               'user': g.user, 'for_view': True,
               'auth_user_obj': g.userobj}
    data_dict = {'id': id}

    try:
        toolkit.check_access('package_update', context, data_dict)
    except toolkit.ObjectNotFound:
        toolkit.abort(404, _('Dataset not found'))
    except toolkit.NotAuthorized:
        toolkit.abort(403, _('User %r not authorized to view datacite xml for %s') % (g.user, id))

    pkg = toolkit.get_action('package_show')(data_dict={'id': id})
    return toolkit.render('package/datacite.html', extra_vars={'pkg_dict': pkg})

def render_basic_package_view(id):
    pkg = toolkit.get_action('package_show')(data_dict={'id': id})
    return toolkit.render('package/basic.html', extra_vars={'pkg_dict': pkg})

@toolkit.chained_action
@toolkit.side_effect_free
def dcat_dataset_show(up_func, context, data_dict):

    parent_output = up_func(context, data_dict)
    _frame = toolkit.request.params.get('frame')
    if _frame == 'schemaorg':
        frametext =   {
            "@context": {"@vocab": "http://schema.org/"},
            "@type": "Dataset"
        }
        framed_output = jsonld.frame(json.loads(parent_output), frametext)
        return framed_output
    return parent_output
    
class Cioos_ThemePlugin(plugins.SingletonPlugin, DefaultTranslation):
    plugins.implements(plugins.ITranslation)
    plugins.implements(plugins.IConfigurer)
    plugins.implements(plugins.ITemplateHelpers)
    plugins.implements(plugins.IFacets)
    plugins.implements(plugins.IPackageController, inherit=True)
    plugins.implements(plugins.IValidators)
    plugins.implements(plugins.IAuthenticator)
    plugins.implements(plugins.IClick)
    plugins.implements(plugins.IBlueprint)
    plugins.implements(plugins.IActions)
    # plugins.implements(plugins.IDatasetForm)

    all_groups_dict_by_name = None

    #IActions

    def get_actions(self):
        return {
            u"dcat_dataset_show": dcat_dataset_show
        }

    # IClick
    def get_commands(self):
        return cli.get_commands()


    def dataset_custom_GroupView(self, package_type, id):
        if toolkit.request.method == 'POST':
            GroupView().post(
                package_type, 
                id
            )
            return toolkit.h.redirect_to('cioos.resorg', package_type=package_type, id=id)
        
        context, pkg_dict = GroupView()._prepare(id)
        dataset_type = pkg_dict['type'] or package_type
        context['is_member'] = True
        users_groups = toolkit.get_action('group_list_authz')(context, {'id': id})

        pkg_group_ids = set(
            group['id'] for group in pkg_dict.get('groups', [])
        )

        user_group_ids = set(group['id'] for group in users_groups)
        filtered_groups = toolkit.get_action('group_list')(context, data_dict={'type':'resorg'})

        # filter groups by type       
        pkg_dict['groups'] = [g for g in pkg_dict.get('groups', []) if g['name'] in filtered_groups]
        group_dropdown = [[group['id'], group['display_name']]
                          for group in users_groups
                          if group['id'] not in pkg_group_ids
                          and group['name'] in filtered_groups]

        for group in pkg_dict.get('groups', []):
            group['user_member'] = (group['id'] in user_group_ids)

        # TODO: remove
        #g.pkg_dict = pkg_dict
        #g.group_dropdown = group_dropdown

        return base.render(
            u'package/group_list.html', {
                u'dataset_type': dataset_type,
                u'pkg_dict': pkg_dict,
                u'group_dropdown': group_dropdown
            }
        ) 

    # IBlueprint
    def get_blueprint(self):
        blueprint = Blueprint('cioos', self.__module__)
        rules = [
            ('/schemamap', 'schemamap', render_schemamap),
            ('/dataset/<id>.dcxml', 'datacite_xml', render_datacite_xml),
            ('/dataset/<id>.basic', 'package_basic', render_basic_package_view),
        ]
        for rule in rules:
            blueprint.add_url_rule(*rule)

        blueprint.add_url_rule('/<package_type>/resorg/<id>', 'resorg', view_func=self.dataset_custom_GroupView, methods=['GET', 'POST'])

        return blueprint

    # IAuthenticator

    def identify(self):
        try:
            remote_addr = toolkit.request.headers['X-Forwarded-For']
        except KeyError:
            remote_addr = toolkit.request.remote_addr

        log_auth.info('Request by %s for %s from %s', toolkit.request.remote_user, toolkit.request.url, remote_addr)
        g.user = None
        g.userobj = None
        return

    def login(self, error=None):
        try:
            remote_addr = toolkit.request.headers['X-Forwarded-For']
        except KeyError:
            remote_addr = toolkit.request.remote_addr
        log_auth.info('Login attempt from %s', remote_addr)
        return

    def logout(self):
        try:
            remote_addr = toolkit.request.headers['X-Forwarded-For']
        except KeyError:
            remote_addr = toolkit.request.remote_addr
        log_auth.info('Logout by %s from %s', toolkit.request.remote_user, remote_addr)
        return

    def abort(self, status_code, detail, headers, comment):
        '''Handle an abort.'''
        try:
            remote_addr = toolkit.request.headers['X-Forwarded-For']
        except KeyError:
            remote_addr = toolkit.request.remote_addr
        log_auth.info('Blocked request to %s with status %s becouse "%s" from %s', toolkit.request.url, status_code, detail, remote_addr)
        return (status_code, detail, headers, comment)

    # IConfigurer

    def update_config(self, config_):
        toolkit.add_template_directory(config_, 'templates')
        toolkit.add_public_directory(config_, 'public')
        toolkit.add_resource('fanstatic', 'cioos_theme')
        toolkit.add_resource('public', 'ckanext-cioos_theme')

    def update_config_schema(self, schema):

        ignore_missing = toolkit.get_validator('ignore_missing')
        fluent_text = toolkit.get_validator('fluent_text')
        boolean_validator = toolkit.get_validator('boolean_validator')

        schema.update({
            'ckan.site_title': [ignore_missing, fluent_field_default(None, None), fluent_text(None, None)],
            'ckan.site_heading': [ignore_missing, fluent_field_default(None, None), fluent_text(None, None)],
            'ckan.site_description': [ignore_missing, fluent_field_default(None, None), fluent_text(None, None)],
            'ckan.site_about': [ignore_missing, fluent_field_default(None, None), fluent_text(None, None)],
            'ckan.site_intro_text': [ignore_missing, fluent_field_default(None, None), fluent_text(None, None)],
            'ckan.site_logo_translated': [ignore_missing, fluent_field_default(None, None), fluent_text(None, None)],
            'ckan.site_home_url': [ignore_missing, url_validator_with_port],
            'ckan.exclude_eov_category': [ignore_missing],
            'ckan.exclude_eov': [ignore_missing],
            'ckan.eov_icon_base_path': [ignore_missing],
            'ckan.header_file_name': [ignore_missing],
            'ckan.footer_file_name': [ignore_missing],
            'ckan.show_social_in_dataset_sidebar': [ignore_missing, boolean_validator],
            'ckan.hide_organization_in_breadcrumb': [ignore_missing, boolean_validator],
            'ckan.hide_organization_in_dataset_sidebar': [ignore_missing, boolean_validator],
            'ckan.show_language_picker_in_top_bar': [ignore_missing, boolean_validator],
            'ckan.show_language_picker_in_menu': [ignore_missing, boolean_validator],
        })
        return schema

    def get_additional_css_path(self):
        return toolkit.config.get('ckan.cioos.ra_css_path')

    def get_helpers(self):
        return {
            'cioos_organizations_info_text': lambda: organizations_info_text,
            'cioos_contact_email': lambda: contact_email,
            'cioos_group_info_text': lambda: group_info_text,
            'cioos_load_json': cioos_helpers.load_json,
            'cioos_geojson_to_bbox': geojson_to_bbox,
            'cioos_get_facets': cioos_helpers.cioos_get_facets,
            #'cioos_get_package_title': cioos_helpers.get_package_title,
            'cioos_get_package_relationships': cioos_helpers.get_package_relationships,
            #'cioos_print_package_relationship_type': cioos_helpers.print_package_relationship_type,
            #'cioos_get_package_relationship_reverse_type': cioos_helpers.get_package_relationship_reverse_type,
            'cioos_datasets': cioos_helpers.cioos_datasets,
            'cioos_count_datasets': cioos_helpers.cioos_count_datasets,
            'cioos_get_eovs': cioos_helpers.cioos_get_eovs,
            'cioos_get_locale_url': self.get_locale_url,
            'cioos_schema_field_map': cioos_helpers.cioos_schema_field_map,
            'cioos_get_additional_css_path': self.get_additional_css_path,
            'cioos_get_doi_authority_url': cioos_helpers.get_doi_authority_url,
            'cioos_get_doi_prefix': cioos_helpers.get_doi_prefix,
            'cioos_get_datacite_org': cioos_helpers.get_datacite_org,
            'cioos_get_datacite_test_mode': cioos_helpers.get_datacite_test_mode,
            'cioos_helper_available': cioos_helpers.helper_available,
            'cioos_group_contacts': self.group_by_ind_or_org,
            'cioos_get_fully_qualified_package_uri': cioos_helpers.get_fully_qualified_package_uri,
            'cioos_version': cioos_helpers.cioos_version,
            'cioos_get_license_def': cioos_helpers.get_license_def,
            'cioos_merge_dict': cioos_helpers.merge_dict,
            'cioos_get_dataset_extents': cioos_helpers.get_dataset_extents,
            'cioos_get_ra_extents': cioos_helpers.get_ra_extents,
            'cioos_get_extra_value':self._get_extra_value
        }

    def get_validators(self):
        return {
            'cioos_clean_and_populate_eovs': clean_and_populate_eovs,
            'cioos_clean_and_populate_ecvs': clean_and_populate_ecvs,
            'cioos_fluent_field_default': fluent_field_default,
            'cioos_url_validator_with_port': url_validator_with_port,
            'cioos_tag_name_validator': cioos_tag_name_validator,
            'cioos_is_valid_range': cioos_is_valid_range,
        }

    # IFacets

    def dataset_facets(self, facets_dict, package_type):
        u"""Modify and return the facets_dict for the dataset search page.

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
        u"""Modify and return the facets_dict for a group's page.

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
        u"""Modify and return the facets_dict for an organization's page.

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
        u"""
            Add facet themes
        :param facets_dict:
        :return:
        """

        # populate search_extras global if any were used
        search_extras = {}
        for (param, value) in toolkit.request.params.items():
            if param not in ['q', 'page', 'sort'] \
                    and len(value) and param.startswith('ext_'):
                search_extras[param] = value
        toolkit.c.search_extras = search_extras

        # remove unneeded facet
        for f in ['groups','organization','tags']:
            if f in facets_dict:
               facets_dict.pop(f)

        if 'themes' not in facets_dict \
                or 'eov' not in facets_dict \
                or 'ecv' not in facets_dict \
                or 'responsible_organizations' not in facets_dict \
                or 'projects' not in facets_dict \
                or 'resource-type' not in facets_dict \
                or 'resorg_groups' not in facets_dict:

            ordered_dict = facets_dict.copy()
            facets_dict.clear()
            
            facets_dict['eov'] = toolkit._('Ocean Variables')
            facets_dict['ecv'] = toolkit._('Climate Variables')
            if show_responsible_organizations:
                facets_dict['resorg_groups' + '_' + self.lang()] = toolkit._('Responsible Organization')
            if not hide_organization_in_dataset_sidebar:
                facets_dict['organization' + '_' + self.lang()] = toolkit._('Organization')
            facets_dict['harvest_source_title'] = toolkit._('Metadata Harvested From')
            facets_dict['tags' + '_' + self.lang()] = toolkit._('Tags')           
            facets_dict['projects'] = toolkit._('Projects')
            facets_dict['resource-type'] = toolkit._('Resource Type')
            
            # add any facets we may have missed
            for key, value in ordered_dict.items():
                if key not in facets_dict:            
                    facets_dict[key] = value
        return facets_dict


    # IPackageController

    # def _cited_responsible_party_to_responsible_organizations(self, parties, force_responsible_organization, as_group = False):
    #     if force_responsible_organization:
    #         if isinstance(force_responsible_organization, list):
    #             resp_orgs = force_responsible_organization
    #         else:
    #             resp_orgs = [force_responsible_organization]
    #     else:
    #         resp_org_roles = cioos_helpers.load_json(toolkit.config.get('ckan.responsible_organization_roles', '["owner", "originator", "custodian", "author", "principalInvestigator"]'))

    #     if as_group:
    #         resp_orgs = [
    #             {
    #                 'name': munge.munge_name(x['organisation-name'].strip()).lower(),
    #                 'display_name': x['organisation-name'].strip(),
    #                 'title': x['organisation-name'].strip(),
    #                 'title_translated': {
    #                     'en' : x['organisation-name'].strip(),
    #                     'fr' : x['organisation-name'].strip(),
    #                 },
    #                 'organisation-uri':{
    #                     'authority': x.get('organisation-uri_authority'),
    #                     'code': x.get('organisation-uri_code'),
    #                     'code-space': x.get('organisation-uri_code-space'),
    #                     'version': x.get('organisation-uri_version'),
    #                 },
    #             } 
    #             for x in cioos_helpers.load_json(parties) if not set(cioos_helpers.load_json(x.get('role'))).isdisjoint(resp_org_roles)
    #         ]
    #     else:
    #         resp_orgs = [x.get('organisation-name', '').strip() for x in cioos_helpers.load_json(parties) if not set(cioos_helpers.load_json(x.get('role'))).isdisjoint(resp_org_roles)]
            
    #     resp_orgs = list(dict.fromkeys(resp_orgs))  # remove duplicates
    #     resp_orgs = list(filter(None, resp_orgs))  # remove empty elements (in a python 2 and 3 friendly way)

    #     return resp_orgs

    def _get_extra_value(self, key, package_dict):
        for extra in package_dict.get('extras', []):
            if extra['key'] == key:
                return extra['value']

    def after_create(self, context, data_dict):
        #pr.update_package_relationships(context, data_dict, is_create=True)
        pass

    def after_update(self, context, data_dict):
        #pr.update_package_relationships(context, data_dict, is_create=False)
        pass

    # modfiey tags, keywords, and eov fields so that they properly index
    def before_index(self, data_dict):
        data_type = data_dict.get('type')
        if data_type != 'dataset':
            return data_dict

        try:
            tags_dict = cioos_helpers.load_json(data_dict.get('keywords', '{}'))
        except Exception as err:
            log.error(data_dict.get('id', 'NO ID'))
            log.error(type(err))
            log.error("error:%s, keywords:%r", err, data_dict.get('keywords', '{}'))
            tags_dict = {"en": [], "fr": []}

        # force_resp_org = cioos_helpers.load_json(data_dict.get('force_responsible_organization', '[]'))
        # data_dict['responsible_organizations'] = self._cited_responsible_party_to_responsible_organizations(data_dict.get('cited-responsible-party', '{}'), force_resp_org)


        # update tag list by language
        data_dict['tags_en'] = tags_dict.get('en', [])
        data_dict['tags_fr'] = tags_dict.get('fr', [])
        data_dict['tags'] = data_dict['tags_en'] + data_dict['tags_fr']

        # update citation by language
        citation_dict = cioos_helpers.load_json(data_dict.get('citation', '{}'))
        data_dict['citation_en'] = citation_dict.get('en', [])
        data_dict['citation_fr'] = citation_dict.get('fr', [])

        # update translation method fields by language
        ttm_dict = cioos_helpers.load_json(data_dict.get('title_translation_method', '{}'))
        data_dict['title_translation_method_en'] = ttm_dict.get('en', [])
        data_dict['title_translation_method_fr'] = ttm_dict.get('fr', [])

        ntm_dict = cioos_helpers.load_json(data_dict.get('notes_translation_method', '{}'))
        data_dict['notes_translation_method_en'] = ntm_dict.get('en', [])
        data_dict['notes_translation_method_fr'] = ntm_dict.get('fr', [])

        ktm_dict = cioos_helpers.load_json(data_dict.get('keywords_translation_method', '{}'))
        data_dict['keywords_translation_method_en'] = ktm_dict.get('en', [])
        data_dict['keywords_translation_method_fr'] = ktm_dict.get('fr', [])
  
        # split xml in harvest_document_content into french and englsih fields for indexing
        hdc = data_dict.get('harvest_document_content')
        if hdc:
            
            namespaces = {'lan': 'http://standards.iso.org/iso/19115/-3/lan/1.0',
                        'mdb': 'http://standards.iso.org/iso/19115/-3/mdb/2.0',
                        'gmd': 'http://www.isotc211.org/2005/gmd'}

            root = ET.fromstring(hdc)

            default_lang = root.xpath("./mdb:defaultLocale/lan:PT_Locale/lan:language/lan:LanguageCode/@codeListValue|./gmd:language/gmd:LanguageCode/@codeListValue", namespaces=namespaces)
            if default_lang:
                default_lang = default_lang[0]

            root_fr = ET.Element("fr")
            root_en = ET.Element("en")
            if default_lang in ["eng","en"]:    
                for locale in root.xpath(".//lan:LocalisedCharacterString[@locale='#fr' or @locale='#FR']|.//gmd:LocalisedCharacterString[@locale='#fr' or @locale='#FR']", namespaces=namespaces):
                    root_fr.append(deepcopy(locale))
                    locale.getparent().remove(locale)
                root_en = deepcopy(root)
            elif default_lang in ["fra","fr"]:
                for locale in root.xpath(".//lan:LocalisedCharacterString[@locale='#en' or @locale='#EN']|.//gmd:LocalisedCharacterString[@locale='#en' or @locale='#EN']", namespaces=namespaces):
                    root_en.append(deepcopy(locale))
                    locale.getparent().remove(locale)
                root_fr = deepcopy(root)
            else:
                log.error('No default language set in xml document. can not split document into language fields')

            data_dict['harvest_document_content_en'] = ET.strip_tags(root_en, '*', '*')
            data_dict['harvest_document_content_fr'] = ET.strip_tags(root_fr, '*', '*')

        # update organization list by language
        org_id = data_dict.get('owner_org')
        if org_id:
            org_details = toolkit.get_action('organization_show')(
                data_dict={
                    'id': org_id,
                    'include_datasets': False,
                    'include_dataset_count': False,
                    'include_extras': True,
                    'include_users': False,
                    'include_groups': False,
                    'include_tags': False,
                    'include_followers': False,
                }
            )
            org_title = org_details.get('title_translated', {})
            data_dict['organization_en'] = org_title.get('en', '')
            data_dict['organization_fr'] = org_title.get('fr', '')

        try:
            title = cioos_helpers.load_json(data_dict.get('title_translated', '{}'))
            data_dict['title_en'] = title.get('en', [])
            data_dict['title_fr'] = title.get('fr', [])
        except Exception as err:
            log.error(err)

        try:
            title = cioos_helpers.load_json(data_dict.get('notes_translated', '{}'))
            data_dict['notes_en'] = title.get('en', [])
            data_dict['notes_fr'] = title.get('fr', [])
        except Exception as err:
            log.error(err)

        try:
            if not self.all_groups_dict_by_name:
                self.all_groups_dict_by_name = self.get_all_groups('group','name')

            for name in data_dict.get('groups', []):
                if name.startswith('resorg'):
                    data_dict['resorg_groups'] = name
                    group_title = self.all_groups_dict_by_name[name].get('title_translated', {})
                    data_dict['resorg_groups_en'] = group_title.get('en', '')
                    data_dict['resorg_groups_fr'] = group_title.get('fr', '')

        except Exception as err:
            log.error(err)

        # create temporal extent index.
        te = data_dict.get('temporal-extent', '{}')
        if te:
            temporal_extent = cioos_helpers.load_json(te)
            temporal_extent_begin = temporal_extent.get('begin')
            temporal_extent_end = temporal_extent.get('end')
            if(temporal_extent_begin):
                data_dict['temporal-extent-begin'] = temporal_extent_begin
            if(temporal_extent_end):
                data_dict['temporal-extent-end'] = temporal_extent_end
            # If end is not set then we will still include these dataset in temporal searches by giving them an end time of 'NOW'
            if(temporal_extent_begin):
                data_dict['temporal-extent-range'] = '[' + temporal_extent_begin + ' TO ' + (temporal_extent_end or '*') + ']'

        # create vertical extent index
        ve = data_dict.get('vertical-extent', '{}')
        if ve:
            vertical_extent = cioos_helpers.load_json(ve)
            vertical_extent_min = vertical_extent.get('min')
            vertical_extent_max = vertical_extent.get('max')
            if(vertical_extent_min):
                data_dict['vertical-extent-min'] = vertical_extent_min
            if(vertical_extent_max):
                data_dict['vertical-extent-max'] = vertical_extent_max

        # eov is multi select so it is a json list rather then a python list
        if(data_dict.get('eov')):
            data_dict['eov'] = cioos_helpers.load_json(data_dict['eov'])

        # ecv is multi select so it is a json list rather then a python list
        if(data_dict.get('ecv')):
            data_dict['ecv'] = cioos_helpers.load_json(data_dict['ecv'])

        for res in data_dict.get('resources', []):
            res_name = cioos_helpers.load_json(res.get('name', '{}'))
            if res_name and isinstance(res_name, dict) and not res.get('name_translated'):
                res['name_translated'] = res_name
            resource_description = cioos_helpers.load_json(res.get('description', '{}'))
            if resource_description and isinstance(resource_description, dict) and not res.get('description_translated'):
                res['description_translated'] = resource_description

        if data_dict.get('projects'):
            data_dict['projects'] = cioos_helpers.load_json(data_dict.get('projects'))

        return data_dict

    # group a list of dictionaries based on individual-name or organization-name keys
    def group_by_ind_or_org(self, dict_list):
        from collections import defaultdict
        from collections import OrderedDict
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
            group_value = d.get('individual-name', '') + '_' + d.get('organisation-name', '')
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
            group_value = d.get('individual-name', '') + '_' + d.get('organisation-name', '')
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
    def before_search(self, search_params):
        if '-dataset_type:harvest' not in search_params.get('fq', {}):
            return search_params

        if toolkit.request:
            lang = toolkit.h.lang()
            search_params['qf'] = 'name^4 title_%s^4 tags_%s^2 text_%s text' % (lang,lang,lang)

        begin = search_params.get('extras', {}).get('ext_year_begin', '*')
        end = search_params.get('extras', {}).get('ext_year_end', '*')
        if begin == end == '*':
            return search_params

        search_params['fq_list'] = search_params.get('fq_list', [])

        show_null_range = search_params.get('extras', {}).get('ext_show_empty_range', 'false')

        if show_null_range == 'true':
            search_params['fq_list'].append('+(temporal-extent-range:[{begin} TO {end}] OR (*:* NOT temporal-extent-range:[* TO *]))'
                                            .format(begin=begin, end=end))
        else:
            search_params['fq_list'].append('+temporal-extent-range:[{begin} TO {end}]'
                                            .format(begin=begin, end=end))

        return search_params



    def populate_schema_select_display_name(self, search_facets, field_name):
        facet_field = search_facets.get(field_name, {})
        items = facet_field.get('items')
        if not items:
            return None
        schema = toolkit.h.scheming_get_dataset_schema('dataset')
        fields = schema['dataset_fields']
        field = toolkit.h.scheming_field_by_name(fields, field_name)
        if not field:
            return None
        choices = toolkit.h.scheming_field_choices(field)
        new_values = []
        for item in items:
            for ch in choices:
                if ch['value'] == item['name']:
                    item['display_name'] = toolkit.h.scheming_language_text(ch.get('label', item['name']))
                    cat = ch.get('category', '')
                    if cat:
                        item['category'] = cat
                    subcat = ch.get('subcatagory', '')
                    if subcat:
                        item['subcategory'] = subcat
            new_values.append(item)
        return new_values
        

    def get_all_groups(self, action_type, key='id'):
        group_list = []
        limit = 25
        offset = 0
        schema_list = toolkit.get_action('scheming_%s_schema_list' % action_type)()
        schema_types = list(dict.fromkeys( schema_list + [action_type] ))

        for type in schema_types:
            while True:
                # need to turn off dataset_count here as it causes a recursive loop with package_search
                res = toolkit.get_action('%s_list' % action_type)(
                    data_dict={
                        'type': type,
                        'limit': limit,
                        'offset': offset,
                        'all_fields': True,
                        'include_dataset_count': False,
                        'include_extras': True,
                        'include_users': False,
                        'include_groups': False,
                        'include_tags': False,
                    }
                )
                if not res:
                    break
                group_list = group_list + res
                offset = offset + limit
        return {x[key]: x for x in group_list}

    def get_group(self, type, id):
        # need to turn off dataset_count, usersand groups here as it causes a recursive loop
        try:
            group = toolkit.get_action('%s_show' % type)(
                data_dict={
                    'id': id,
                    'include_datasets': False,
                    'include_dataset_count': False,
                    'include_extras': True,
                    'include_users': False,
                    'include_groups': False,
                    'include_tags': False,
                    'include_followers': False,
                }
            )
        except NotFound as e:
            log.warning('Group or Organization %s not found',id)
            return None
        return group

    # update eov search facets with keys from choices list in the scheming extension schema
    # format search results for consistant json output
    # add organization extra fields to results
    def after_search(self, search_results, search_params):
        # no need to do all this if not returning data anyway
        if search_params.get('rows') == 0:
            return search_results

        search_facets = search_results.get('search_facets', {})

        items = self.populate_schema_select_display_name(search_facets, 'eov')
        if items:
            search_results['search_facets']['eov']['items'] = items

        items = self.populate_schema_select_display_name(search_facets, 'ecv')
        if items:
            search_results['search_facets']['ecv']['items'] = items
        

        license_id = search_facets.get('license_id', {})
        items = license_id.get('items', [])
        new_license_items = []
        if items:
            for item in items:
                license = toolkit.h.cioos_get_license_def(item['name'], None, None)
                if license:
                    item['display_name'] = license['license_title']
                new_license_items.append(item)
            search_results['search_facets']['license_id']['items'] = new_license_items

        org_dict = self.get_all_groups('organization')
        group_dict = self.get_all_groups('group')
        group_dict_by_name = {v['name']: v for k,v in group_dict.items()}

        resorg_groups = search_facets.get('resorg_groups', {})
        groups = search_facets.get('groups', {})

        items = resorg_groups.get('items', [])
        new_resorg_items = []
        if items:     
            for item in items:
                item['display_name'] = group_dict_by_name[item['name']]['display_name']
                new_resorg_items.append(item)
            search_results['search_facets']['resorg_groups']['items'] = new_resorg_items

        # convert string encoded json to json objects for translated fields
        # package_search with filters uses solr index values which are strings
        # this is inconsistant with package data which is returned as json objects
        # by the package_show and package_search end points whout filters applied
        for i, result in enumerate(search_results.get('results', [])):
            # force_resp_org = cioos_helpers.load_json(self._get_extra_value('force_responsible_organization', result))
            cited_responsible_party = result.get('cited-responsible-party')

            # Update group list
            groups = result.get('groups')
            if groups:
                # group_dict = self.get_all_groups('group')
                new_group_list = []
                for group in groups:
                    new_group_list.append( group_dict.get(group['id'],group) )
                if new_group_list:
                    result['groups'] = new_group_list

            if result.get('cited-responsible-party'):
                result['cited-responsible-party'] = self.group_by_ind_or_org(result.get('cited-responsible-party'))
            if result.get('metadata-point-of-contact'):
                result['metadata-point-of-contact'] = self.group_by_ind_or_org(result.get('metadata-point-of-contact'))

            # fluent output validators set title and notes to the default language on package_show
            # doing the same here so the output is consistent
            title = result.get('title_translated')
            if(title):
                result['title_translated'] = cioos_helpers.load_json(title)
                if isinstance(result['title_translated'], dict):
                    result['title'] = scheming_language_text(result['title_translated'], toolkit.config.get('ckan.locale_default', 'en'))

            notes = result.get('notes_translated')
            if(notes):
                result['notes_translated'] = cioos_helpers.load_json(notes)
                if isinstance(result['notes_translated'], dict):
                    result['notes'] = scheming_language_text(result['notes_translated'], toolkit.config.get('ckan.locale_default', 'en'))

            for res in result.get('resources', []):
                res_name = cioos_helpers.load_json(res.get('name_translated', '{}'))
                if res_name and isinstance(res_name, dict):
                    res['name'] = scheming_language_text(res_name, toolkit.config.get('ckan.locale_default', 'en'))
                resource_description = cioos_helpers.load_json(res.get('description_translated', '{}'))
                if resource_description and isinstance(resource_description, dict):
                    res['description'] = scheming_language_text(resource_description, toolkit.config.get('ckan.locale_default', 'en'))

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
                    "projects"]:
                tmp = result.get(field)
                if tmp:
                    result[field] = cioos_helpers.load_json(tmp)

            # update organization object while we are at it
            org_id = result.get('owner_org')
            if org_id:
                org_details = org_dict.get(org_id, {})
                organization = result.get('organization', {})
                if organization or org_details:
                    new_org_dict = {**organization, **org_details}
                    result['organization'] = new_org_dict
                else:
                    log.warn('No org details for owner_org %s', org_id)

            search_results['results'][i] = result      
        return search_results

    # add organization extras to organization object in package.
    # this will make the show and search endpoints look the same
    def after_show(self, context, package_dict):
        
        org_id = package_dict.get('owner_org')
        data_type = package_dict.get('type')

        if org_id and (data_type == 'dataset' or data_type == 'harvest'):
            org_details = self.get_group('organization',org_id)           
            if org_details:
                package_org = package_dict['organization']
                new_org = {**package_org, **org_details}
                if new_org:
                    package_dict['organization'] = new_org

        if data_type == 'harvest':
            return package_dict        

        # Update group list
        groups = package_dict.get('groups')
        if groups:
            group_dict = self.get_all_groups('group')
            new_group_list = []
            for group in groups:
                new_group_list.append( group_dict.get(group['id'],group) )
            if new_group_list:
                package_dict['groups'] = new_group_list
                
            
        # force_resp_org = cioos_helpers.load_json(self._get_extra_value('force_responsible_organization', package_dict))
        # cited_responsible_party = package_dict.get('cited-responsible-party')
        # if((cited_responsible_party or force_resp_org) and not package_dict.get('responsible_organizations')):
        #     package_dict['responsible_organizations'] = self._cited_responsible_party_to_responsible_organizations(cited_responsible_party, force_resp_org)

        if package_dict.get('cited-responsible-party'):
            package_dict['cited-responsible-party'] = self.group_by_ind_or_org(package_dict.get('cited-responsible-party'))
        if package_dict.get('metadata-point-of-contact'):
            package_dict['metadata-point-of-contact'] = self.group_by_ind_or_org(package_dict.get('metadata-point-of-contact'))

        result = package_dict
        title = result.get('title_translated')
        if(title):
            result['title_translated'] = cioos_helpers.load_json(title)
        notes = result.get('notes_translated')
        if(notes):
            result['notes_translated'] = cioos_helpers.load_json(notes)

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
                "projects"]:
            tmp = result.get(field)
            if tmp:
                result[field] = cioos_helpers.load_json(tmp)
        package_dict = result

        # Update package relationships with package name
        ras = package_dict['relationships_as_subject']
        for rel in ras:
            if rel.get('__extras'):
                id = rel['__extras']['object_package_id']
                result = toolkit.get_action('package_search')(context, data_dict={'q': 'id:%s' % id, 'fl': 'name'})
                if result['results']:
                    rel['__extras']['object_package_name'] = result['results'][0]['name']
                rel['__extras']['subject_package_name'] = package_dict['name']
            else:
                id = rel['object_package_id']
                result = toolkit.get_action('package_search')(context, data_dict={'q': 'id:%s' % id, 'fl': 'name'})
                if result['results']:
                    rel['object_package_name'] = result['results'][0]['name']
                rel['subject_package_name'] = package_dict['name']

        rao = package_dict['relationships_as_object']
        for rel in rao:
            if rel.get('__extras'):
                rel['__extras']['object_package_name'] = package_dict['name']
                id = rel['__extras']['subject_package_id']
                result = toolkit.get_action('package_search')(context, data_dict={'q': 'id:%s' % id, 'fl': 'name'})
                if result['results']:
                    rel['__extras']['subject_package_name'] = result['results'][0]['name']
            else:
                rel['object_package_name'] = package_dict['name']
                id = rel['subject_package_id']
                result = toolkit.get_action('package_search')(context, data_dict={'q': 'id:%s' % id, 'fl': 'name'})
                if result['results']:
                    rel['subject_package_name'] = result['results'][0]['name']

        return package_dict

    # Custom section
    def read_template(self):
        return 'package/read.html'

    def lang(self):
        return toolkit.h.lang()

    def get_locale_url(self, base_url, locale_urls):
        default_locale = toolkit.config.get('ckan.locale_default', toolkit.config.get('ckan.locales_offered', ['en'])[0])
        lang = toolkit.h.lang() or default_locale
        if base_url.endswith('/'):
            return base_url + locale_urls.get(lang)
        return base_url + '/' + locale_urls.get(lang)
