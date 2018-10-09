import ckan.plugins as plugins
import ckan.plugins.toolkit as toolkit
import json
from shapely.geometry import shape


def load_json(j):
    return json.loads(j);

def geojson_to_bbox(o):
    return shape(o).bounds;

#from the docs
def most_popular_groups():
    '''Return a sorted list of the groups with the most datasets.'''

    # Get a list of all the site's groups from CKAN, sorted by number of
    # datasets.
    groups = toolkit.get_action('group_list')(
        data_dict={'sort': 'package_count desc', 'all_fields': True})

    # Truncate the list to the 10 most popular groups only.
    groups = groups[:5]

    return groups

def groups():
    '''Return a sorted list of the groups'''

    # Get a list of all the site's groups from CKAN, sorted by number of
    # datasets.
    groups = toolkit.get_action('group_list')(
        data_dict={'sort': 'title asc', 'all_fields': True})

    return groups

#from the docs
def most_popular_datasets():
    '''Return a sorted list of the groups with the most datasets.'''

    # Get a list of all the site's groups from CKAN, sorted by number of
    # datasets.
    groups = toolkit.get_action('package_search')(
        data_dict={'sort': 'views_recent desc', 'all_fields': True})

    # Truncate the list to the 10 most popular groups only.
    groups = groups[:5]

    return groups

#from the docs
def most_popular_resources():
    '''Return a sorted list of the groups with the most datasets.'''

    # Get a list of all the site's groups from CKAN, sorted by number of
    # datasets.
    groups = toolkit.get_action('resource_search')(
        data_dict={'sort': 'views_recent desc', 'all_fields': True})

    # Truncate the list to the 10 most popular groups only.
    groups = groups[:5]

    return groups

def recent_packages_html():
    '''Return a sorted list of the groups with the most datasets.'''

    # Get a list of all the site's groups from CKAN, sorted by number of
    # datasets.
    groups = toolkit.get_action('recently_changed_packages_activity_list_html')(
        data_dict={'limit': '5'})

    return groups



class Cioos_ThemePlugin(plugins.SingletonPlugin):
    plugins.implements(plugins.IConfigurer)
    plugins.implements(plugins.ITemplateHelpers)
    # IConfigurer

    def update_config(self, config_):
        toolkit.add_template_directory(config_, 'templates')
        toolkit.add_public_directory(config_, 'public')
        toolkit.add_resource('fanstatic', 'cioos_theme')

    def get_helpers(self):
        '''Register the most_popular_groups() function above as a template
        helper function.

        '''
        # Template helper function names should begin with the name of the
        # extension they belong to, to avoid clashing with functions from
        # other extensions.
        return {
	  'cioos_load_json': load_json, 
	  'cioos_geojson_to_bbox': geojson_to_bbox,
	  'cioos_most_popular_groups': most_popular_groups,
	  'cioos_groups': groups,
	  'cioos_most_popular_datasets': most_popular_datasets,
	  'cioos_most_popular_resources': most_popular_resources,
	  'cioos_recent_packages_html': recent_packages_html
	}

