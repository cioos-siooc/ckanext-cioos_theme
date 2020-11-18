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
import copy
import logging
import json
import jsonpickle
log = logging.getLogger(__name__)

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


def _merge_lists(key, list1, list2):
    merged = {}
    for item in list1 + list2:
        if item[key] in merged:
            merged[item[key]].update(item)
        else:
            merged[item[key]] = item
    return [v for (k, v) in merged.items()]


def cioos_get_eovs(show_all=False):
    '''Return a list of eov's in a similar format to the facet list
    If show_all is true then the complete list of eov's is returned. The name
    and display_name fields are updated from the eoc choices list as found in
    ckanext-scheming. If show_all is false only the eov's returned as part of
    the active facet list are returned.

    param show_all: display all eov fields or only the ones that are currently
                    active.
       '''
    schema = toolkit.h.scheming_get_dataset_schema('dataset')
    fields = []
    choices = []
    facets = toolkit.h.cioos_get_facets()  # needed to make get_facet_items_dict work
    eov = toolkit.h.get_facet_items_dict('eov', limit=None, exclude_active=False)
    if schema:
        fields = schema.get('dataset_fields')
    if fields:
        # retreave a copy of the choices list for the eov field
        choices = copy.deepcopy(toolkit.h.scheming_field_choices(toolkit.h.scheming_field_by_name(fields, 'eov')))
        # make choices list more facet like
        for x in choices:
            x['name'] = x['value']
            x['display_name'] = x['label']

    if show_all:
        output = _merge_lists('name', eov, choices)
    else:
        lookup = {x['name']: x for x in eov}
        for x in choices:
            if x['name'] in lookup:
                lookup[x['name']].update(x)
        output = list(lookup.values())

    for x in output:
        # set count to zero for eov's not in facet list
        if 'count' not in x:
            x['count'] = 0
        # generate icon file name if not set
        if 'icon' not in x:
            x['icon'] = 'icon-' + x['name'].lower() + '.png'
    return output


def cioos_count_datasets():
    '''Return a count of datasets'''
    user = logic.get_action('get_site_user')({'model': model, 'ignore_auth': True}, {})
    context = {'model': model, 'session': model.Session, 'user': user['name']}
    # Get a list of all the site's datasets from CKAN, no need to return actual data
    datasets = logic.get_action('package_search')(context, {"fl": "id", "rows": "0"})
    return datasets['count']


def cioos_datasets():
    '''Return a list of the datasets'''

    user = logic.get_action('get_site_user')({'model': model, 'ignore_auth': True}, {})
    context = {'model': model, 'session': model.Session, 'user': user['name']}
    # Get a list of all the site's datasets from CKAN
    datasets = logic.get_action('package_search')(context, {"fl": "id"})
    return datasets

