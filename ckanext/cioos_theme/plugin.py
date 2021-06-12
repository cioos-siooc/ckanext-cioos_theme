# encoding: utf-8

import ckan.plugins as plugins
import ckan.plugins.toolkit as toolkit
import ckan.model as model
from ckan.lib.search import rebuild
import ckanext.cioos_theme.helpers as cioos_helpers
from ckanext.scheming.validation import scheming_validator
from ckanext.harvest.model import (HarvestJob, HarvestObject)
from ckan.model import (Package, PackageRevision, PackageTagRevision, PackageTag, PackageExtra, PackageExtraRevision, PackageRelationship, PackageRelationshipRevision)
from ckan.logic import NotFound
from ckan.lib.plugins import DefaultTranslation
# from ckanext.harvest import model as harvest_model
from ckanext.harvest.queue import (resubmit_objects)
from sqlalchemy import and_, or_, text, String
from sqlalchemy.sql import select, update, delete, bindparam
import json
from shapely.geometry import shape
import logging
import ckan.lib.navl.dictization_functions as df
from ckan.common import c
from six.moves.urllib.parse import urlparse
import string
from ckan.common import _
import routes.mapper
import ckan.lib.base as base
import re
import time

Invalid = df.Invalid

log = logging.getLogger(__name__)

# import debugpy

StopOnError = df.StopOnError
missing = df.missing
log = logging.getLogger(__name__)

# debugpy.listen(('0.0.0.0', 5678))
# log.debug("Waiting for debugger attach")
# debugpy.wait_for_client()




show_responsible_organizations = toolkit.asbool(
    toolkit.config.get('cioos.show_responsible_organizations_facet', "True"))

contact_email = toolkit.config.get('cioos.contact_email', "info@cioos.ca")
organizations_info_text = toolkit.config.get(
    'cioos.organizations_info_text',
    {
        "en": "CKAN Organizations are used to create, manage and publish collections of datasets. Users can have different roles within an Organization, depending on their level of authorisation to create, edit and publish.",
        "fr": u"Les Organisations CKAN sont utilisées pour créer, gérer et publier des collections de jeux de données. Les utilisateurs peuvent avoir différents rôles au sein d'une Organisation, en fonction de leur niveau d'autorisation pour créer, éditer et publier."
    }
)





def geojson_to_bbox(o):
    return shape(o).bounds


# IValidators

# this validator tries to populate eov from keywords. It looks for any english
# keywords that match either the value or label in the choice list for the eov
# field and add's them to the eov field.
@scheming_validator
def clean_and_populate_eovs(field, schema):

    def validator(key, data, errors, context):
        if errors[key] and (u'Select at least one' not in errors[key] or 'Select at least one' not in errors[key]):
            return

        keywords_main = data.get(('keywords',), {})
        if keywords_main:
            eov_data = keywords_main.get('en', [])
        else:
            extras = data.get(("__extras", ), {})
            eov_data = extras.get('keywords-en', '').split(',')

        eov_list = {}
        for x in toolkit.h.scheming_field_choices(toolkit.h.scheming_field_by_name(schema['dataset_fields'], 'eov')):
            eov_list[x['value'].lower()] = x['value']
            eov_list[x['label'].lower()] = x['value']

        d = json.loads(data.get(key, '[]'))
        for x in eov_data:
            if isinstance(x, basestring):  # TODO: change basestring to str when moving to python 3
                val = eov_list.get(x.lower(), '')
            else:
                val = eov_list.get(x, '')
            if val and val not in d:
                d.append(val)

        if len(d) and u'Select at least one' in errors[key]:
            errors[key].remove(u'Select at least one')
        if len(d) and 'Select at least one' in errors[key]:
            errors[key].remove('Select at least one')

        data[key] = json.dumps(d)
        return data

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
           set(pieces.netloc) <= set(string.letters + string.digits + '-.:') and \
           pieces.scheme in ['http', 'https']:
            return
    except ValueError:
        # url is invalid
        pass
    errors[key].append(_('Please provide a valid URL'))


@scheming_validator
def cioos_tag_name_validator(field, schema):

    def validator(value, context):
        tagname_match = re.compile('[\w \-.\']*$', re.UNICODE)
        if not tagname_match.match(value):
            raise Invalid(_('Tag "%s" must be alphanumeric characters or symbols: -_.\'') % (value))
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

