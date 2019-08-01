import ckan.plugins as plugins
import ckan.plugins.toolkit as toolkit
import ckanext.cioos_theme.helpers as OGSLhelpers #OGSL helpers
from ckan.lib.plugins import DefaultTranslation
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



class Cioos_ThemePlugin(plugins.SingletonPlugin, DefaultTranslation):
    plugins.implements(plugins.ITranslation)
    plugins.implements(plugins.IConfigurer)
    plugins.implements(plugins.ITemplateHelpers)
    plugins.implements(plugins.IFacets) #OSGL
    plugins.implements(plugins.IPackageController, inherit=True) #OSGL

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
	  'cioos_recent_packages_html': recent_packages_html,
      'get_organization_list': OGSLhelpers.get_organization_list,
      'get_organization_dict': OGSLhelpers.get_organization_dict,
      'get_organization_dict_extra': OGSLhelpers.get_organization_dict_extra
	}

    # # IFacets
    #
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
        if 'themes' not in facets_dict:
            # Horrible hack
            # Insert facet themes at first position of the OrderedDict facets_dict.
            ordered_dict = facets_dict.copy()
            facets_dict.clear()
            #facets_dict['themes'] = toolkit._('Theme')
            #facets_dict['keywords_' + self.lang()] = toolkit._('Keywords')

            for key, value in ordered_dict.items():
                # Make translation 'on the fly' of facet tags.
                # Should check for all translated fields.
                # Should check translation exists.
               if key == 'tags':
                   facets_dict[key + '_' + self.lang()] = value
               else:
                   facets_dict[key] = value
            return facets_dict

    # IPackageController

    def before_index(self, data_dict):
        tags_dict = json.loads(data_dict.get('keywords', '{}'))
        data_dict['tags_en'] = tags_dict.get('en', [])
        data_dict['tags_fr'] = tags_dict.get('fr', [])

        # if data_dict.get('extras_themes', None):
        #     data_dict['themes'] = json.loads(data_dict.get('extras_themes', '[]'))
        return data_dict

    # Custom section

    def read_template(self):
        return 'package/read.html'

    def lang(self):
        from ckantoolkit import h
        return h.lang()