def cioos_schema_field_map():
    from ckanext.spatial.model import ISODocument
    import jinja2

    map = [
        {'schema': 'title_translated', 'spatial': 'title'},
        {'schema': 'notes_translated', 'spatial': 'abstract'},
        {'schema': 'name', 'spatial': 'unique_resource_identifier'},
        {'schema': ['keywords', 'eov'], 'spatial': 'keywords'},
        {'schema': ['bbox-north-lat', 'bbox-south-lat', 'bbox-east-long', 'bbox-west-long'], 'spatial': 'bbox'}
    ]

    mapkey = {x['spatial']: x['schema'] for x in map}

    schema = toolkit.h.scheming_get_dataset_schema('dataset')
    fields = schema['dataset_fields']
    doc = ISODocument('<xml></xml>')
    j = jsonpickle.encode(doc.elements)

    # output = '|name|*|xml path|'
    # for item in json.loads(j):
    #     output += '|' + item['name'] + '|' + item['multiplicity'] + '|' + ',\n'.join(item['search_paths']) + '|'

    output = '<table class="table table-striped table-bordered table-condensed"><thead><tr><th>Req</th><th style="width:200px;">schema name</th><th style="width:200px;">harvest name</th><th style="width:40px;">N</th><th>xml path</th></tr></thead><tbody>'
    matched_schema_fields = []
    for item in json.loads(j):
        sp = item['search_paths']
        if isinstance(item['search_paths'], list):
            sp = '<br/>'.join(item['search_paths'])

        search_item = mapkey.get(item['name'], item['name'])
        field = toolkit.h.scheming_field_by_name(fields, search_item)
        if isinstance(search_item, list):
            fn = []
            fl = []
            for x in search_item:
                field = toolkit.h.scheming_field_by_name(fields, x)
                fn.append(field['field_name'])
                fl.append(toolkit.h.scheming_language_text(field['label']))
                matched_schema_fields.append(field['field_name'])
            field = {}
            field['field_name'] = ',<br/>'.join(fn)
            field['label'] = ',<br/>'.join(fl)

        schema_name = ''
        schema_label = ''
        subfields = None
        required = ''

        if field:
            schema_name = field['field_name']
            schema_label = ' (' + toolkit.h.scheming_language_text(field['label']) + ')'
            subfields = field.get('subfields')
            if field.get('required'):
                required = '<span class="required">*</span>'
            matched_schema_fields.append(schema_name)

        output = output + '<tr><td>' + required + '</td><td>' + schema_name + schema_label + '</td><td>' + item['name'] + '</td><td>' + item['multiplicity'] + '</td><td>' + sp + '</td></tr>'
        output = output + cioos_schema_field_map_child(subfields, item.get('elements'), "", 1, matched_schema_fields)

    for field in fields:
        if field['field_name'] not in matched_schema_fields:
            schema_name = field['field_name']
            schema_label = ' (' + toolkit.h.scheming_language_text(field['label']) + ')'
            matched_schema_fields.append(schema_name)
            output = output + '<tr><td></td><td>' + schema_name + schema_label + '</td><td>' + '</td><td>' + '</td><td>' + '</td></tr>'
    return jinja2.Markup(output + '</tbody></table>')


def cioos_schema_field_map_child(schema_subfields, harvest_elements, path, indent, matched_schema_fields):
    output = ''
    if harvest_elements and isinstance(harvest_elements, list):
        for item in harvest_elements:
            if not item.get('name'):
                continue
            sp = item['search_paths']
            if isinstance(item['search_paths'], list):
                sp = '<br/>'.join(item['search_paths'])

            schema_name = ''
            schema_label = ''
            subfields = schema_subfields
            field = None

            log.debug(path + item['name'])

            if schema_subfields:
                field = toolkit.h.scheming_field_by_name(schema_subfields, item['name']) or \
                    toolkit.h.scheming_field_by_name(schema_subfields, path + item['name'])
            if field:
                schema_name = field['field_name']
                schema_label = ' (' + toolkit.h.scheming_language_text(field['label']) + ')'
                subfields = field.get('subfields')
                matched_schema_fields.append(schema_name)
                if schema_name:
                    schema_name = '<i class="fa fa-angle-right"></i>' + schema_name
            harvest_name = ''
            if item['name']:
                harvest_name = '<i class="fa fa-angle-right"></i>' + item['name']

            output = output + '<tr class="child' + str(indent) + '"><td>' + schema_name + schema_label + '</td><td>' + harvest_name + '</td><td>' + item['multiplicity'] + '</td><td>' + sp + '</td></tr>'
            output = output + cioos_schema_field_map_child(subfields, item.get('elements'), path + item['name'] + '_', indent + 1, matched_schema_fields)
    if schema_subfields:
        for field in schema_subfields:
            if field['field_name'] not in matched_schema_fields:
                schema_name = field['field_name']
                schema_label = ' (' + toolkit.h.scheming_language_text(field['label']) + ')'
                matched_schema_fields.append(schema_name)
                output = output + '<tr><td>' + schema_name + schema_label + '</td><td>' + '</td><td>' + '</td><td>' + '</td></tr>'
    return output


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
