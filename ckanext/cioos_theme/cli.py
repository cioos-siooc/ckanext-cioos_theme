import click
from ckan import model
from ckan.logic import get_action, ValidationError
import ckan.lib.search
from ckanext.cioos_theme.util.package_relationships import get_relationships_from_schema
import re
import os
import math
from past.utils import old_div
from ckan.plugins.toolkit import config
import json
import datetime
from ckanext.cioos_theme.helpers import load_json
from ckanext.cioos_theme.util.search import GeoPackageSearchQuery


def get_commands():
    return [
        sitemap,
        package_relationships,
        menu
    ]


###########################################################################
# Site Map
###########################################################################
@click.group()
def sitemap():
    '''Generate a sitemap xml file for use by search engine bots.'''
    pass


@sitemap.command()
@click.argument(u"page_size", default=1000)
@click.argument(u"max_per_page", default=50000)
def create(page_size, max_per_page):
    ''' Create sitemap.xml '''
    # original function taken from https://github.com/GSA/ckanext-geodatagov/blob/ded11ffd3e4c97b8d418e45bfeeea0c3f4f10796/ckanext/geodatagov/commands.py
    click.echo('sitemap is being generated...')

    # cron job
    # ckan --config=/srv/app/ckan.ini sitemap create
    # sql = '''Select id from package where id not in (select pkg_id from miscs_solr_sync); '''

    package_query = GeoPackageSearchQuery()

    count = package_query.get_count()
    click.echo('%s records found' % count)
    if not count:
        click.echo('Nothing to process, exiting.')
        return

    start = 0
    filename_number = 1
    file_list = []

    # write to a temp file
    DIR_SITEMAP = "/srv/app/src/ckan/ckan/public/sitemap/"
    if not os.path.exists(DIR_SITEMAP):
        os.makedirs(DIR_SITEMAP)
    path = "%ssitemap-%s.xml" % (DIR_SITEMAP, filename_number)
    fd = os.open(path, os.O_WRONLY|os.O_CREAT|os.O_TRUNC)

    # write header
    os.write(fd, '<?xml version="1.0" encoding="UTF-8"?>\n'.encode('utf-8'))
    os.write(fd, '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'.encode('utf-8'))
    file_list.append({
        'path': path,
        'filename_s3': "/sitemap/sitemap-%s.xml" % filename_number
    })

    for x in range(0, int(math.ceil(old_div(count, page_size))) + 1):
        pkgs = package_query.get_paginated_entity_name_modtime(
            max_results=page_size, start=start
        )

        for pkg in pkgs:
            os.write(fd, '    <url>\n'.encode('utf-8'))
            os.write(fd, ('        <loc>%s</loc>\n' % (
                '%s/dataset/%s' % (config.get('ckan.site_url'), pkg.get('name')),
            )).encode('utf-8'))
            os.write(fd, ('        <lastmod>%s</lastmod>\n' % (
                pkg.get('metadata_modified').strftime('%Y-%m-%d'),
            )).encode('utf-8'))
            os.write(fd, '    </url>\n'.encode('utf-8'))
        click.echo('%i to %i of %i records done.' % (start + 1, min(start + page_size, count), count))
        start = start + page_size

        if start % max_per_page == 0 and \
                x != int(math.ceil(old_div(count, page_size))):

            # write footer
            os.write(fd, '</urlset>\n'.encode('utf-8'))
            os.close(fd)

            click.echo('done with %s.', path)

            filename_number = filename_number + 1
            path = "%ssitemap-%s.xml" % (DIR_SITEMAP, filename_number)
            fd = os.open(path, os.O_WRONLY|os.O_CREAT|os.O_TRUNC)

            # write header
            os.write(fd, '<?xml version="1.0" encoding="UTF-8"?>\n'.encode('utf-8'))
            os.write(fd, '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'.encode('utf-8'))

            file_list.append({
                'path': path,
                'filename_s3': "/sitemap/sitemap-%s.xml" % filename_number
            })

    # write footer
    os.write(fd, '</urlset>\n'.encode('utf-8'))
    os.close(fd)

    click.echo('done with %s.' % path)

    # if not upload_to_s3:
        # log.info('Skip upload and finish.')
        # click.echo('Done locally: File list\n{}'.format(json.dumps(file_list, indent=4)))
        # return file_list

    # bucket_name = config.get('ckanext.geodatagov.aws_bucket_name')
    # bucket_path = config.get('ckanext.geodatagov.s3sitemap.aws_storage_path', '')
    # bucket = get_s3_bucket(bucket_name)

    path = DIR_SITEMAP + "sitemap.xml"
    fd = os.open(path, os.O_WRONLY|os.O_CREAT)

    # write header
    os.write(fd, '<?xml version="1.0" encoding="UTF-8"?>\n'.encode('utf-8'))
    os.write(fd, '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'.encode('utf-8'))

    current_time = datetime.datetime.now().strftime('%Y-%m-%d')
    for item in file_list:
        # upload_to_key(bucket, item['path'],
        #               bucket_path + item['filename_s3'])
        # os.remove(item['path'])

        # add to sitemap index file
        os.write(fd, '    <sitemap>\n'.encode('utf-8'))
        os.write(fd, ('        <loc>%s%s</loc>\n' % (config.get('ckan.site_url'), item['filename_s3'],
        )).encode('utf-8'))
        os.write(fd, ('        <lastmod>%s</lastmod>\n' % (
            current_time,
        )).encode('utf-8'))
        os.write(fd, '    </sitemap>\n'.encode('utf-8'))
    os.write(fd, '</sitemapindex>\n'.encode('utf-8'))
    os.close(fd)

    click.echo('Sitemap complete.')


