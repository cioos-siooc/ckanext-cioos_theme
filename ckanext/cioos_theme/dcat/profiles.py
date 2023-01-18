from rdflib.namespace import Namespace, RDF, SKOS, RDFS
from ckanext.dcat.profiles import SchemaOrgProfile, CleanedURIRef, URIRefOrLiteral
from rdflib import URIRef, BNode, Literal
from ckanext.cioos_theme.helpers import load_json
from ckan.plugins import toolkit
from ckanext.dcat.utils import catalog_uri
from shapely.geometry import shape
import json
import re
import hashlib
import logging
from ckanext.dcat.utils import DCAT_EXPOSE_SUBCATALOGS, DCAT_CLEAN_TAGS

log = logging.getLogger(__name__)

DCT = Namespace("http://purl.org/dc/terms/")
DCAT = Namespace("http://www.w3.org/ns/dcat#")
ADMS = Namespace("http://www.w3.org/ns/adms#")
VCARD = Namespace("http://www.w3.org/2006/vcard/ns#")
FOAF = Namespace("http://xmlns.com/foaf/0.1/")
SCHEMA = Namespace('http://schema.org/')
TIME = Namespace('http://www.w3.org/2006/time')
LOCN = Namespace('http://www.w3.org/ns/locn#')
GSP = Namespace('http://www.opengis.net/ont/geosparql#')
OWL = Namespace('http://www.w3.org/2002/07/owl#')
SPDX = Namespace('http://spdx.org/rdf/terms#')

PROV = Namespace("http://www.w3.org/ns/prov#")

GEOJSON_IMT = 'https://www.iana.org/assignments/media-types/application/vnd.geo+json'

def dataset_uri(dataset_dict):
    uri = dataset_dict.get("uri")
    if not uri:
        uri = catalog_uri().rstrip('/') + '/dataset/' + dataset_dict['name']
    return uri

def resource_uri(resource_dict, dataset_dict):
    uri = resource_dict.get('uri')
    if not uri or uri == 'None':
        uri = '{0}/resource/{1}'.format(dataset_uri(dataset_dict).rstrip('/'),
                                        'ca-cioos-resource_' + hashlib.md5((resource_dict['name'] + ' ' + resource_dict['url']).encode('utf-8')).hexdigest())

    return uri

