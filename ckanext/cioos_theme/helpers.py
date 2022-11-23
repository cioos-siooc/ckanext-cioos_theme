'''
  OGSL custom template helper function.

  Consists of functions typically used within templates, but also
  available to Controllers. This module is available to templates as 'h'.

'''

import ckan.plugins.toolkit as toolkit
import ckan.plugins as p
from collections import OrderedDict
from ckantoolkit import _, c, config
# from ckantoolkit import h
import ckan.logic as logic
import ckan.model as model
from ckan.model import PackageRelationship
from ckan.common import config
import copy
import logging
import json
import jsonpickle
import importlib_metadata as metadata
log = logging.getLogger(__name__)

try:
    # CKAN >= 2.6
    from ckan.exceptions import HelperError
except ImportError:
    # CKAN < 2.6
    class HelperError(Exception):
        pass

get_action = logic.get_action


def load_json(j):
    try:
        new_val = json.loads(j)
    except Exception:
        new_val = j
    return new_val

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
    '''
    Checks if a given helper name is available on `h`
    '''
    try:
        getattr(toolkit.h, helper_name)
    except (AttributeError, HelperError):
        return False
    return True


def generate_doi_suffix():
    import random
    chars = ['a','b','c','d','e','f','g','h','j','k','m','n','p','q','r','s',
             't','u','v','w','x','y','z','0','1','2','3','4','5','6','7','8','9']
    str1 = ''.join(random.SystemRandom().choice(chars) for _ in range(4))
    str2 = ''.join(random.SystemRandom().choice(chars) for _ in range(4))
    return str1 + '-' + str2


def get_doi_authority_url():
    return toolkit.config.get('ckan.cioos.doi_authority_url', 'https://doi.org/')


def get_doi_prefix():
    return toolkit.config.get('ckan.cioos.doi_prefix')


def get_datacite_org():
    return toolkit.config.get('ckan.cioos.datacite_org')


def get_datacite_test_mode():
    return toolkit.config.get('ckan.cioos.datacite_test_mode', 'True')


def get_fully_qualified_package_uri(pkg, uri_field, default_authority=None):
    fqURI = []
    uris = pkg.get(uri_field)

    if not uris:
        # try to build out of flat fields
        sep = toolkit.h.scheming_composite_separator()
        uris = [{
            "authority": pkg.get(uri_field + 'authority'),
            "code-space": pkg.get(uri_field + 'code-space'),
            "code": pkg.get(uri_field + 'code'),
            "version": pkg.get(uri_field + 'version')
        }] if pkg.get(uri_field + 'code') else None

    if not uris:
        return fqURI

    if isinstance(uris, dict):
        uris = [uris]

    for uri in uris:
        if not uri:
            continue
        authority = uri.get('authority') or default_authority
        code_space = uri.get('code-space')
        code = uri.get('code')
        version = uri.get('version')
        if not code:
            continue
        if toolkit.h.is_url(code):
            fqURI.append(code)
            continue
        code = '/'.join([code_space, code])
        if authority not in code:
            fqURI.append('https://' + authority + '/' + code)
    return fqURI


def get_package_relationships(pkg):
    '''Returns the relationships of a package.

    :param id: the id or name of the package
    '''
    rel = pkg.get('relationships_as_subject') + pkg.get('relationships_as_object')
    b = []
    for x in rel:
        if x not in b:
            b.append(x)
    return b


def print_package_relationship_type(type):
    out = 'depends on'
    if 'child' in type:
        out = 'parent'
    elif 'parent' in type:
        out = 'child'
    elif 'link' in type:
        out = 'cross link'
    return out


def get_package_relationship_reverse_type(type):
    return PackageRelationship.reverse_type(type)


