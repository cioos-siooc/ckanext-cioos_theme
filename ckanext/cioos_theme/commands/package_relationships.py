from ckan import model
from ckan.logic import get_action, ValidationError
import ckan.lib.search
from ckan.lib.cli import CkanCommand
from ckanext.cioos_theme.package_relationships import get_relationships_from_schema
import re

from ckanext.cioos_theme.helpers import load_json
# import debugpy
import logging
log = logging.getLogger(__name__)

# debugpy.listen(('0.0.0.0', 5678))
# log.debug("Waiting for debugger attach")
# debugpy.wait_for_client()

class PackageRelationships(CkanCommand):
    '''Performs package relationship related operations.

    Usage:
        package_relationships rebuild [dataset_name]  - create package
            relationships for a dataset_name if given, if not then rebuild
            package relationships for all datasets

        package_relationships clear [dataset_name]  - remove package
            relationships for a dataset_name if given, if not then remove
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

        dataset_id_arg = None

        if len(self.args) > 1:
            dataset_id_arg = self.args[1]

        context = {'model': model, 'session': model.Session, "ignore_auth": True}

        query_str = 'aggregation-info:[* TO *]'
        if dataset_id_arg:
            query_str = query_str + ' AND name:%s' % dataset_id_arg

        # TODO: add paging incase we have more then 1000 records
        query = get_action('package_search')(
            context, data_dict={
                "q": query_str,
                "fl": "id,name,extras_aggregation-info",
                "rows": 1000
            })

        to_index = []
        for package_dict in query['results']:
            to_delete = []
            to_add = []
            existing_rels = []

            rels_from_schema = get_relationships_from_schema(load_json(package_dict.get('aggregation-info', [])))

            # get existing package relationships where this package is the
            # subject (from)
            try:
                existing_rels = get_action('package_relationships_list')(
                    data_dict={
                        'id': package_dict['id']
                    }
                )
            except Exception as e:
                print('No package relationship found for dataset %s: %r'
                      % package_dict['id'], e)
                existing_rels = []

            if clear:
                to_delete = existing_rels
                to_add = []
            else:
                # existing_rels - rels_from_schema
                # do not delete inbound relationships, ie where this dataset is the object/target
                to_delete = to_delete + [x for x in existing_rels
                                         if x not in rels_from_schema and
                                         x['type'] not in ['linked_from', 'parent_of', 'has_derivation', 'dependency_of']]
                # rels_from_schema - existing_rels
                to_add = to_add + [x for x in rels_from_schema
                                   if x not in existing_rels]

            # delete relationships
            for d in to_delete:
                try:
                    get_action('package_relationship_delete')(context, data_dict=d)
                    to_index.append(d['object'])
                    print('Deleted package relationship %s %s %s' % (d['subject'],
                          d['type'], d['object']))
                except Exception as e:
                    print('Failed to delete package relationship for dataset %s: %r' % (package_dict['id'], e))

            if to_delete:
                # we have to purge relationships flagged as deleted otherwise we
                # will get a detachedinstanceerror when trying to re-add the
                # relationship later
                for r in model.Session.query(model.PackageRelationship).filter(
                        model.PackageRelationship.state == 'deleted').all():
                    r.purge()
                model.repo.commit_and_remove()

            # create relationships
            for a in to_add:
                try:
                    get_action('package_relationship_create')(context, data_dict=a)
                    to_index.append(a['object'])
                    print('Created package relationship %s %s %s' % (a['subject'],
                          a['type'], a['object']))
                except Exception as e:
                    print('Failed to create package relationship for dataset %s: %r' % (package_dict['id'], e))

            to_index.append(package_dict['id'])

        print('Indexing datasets: %r' % to_index)
        # remove duplicates
        to_index = list(dict.fromkeys(to_index))
        # trigger indexing of datasets involved in relationships
        for target_package_id in to_index:
            ckan.lib.search.rebuild(target_package_id)
