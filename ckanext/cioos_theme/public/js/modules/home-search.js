ckan.module('home-search', function (jQuery) {

  return {
    initialize: function () {
      $.proxyAll(this, /_on/);
      this.el.ready(this._onReady);
    },

    _onReady: function () {
      var form = this.el.find('form.home-search-form');
      if (!form.length) {
        form = this.el.closest('form.home-search-form');
      }
      this.form = form;

      // Prevent date-query module from auto-submitting on the home page.
      // The date-query module calls form.submit() on date change. We
      // intercept that by temporarily blocking submit until the user
      // explicitly clicks the search button.
      this._blockAutoSubmit = true;

      var self = this;
      form.on('submit', function (e) {
        if (self._blockAutoSubmit && e.originalEvent === undefined) {
          // Programmatic submit (from date-query) — block it
          e.preventDefault();
          return false;
        }
        // Real user submit — allow and clean up empty fields
        self._cleanEmptyFields();
        return true;
      });

      // "/" keyboard shortcut to focus the search input
      jQuery(document).on('keydown', function (e) {
        if (e.key === '/' && !self._isInputFocused()) {
          e.preventDefault();
          form.find('input[name="q"]').focus();
        }
      });

      // Search button: allow real submit
      form.find('button[type="submit"]').on('click', function () {
        self._blockAutoSubmit = false;
      });

      // Fix Leaflet map sizing when the advanced filters panel is revealed.
      // Leaflet can't calculate tile positions inside a hidden container,
      // so we trigger a window resize once the collapse transition finishes —
      // Leaflet listens for this and recalculates its layout automatically.
      jQuery('#homeAdvancedFilters').on('shown.bs.collapse', function () {
        window.dispatchEvent(new Event('resize'));
      });

      // EOV grid filter — hide non-matching cards and empty category headers
      jQuery('#homeEovFilter').on('input', function () {
        var query = jQuery(this).val().toLowerCase();
        var grid = jQuery('#homeEovGrid');
        // First, show all category grids so :visible checks work on items
        grid.find('.home-eov-category-label, .home-eov-grid').show();
        // Toggle individual cards by label match
        grid.find('.home-eov-item').each(function () {
          var label = jQuery(this).find('.home-eov-label').text().toLowerCase();
          jQuery(this).toggle(label.indexOf(query) !== -1);
        });
        // Then hide category sections where all cards are filtered out
        grid.find('.home-eov-category-label').each(function () {
          var $label = jQuery(this);
          var $ul = $label.next('.home-eov-grid');
          var hasVisible = $ul.find('.home-eov-item:visible').length > 0;
          $label.toggle(hasVisible);
          $ul.toggle(hasVisible);
        });
      });

      // Checklist filter inputs — hide non-matching items as user types
      this.el.find('.home-filter-search-input').on('input', function () {
        var query = jQuery(this).val().toLowerCase();
        var targetId = jQuery(this).data('filter-target');
        var list = jQuery('[data-filter-list="' + targetId + '"]');
        list.find('.home-filter-check-item').each(function () {
          var label = jQuery(this).find('.home-filter-check-label').text().toLowerCase();
          jQuery(this).toggle(label.indexOf(query) !== -1);
        });
      });
    },

    _isInputFocused: function () {
      var tag = document.activeElement && document.activeElement.tagName;
      return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT';
    },

    _cleanEmptyFields: function () {
      // Remove empty form fields so the URL stays clean.
      // Skip filter search inputs (no name) and unchecked checkboxes.
      this.form.find('input[name], select').each(function () {
        var $el = jQuery(this);
        if ($el.is(':checkbox') && !$el.is(':checked')) {
          $el.attr('disabled', true);
        } else if (!$el.is(':checkbox') && !$el.val()) {
          $el.attr('disabled', true);
        }
      });
    },

    teardown: function () {}
  };
});
