'''
  OGSL custom template helper function.

  Consists of functions typically used within templates, but also
  available to Controllers. This module is available to templates as 'h'.

'''

import ckan.plugins.toolkit as toolkit

def get_organization_list(data_dict):
    '''Returns a list of organizations.

    :param id: the id or name of the organization
    '''
    # If a context of None is passed to the action function then the default context dict will be created
    # All other parameters are optional and are set to their default value
    # cf. http://docs.ckan.org/en/latest/extensions/plugins-toolkit.html#ckan.plugins.toolkit.ckan.plugins.toolkit.get_action
    return toolkit.get_action('organization_list')(None, data_dict = data_dict)

def get_organization_dict(id):
    '''Returns the details of an organization.

    :param id: the id or name of the organization
    '''
    # If a context of None is passed to the action function then the default context dict will be created
    # All other parameters are optional and are set to their default value
    # cf. http://docs.ckan.org/en/latest/api/index.html#ckan.logic.action.get.organization_show
    return toolkit.get_action('organization_show')(None, data_dict = {'id': id})

def get_organization_dict_extra(organization_dict, key, default=None):
    '''Returns the value for the organization extra with the provided key.

    If the key is not found, it returns a default value, which is None by
    default.

    :param organization_dict: dictized organization
    :key: extra key to lookup
    :default: default value returned if not found
    '''
    extras = organization_dict['extras'] if 'extras' in organization_dict else []

    for extra in extras:
        if extra['key'] == key:
            return extra['value']

    return default
