from rdflib.namespace import Namespace, RDF, SKOS, RDFS
from ckanext.dcat.profiles import SchemaOrgProfile, CleanedURIRef, URIRefOrLiteral
from rdflib import URIRef, BNode, Literal
from ckanext.cioos_theme.plugin import load_json
from ckan.plugins import toolkit
from shapely.geometry import shape
import json
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
        log.debug('parties:%r', parties)
        for responsible_party in parties:
            if responsible_party['role'] == 'publisher':
                name = responsible_party.get('organisation-name')
                email = responsible_party.get('contact-info_email')
                url = responsible_party.get('contact-info_online-resource_url')
                identifier = responsible_party.get('organisation-uri', {})
                if isinstance(identifier, basestring):
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
            for s, p, o in self.g.triples((None, SCHEMA.contactType, None)):
                log.debug('%s, %s, %s', s, p, o)
                self.g.remove((s, None, None))

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
            items = [
                ('publisher_email', SCHEMA.email, ['contact_email', 'maintainer_email', 'author_email'], Literal),
                ('publisher_name', SCHEMA.name, ['contact_name', 'maintainer', 'author'], Literal),
            ]

            self._add_triples_from_dict(dataset_dict, contact_point, items)

    def graph_from_dataset(self, dataset_dict, dataset_ref):
        g = self.g

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

        # Publisher
        self.infer_publisher(dataset_dict)
        self._publisher_graph(dataset_ref, dataset_dict)


        # Temporal
        temporal_extent = load_json(dataset_dict.get('temporal-extent', {}))
        start = temporal_extent.get('begin')
        end = temporal_extent.get('end')
        if start or end:
            if start and end:
                self.g.add((dataset_ref, SCHEMA.temporalCoverage, Literal('%s/%s' % (start, end))))
            elif start:
                self._add_date_triple(dataset_ref, SCHEMA.temporalCoverage, start)
            elif end:
                self._add_date_triple(dataset_ref, SCHEMA.temporalCoverage, end)