def get_package_title(id):
    '''Returns the title of a package.

    :param id: the id or name of the package
    '''
    try:
        pkg = toolkit.get_action('package_show')(None, data_dict={'id': id})
    except Exception as e:
        return None
    return toolkit.h.get_translated(pkg, 'title')


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
    import ckanext.spatial.model as spatial_model
    import jinja2
    import inspect

    # map spatial key to schema field_name {'spatial': 'schema'}
    map = {
        'title': 'title_translated',
        'abstract': 'notes_translated',
        'guid': 'name',
        'keywords': ['keywords', 'eov'],
        'bbox': ['bbox-north-lat', 'bbox-south-lat', 'bbox-east-long', 'bbox-west-long'],
        'license_id': 'use-constraints'
        }

    schema = toolkit.h.scheming_get_dataset_schema('dataset')
    doc = spatial_model.ISODocument('<xml></xml>')

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
                instanse = class_('<xml></xml>')

        class_dict[x[0]]['class'] = jsonpickle.encode(instanse)

    # Dataset
    fields = schema['dataset_fields']
    j = jsonpickle.encode(doc.elements)
    isodoc_dict = json.loads(j)
    output = cioos_schema_field_map_parent(fields, isodoc_dict, class_dict, map, 'Dataset Fields')

    # Resources
    resource_fields_schema = [{'field_name': 'resource_fields', 'simple_subfields': schema['resource_fields']}]
    j = jsonpickle.encode([x for x in doc.elements if isinstance(x, spatial_model.ISOResourceLocator)], unpicklable=False)
    isodoc_dict = json.loads(j)
    resource_locator = [x for x in isodoc_dict if x['name'] == 'resource-locator']

    map = {
        'resource-locator': 'resource_fields'
        }

    output = output + cioos_schema_field_map_parent(resource_fields_schema, resource_locator, class_dict, map, 'Resource Fields')
    return jinja2.Markup(output)


# process any first level fields in the isodocument
def cioos_schema_field_map_parent(fields, isodoc_dict, class_dict, mapkey, caption):
    output = '''<table class="table table-bordered table-condensed">
        <caption>''' + caption + '''</caption>
        <thead>
            <tr>
                <th style="width:40px;">Req</th>
                <th style="width:200px;">Schema Name</th>
                <th style="width:200px;">Harvest Name</th>
                <th style="width:40px;">N</th>
                <th style="width:100px;">Description</th>
                <th>XML Path</th>

            </tr>
        </thead><tbody>'''
    matched_schema_fields = []

    # loop through spatial harvester isodocument fields
    for item in isodoc_dict:
        # get class name of entry in spatial harvester class
        (objpath, delimiter, objtype) = item.get('py/object', '').rpartition('.')
        # update class with pre determined definition if appropreit
        if objtype != 'ISOElement' and item.get('elements') and objtype.startswith('ISO'):
            class_json_def = json.loads(class_dict.get(objtype, {}).get('class', '{}'))
            elem = class_json_def.get('elements', [])
            item['elements'] = elem

        # get the search paths for the current item
        sp = item['search_paths']
        if isinstance(item['search_paths'], list):
            sp = '<br/>'.join(item['search_paths'])

        # map item name to a new name if it is entered in the mapkey dictinary
        search_item = mapkey.get(item['name'], item['name'])

        # get ckan schema field with the same name, if it exists
        field = toolkit.h.scheming_field_by_name(fields, search_item)
        # the mapkey fields could be a list as sometimes more then one ckan
        # schema field maps to a spatial harvest field
        if isinstance(search_item, list):
            fn = []
            fl = []
            for x in search_item:
                field = toolkit.h.scheming_field_by_name(fields, x)
                fn.append(field['field_name'])
                fl.append(toolkit.h.scheming_language_text(field.get('label', '')))
                matched_schema_fields.append(field['field_name'])
            field = {}
            field['field_name'] = ',<br/>'.join(fn)
            field['label'] = ',<br/>'.join(fl)

        schema_name = ''
        schema_label = ''
        schema_help = ''
        subfields = None
        required = ''

        if field:
            schema_name = field['field_name']
            schema_label = ' (' + toolkit.h.scheming_language_text(field.get('label', '')) + ')'
            schema_help = field.get('help_text', '')
            subfields = field.get('simple_subfields') or field.get('repeating_subfields')
            if field.get('required'):
                required = '<span class="required">*</span>'
            matched_schema_fields.append(schema_name)

        output = output + '<tr><td>' + required + '</td><td>' + schema_name + schema_label + '</td><td>' + item['name'] + '</td><td>' + item['multiplicity'] + '</td><td>' + schema_help +'</td><td>' + sp + '</td></tr>'
        (output_new, matched_schema_fields) = cioos_schema_field_map_child(subfields, None, item.get('elements'), "", 1, matched_schema_fields)
        output = output + output_new

    # add any fields in schema that have not found a match in spatial harvest
    for field in fields:
        if field['field_name'] not in matched_schema_fields:
            schema_name = field['field_name']
            schema_label = ' (' + toolkit.h.scheming_language_text(field.get('label', '')) + ')'
            matched_schema_fields.append(schema_name)
            required = ''
            if field.get('required'):
                required = '<span class="required">*</span>'
            output = output + '<tr><td>' + required + '</td><td>' + schema_name + schema_label + '</td><td></td><td></td><td></td><td></td></tr>'
    return output + '</tbody></table>'

