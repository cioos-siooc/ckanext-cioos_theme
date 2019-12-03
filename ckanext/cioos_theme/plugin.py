import ckan.plugins as plugins
import ckan.plugins.toolkit as toolkit
import ckanext.cioos_theme.helpers as cioos_helpers
from ckanext.scheming.validation import scheming_validator
from ckan.lib.plugins import DefaultTranslation
import json
from shapely.geometry import shape
import logging
import ckan.lib.navl.dictization_functions as df
from ckan.common import c


StopOnError = df.StopOnError
missing = df.missing
log = logging.getLogger(__name__)


def load_json(j):
    try:
        new_val = json.loads(j)
    except Exception:
        new_val = j
    return new_val


def geojson_to_bbox(o):
    return shape(o).bounds


# from the docs
# def most_popular_groups():
#     '''Return a sorted list of the groups with the most datasets.'''
#
#     # Get a list of all the site's groups from CKAN, sorted by number of
#     # datasets.
#     groups = toolkit.get_action('group_list')(
#         data_dict={'sort': 'package_count desc', 'all_fields': True})
#
#     # Truncate the list to the 10 most popular groups only.
#     groups = groups[:5]
#
#     return groups
#
#
# def groups():
#     '''Return a sorted list of the groups'''
#
#     # Get a list of all the site's groups from CKAN, sorted by number of
#     # datasets.
#     groups = toolkit.get_action('group_list')(
#         data_dict={'sort': 'title asc', 'all_fields': True})
#
#     return groups
#
#
# # from the docs
# def most_popular_datasets():
#     '''Return a sorted list of the groups with the most datasets.'''
#
#     # Get a list of all the site's groups from CKAN, sorted by number of
#     # datasets.
#     groups = toolkit.get_action('package_search')(
#         data_dict={'sort': 'views_recent desc', 'all_fields': True})
#
#     # Truncate the list to the 10 most popular groups only.
#     groups = groups[:5]
#
#     return groups
#
#
# def most_popular_resources():
#     '''Return a sorted list of the groups with the most datasets.'''
#
#     # Get a list of all the site's groups from CKAN, sorted by number of
#     # datasets.
#     groups = toolkit.get_action('resource_search')(
#         data_dict={'sort': 'views_recent desc', 'all_fields': True})
#
#     # Truncate the list to the 10 most popular groups only.
#     groups = groups[:5]
#
#     return groups
#
# def recent_packages_html():
#     '''Return a sorted list of the groups with the most datasets.'''
#
#     # Get a list of all the site's groups from CKAN, sorted by number of
#     # datasets.
#     groups = toolkit.get_action('recently_changed_packages_activity_list_html')(
#         data_dict={'limit': '5'})
#
#     return groups

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
            if isinstance(x, basestring):
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

