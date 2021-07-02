import ckan.plugins.toolkit as toolkit
import ckan.model as model
from ckan.lib.search import rebuild
from ckan.logic import NotFound, ValidationError
import re
import logging
from ckanext.cioos_theme.helpers import load_json

log = logging.getLogger(__name__)

def get_relationships_from_schema(rel_json, subject_name):
    # compare schema field, here called aggregation-info and
    # package relationships.
    rels_from_schema = []
    for x in rel_json:
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
        if x['aggregate-dataset-identifier']:
            rels_from_schema.append({
                "subject": subject_name,
                "type": type,
                "object": x['aggregate-dataset-identifier'],
                "comment": comment
            })
    return rels_from_schema

def update_package_relationships(context, package_dict, is_create):
    to_delete = []
    to_add = []
    to_index = []
    relationships_errors = []

    if context['auth_user_obj'] is None:
        # updating package relationships during harvest creates all kinds of issues
        # a seperate command is avaiable to be run on a cron job to handle this situation
        # skip for now.
        return

    rels_from_schema = get_relationships_from_schema(load_json(package_dict.get('aggregation-info', [])), package_dict['name'])
    existing_rels = []
    # get existing package relationships where this package is the subject (from)
    existing_rels = toolkit.get_action('package_relationships_list')(
        data_dict={
            'id': package_dict['id']
        }
    )

    # existing_rels - rels_from_schema
    # do not delete inbound relationships, ie where this dataset is the object/target
    to_delete = to_delete + [x for x in existing_rels
                             if x not in rels_from_schema and
                             x['type'] not in ['linked_from', 'parent_of', 'has_derivation', 'dependency_of']]

    # rels_from_schema - existing_rels
    to_add = to_add + [x for x in rels_from_schema if x not in existing_rels]

    # delete relationships
    for d in to_delete:
        try:
            toolkit.get_action('package_relationship_delete')(data_dict=d)
            to_index.append(d['object'])
            log.debug('Deleted package relationship %s %s %s', d['subject'], d['type'], d['object'])
        except Exception as e:
            log.debug('%s' % str(e))
            relationships_errors.append('%r' % e)

    if to_delete:
        # we have to purge relationships flaged as deleted otherwise we
        # will get a detachedinstanceerror when trying to re-add the
        # relationship later
        for r in model.Session.query(model.PackageRelationship).filter(
                model.PackageRelationship.state == 'deleted').all():
            r.purge()
        model.repo.commit_and_remove()

    # create relationships
    for a in to_add:
        try:
            toolkit.get_action('package_relationship_create')(context, data_dict=a)
            to_index.append(a['object'])
            log.debug('Created package relationship %s %s %s', a['subject'], a['type'], a['object'])
        except toolkit.ObjectNotFound as e:
            log.debug('Package relationship Not Found for %s %s %s', a['subject'], a['type'], a['object'])
            relationships_errors.append('Failed to create package relationship for dataset %s: %r' % (package_dict['id'], e))

    # trigger indexing of datasets we are linking to
    for package_id in to_index:
        rebuild(package_id)

    if relationships_errors:
        raise toolkit.ValidationError(relationships_errors)

    return
