# ckanext-cioos_theme

This repository ships two CKAN plugins for the CIOOS-SIOOC catalogue:

- **`cioos`** (package [`ckanext/cioos`](ckanext/cioos/README.md)): all
  non-visual catalogue logic: schema validators, search indexing and facets,
  API output, DCAT/Schema.org, DataCite XML, sitemaps, spatial query actions and
  the fail2ban request logging. It is independent of the theme ([ADR 0002](https://github.com/cioos-siooc/cioos-ckan-docker-base/blob/development-2-12/docs/adr/0002-domain-logic-in-ckanext-cioos.md))
  and is hosted here until it gets a repository of its own.
- **`cioos_theme`** (package `ckanext/cioos_theme`): the Legacy theme, i.e. the
  look and feel of the catalogue, its page layouts, the home, schema map and
  basic dataset pages, and the `ckan menu create` command that syncs the header
  menu from a regional WordPress site. Its templates use the `cioos` helpers
  (`h.cioos_load_json`, `h.cioos_get_license_def`, ...).

Never put non-visual logic in `ckanext/cioos_theme`, and never import
`ckanext.cioos_theme` from `ckanext.cioos`.

## Requirements

CKAN 2.12 with ckanext-scheming, ckanext-fluent, ckanext-dcat and
ckanext-spatial. In [cioos-ckan-docker-base](https://github.com/cioos-siooc/cioos-ckan-docker-base)
this repository is a submodule under `src/` and the image installs it; for a
manual install run `pip install -e .` and add `cioos cioos_theme` to
`ckan.plugins` (`cioos` first).

## Customizing the theme

The theme exposes 3 CSS custom properties that a deployment overrides with a
single CSS file, no fork or rebuild required:

| Token                  | Default   | Used for                             |
|------------------------|-----------|--------------------------------------|
| `--cioos-primary`      | `#52a79b` | links, buttons, nav highlight        |
| `--cioos-primary-dark` | `#3d7a71` | hover state of the above             |
| `--cioos-accent`       | `#fa7268` | secondary accent (citations, ERDDAP) |

Neutrals (`--cioos-neutral-0/100/300/600/900`), `--cioos-nav-bg` and
`--cioos-footer-bg` are defined in `:root` of
`ckanext/cioos_theme/public/cioos_theme.css` but are intentionally fixed across
regions.

`public/cioos_theme_overrides.css` is the last file of the `cioos_theme_css`
webassets bundle, so its `:root` declarations win. cioos-ckan-docker-base
bind-mounts its root `cioos_theme_overrides.css` over it; set the tokens there:

```css
:root {
  --cioos-primary:      #1b6ca8;
  --cioos-primary-dark: #14507c;
  --cioos-accent:       #f4a261;
}
```

then restart CKAN (webassets re-bundles with a new cache-buster).

When editing the theme CSS, use the existing tokens rather than new hex
literals; derive new shades with `color-mix()` on a token.

## Commands

```bash
ckan menu create --url https://<site>/wp-json/ra/menu/ --output /menu/<region>_menu_list.html
```

Builds the header menu template from a WordPress site exposing
`/wp-json/ra/menu/en` and `/wp-json/ra/menu/fr`; point `ckan.header_file_name`
at the output file.

## Translations

Each package has its own catalogue (`ckanext/<package>/i18n/`). For the theme,
`setup.cfg` holds the defaults:

```bash
python setup.py extract_messages
python setup.py update_catalog -l fr
# translate, then
python setup.py compile_catalog -l fr
```

For `cioos`, point the same commands at its package:

```bash
python setup.py extract_messages --input-dirs ckanext/cioos -o ckanext/cioos/i18n/ckanext-cioos.pot
python setup.py update_catalog -l fr -D ckanext-cioos -i ckanext/cioos/i18n/ckanext-cioos.pot -d ckanext/cioos/i18n
python setup.py compile_catalog -l fr -D ckanext-cioos -d ckanext/cioos/i18n
```
