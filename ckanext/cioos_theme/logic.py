import os
import ckan.plugins.toolkit as toolkit
from pygeometa.core import render_template

from logging import getLogger

log = getLogger(__name__)


@toolkit.side_effect_free
def cioos_package_export(context, data_dict):
    try:
        id = data_dict['id']
    except KeyError:
        raise toolkit.ValidationError({'id': 'missing id'})

    dataset_dict = toolkit.get_action('package_show')(context, {'id': id})

    dir_path = os.path.dirname(os.path.realpath(__file__))
    schema_path = dir_path + '/../../../metadata-xml/metadata_xml/iso19115-cioos-template'

    # dictionary representation of YAML
    dataset_dict['mcf'] = {'version': 1.0}
    dataset_dict['metadata'] = {
        'naming_authority_en': toolkit.h.cioos_load_json(dataset_dict.get('unique-resource-identifier-full', '{}')).get('authority'),
        'naming_authority_fr': toolkit.h.cioos_load_json(dataset_dict.get('unique-resource-identifier-full', '{}')).get('authority'),
        'identifier': toolkit.h.cioos_load_json(dataset_dict.get('unique-resource-identifier-full', '{}')).get('code'),
        'language': dataset_dict['metadata-language'],
        'language_alternate': 'fr' if dataset_dict['metadata-language'] != 'fr' else 'en',
        'maintenance_note_en': dataset_dict.get('maintenance_note', {}).get('en'),
        'maintenance_note_fr': dataset_dict.get('maintenance_note', {}).get('fr'),
        'use_constraints_en': 'see license',
        'use_constraints_fr': 'see license',
        'use_constraints': {
            'limitations_en': 'see license',
            'limitations_fr': 'see license',
            'license': {
                'title': dataset_dict.get('license_title'),
                'code': dataset_dict.get('license_code'),
                'link': dataset_dict.get('license_url')
                }
            }
        # 'comment_en': dataset_dict.get('notes_translated', {}).get('en'),
        # 'comment_fr': dataset_dict.get('notes_translated', {}).get('fr'),
        # 'history_en': history_en,
        # 'history_fr': history_fr
        }
    dataset_dict['spatial'] = {
        'bbox': [dataset_dict.get('bbox-west-long'),
                 dataset_dict.get('bbox-north-lat'),
                 dataset_dict.get('bbox-east-long'),
                 dataset_dict.get('bbox-south-lat')],
        'polygon': dataset_dict.get('spatial'),
        'vertical': [toolkit.h.cioos_load_json(dataset_dict.get('vertical-extent', '{}')).get('min'), toolkit.h.cioos_load_json(dataset_dict.get('vertical-extent', '{}')).get('max')]
        }

    creation_date = [x['value'] for x in toolkit.h.cioos_load_json(dataset_dict.get('dataset-reference-date')) if x['type'] == 'creation']
    publication_date = [x['value'] for x in toolkit.h.cioos_load_json(dataset_dict.get('dataset-reference-date')) if x['type'] == 'publication']
    revision_date = [x['value'] for x in toolkit.h.cioos_load_json(dataset_dict.get('dataset-reference-date')) if x['type'] == 'revision']

    dataset_dict['identification'] = {
        'title_en': dataset_dict.get('title_translated', {}).get('en'),
        'title_fr': dataset_dict.get('title_translated', {}).get('fr'),
        'abstract_en': dataset_dict.get('notes_translated', {}).get('en'),
        'abstract_fr': dataset_dict.get('notes_translated', {}).get('fr'),
        'keywords': {
            'default': {
                'keywords_en': dataset_dict.get('keywords').get('en'),
                'keywords_fr': dataset_dict.get('keywords').get('fr')
                },
            'eov': {
                'keywords_en': dataset_dict.get('eov')
                }
            },
        'temporal_begin': toolkit.h.cioos_load_json(dataset_dict.get('temporal-extent')).get('begin'),
        'temporal_end': toolkit.h.cioos_load_json(dataset_dict.get('temporal-extent')).get('end'),
        # temporal_duration: P1D
        # time_coverage_resolution: P1D
        'status': dataset_dict.get('progress'),
        # acknowledgement: acknowledgement
        # 'project_en': '',
        # 'project_fr': ''
        }

    dataset_dict['identification']['dates'] = {}
    if len(creation_date) > 0:
        dataset_dict['identification']['dates']['creation'] = creation_date[0]
    if len(publication_date) > 0:
        dataset_dict['identification']['dates']['publication'] = publication_date[0]
    if len(revision_date) > 0:
        dataset_dict['identification']['dates']['revision'] = revision_date[0]

    log.debug('DATES:%r', dataset_dict['identification']['dates'])

    contacts = {}
    for rp in toolkit.h.cioos_load_json(dataset_dict.get('cited-responsible-party')):
        contact = {}
        if rp.get('individual-name'):
            contact['individual'] = {
                'name': rp.get('individual-name'),
                'email': rp.get('contact-info_email'),
                'country': rp.get('contact-info_country', 'Canada')
                }
        if rp.get('organisation-name'):
            contact['organization'] = {
                'name': rp.get('organisation-name'),
                'email': rp.get('contact-info_email'),
                'country': rp.get('contact-info_country', 'Canada')
                }
        contacts[rp.get('role')] = contact
    dataset_dict['contact'] = contacts
    log.debug('CONTACT:%r', dataset_dict['contact'])

    point_of_contacts = []
    dataset_dict['metadata-point-of-contact'] = toolkit.h.cioos_load_json(dataset_dict.get('metadata-point-of-contact'))
    if isinstance(dataset_dict['metadata-point-of-contact'], dict):
        dataset_dict['metadata-point-of-contact'] = [dataset_dict.get('metadata-point-of-contact')]
    for rp in dataset_dict.get('metadata-point-of-contact'):
        contact = {}
        if rp.get('individual-name'):
            contact['individual'] = {
                'name': rp.get('individual-name'),
                'email': rp.get('contact-info_email'),
                'country': rp.get('contact-info_country', 'Canada')
                }
        if rp.get('organisation-name'):
            contact['organization'] = {
                'name': rp.get('organisation-name'),
                'email': rp.get('contact-info_email'),
                'country': rp.get('contact-info_country', 'Canada')
                }
        contact['role'] = rp.get('role')
        point_of_contacts.append(contact)

    dataset_dict['contact']['pointOfContact'] = point_of_contacts

    dataset_dict['distribution'] = []
    for r in dataset_dict.get('resources'):
        res_obj = r
        res_obj['description_en'] = r.get('description')
        res_obj['description_fr'] = r.get('description')
        dataset_dict['distribution'].append(res_obj)

#    import pprint
#    log.debug('%s', pprint.pprint(dataset_dict))
    xml_string = render_template(dataset_dict, schema_local=schema_path)
    #  xml_string = '<xml></xml>'
    # with open('output.xml', 'w') as ff:
    #    ff.write(xml_string)
    r = toolkit.response
    r.content_type = 'application/xml'
    return(xml_string)