class CIOOSDCATProfile(SchemaOrgProfile):

    def parse_dataset(self, dataset_dict, dataset_ref):

        dataset_dict['extras'] = []
        dataset_dict['resources'] = []

        # Basic fields
        for key, predicate in (
                ('title', DCT.title),
                ('notes', DCT.description),
                ('version', OWL.versionInfo),
                ):
            value = self._object_value(dataset_ref, predicate)
            if value:
                dataset_dict[key] = value

        if not dataset_dict.get('version'):
            # adms:version was supported on the first version of the DCAT-AP
            value = self._object_value(dataset_ref, ADMS.version)
            if value:
                dataset_dict['version'] = value

        # # handle multilingule urls
        # value = self._object_value(dataset_ref, DCAT.landingPage)
        # value = load_json(value)
        # if value and isinstance(value, dict):
        #     dataset_dict['url'] = toolkit.h.scheming_language_text(value)

        # Tags
        # replace munge_tag to noop if there's no need to clean tags
        do_clean = toolkit.asbool(toolkit.config.get(DCAT_CLEAN_TAGS, False))
        tags_val = [munge_tag(tag) if do_clean else tag for tag in self._keywords(dataset_ref)]
        tags = [{'name': tag} for tag in tags_val]
        dataset_dict['tags'] = tags

        # Extras

        #  Simple values
        for key, predicate in (
                ('issued', DCT.issued),
                ('modified', DCT.modified),
                ('identifier', DCT.identifier),
                ('version_notes', ADMS.versionNotes),
                ('frequency', DCT.accrualPeriodicity),
                ('provenance', DCT.provenance),
                ('dcat_type', DCT.type),
                ):
            value = self._object_value(dataset_ref, predicate)
            if value:
                dataset_dict['extras'].append({'key': key, 'value': value})

        #  Lists
        for key, predicate, in (
                ('language', DCT.language),
                ('theme', DCAT.theme),
                ('alternate_identifier', ADMS.identifier),
                ('conforms_to', DCT.conformsTo),
                ('documentation', FOAF.page),
                ('related_resource', DCT.relation),
                ('has_version', DCT.hasVersion),
                ('is_version_of', DCT.isVersionOf),
                ('source', DCT.source),
                ('sample', ADMS.sample),
                ):
            values = self._object_value_list(dataset_ref, predicate)
            if values:
                dataset_dict['extras'].append({'key': key,
                                               'value': json.dumps(values)})

        # Contact details
        contact = self._contact_details(dataset_ref, DCAT.contactPoint)
        if not contact:
            # adms:contactPoint was supported on the first version of DCAT-AP
            contact = self._contact_details(dataset_ref, ADMS.contactPoint)

        if contact:
            for key in ('uri', 'name', 'email'):
                if contact.get(key):
                    dataset_dict['extras'].append(
                        {'key': 'contact_{0}'.format(key),
                         'value': contact.get(key)})

        # Publisher
        publisher = self._publisher(dataset_ref, DCT.publisher)
        for key in ('uri', 'name', 'email', 'url', 'type'):
            if publisher.get(key):
                dataset_dict['extras'].append(
                    {'key': 'publisher_{0}'.format(key),
                     'value': publisher.get(key)})

        # Temporal
        start, end = self._time_interval(dataset_ref, DCT.temporal)
        if start:
            dataset_dict['extras'].append(
                {'key': 'temporal_start', 'value': start})
        if end:
            dataset_dict['extras'].append(
                {'key': 'temporal_end', 'value': end})

        # Spatial
        spatial = self._spatial(dataset_ref, DCT.spatial)
        for key in ('uri', 'text', 'geom'):
            if spatial.get(key):
                dataset_dict['extras'].append(
                    {'key': 'spatial_{0}'.format(key) if key != 'geom' else 'spatial',
                     'value': spatial.get(key)})

        # Dataset URI (explicitly show the missing ones)
        dataset_uri = (str(dataset_ref)
                       if isinstance(dataset_ref, URIRef)
                       else '')
        dataset_dict['extras'].append({'key': 'uri', 'value': dataset_uri})

        # access_rights
        access_rights = self._access_rights(dataset_ref, DCT.accessRights)
        if access_rights:
            dataset_dict['extras'].append({'key': 'access_rights', 'value': access_rights})

        # License
        if 'license_id' not in dataset_dict:
            dataset_dict['license_id'] = self._license(dataset_ref)

        # change license over to "use-limitations"
        # use_limitations_str = dataset_dict.get('use-limitations', '[]')
        # dataset_name = dataset_dict.get('name')
        # try:
        #     use_limitations = json.loads(use_limitations_str)
        #     if use_limitations:
        #         for use_limitation in use_limitations:
        #             creative_work = BNode()
        #             g.add((creative_work, RDF.type, SCHEMA.CreativeWork))
        #             license_str = "License text for {}".format(dataset_name)
        #             g.add((creative_work, SCHEMA.text, Literal(use_limitation)))
        #             g.add((creative_work, SCHEMA.name, Literal(license_str)))
        #             g.add((dataset_ref, SCHEMA.license, creative_work))
        # NB: this is accurate in Python 2.  In Python 3 JSON parsing
        #     exceptions are moved to json.JSONDecodeError
        # except ValueError:
        #     pass


        # Source Catalog
        if toolkit.asbool(toolkit.config.get(DCAT_EXPOSE_SUBCATALOGS, False)):
            catalog_src = self._get_source_catalog(dataset_ref)
            if catalog_src is not None:
                src_data = self._extract_catalog_dict(catalog_src)
                dataset_dict['extras'].extend(src_data)

        # Resources
        for distribution in self._distributions(dataset_ref):

            resource_dict = {}

            #  Simple values
            for key, predicate in (
                    ('name', DCT.title),
                    ('description', DCT.description),
                    ('access_url', DCAT.accessURL),
                    ('download_url', DCAT.downloadURL),
                    ('issued', DCT.issued),
                    ('modified', DCT.modified),
                    ('status', ADMS.status),
                    ('license', DCT.license),
                    ):
                value = self._object_value(distribution, predicate)
                if value:
                    resource_dict[key] = value

            resource_dict['url'] = (self._object_value(distribution,
                                                       DCAT.downloadURL) or
                                    self._object_value(distribution,
                                                       DCAT.accessURL))
            #  Lists
            for key, predicate in (
                    ('language', DCT.language),
                    ('documentation', FOAF.page),
                    ('conforms_to', DCT.conformsTo),
                    ):
                values = self._object_value_list(distribution, predicate)
                if values:
                    resource_dict[key] = json.dumps(values)

            # rights
            rights = self._access_rights(distribution, DCT.rights)
            if rights:
                resource_dict['rights'] = rights

            # Format and media type
            normalize_ckan_format = toolkit.asbool(toolkit.config.get(
                'ckanext.dcat.normalize_ckan_format', True))
            imt, label = self._distribution_format(distribution,
                                                   normalize_ckan_format)

            if imt:
                resource_dict['mimetype'] = imt

            if label:
                resource_dict['format'] = label
            elif imt:
                resource_dict['format'] = imt

            # Size
            size = self._object_value_int(distribution, DCAT.byteSize)
            if size is not None:
                resource_dict['size'] = size

            # Checksum
            for checksum in self.g.objects(distribution, SPDX.checksum):
                algorithm = self._object_value(checksum, SPDX.algorithm)
                checksum_value = self._object_value(checksum, SPDX.checksumValue)
                if algorithm:
                    resource_dict['hash_algorithm'] = algorithm
                if checksum_value:
                    resource_dict['hash'] = checksum_value

            # Distribution URI (explicitly show the missing ones)
            resource_dict['uri'] = (str(distribution)
                                    if isinstance(distribution,
                                                  URIRef)
                                    else '')

            dataset_dict['resources'].append(resource_dict)

        if self.compatibility_mode:
            # Tweak the resulting dict to make it compatible with previous
            # versions of the ckanext-dcat parsers
            for extra in dataset_dict['extras']:
                if extra['key'] in ('issued', 'modified', 'publisher_name',
                                    'publisher_email',):

                    extra['key'] = 'dcat_' + extra['key']

                if extra['key'] == 'language':
                    extra['value'] = ','.join(
                        sorted(json.loads(extra['value'])))

        return dataset_dict

    '''
    CIOOS extensions to DCAT profile to add standard names and spatial to DCAT output based on the same extension by IOOS
    TODO: review https://www.w3.org/2015/spatial/wiki/ISO_19115_-_DCAT_-_Schema.org_mapping#Metadata_.28ISO_19115.29_-_Catalog_record_.28DCAT.29
      and make sure all mappings work
    '''

    def infer_publisher(self, values):
        name = ''
        uri = ''
        email = ''
        url = ''
        parties = []

        if isinstance(load_json(values.get('metadata-point-of-contact')), dict):
            parties = load_json(values.get('cited-responsible-party', '[]')) + [(load_json(values.get('metadata-point-of-contact', '{}')))]
        else:
            parties = load_json(values.get('cited-responsible-party', '[]')) + load_json(values.get('metadata-point-of-contact', '[]'))

        for responsible_party in parties:
            if 'publisher' in responsible_party['role']:
                name = responsible_party.get('organisation-name') or responsible_party.get('individual-name')
                email = responsible_party.get('contact-info_email')
                url = responsible_party.get('contact-info_online-resource_url')
                org_fquri = toolkit.h.cioos_get_fully_qualified_package_uri(responsible_party, 'organization-uri')
                if org_fquri:
                    org_fquri = org_fquri[0]
                ind_fquri = toolkit.h.cioos_get_fully_qualified_package_uri(responsible_party, 'individual-uri')
                if ind_fquri:
                    ind_fquri = ind_fquri[0]
                identifier = org_fquri or ind_fquri
                if isinstance(identifier, str):
                    uri = identifier
                else:
                    uri = ''
            if name:
                break
        if(not name):
            org_details = values.get('organization')
            org_id = org_details.get('id')
            url = org_details.get('external_home_url')

            name = toolkit.h.scheming_language_text(load_json(org_details.get('title_translated', {})))
            qualified_uri = toolkit.h.cioos_get_fully_qualified_package_uri(org_details, 'organization-uri')
            if qualified_uri:
                qualified_uri = qualified_uri[0]
            ckan_page_uri = '{0}/organization/{1}'.format(toolkit.config.get('ckan.site_url').rstrip('/'), org_id)
            uri = qualified_uri or ckan_page_uri

        values['publisher_name'] = name
        values['publisher_uri'] = uri
        values['publisher_email'] = email
        values['publisher_url'] = url

    def _basic_fields_graph(self, dataset_ref, dataset_dict):


        items = [
            ('identifier', SCHEMA.identifier, None, Literal),
            ('issued', SCHEMA.datePublished, ['metadata_created'], Literal),
            ('modified', SCHEMA.dateModified, ['metadata_modified'], Literal),
            ('license', SCHEMA.license, ['license_url', 'license_title'], Literal),
        ]
        self._add_triples_from_dict(dataset_dict, dataset_ref, items)

        items = [
            ('issued', SCHEMA.datePublished, ['metadata_created'], Literal),
            ('modified', SCHEMA.dateModified, ['metadata_modified'], Literal),
        ]

        self._add_date_triples_from_dict(dataset_dict, dataset_ref, items)

        # Dataset URL
        dataset_url = toolkit.h.url_for('dataset.read',
                              id=dataset_dict['name'],
                              _external=True)
        self.g.add((dataset_ref, SCHEMA.url, Literal(dataset_url)))


        default_language = dataset_dict.get('metadata-language', 'en')
        notes = dataset_dict.get('notes_translated', dataset_dict.get('notes'))
        title = dataset_dict.get('title_translated', dataset_dict.get('title'))

        # remove previous notes and replace with translated version
        for s, p, o in self.g.triples((None, RDF.type, SCHEMA.Dataset)):
            self.g.remove((s, SCHEMA.description, None))
            notes_obj = load_json(notes)
            if isinstance(notes_obj, dict):
                for lang in notes_obj:
                    self.g.add((s, SCHEMA.description, Literal(notes_obj[lang], lang=lang)))
            else:
                self.g.add((s, SCHEMA.name, Literal(notes_obj, lang=default_language)))

            self.g.remove((s, SCHEMA.name, None))
            title_obj = load_json(title)
            if isinstance(title_obj, dict):
                for lang in title_obj:
                    self.g.add((s, SCHEMA.name, Literal(title_obj[lang], lang=lang)))
            else:
                self.g.add((s, SCHEMA.name, Literal(title_obj, lang=default_language)))

    def _catalog_graph(self, dataset_ref, dataset_dict):
        # remove all previous catalogs set by base profile as it is garbage.
        for s, p, o in self.g.triples((None, RDF.type, SCHEMA.DataCatalog)):
            self.g.remove((s, None, None))
        self.g.remove((dataset_ref, SCHEMA.includedInDataCatalog, None))

        data_catalog = BNode()
        self.g.add((dataset_ref, SCHEMA.includedInDataCatalog, data_catalog))
        self.g.add((data_catalog, RDF.type, SCHEMA.DataCatalog))
        self.g.add((data_catalog, SCHEMA.name, Literal(toolkit.h.scheming_language_text(load_json(toolkit.config.get('ckan.site_title'))))))
        self.g.add((data_catalog, SCHEMA.description, Literal(toolkit.h.scheming_language_text(load_json(toolkit.config.get('ckan.site_description'))))))
        self.g.add((data_catalog, SCHEMA.url, Literal(toolkit.config.get('ckan.site_url'))))

    def _publisher_graph(self, dataset_ref, dataset_dict):
        if any([
            self._get_dataset_value(dataset_dict, 'publisher_uri'),
            self._get_dataset_value(dataset_dict, 'publisher_name'),
        ]):

            publisher_uri = dataset_dict.get('publisher_uri')

            if publisher_uri:
                publisher_details = CleanedURIRef(publisher_uri)
            else:
                # No organization nor publisher_uri
                publisher_details = BNode()

            self.g.remove((dataset_ref, SCHEMA.publisher, None))
            self.g.remove((publisher_details, SCHEMA.name, None))
            self.g.remove((publisher_details, SCHEMA.contactPoint, None))

            # add publisher
            self.g.add((publisher_details, RDF.type, SCHEMA.Organization))
            self.g.add((dataset_ref, SCHEMA.publisher, publisher_details))

            publisher_name = dataset_dict.get('publisher_name')
            self.g.add((publisher_details, SCHEMA.name, Literal(publisher_name)))

            contact_point = BNode()
            self.g.add((contact_point, RDF.type, SCHEMA.ContactPoint))

            self.g.add((publisher_details, SCHEMA.contactPoint, contact_point))

            self.g.add((contact_point, SCHEMA.contactType, Literal('Publisher')))

            publisher_url = dataset_dict.get('publisher_url')
            self.g.add((contact_point, SCHEMA.url, Literal(publisher_url)))

    def _resources_graph(self, dataset_ref, dataset_dict):
        g = self.g
        for resource_dict in dataset_dict.get('resources', []):
            distribution = URIRef(resource_uri(resource_dict, dataset_dict))
            g.add((dataset_ref, SCHEMA.distribution, distribution))
            g.add((distribution, RDF.type, SCHEMA.DataDownload))
            self._distribution_graph(distribution, resource_dict)

    def _tags_graph(self, dataset_ref, dataset_dict):
        keywords = dataset_dict.get('keywords')
        for lang in keywords:
            for tag in keywords[lang]:
                self.g.add((dataset_ref, SCHEMA.keywords, Literal(tag, lang=lang)))

    def graph_from_dataset(self, dataset_dict, dataset_ref):

        g = self.g

        self.g.remove((dataset_ref, None, None))

        # Namespaces
        self._bind_namespaces()

        # change @id to point to jsonld document
        dataset_ref = URIRef(dataset_uri(dataset_dict) + '.jsonld')
        g.add((dataset_ref, RDF.type, SCHEMA.Dataset))

        self.g.namespace_manager.bind('@vocab', SCHEMA, replace=True)

        # remove all previous contact points set by base profile as it is garbage.
        for s, p, o in self.g.triples((None, SCHEMA.contactPoint, None)):
            self.g.remove((s, None, None))
        for s, p, o in g.triples((None, RDF.type, SCHEMA.ContactPoint)):
            self.g.remove((s, None, None))

        for mp in load_json(dataset_dict.get('metadata-point-of-contact','[]')):
            name = mp.get('individual-name')
            org = mp.get('organisation-name')
            email = mp.get('contact-info_email')
            roles = mp.get('role')
            url = mp.get('contact-info_online-resource_url')
            ind_identifier = mp.get('individual-uri', {}).get('code')
            org_identifier = mp.get('organisation-uri', {}).get('code')
            uri = ind_identifier or org_identifier
            if uri:
                contact_details = CleanedURIRef(uri)
            else:
                contact_details = BNode()

            if name:
                self.g.add((contact_details, RDF.type, VCARD.Individual))
                self.g.add((dataset_ref, DCAT.contactPoint, contact_details))
                self.g.add((contact_details, VCARD.fn, Literal(name)))
                self.g.add((contact_details, VCARD.hasEmail, Literal('mailto:' + email)))
                self.g.add((contact_details, VCARD.role, Literal(roles)))
                self.g.add((contact_details, VCARD.org, Literal(org)))
            else:
                self.g.add((contact_details, RDF.type, VCARD.Organization))
                self.g.add((dataset_ref, DCAT.contactPoint, contact_details))
                self.g.add((contact_details, VCARD.fn, Literal(org)))
                self.g.add((contact_details, VCARD.hasEmail, Literal('mailto:' + email)))
                self.g.add((contact_details, VCARD.role, Literal(roles)))

        # Creators
        for responsible_party in load_json(dataset_dict.get('cited-responsible-party', '[]')):
            if 'publisher' in responsible_party['role']:
                continue

            name = responsible_party.get('individual-name')
            org = responsible_party.get('organisation-name')
            email = responsible_party.get('contact-info_email')
            url = responsible_party.get('contact-info_online-resource_url')
            ind_identifier = responsible_party.get('individual-uri', {})
            if isinstance(ind_identifier, str):
                ind_uri = ind_identifier
            else:
                code = ind_identifier.get('code')
                codeSpace = ind_identifier.get('code-space')
                authority = ind_identifier.get('authority')
                version = ind_identifier.get('version')
                if code:
                    id_list = [authority, codeSpace, code, version]
                    ind_uri = '/'.join(x.strip() for x in id_list if x.strip())
                else:
                    ind_uri = ''
            org_identifier = responsible_party.get('organisation-uri', {})
            if isinstance(org_identifier, str):
                org_uri = org_identifier
            else:
                code = org_identifier.get('code')
                codeSpace = org_identifier.get('code-space')
                authority = org_identifier.get('authority')
                version = org_identifier.get('version')
                if code:
                    id_list = [authority, codeSpace, code, version]
                    org_uri = '/'.join(x.strip() for x in id_list if x.strip())
                else:
                    org_uri = ''
            if ind_uri:
                creator_details = CleanedURIRef(uri)
            elif org_uri:
                creator_details = CleanedURIRef(uri)
            else:
                creator_details = BNode()
            if name:
                if ',' in name:
                    ind_names = name.split(',')
                    names = ind_names[1].split()
                    given = names[0].strip()
                    additional = ','.join(names[1:-1])
                    family = ind_names[0]
                else:
                    ind_names = name.split(' ')
                    given = ind_names[0]
                    additional = ','.join(ind_names[1:-1])
                    family = ind_names[-1]

                self.g.add((creator_details, RDF.type, SCHEMA.Person))
                self.g.add((creator_details, SCHEMA.name, Literal(name)))
                self.g.add((creator_details, SCHEMA.sameAs, Literal(ind_uri)))
                self.g.add((creator_details, SCHEMA.givenName, Literal(given)))
                self.g.add((creator_details, SCHEMA.additionalName, Literal(additional)))
                self.g.add((creator_details, SCHEMA.familyName, Literal(family)))
                self.g.add((creator_details, SCHEMA.affiliation, Literal(org)))
            elif org:
                self.g.add((creator_details, RDF.type, SCHEMA.Organization))
                self.g.add((creator_details, SCHEMA.name, Literal(org)))
                self.g.add((creator_details, SCHEMA.sameAs, Literal(org_uri)))

            self.g.add((dataset_ref, SCHEMA.creator, creator_details))

        # variableMeasured
        try:
            std_names = dataset_dict.get('cf_standard_names')
        except Exception:
            # TODO: add logging, etc
            pass

        if (std_names is not None and
           hasattr(std_names, '__iter__')):
            for standard_name in sorted(std_names):
                g.add((dataset_ref, SCHEMA.variableMeasured,
                      Literal(standard_name)))

        for variable in dataset_dict.get('variable-measured', []):
            self.g.add((dataset_ref, SCHEMA.variableMeasured, Literal(variable)))



        schema = toolkit.h.scheming_get_dataset_schema('dataset')
        fields = schema['dataset_fields']
        field = toolkit.h.scheming_field_by_name(fields, 'eov')
        choices = toolkit.h.scheming_field_choices(field)
        for eov in dataset_dict.get('eov', []):
            eov_node = BNode()
            g.add((dataset_ref, SCHEMA.variableMeasured, eov_node))
            self.g.add((eov_node, RDF.type, SCHEMA.PropertyValue))
            self.g.add((eov_node, SCHEMA.name,
                        Literal(
                            toolkit.h.scheming_choices_label(choices, eov)
                        )
                        ))
            # self.g.add((eov_node, SCHEMA.description, ))
            # self.g.add((eov_node, SCHEMA.propertyID, ))


        spatial_uri = dataset_dict.get('spatial_uri')
        spatial_text = dataset_dict.get('spatial_text')

        if spatial_uri:
            spatial_ref = URIRef(spatial_uri)
        else:
            spatial_ref = BNode()

        if spatial_text:
            g.add((dataset_ref, DCT.spatial, spatial_ref))
            g.add((spatial_ref, RDF.type, DCT.Location))
            g.add((spatial_ref, RDFS.label, Literal(spatial_text)))

        spatial_uri = dataset_dict.get('spatial_uri')
        spatial_text = dataset_dict.get('spatial_text')
        spatial_geom = dataset_dict.get('spatial')

        if spatial_uri or spatial_text or spatial_geom:
            if spatial_uri:
                spatial_ref = CleanedURIRef(spatial_uri)
            else:
                spatial_ref = BNode()

        g.add((spatial_ref, RDF.type, SCHEMA.Place))
        g.add((dataset_ref, SCHEMA.spatialCoverage, spatial_ref))

        if spatial_text:
            g.add((spatial_ref, SKOS.prefLabel, Literal(spatial_text)))

        if spatial_geom:
            try:
                geo_json = load_json(spatial_geom)
                bounds = shape(geo_json).bounds
                bbox = [str(bound) for bound in bounds[1::-1] + bounds[:1:-1]]
            except Exception:
                pass
            else:
                bbox_str = ' '.join(bbox)
                geo_shape = BNode()
                g.add((geo_shape, RDF.type, SCHEMA.GeoShape))
                g.add((geo_shape, SCHEMA.box, Literal(bbox_str)))
                # Add bounding box element
                g.add((spatial_ref, SCHEMA.geo, geo_shape))

        # Basic fields
        self._basic_fields_graph(dataset_ref, dataset_dict)

        # Catalog
        self._catalog_graph(dataset_ref, dataset_dict)

        # Publisher
        self.infer_publisher(dataset_dict)
        self._publisher_graph(dataset_ref, dataset_dict)

        # Tags
        self._tags_graph(dataset_ref, dataset_dict)

        if dataset_dict.get('measurement-techniques'):
            self.g.add((dataset_ref, SCHEMA.measurementTechnique,
                        Literal('. '.join(dataset_dict['measurement-techniques']))
                        ))

        organization = dataset_dict.get("organization")
        if organization:
            fquri = toolkit.h.cioos_get_fully_qualified_package_uri(
                organization,
                'organization-uri'
            )
            if fquri:
                fquri = fquri[0]
            org_uri = (fquri or
                       organization.get('external_home_url') or
                       toolkit.h.url_for('organization.read',
                                         id=organization['name'],
                                         _external=True)
                       )
            provider_ref = URIRef(org_uri)
            g.add((provider_ref, RDF.type, SCHEMA.Organization))
            g.add((provider_ref, SCHEMA.legalName, Literal(organization['title'])))
            g.add((provider_ref, SCHEMA.name, Literal(organization['display_name'])))
            if organization.get('external_home_url'):
                g.add((provider_ref, SCHEMA.url, Literal(organization['external_home_url'])))
            for lang in organization.get('image_url_translated', {}):
                g.add((provider_ref, SCHEMA.logo,
                       Literal(organization['image_url_translated'][lang], lang=lang)
                       ))
            self.g.add((dataset_ref, SCHEMA.provider, provider_ref))

        # removed this section as maintaining chain of custody info for each catalogue 
        # is difficult and probably not very useful
        # for provider in dataset_dict.get('provider', []):
        #     self.g.add((dataset_ref, SCHEMA.provider, Literal(provider)))

        # Resources
        if dataset_dict.get('resources'):
            for s, p, o in g.triples((None, RDF.type, SCHEMA.DataDownload)):
                self.g.remove((s, None, None))
            self.g.remove((dataset_ref, SCHEMA.distribution, None))
        self._resources_graph(dataset_ref, dataset_dict)

        # Add contentUrl to Distribution
        for s, p, o in self.g.triples((None, RDF.type, SCHEMA.DataDownload)):
            url = self.g.value(s, SCHEMA.url, None)
            g.add((s, SCHEMA.contentUrl, Literal(url)))

        # Identifier
        unique_identifiers = dataset_dict.get('unique-resource-identifier-full', {})
        if unique_identifiers:
            self.g.remove((dataset_ref, SCHEMA.identifier, None))
            for unique_identifier in unique_identifiers:
                if 'doi.org' in unique_identifier.get('authority', '') or not unique_identifier.get('authority'):
                    doi = re.sub(r'^http.*doi\.org/', '', unique_identifier['code'], flags=re.IGNORECASE)  # strip https://doi.org/ and the like
                    if doi and re.match(r'^10.\d{4,9}\/[-._;()/:A-Z0-9]+$', doi, re.IGNORECASE):
                        identifier = BNode()
                        g.add((dataset_ref, SCHEMA.identifier, identifier))
                        self.g.add((identifier, RDF.type, SCHEMA.PropertyValue))
                        self.g.add((identifier, SCHEMA.propertyID, Literal("https://registry.identifiers.org/registry/doi")))
                        self.g.add((identifier, SCHEMA.name, Literal("DOI: %s" % doi)))
                        self.g.add((identifier, SCHEMA.value, Literal("doi:%s" % doi)))
                        self.g.add((identifier, SCHEMA.url, Literal("https://doi.org/%s" % doi)))

                        uri = dataset_uri(dataset_dict)
                        self.g.add((dataset_ref, DCAT.previousVersion, URIRefOrLiteral(uri)))
                        self.g.add((dataset_ref, PROV.wasRevisionOf, URIRefOrLiteral(uri)))
        else:
            uri = dataset_uri(dataset_dict)
            g.add((dataset_ref, SCHEMA.identifier, Literal('%s' % uri)))

        # dataset @id
        # this should add a new id to the dataset graph but I can't remove the existing id
        # which is set to the db pk guid
        # uri = dataset_uri(dataset_dict)
        # g.add((dataset_ref, SCHEMA['@id'],  Literal('%s' % uri+'.jsonld')))

        metadata_dates = [x['value'] for x in load_json(dataset_dict.get('metadata-reference-date', []))]
        metadata_dates.sort(reverse=True)
        version_date = ''
        if metadata_dates:
            version_date = metadata_dates[0]
        version = dataset_dict.get('version', version_date or '1')

        # Add version, default latest metadata_reference_date
        g.add((dataset_ref, SCHEMA.version, Literal('%s' % version))),

        # Temporal
        temporal_extent = load_json(dataset_dict.get('temporal-extent', {}))
        if (isinstance(temporal_extent, list)):
            temporal_extent = temporal_extent[0]
        start = temporal_extent.get('begin')
        end = temporal_extent.get('end')
        if start or end:
            if start:
                self.g.add((dataset_ref, SCHEMA.temporalCoverage, Literal('%s/%s' % (start, end or '..'))))
            elif end:
                self._add_date_triple(dataset_ref, SCHEMA.temporalCoverage, Literal('../%s' % (end)))

        # About
        # this section could capture platform or instrument linkages
        acquisition_information = load_json(dataset_dict.get('acquisition-information', {}))
        if acquisition_information:
            platform = acquisition_information.get('platform', {})
            instruments = platform.get('instrument', [])
            scope = acquisition_information.get('scope', {})
            scope_level = scope.get('level', {})
            scope_desc = scope.get('description', {})

            aboutRef = BNode()
            g.add(dataset_ref, SCHEMA.about, aboutRef)
            g.add((aboutRef, RDF.type, SCHEMA.Event))
            g.add((aboutRef, SCHEMA.name, Literal(scope_level)))
            g.add((aboutRef, SCHEMA.description, Literal(scope_desc)))

            actionRef = BNode()
            g.add((actionRef, RDF.type, SCHEMA.Action))

            instrumentRef = BNode()
            g.add((instrumentRef, RDF.type, SCHEMA.Thing))
            g.add((instrumentRef, SCHEMA.name, Literal('Platform')))
            g.add((instrumentRef, SCHEMA.description, Literal(platform.get('description'))))
            g.add((instrumentRef, SCHEMA.url, Literal(platform.get('identifier'))))

            g.add((actionRef, SCHEMA.instrument, instrumentRef))
            g.add((actionRef, SCHEMA.name, Literal(scope_level)))
            g.add((aboutRef, SCHEMA.potentialAction, actionRef))

            for instrument in instruments:
                actionRef = BNode()
                g.add((actionRef, RDF.type, SCHEMA.Action))

                instrumentRef = BNode()
                g.add((instrumentRef, RDF.type, SCHEMA.Thing))
                g.add((instrumentRef, SCHEMA.name, instrument.get('type')))
                g.add((instrumentRef, SCHEMA.description, Literal(instrument.get('description'))))
                g.add((instrumentRef, SCHEMA.url, Literal(instrument.get('identifier'))))

                g.add((actionRef, SCHEMA.instrument, instrumentRef))
                g.add((actionRef, SCHEMA.name, Literal(scope_level)))
                g.add((aboutRef, SCHEMA.potentialAction, actionRef))
