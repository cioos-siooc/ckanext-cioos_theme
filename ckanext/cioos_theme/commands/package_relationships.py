from ckan import model
from ckan.logic import get_action, ValidationError

from ckan.lib.cli import CkanCommand

import re

from ckanext.cioos_theme.helpers import load_json

import logging
log = logging.getLogger(__name__)

class PackageRelationships(CkanCommand):
    '''Performs package relationship related operations.

    Usage:
        package_relationships rebuild [dataset_name]  - create package
            relationships for a dataset_name if given, if not then rebuild
            package relationships for all datasets

    '''

    summary = __doc__.split('\n')[0]
    usage = __doc__
    max_args = 2
    min_args = 0

    def __init__(self, name):
        super(PackageRelationships, self).__init__(name)

    def _load_config(self):
        super(PackageRelationships, self)._load_config()


    def command(self):
        if not self.args:
            # default to printing help
            print(self.usage)
            return

        cmd = self.args[0]

        self._load_config()
        if cmd == 'rebuild':
            self.rebuild(clear=False)
        elif cmd == 'clear':
            self.rebuild(clear=True)
        else:
            print('Command %s not recognized' % cmd)

    def rebuild(self, clear=False):
        from ckan.lib.search import rebuild, commit

        to_delete = []
        to_add = []
        to_index = []
        relationships_errors = []
        dataset_id_arg = None

        if len(self.args) > 1:
            dataset_id_arg = self.args[1]

        user = get_action('get_site_user')({'model': model, 'ignore_auth': True}, {})
        context = {'model': model, 'session': model.Session, 'user': user['name']}

        query_str = 'aggregation-info:[* TO *]'
        if dataset_id_arg:
            query_str = query_str + ' AND name:%s' % dataset_id_arg

        query = get_action('package_search')(
            context, data_dict={
                "q": query_str,
                "fl": "id,name,extras_aggregation-info"
            })
        for package_dict in query['results']:

            # compare schema field, here called aggregation-info and
            # package relationships. This block should be split off
            # into it's own function so it can be overriden
            existing_rels = []
            rels_from_schema = []
            for x in load_json(package_dict.get('aggregation-info', [])):
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
            try:
                existing_rels = get_action('package_relationships_list')(
                    data_dict={
                        'id': package_dict['id']
                    }
                )
            except Exception as e:
                log.warn('No package relationship found for dataset %s: %r' % (package_dict['id'], e))
                existing_rels = []

            if clear:
                to_delete = existing_rels
                to_add = []
            else:
                to_delete = to_delete + [x for x in existing_rels if x not in rels_from_schema]  # existing_rels - rels_from_schema
                to_add = to_add + [x for x in rels_from_schema if x not in existing_rels]  # rels_from_schema - existing_rels

            # delete relationships
            for d in to_delete:
                try:
                    get_action('package_relationship_delete')(data_dict=d)
                    to_index.append(d['object'])
                    log.debug('Deleted package relationship %s %s %s', d['subject'], d['type'], d['object'])
                except Exception as e:
                    log.warn('Failed to delete package relationship for dataset %s: %r' % (package_dict['id'], e))
            # create relationships
            for a in to_add:
                try:
                    get_action('package_relationship_create')(context, data_dict=a)
                    to_index.append(a['object'])
                    log.debug('Created package relationship %s %s %s', a['subject'], a['type'], a['object'])
                except Exception as e:
                    log.warn('Failed to create package relationship for dataset %s: %r' % (package_dict['id'], e))

            # trigger indexing of datasets we are linking to
            for target_package_id in to_index:
                rebuild(target_package_id)

            # index this dataset
            # if dataset_id_arg is None:
            #    rebuild(package_dict['id'])