class Cioos_ThemePlugin(plugins.SingletonPlugin, DefaultTranslation):
    plugins.implements(plugins.ITranslation)
    plugins.implements(plugins.IConfigurer)
    plugins.implements(plugins.ITemplateHelpers)
    plugins.implements(plugins.IFacets)
    plugins.implements(plugins.IPackageController, inherit=True)
    plugins.implements(plugins.IValidators)
    plugins.implements(plugins.IAuthenticator)
    plugins.implements(plugins.IRoutes)

    # IRoute

    def before_map(self, route_map):
        with routes.mapper.SubMapper(route_map, controller='ckanext.cioos_theme.plugin:CIOOSController') as m:
            m.connect('schemamap', '/schemamap', action='schemamap')
        return route_map

    def after_map(self, route_map):
        return route_map

    # IAuthenticator

    def identify(self):
        try:
            remote_addr = toolkit.request.headers['X-Forwarded-For']
        except KeyError:
            remote_addr = toolkit.request.remote_addr

        log.info('Request by %s for %s from %s', toolkit.request.remote_user, toolkit.request.url, remote_addr)
        c.user = None
        c.userobj = None
        return

    def login(self, error=None):
        try:
            remote_addr = toolkit.request.headers['X-Forwarded-For']
        except KeyError:
            remote_addr = toolkit.request.remote_addr
        log.info('Login attempt from %s', remote_addr)
        return

    def logout(self):
        try:
            remote_addr = toolkit.request.headers['X-Forwarded-For']
        except KeyError:
            remote_addr = toolkit.request.remote_addr
        log.info('Logout by %s from %s', toolkit.request.remote_user, remote_addr)
        return

    def abort(self, status_code, detail, headers, comment):
        '''Handle an abort.'''
        try:
            remote_addr = toolkit.request.headers['X-Forwarded-For']
        except KeyError:
            remote_addr = toolkit.request.remote_addr
        log.info('Blocked request to %s with status %s becouse "%s" from %s', toolkit.request.url, status_code, detail, remote_addr)
        return (status_code, detail, headers, comment)

    # IConfigurer

    def update_config(self, config_):
        toolkit.add_template_directory(config_, 'templates')
        toolkit.add_public_directory(config_, 'public')
        toolkit.add_resource('fanstatic', 'cioos_theme')

    def update_config_schema(self, schema):

        ignore_missing = toolkit.get_validator('ignore_missing')
        fluent_text = toolkit.get_validator('fluent_text')
        boolean_validator = toolkit.get_validator('boolean_validator')

        schema.update({
            'ckan.site_title': [ignore_missing, fluent_field_default(None, None), fluent_text(None, None)],
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
            'ckan.show_responsible_organization_in_dataset_sidebar': [ignore_missing, boolean_validator],
        })
        return schema

    def get_additional_css_path(self):
        return toolkit.config.get('ckan.cioos.ra_css_path', '/ra.css')

    def get_helpers(self):
        """Register the most_popular_groups() function above as a template helper function."""
        # Template helper function names should begin with the name of the
        # extension they belong to, to avoid clashing with functions from
        # other extensions.
        return {
            'cioos_organizations_info_text': lambda: organizations_info_text,
            'cioos_contact_email': lambda: contact_email,
            'cioos_load_json': cioos_helpers.load_json,
            'cioos_geojson_to_bbox': geojson_to_bbox,
            # 'cioos_most_popular_groups': most_popular_groups,
            # 'cioos_groups': groups,
            # 'cioos_most_popular_datasets': most_popular_datasets,
            # 'cioos_most_popular_resources': most_popular_resources,
            # 'cioos_recent_packages_html': recent_packages_html,
            'cioos_get_facets': cioos_helpers.cioos_get_facets,
            # 'cioos_get_organization_list': cioos_helpers.get_organization_list,
            # 'cioos_get_organization_dict': cioos_helpers.get_organization_dict,
            # 'cioos_get_organization_dict_extra': cioos_helpers.get_organization_dict_extra
            'cioos_get_package_title': cioos_helpers.get_package_title,
            'cioos_get_package_relationships': cioos_helpers.get_package_relationships,
            'cioos_print_package_relationship_type': cioos_helpers.print_package_relationship_type,
            'cioos_get_package_relationship_reverse_type': cioos_helpers.get_package_relationship_reverse_type,
            'cioos_datasets': cioos_helpers.cioos_datasets,
            'cioos_count_datasets': cioos_helpers.cioos_count_datasets,
            'cioos_get_eovs': cioos_helpers.cioos_get_eovs,
            'cioos_get_locale_url': self.get_locale_url,
            'cioos_schema_field_map': cioos_helpers.cioos_schema_field_map,
            'cioos_get_additional_css_path': self.get_additional_css_path
        }

    def get_validators(self):
        return {
            # 'cioos_if_empty_same_as__extras': if_empty_same_as__extras,
            'cioos_clean_and_populate_eovs': clean_and_populate_eovs,
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
        self._update_facets(facets_dict)
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
        self._update_facets(facets_dict)
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
        self._update_facets(facets_dict)
        return facets_dict

    def _update_facets(self, facets_dict):
        u"""
            Add facet themes
        :param facets_dict:
        :return:
        """

        # remove groups facet
        if 'groups' in facets_dict:
            facets_dict.pop('groups')

        if 'themes' not in facets_dict \
                or 'eov' not in facets_dict \
                or 'responsible_organizations' not in facets_dict:
            # Horrible hack
            # Insert facet themes at first position of the OrderedDict facets_dict.
            ordered_dict = facets_dict.copy()
            facets_dict.clear()
            # facets_dict['themes'] = toolkit._('Theme')
            facets_dict['eov'] = toolkit._('Ocean Variables')

            if show_responsible_organizations:
                facets_dict['responsible_organizations'] = toolkit._('Responsible Organization')

            for key, value in ordered_dict.items():
                # Make translation 'on the fly' of facet tags.
                # Should check for all translated fields.
                # Should check translation exists.
                if key == 'tags' or key == 'organization':
                    facets_dict[key + '_' + self.lang()] = value
                else:
                    facets_dict[key] = value
        return facets_dict

    # IPackageController

    def _cited_responsible_party_to_responsible_organizations(self, parties, force_responsible_organization):
        if force_responsible_organization:
            if isinstance(force_responsible_organization, list):
                resp_orgs = force_responsible_organization
            else:
                resp_orgs = [force_responsible_organization]
        else:
            resp_org_roles = json.loads(toolkit.config.get('ckan.responsible_organization_roles', '["owner", "originator", "custodian", "author", "principalInvestigator"]'))
            resp_orgs = [x.get('organisation-name', '').strip() for x in json.loads(parties) if x.get('role') in resp_org_roles]
            resp_orgs = list(dict.fromkeys(resp_orgs))  # remove duplicates
            resp_orgs = list(filter(None, resp_orgs)) # remove empty elements (in a python 2 and 3 friendly way)
        return resp_orgs

    def _get_extra_value(self, key, package_dict):
        for extra in package_dict.get('extras', []):
            if extra['key'] == key:
                return extra['value']

    # def _check_harvest_relationship_targets(self, context, package_dict, to_add, is_create):
    #
    #     related_datasets = [x["object"] for x in to_add]
    #     # rd_query = 'name:(' + ' OR '.join(related_datasets) + ')'
    #     # response = toolkit.get_action('package_search')(
    #     #     context,
    #     #     data_dict={
    #     #         "q": rd_query,
    #     #         "fl": "name"
    #     #     })
    #
    #     # package_search action was not finding all newly created datasets
    #     # so trying an ORM query instead
    #     results = model.Session.query(Package)\
    #         .filter(
    #             or_(
    #                 (Package.id.in_(related_datasets)),
    #                 (Package.name.in_(related_datasets))
    #             )
    #         )
    #
    #     existing_datasets = [x.name for x in results]
    #     missing_datasets = [x for x in related_datasets if x not in existing_datasets]  # related_datasets - existing-datasets
    #
    #     log.debug('existing_datasets: %r', existing_datasets)
    #     log.debug('missing_datasets: %r', missing_datasets)
    #
    #     if not missing_datasets:
    #         return 'process'
    #
    #     # one or more relationship targets do not yet exist
    #
    #     # get current harvest object
    #     h_obj = model.Session.query(HarvestObject)\
    #         .filter(HarvestObject.package_id == bindparam('b_package_id'))\
    #         .params(b_package_id=package_dict['id'])\
    #         .first()
    #
    #     # Harvest objects will not have guid or package_id assigned
    #     # until they have been processed. if one or more harvest objects
    #     # state is not yet COMPLETE or ERROR then we will put this object
    #     # back on the harvest queue. We will only do this ?once? however.
    #
    #     num_objects_in_progress = \
    #         model.Session.query(HarvestObject.id) \
    #             .filter(HarvestObject.harvest_job_id == h_obj.harvest_job_id) \
    #             .filter(and_((HarvestObject.state != u'COMPLETE'),
    #                         (HarvestObject.state != u'ERROR'))) \
    #             .filter(HarvestObject.retry_times > 3) \
    #             .count()
    #
    #     if not num_objects_in_progress:
    #         return 'process'
    #
    #     # use retry_times so we know when to give up
    #     # this isn't great because for a sufficiently complex set of
    #     # relationship this will still fail to find all packages.
    #     # Also I should not overload retry_times. how to add my own counter?
    #     if h_obj.retry_times > 3:
    #         log.debug('package relationships retry counter > 2. skipping relationship.')
    #         return 'process'
    #
    #     # Return the harvest object to the wait queue
    #     model.Session.query(HarvestObject) \
    #         .filter(HarvestObject.harvest_job_id == h_obj.harvest_job_id) \
    #         .filter(HarvestObject.package_id == h_obj.package_id) \
    #         .update({HarvestObject.state: u'WAITING',
    #                 HarvestObject.package_id: None,
    #                 HarvestObject.import_started: None,
    #                 HarvestObject.import_finished: None,
    #                 HarvestObject.current: False,
    #                 HarvestObject.metadata_modified_date: None}, synchronize_session='fetch')
    #
    #     # Resubmit pending harvest objects that are missing from
    #     # Redis, like the one we just set to WAITING.
    #     resubmit_objects()
    #
    #     if is_create:
    #         # purge package so we don't get 'URL in use' errors or clutter up the trash
    #         # probably a better way to do this?
    #
    #         # package_subquery = model.Session.query(Package.id)\
    #         #     .filter(Package.id == package_dict['id']).subquery()
    #         #
    #         # model.Session.query(PackageTagRevision)\
    #         #     .filter(PackageTagRevision.package_id.in_(package_subquery))\
    #         #     .delete(synchronize_session='fetch')
    #         # model.Session.query(PackageTag)\
    #         #     .filter(PackageTag.package_id.in_(package_subquery))\
    #         #     .delete(synchronize_session='fetch')
    #         # model.Session.query(PackageExtraRevision)\
    #         #     .filter(PackageExtraRevision.package_id.in_(package_subquery))\
    #         #     .delete(synchronize_session='fetch')
    #         # model.Session.query(PackageExtra)\
    #         #     .filter(PackageExtra.package_id.in_(package_subquery))\
    #         #     .delete(synchronize_session='fetch')
    #         # model.Session.query(PackageRelationshipRevision)\
    #         #     .filter((PackageRelationshipRevision.object_package_id.in_(package_subquery)) |
    #         #             (PackageRelationshipRevision.subject_package_id.in_(package_subquery))) \
    #         #     .delete(synchronize_session='fetch')
    #         # model.Session.query(PackageRelationship)\
    #         #     .filter((PackageRelationship.object_package_id.in_(package_subquery)) |
    #         #             (PackageRelationship.subject_package_id.in_(package_subquery))) \
    #         #     .delete(synchronize_session='fetch')
    #         # model.Session.query(PackageRevision)\
    #         #     .filter(PackageRevision.id.in_(package_subquery))\
    #         #     .delete(synchronize_session='fetch')
    #         # model.Session.query(Package)\
    #         #     .filter(Package.id.in_(package_subquery))\
    #         #     .delete(synchronize_session='fetch')
    #
    #         # model.Session.flush()
    #
    #         # remove resources as they are created after this function runs
    #         package_dict.pop('resources')
    #
    #         # commit repository so that we can later pruge it, otherwise we get 'NotFound' errors on member
    #         model.repo.commit()
    #
    #         # members = model.Session.query(model.Member) \
    #         #     .filter(model.Member.table_id == package_dict['id']) \
    #         #     .filter(model.Member.table_name == 'package')
    #         # if members.count() > 0:
    #         #     for m in members.all():
    #         #         m.purge()
    #
    #         # for r in model.Session.query(model.PackageRelationship).filter(
    #         #         or_(model.PackageRelationship.subject_package_id == package_dict['id'],
    #         #             model.PackageRelationship.object_package_id == package_dict['id'])).all():
    #         #     r.purge()
    #
    #         # pkg = model.Package.get(package_dict['id'])
    #         # pkg.purge()
    #         # model.repo.commit_and_remove()
    #
    #         toolkit.get_action('dataset_purge')(
    #         data_dict={
    #             'id': package_dict['id']
    #         }
    #     )
    #     return 'retry'

    def _update_package_relationships(self, context, package_dict, is_create):
        to_delete = []
        to_add = []
        to_index = []
        relationships_errors = []

        user = toolkit.get_action('get_site_user')({'model': model, 'ignore_auth': True}, {})
        context = {'model': model, 'session': model.Session, 'user': user['name']}

        # compare schema field, here called aggregation-info and
        # package relationships. This block should be split off
        # into it's own function so it can be overriden
        existing_rels = []
        rels_from_schema = []
        for x in cioos_helpers.load_json(package_dict.get('aggregation-info', [])):
            comment = '/'.join([x['initiative-type'], x['association-type']])
            comment = re.sub(r'([A-Z])', r' \1', comment)
            comment = comment.title()

            type = 'links_to'
            if x['association-type'] == 'largerWorkCitation':
                type = 'child_of'
            if x['association-type'] == 'crossReference':
                type = 'links_to'
            if x['association-type'] == 'dependency':
                type = 'depends_on'
            if x['association-type'] == 'revisionOf':
                type = 'derives_from'
            if x['association-type'] == 'series':
                type = 'links_to'
            if x['association-type'] == 'isComposedOf':
                type = 'derives_from'
            rels_from_schema.append({
                "subject": package_dict['name'],
                "type": type,
                "object": x['aggregate-dataset-identifier'],
                "comment": comment
            })

        # get existing package relationships where this package is the subject (from)
        existing_rels = toolkit.get_action('package_relationships_list')(
            data_dict={
                'id': package_dict['id']
            }
        )

        to_delete = to_delete + [x for x in existing_rels if x not in rels_from_schema]  # existing_rels - rels_from_schema
        to_add = to_add + [x for x in rels_from_schema if x not in existing_rels]  # rels_from_schema - existing_rels

        # if to_add and context.get('validate') is None:
        #     # We are in a harvest job so better check packages exist
        #     if self._check_harvest_relationship_targets(context, package_dict, to_add, is_create) == 'retry':
        #         return


        # delete relationships
        for d in to_delete:
            toolkit.get_action('package_relationship_delete')(data_dict=d)
            to_index.append(d['object'])
            log.debug('Deleted package relationship %s %s %s', d['subject'], d['type'], d['object'])

        # create relationships
        for a in to_add:
            try:
                toolkit.get_action('package_relationship_create')(context, data_dict=a)
                to_index.append(a['object'])
                log.debug('Created package relationship %s %s %s', a['subject'], a['type'], a['object'])
            except toolkit.ObjectNotFound as e:
                relationships_errors.append('Failed to create package relationship for dataset %s: %r' % (package_dict['id'], e))

        # trigger indexing of datasets we are linking to
        for package_id in to_index:
            rebuild(package_id)

        if relationships_errors and context.get('validate') is not None:
            # errors during harvest are likely and will be handled by the
            # package_relationships rebuild paster command so no need to raise
            # them here
            raise toolkit.ValidationError(relationships_errors)

        return package_dict

    def after_create(self, context, package_dict):
        # self._update_package_relationships(context, package_dict, is_create=True)
        pass

    def after_update(self, context, package_dict):
        # self._update_package_relationships(context, package_dict, is_create=False)
        pass

    def before_update(self, context, package_dict):
        if package_dict.state == 'deleted':
            existing_rels = toolkit.get_action('package_relationships_list')(
                data_dict={
                    'id': package_dict['id']
                }
            )
            for d in to_delete:
                toolkit.get_action('package_relationship_delete')(data_dict=d)
                to_index.append(d['object'])

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

        force_resp_org = cioos_helpers.load_json(data_dict.get('force_responsible_organization', '[]'))
        data_dict['responsible_organizations'] = self._cited_responsible_party_to_responsible_organizations(data_dict.get('cited-responsible-party', '{}'), force_resp_org)

        # update tag list by language
        data_dict['tags_en'] = tags_dict.get('en', [])
        data_dict['tags_fr'] = tags_dict.get('fr', [])
        data_dict['tags'] = data_dict['tags_en'] + data_dict['tags_fr']

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
            if(temporal_extent_begin and temporal_extent_end):
                data_dict['temporal-extent-range'] = '[' + temporal_extent_begin + ' TO ' + temporal_extent_end + ']'

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

        return data_dict

    # update eov search facets with keys from choices list in the scheming extension schema
    # format search results for consistant json output
    # add organization extra fields to results
    def after_search(self, search_results, search_params):
        # no need to do all this if not returning data anyway
        if search_params.get('rows') == 0:
            return search_results

        search_facets = search_results.get('search_facets', {})
        eov = search_facets.get('eov', {})
        items = eov.get('items', [])
        if items:
            schema = toolkit.h.scheming_get_dataset_schema('dataset')
            fields = schema['dataset_fields']
            field = toolkit.h.scheming_field_by_name(fields, 'eov')
            choices = toolkit.h.scheming_field_choices(field)
            new_eovs = []
            for item in items:
                for ch in choices:
                    if ch['value'] == item['name']:
                        item['display_name'] = toolkit.h.scheming_language_text(ch.get('label', item['name']))
                        item['category'] = ch.get('catagory', u'')
                new_eovs.append(item)
            search_results['search_facets']['eov']['items'] = new_eovs

        # need to turn off dataset_count here as it causes a recursive loop with package_search
        org_list = toolkit.get_action('organization_list')(
            data_dict={
                'all_fields': True,
                'include_dataset_count': False,
                'include_extras': True,
                'include_users': False,
                'include_groups': False,
                'include_tags': False,
            }
        )
        org_dict = {x['id']: x for x in org_list}
        # convert string encoded json to json objects for translated fields
        # package_search with filters uses solr index values which are strings
        # this is inconsistant with package data which is returned as json objects
        # by the package_show and package_search end points whout filters applied
        for result in search_results.get('results', []):

            force_resp_org = cioos_helpers.load_json(self._get_extra_value('force_responsible_organization', result))
            cited_responsible_party = result.get('cited-responsible-party')
            if((cited_responsible_party or force_resp_org) and not result.get('responsible_organizations')):
                result['responsible_organizations'] = self._cited_responsible_party_to_responsible_organizations(cited_responsible_party, force_resp_org)

            title = result.get('title_translated')
            if(title):
                result['title_translated'] = cioos_helpers.load_json(title)
            notes = result.get('notes_translated')
            if(notes):
                result['notes_translated'] = cioos_helpers.load_json(notes)
            keywords = result.get('keywords')
            if(keywords):
                result['keywords'] = cioos_helpers.load_json(keywords)

            # update organization object while we are at it
            org_id = result.get('owner_org')
            if org_id:
                org_details = org_dict.get(org_id)
                if org_details:
                    org_title = org_details.get('title_translated', {})
                    organization = result.get('organization', {})
                    if not organization:
                        organization = {}
                    if org_title:
                        organization['title_translated'] = org_title
                    org_description = org_details.get('description_translated', {})
                    if org_description:
                        organization['description_translated'] = org_description
                    org_image_url = org_details.get('image_url_translated', {})
                    if org_image_url:
                        organization['image_url_translated'] = org_image_url
                    if organization:
                        result['organization'] = organization
                else:
                    log.warn('No org details for owner_org %s', result.get('org_descriptionid'))
            else:
                log.warn('No owner_org for dataset %s: %s: %s', result.get('id'), result.get('name'), result.get('title'))

        return search_results

    # add organization extras to organization object in package.
    # this will make the show and search endpoints look the same
    def after_show(self, context, package_dict):
        org_id = package_dict.get('owner_org')
        data_type = package_dict.get('type')

        if org_id and data_type == 'dataset':
            # need to turn off dataset_count, usersand groups here as it causes a recursive loop
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
            if org_title:
                package_dict['organization']['title_translated'] = org_title

            org_description = org_details.get('description_translated', {})
            if org_description:
                package_dict['organization']['description_translated'] = org_description

            org_image_url = org_details.get('image_url_translated', {})
            if org_image_url:
                package_dict['organization']['image_url_translated'] = org_image_url

        force_resp_org = cioos_helpers.load_json(self._get_extra_value('force_responsible_organization', package_dict))
        cited_responsible_party = package_dict.get('cited-responsible-party')
        if((cited_responsible_party or force_resp_org) and not package_dict.get('responsible_organizations')):
            package_dict['responsible_organizations'] = self._cited_responsible_party_to_responsible_organizations(cited_responsible_party, force_resp_org)

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
        from ckantoolkit import h
        return h.lang()

    def get_locale_url(self, base_url, locale_urls):
        default_locale = toolkit.config.get('ckan.locale_default', toolkit.config.get('ckan.locales_offered', ['en'])[0])
        lang = toolkit.h.lang() or default_locale
        if base_url.endswith('/'):
            return base_url + locale_urls.get(lang)
        return base_url + '/' + locale_urls.get(lang)


class CIOOSController(base.BaseController):

    def schemamap(self):
        return base.render('schemamap.html')