# process any child elements of first level or lower isodocument fields.
def cioos_schema_field_map_child(schema_subfields, schema_parentfields, harvest_elements, path, indent, matched_schema_fields):
    output = ''
    if not harvest_elements:
        return output, matched_schema_fields
    if not isinstance(harvest_elements, list):
        return output, matched_schema_fields

    for item in harvest_elements:
        if not item or not item.get('name'):
            continue
        sp = item['search_paths']
        if isinstance(item['search_paths'], list):
            sp = '<br/>'.join(item['search_paths'])

        field = None
        if schema_subfields:
            field = toolkit.h.scheming_field_by_name(schema_subfields, item['name']) or \
                toolkit.h.scheming_field_by_name(schema_subfields, path + item['name'])
        if not field and schema_parentfields:
            field = toolkit.h.scheming_field_by_name(schema_parentfields, item['name']) or \
                toolkit.h.scheming_field_by_name(schema_parentfields, path + item['name'])

        schema_name = ''
        schema_label = ''
        schema_help = ''
        subfields = None
        parentfields = schema_subfields
        required = ''

        if field:
            schema_name = field['field_name']
            schema_label = ' (' + toolkit.h.scheming_language_text(field.get('label', '')) + ')'
            schema_help = field.get('help_text', '')
            subfields = field.get('simple_subfields') or field.get('repeating_subfields')
            matched_schema_fields.append(schema_name)
            schema_name = '<i class="fa fa-angle-right"></i>' + schema_name
            if field.get('required'):
                required = '<span class="required">*</span>'

        harvest_name = ''
        if item['name']:
            harvest_name = '<i class="fa fa-angle-right"></i>' + item['name']

        output = output + '<tr class="child' + str(indent) + '"><td>' + required + '</td><td>' + schema_name + schema_label + '</td><td>' + harvest_name + '</td><td>' + item['multiplicity'] + '</td><td>' + schema_help +'</td><td>' + sp + '</td></tr>'
        (output_new, matched_schema_fields) = cioos_schema_field_map_child(subfields, parentfields, item.get('elements'), path + item['name'] + '_', indent + 1, matched_schema_fields)
        output = output + output_new

    # outout any schema fields at this sublevel which do not have a match.
    if schema_subfields:
        for field in schema_subfields:
            if field['field_name'] not in matched_schema_fields:
                schema_name = field['field_name']
                schema_label = ' (' + toolkit.h.scheming_language_text(field.get('label', '')) + ')'
                matched_schema_fields.append(schema_name)
                required = ''
                if field.get('required'):
                    required = '<span class="required">*</span>'
                output = output + '<tr><td>' + required + '</td><td>' + schema_name + schema_label + '</td><td></td><td></td><td></td><td></td></tr>'
    return output, matched_schema_fields


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
        'facet.field': list(facets.keys()),
        'rows': 0,
        'include_private': toolkit.asbool(config.get(
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


def cioos_version():
    '''Return CIOOS version'''
    return metadata.version('ckanext.cioos_theme')
