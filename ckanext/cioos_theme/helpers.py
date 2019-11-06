'''
  OGSL custom template helper function.

  Consists of functions typically used within templates, but also
  available to Controllers. This module is available to templates as 'h'.

'''

import ckan.plugins.toolkit as toolkit
import ckan.plugins as p
from ckan.common import OrderedDict, _, c
# from ckantoolkit import h
import ckan.logic as logic
import ckan.model as model
from ckan.common import config
from paste.deploy.converters import asbool

get_action = logic.get_action

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


def cioos_count_datasets():
    '''Return a count of datasets'''
    datasets = toolkit.h.cioos_datasets()
    return len(datasets)


def cioos_datasets():
    '''Return a list of the datasets'''

    user = logic.get_action('get_site_user')({'model': model, 'ignore_auth': True}, {})
    context = {'model': model, 'session': model.Session, 'user': user['name']}
    # Get a list of all the site's datasets from CKAN
    datasets = logic.get_action('package_list')(context, {})
    return datasets


def cioos_get_facets(package_type='dataset'):
    ''' get all dataset for the given package type, including private ones.
        This function works similarly to code found in ckan/ckan/controllers/package.py
        in that it does a search of all datasets and populates the following
        globals for later use:
            c.facet_titles
            c.search_facets
    '''
    facets = OrderedDict()

    default_facet_titles = {
        'organization': _('Organizations'),
        'groups': _('Groups'),
        'tags': _('Tags'),
        'res_format': _('Formats'),
        'license_id': _('Licenses'),
    }

    for facet in toolkit.h.facets():
        if facet in default_facet_titles:
            facets[facet] = default_facet_titles[facet]
        else:
            facets[facet] = facet

    # Facet titles
    for plugin in p.PluginImplementations(p.IFacets):
        facets = plugin.dataset_facets(facets, package_type)

    c.facet_titles = facets

    data_dict = {
        'facet.field': facets.keys(),
        'rows': 0,
        'include_private': asbool(config.get(
            'ckan.search.default_include_private', True)),
    }

    context = {'model': model, 'session': model.Session,
               'user': c.user, 'for_view': True,
               'auth_user_obj': c.userobj}

    query = get_action('package_search')(context, data_dict)
    c.search_facets = query['search_facets']
    # return {
    #     'search': c.search_facets,
    #     'titles': c.facet_titles,
    # }
