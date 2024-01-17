from ckan.lib.cli import CkanCommand

class SiteMap(CkanCommand):
    '''Generate a sitemap xml file for use by search engine bots.

    Usage:
        sitemap create - create sitemap.xml file and write to /tmp/s3sitemap/

        sitemap clear  - remove sitemap file

    '''
    summary = __doc__.split('\n')[0]
    usage = __doc__
    max_args = 1
    min_args = 0

    def __init__(self, name):
        super(SiteMap, self).__init__(name)

    def _load_config(self):
        super(SiteMap, self)._load_config()

    def command(self):
        if not self.args:
            # default to printing help
            print(self.usage)
            return

        cmd = self.args[0]

        self._load_config()
        if cmd == 'create':
            self.create_sitemap()
        elif cmd == 'clear':
            self.rebuild(clear=True)
        else:
            print('Command %s not recognized' % cmd)

    def create_sitemap(self, upload_to_s3=True, page_size=1000, max_per_page=50000):
        # original function taken from https://github.com/GSA/ckanext-geodatagov/blob/ded11ffd3e4c97b8d418e45bfeeea0c3f4f10796/ckanext/geodatagov/commands.py
        log.info('sitemap is being generated...')

        # cron job
        # ckan --config=/srv/app/ckan.ini sitemap create
        # sql = '''Select id from package where id not in (select pkg_id from miscs_solr_sync); '''

        package_query = GeoPackageSearchQuery()

        count = package_query.get_count()
        log.info('%s records found', count)
        if not count:
            log.info('Nothing to process, exiting.')
            return

        start = 0
        filename_number = 1
        file_list = []

        # write to a temp file
        DIR_SITEMAP = "/tmp/s3sitemap/"
        if not os.path.exists(DIR_SITEMAP):
            os.makedirs(DIR_SITEMAP)

        fd, path = mkstemp(suffix=".xml",
                           prefix="sitemap-%s-" % filename_number,
                           dir=DIR_SITEMAP)
        # write header
        os.write(fd, '<?xml version="1.0" encoding="UTF-8"?>\n'.encode('utf-8'))
        os.write(fd, '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'.encode('utf-8'))
        file_list.append({
            'path': path,
            'filename_s3': "sitemap-%s.xml" % filename_number
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
            log.info('%i to %i of %i records done.', start + 1, min(start + page_size, count), count)
            start = start + page_size

            if start % max_per_page == 0 and \
                    x != int(math.ceil(old_div(count, page_size))):

                # write footer
                os.write(fd, '</urlset>\n'.encode('utf-8'))
                os.close(fd)

                log.info('done with %s.', path)

                filename_number = filename_number + 1
                fd, path = mkstemp(suffix=".xml",
                                   prefix="sitemap-%s-" % filename_number,
                                   dir=DIR_SITEMAP)
                # write header
                os.write(fd, '<?xml version="1.0" encoding="UTF-8"?>\n'.encode('utf-8'))
                os.write(fd, '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'.encode('utf-8'))

                file_list.append({
                    'path': path,
                    'filename_s3': "sitemap-%s.xml" % filename_number
                })

        # write footer
        os.write(fd, '</urlset>\n'.encode('utf-8'))
        os.close(fd)

        log.info('done with %s.', path)

        # if not upload_to_s3:
            # log.info('Skip upload and finish.')
        print('Done locally: File list\n{}'.format(json.dumps(file_list, indent=4)))
        return file_list

        # bucket_name = config.get('ckanext.geodatagov.aws_bucket_name')
        # bucket_path = config.get('ckanext.geodatagov.s3sitemap.aws_storage_path', '')
        # bucket = get_s3_bucket(bucket_name)
        #
        # fd, path = mkstemp(suffix=".xml",
        #                    prefix="sitemap-",
        #                    dir=DIR_SITEMAP)
        #
        # # write header
        # os.write(fd, '<?xml version="1.0" encoding="UTF-8"?>\n'.encode('utf-8'))
        # os.write(fd, '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'.encode('utf-8'))
        #
        # current_time = datetime.datetime.now().strftime('%Y-%m-%d')
        # for item in file_list:
        #     upload_to_key(bucket, item['path'],
        #                   bucket_path + item['filename_s3'])
        #     os.remove(item['path'])
        #
        #     # add to sitemap index file
        #     os.write(fd, '    <sitemap>\n'.encode('utf-8'))
        #     os.write(fd, ('        <loc>%s</loc>\n' % (
        #         config.get('ckanext.geodatagov.s3sitemap.aws_s3_url') + config.get(
        #             'ckanext.geodatagov.s3sitemap.aws_storage_path') + item['filename_s3'],
        #     )).encode('utf-8'))
        #     os.write(fd, ('        <lastmod>%s</lastmod>\n' % (
        #         current_time,
        #     )).encode('utf-8'))
        #     os.write(fd, '    </sitemap>\n'.encode('utf-8'))
        # os.write(fd, '</sitemapindex>\n'.encode('utf-8'))
        # os.close(fd)
        #
        # upload_to_key(bucket, path, bucket_path + 'sitemap.xml')
        # os.remove(path)
        #
        # log.info('Sitemap upload complete.')