###########################################################################
# Package Relationships
###########################################################################
@click.group(u"package-relationships")
def package_relationships():
    '''Performs package relationship related operations.'''
    pass


@package_relationships.command()
@click.argument('dataset_id_or_name', default=None, required=False)
def clear(dataset_id_or_name):
    '''remove package relationships for a dataset_name if given, if not then
    remove package relationships for all datasets'''
    rebuild(dataset_id_or_name, clear=True)


@package_relationships.command()
@click.argument('dataset_id_or_name', default=None, required=False)
def build(dataset_id_or_name):
    rebuild(dataset_id_or_name, clear=False)

def rebuild(dataset_id_or_name=None, clear=False):
    '''create package relationships for a dataset_name if given, if not then
    rebuild package relationships for all datasets'''
    from ckan.lib.search import rebuild, commit

    # cron job
    # ckan --config=/srv/app/ckan.ini package_relationships rebuild [dataset name]

    dataset_id_arg = dataset_id_or_name

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

        rels_from_schema = get_relationships_from_schema(load_json(package_dict.get('aggregation-info', [])), package_dict['name'])

        # get existing package relationships where this package is the
        # subject (from)
        try:
            existing_rels = get_action('package_relationships_list')(
                data_dict={
                    'id': package_dict['id']
                }
            )
        except Exception as e:
            click.echo('No package relationship found for dataset %s: %r'
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
                click.echo('Deleted package relationship %s %s %s' % (d['subject'],
                           d['type'], d['object']))
            except Exception as e:
                click.echo('Failed to delete package relationship for dataset %s: %r' % (package_dict['id'], e))

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
                click.echo('Created package relationship %s %s %s' % (a['subject'],
                           a['type'], a['object']))
            except Exception as e:
                click.echo('Failed to create package relationship for dataset %s: %r' % (package_dict['id'], e))

        to_index.append(package_dict['id'])

    click.echo('Indexing datasets: %r' % to_index)
    # remove duplicates
    to_index = list(dict.fromkeys(to_index))
    # trigger indexing of datasets involved in relationships
    for target_package_id in to_index:
        ckan.lib.search.rebuild(target_package_id)


###########################################################################
# Sync Menu from wordpress
###########################################################################
@click.group()
def menu():
    '''Generate a html menu snipit from an existing wordpress site'''
    pass


@menu.command()
@click.option(u"--url", default=lambda: (config.get('ckan.site_home_url', config.get('ckan.site_home')) + '/wp-json/ra/menu/').replace("//", "/"), help="[ckan.site_home_url|ckan.site_home]/wp-json/ra/menu/")
@click.option(u"--output", default='/menu/menu_list.html', help="path to menu list output file")
@click.option(u"--echo", default=False, help="echo file output to stdout")
def create(url, output, echo):
    '''create menu file from wordpress site'''

    import requests

    def process_list_item(menu_item, indent=2, parent_class=''):
        indent_str = ' ' * indent
        indent_str2 = ' ' * (indent + 2)
        out = ''
        if menu_item.get('sub_menu_items'):
            out += indent_str + '<li class="menu-item menu-item-has-children %s">\n' % parent_class
        else:
            out += indent_str + '<li class="menu-item">\n'
        out += indent_str2 + '<a href="%s"><span class="mega-indicator">%s</span></a>\n' % (menu_item['url'], menu_item['title'])
        if menu_item.get('sub_menu_items'):
            out += indent_str2 + '<ul class="sub-menu">\n'
            for sub_menu_item in menu_item['sub_menu_items']:
                out += process_list_item(sub_menu_item, indent + 4)
            out += indent_str2 + '</ul>\n'
        out += indent_str + '</li>\n'
        return out

    r_en = requests.get(url + 'en')
    r_fr = requests.get(url + 'fr')

    out_en = ''
    for menu_item in json.loads(r_en.content):
        out_en += process_list_item(menu_item, indent=4, parent_class='menu-parent')

    out_fr = ''
    for menu_item in json.loads(r_fr.content):
        out_fr += process_list_item(menu_item, indent=4, parent_class='menu-parent')

    content = "{%- if h.lang() == 'en' -%}\n"
    content += out_en
    content += "  {% else %}\n"
    content += out_fr
    content += "  {% endif %}\n"

    # Write the file to disk
    with open('ckanext-cioos_theme/ckanext/cioos_theme/templates' + output, 'w') as file:
        file.write(content)

    if echo:
        print(content)
