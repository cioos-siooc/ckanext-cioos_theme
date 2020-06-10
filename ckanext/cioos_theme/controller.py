import ckan.model as model
import ckan.plugins.toolkit as toolkit
import ckan.lib.base as base

from logging import getLogger

log = getLogger(__name__)

class CioosThemeController(toolkit.BaseController):

    # /formats
    def index(self):
        return base.render('formats/index.html')
