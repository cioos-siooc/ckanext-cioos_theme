from rdflib.namespace import Namespace, RDF, SKOS, RDFS
from ckanext.dcat.profiles import SchemaOrgProfile, CleanedURIRef, URIRefOrLiteral
from rdflib import URIRef, BNode, Literal
from ckanext.cioos_theme.helpers import load_json
from ckan.plugins import toolkit
from shapely.geometry import shape
import json
import re
import logging
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

DCT = Namespace("http://purl.org/dc/terms/")
DCAT = Namespace("http://www.w3.org/ns/dcat#")
SCHEMA = Namespace('http://schema.org/')

GEOJSON_IMT = 'https://www.iana.org/assignments/media-types/application/vnd.geo+json'

class CIOOSDCATProfile(SchemaOrgProfile):
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

        if isinstance(load_json(values['metadata-point-of-contact']), dict):
            parties = load_json(values['cited-responsible-party']) + [(load_json(values['metadata-point-of-contact']))]
        else:
            parties = load_json(values['cited-responsible-party']) + load_json(values['metadata-point-of-contact'])

        for responsible_party in parties:
            if 'publisher' in responsible_party['role']:
                name = responsible_party.get('organisation-name') or responsible_party.get('individual-name')
                email = responsible_party.get('contact-info_email')
                url = responsible_party.get('contact-info_online-resource_url')
                identifier = responsible_party.get('organisation-uri') or responsible_party.get('individual-uri', {})
                if isinstance(identifier, str):
                    uri = identifier
                else:
                    code = identifier.get('code')
                    codeSpace = identifier.get('code-space')
                    authority = identifier.get('authority')
                    version = identifier.get('version')
                    if code:
                        id_list = [authority, codeSpace, code, version]
                        uri = '/'.join(x.strip() for x in id_list if x.strip())
                    else:
                        uri = ''
            if name:
                break
        if(not name):
            org_details = values.get('organization')
            org_id = org_details.get('id')
            url = org_details.get('external_home_url')

            name = toolkit.h.scheming_language_text(load_json(org_details.get('title_translated', {})))
            uri_details = org_details.get('organization-uri', {})
            if uri_details:
                code = uri_details.get('code')
                codeSpace = uri_details.get('code-space')
                authority = uri_details.get('authority')
                version = uri_details.get('version')
                id_list = [authority, codeSpace, code, version]
                uri = '/'.join(x.strip() for x in id_list if x.strip())
            else:
                uri = '{0}/organization/{1}'.format(toolkit.config.get('ckan.site_url').rstrip('/'), org_id)

        values['publisher_name'] = name
        values['publisher_uri'] = uri
        values['publisher_email'] = email
        values['publisher_url'] = url

    def _basic_fields_graph(self, dataset_ref, dataset_dict):
        notes = dataset_dict.get('notes_translated', dataset_dict.get('notes'))

        # remove previous notes and replace with translated version
        for s, p, o in self.g.triples((None, RDF.type, SCHEMA.Dataset)):
            self.g.remove((s, SCHEMA.description, None))
            self.g.add((s, SCHEMA.description, Literal(toolkit.h.scheming_language_text(load_json(notes)))))

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

            # remove all previous contact points set by base profile as it is garbage.
            for s, p, o in self.g.triples((None, SCHEMA.contactType, Literal('customer service'))):
                self.g.remove((s, None, None))

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
            # items = [
            #     ('publisher_email', SCHEMA.email, ['contact_email', 'maintainer_email', 'author_email'], Literal),
            #     ('publisher_name', SCHEMA.name, ['contact_name', 'maintainer', 'author'], Literal),
            # ]
            #
            # self._add_triples_from_dict(dataset_dict, contact_point, items)

    def graph_from_dataset(self, dataset_dict, dataset_ref):
        g = self.g

        # Creators
        for responsible_party in load_json(dataset_dict['cited-responsible-party']):
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
                ind_names = name.split(' ')
                self.g.add((creator_details, RDF.type, SCHEMA.Person))
                self.g.add((creator_details, SCHEMA.name, Literal(name)))
                self.g.add((creator_details, SCHEMA.sameAs, Literal(ind_uri)))
                self.g.add((creator_details, SCHEMA.givenName, Literal(ind_names[0])))
                self.g.add((creator_details, SCHEMA.additionalName, Literal(','.join(ind_names[1:-1]))))
                self.g.add((creator_details, SCHEMA.familyName, Literal(ind_names[-1])))
                self.g.add((creator_details, SCHEMA.affiliation, Literal(org)))
            elif org:
                self.g.add((creator_details, RDF.type, SCHEMA.Organization))
                self.g.add((creator_details, SCHEMA.name, Literal(org)))
                self.g.add((creator_details, SCHEMA.sameAs, Literal(org_uri)))

            self.g.add((dataset_ref, SCHEMA.creator, creator_details))

        # change license over to "use-limitations"
        use_limitations_str = dataset_dict.get('use-limitations', '[]')
        dataset_name = dataset_dict.get('name')
        try:
            use_limitations = json.loads(use_limitations_str)
            if use_limitations:
                for use_limitation in use_limitations:
                    creative_work = BNode()
                    g.add((creative_work, RDF.type, SCHEMA.CreativeWork))
                    license_str = "License text for {}".format(dataset_name)
                    g.add((creative_work, SCHEMA.text, Literal(use_limitation)))
                    g.add((creative_work, SCHEMA.name, Literal(license_str)))
                    g.add((dataset_ref, SCHEMA.license, creative_work))
        # NB: this is accurate in Python 2.  In Python 3 JSON parsing
        #     exceptions are moved to json.JSONDecodeError
        except ValueError:
            pass

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
                gj = load_json(spatial_geom)
                bounds = shape(gj).bounds
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

        #### TODO: Remove schema:description and replace with this plus translation
        #('notes', SCHEMA.description, None, Literal),

        # Basic fields
        self._basic_fields_graph(dataset_ref, dataset_dict)

        # Catalog
        self._catalog_graph(dataset_ref, dataset_dict)

        # Publisher
        self.infer_publisher(dataset_dict)
        self._publisher_graph(dataset_ref, dataset_dict)

        # Distribution
        # add contentUrl
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

        # Temporal
        temporal_extent = load_json(dataset_dict.get('temporal-extent', {}))
        if (isinstance(temporal_extent, list)):
            temporal_extent = temporal_extent[0]
        start = temporal_extent.get('begin')
        end = temporal_extent.get('end')
        if start or end:
            if start and end:
                self.g.add((dataset_ref, SCHEMA.temporalCoverage, Literal('%s/%s' % (start, end))))
            elif start:
                self._add_date_triple(dataset_ref, SCHEMA.temporalCoverage, start)
            elif end:
                self._add_date_triple(dataset_ref, SCHEMA.temporalCoverage, end)