class Cioos_ThemePlugin(plugins.SingletonPlugin, DefaultTranslation):
    plugins.implements(plugins.ITranslation)
    plugins.implements(plugins.IConfigurer)
    plugins.implements(plugins.ITemplateHelpers)
    plugins.implements(plugins.IFacets)
    plugins.implements(plugins.IPackageController, inherit=True)
    plugins.implements(plugins.IValidators)
    plugins.implements(plugins.IAuthenticator)

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

    def get_helpers(self):
        """Register the most_popular_groups() function above as a template helper function."""
        # Template helper function names should begin with the name of the
        # extension they belong to, to avoid clashing with functions from
        # other extensions.
        return {
            'cioos_load_json': load_json,
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
            'cioos_datasets': cioos_helpers.cioos_datasets,
            'cioos_count_datasets': cioos_helpers.cioos_count_datasets,
            'cioos_get_eovs': cioos_helpers.cioos_get_eovs
        }

    def get_validators(self):
        return {
            # 'cioos_if_empty_same_as__extras': if_empty_same_as__extras,
            'cioos_clean_and_populate_eovs': clean_and_populate_eovs,
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
        if 'themes' not in facets_dict or 'eov' not in facets_dict:
            # Horrible hack
            # Insert facet themes at first position of the OrderedDict facets_dict.
            ordered_dict = facets_dict.copy()
            facets_dict.clear()
            # facets_dict['themes'] = toolkit._('Theme')
            facets_dict['eov'] = toolkit._('Ocean Variables')

            for key, value in ordered_dict.items():
                # Make translation 'on the fly' of facet tags.
                # Should check for all translated fields.
                # Should check translation exists.
                if key == 'tags' or key == 'organization':
                # if key == 'tags':
                    facets_dict[key + '_' + self.lang()] = value
                else:
                    facets_dict[key] = value
        return facets_dict

    # IPackageController

    # def after_create(self, context, pkg_dict):
    #     # dosn't work to update name in validator as id is populated by database. better to use a validator and populate usig uuid
    #     # import uuid
    #     # str(uuid.uuid4())
    #     name = pkg_dict.get('name', '')
    #     if not name:
    #         pkg_dict['name'] = pkg_dict.get('id', name)

    # modfiey tags, keywords, and eov fields so that they properly index
    def before_index(self, data_dict):
        try:
            tags_dict = json.loads(data_dict.get('keywords', '{}'))
        except Exception as err:
            log.error(data_dict.get('id', 'NO ID'))
            log.error(type(err))
            log.error("error:%s, keywords:%r", err, data_dict.get('keywords', '{}'))
            tags_dict = {"en": [], "fr": []}

        # update tag list by language
        data_dict['tags_en'] = tags_dict.get('en', [])
        data_dict['tags_fr'] = tags_dict.get('fr', [])
        data_dict['tags'] = data_dict['tags_en'] + data_dict['tags_fr']

        # update organization list by language
        org_id = data_dict.get('owner_org')
        data_type = data_dict.get('type')
        if org_id and data_type == 'dataset':
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
            title = json.loads(data_dict.get('title_translated', '{}'))
            data_dict['title_en'] = title.get('en', [])
            data_dict['title_fr'] = title.get('fr', [])
        except Exception as err:
            log.error(err)

        te = data_dict.get('temporal-extent', '{}')
        if te:
            temporal_extent = load_json(te)
            temporal_extent_begin = temporal_extent.get('begin')
            temporal_extent_end = temporal_extent.get('end')
            if(temporal_extent_begin):
                data_dict['temporal-extent-begin'] = temporal_extent_begin
            if(temporal_extent_end):
                data_dict['temporal-extent-end'] = temporal_extent_end
            if(temporal_extent_begin and temporal_extent_end):
                data_dict['temporal-extent-range'] = '[' + temporal_extent_begin + ' TO ' + temporal_extent_end + ']'

        ve = data_dict.get('vertical-extent', '{}')
        if ve:
            vertical_extent = load_json(ve)
            vertical_extent_min = vertical_extent.get('min')
            vertical_extent_max = vertical_extent.get('max')
            if(vertical_extent_min):
                data_dict['vertical-extent-min'] = vertical_extent_min
            if(vertical_extent_max):
                data_dict['vertical-extent-max'] = vertical_extent_max

        # eov is multi select so it is a json list rather then a python list
        if(data_dict.get('eov')):
            data_dict['eov'] = load_json(data_dict['eov'])
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
                for c in choices:
                    if c['value'] == item['name']:
                        item['display_name'] = toolkit.h.scheming_language_text(c.get('label', item['name']))
                        item['category'] = c.get('catagory', u'')
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
            title = result.get('title_translated')
            if(title):
                result['title_translated'] = load_json(title)
            notes = result.get('notes_translated')
            if(notes):
                result['notes_translated'] = load_json(notes)
            keywords = result.get('keywords')
            if(keywords):
                result['keywords'] = load_json(keywords)

            # update organization object while we are at it
            org_id = result.get('owner_org')
            if org_id:
                org_details = org_dict.get(org_id)
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

        return package_dict


    # Custom section
    def read_template(self):
        return 'package/read.html'

    def lang(self):
        from ckantoolkit import h
        return h.lang()
