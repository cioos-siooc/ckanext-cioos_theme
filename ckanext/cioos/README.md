# ckanext.cioos (plugin `cioos`)

The CIOOS catalogue's domain logic for CKAN, independent of the theme
([ADR 0002](https://github.com/cioos-siooc/cioos-ckan-docker-base/blob/development-2-12/docs/adr/0002-domain-logic-in-ckanext-cioos.md)).
It is hosted in the ckanext-cioos_theme repository for now (see its
[README](../../README.md)) and does not depend on `ckanext.cioos_theme`.
Enable the `cioos` plugin alongside whichever theme plugin the deployment uses:

```
ckan.plugins = ... scheming_datasets fluent dcat ... cioos cioos_theme cioos_harvest ...
```

It requires ckanext-scheming (with the [CIOOS schema](https://github.com/cioos-siooc/cioos-siooc-schema)),
ckanext-fluent, ckanext-dcat and ckanext-spatial.

## What it provides

| Area | Where |
|---|---|
| Schema validators (`cioos_clean_and_populate_eovs`/`_ecvs`, `cioos_name_validator`, `cioos_tag_name_validator`, `cioos_is_valid_range`) | `validators.py` |
| Solr indexing (bilingual fields, temporal/vertical extents, ISO XML split by language) and search tuning (per-language `qf`, temporal and metadata-date filters) | `plugin.py` `before_dataset_index` / `before_dataset_search` |
| Facets (EOV, ECV, Responsible organisation, projects, …) | `plugin.py` `IFacets` |
| API output normalisation: JSON fields decoded, contacts grouped, organisation and group details merged into `package_show` / `package_search` | `plugin.py` `after_dataset_show` / `after_dataset_search` |
| `cioos_dcat` RDF profile and `dcat_dataset_show?frame=schemaorg` | `dcat/profiles.py`, `logic.py` |
| `spatial_query_geo` and `spatial_query_geo_package_search` actions (bbox or WKT polygon) | `logic.py` |
| Views: DataCite XML (`/dataset/<id>.dcxml`), Responsible organisations (`/dataset/resorg/<id>`), lineage (`/dataset/lineage/<id>`) | `views.py` |
| CLI: `ckan sitemap create`, `ckan package-relationships build/clear` | `cli.py` |
| Template helpers: licences, fully-qualified URIs, DOIs, JSON decoding, structured data | `helpers.py` |
| New organisations get a bilingual `title_translated` | `plugin.py` `IOrganizationController` |
| Request, login and abort logging for fail2ban (logger `ckanext.cioos_theme.plugin.auth`) | `plugin.py` `IAuthenticator` |

Solr field names, API output, JSON-LD, URLs and validator rules are a public
contract: change them deliberately, not as a side effect of refactoring.

## Configuration

| Key | Default | |
|---|---|---|
| `cioos.show_responsible_organizations_facet` | `True` | Show the Responsible organisation facet |
| `ckan.hide_organization_in_dataset_sidebar` | `false` | Also hides the Organization facet |
| `ckan.cioos.exclude_facets` | `[]` | JSON list of facets to hide |
| `ckan.cioos.doi_authority_url` | `https://doi.org/` | DataCite XML |
| `ckan.cioos.doi_prefix`, `ckan.cioos.datacite_org`, `ckan.cioos.datacite_test_mode` | | DataCite XML |

## Tests

From the cioos-ckan-docker-base repository, `just smoke-test` runs them in the
CKAN container. In a dev stack:

```bash
docker compose exec ckan bash -c "cd /srv/app/src_extensions/ckanext-cioos_theme && pytest ckanext/cioos/tests --ckan-ini=/srv/app/ckan.ini"
```

## Translations

`i18n/` holds the French catalogue (domain `ckanext-cioos`); see
[Translations](../../README.md#translations) in the repository README.
