ckan.module('date-query', function (jQuery) {

  return {
    initialize: function () {
      console.log("I've been called for element: %o", this.el);
      var module = this;
      $.proxyAll(this, /_on/);
      this.el.ready(this._onReady);
    },

    _getParameterByName: function (name) {
      var match = RegExp('[?&]' + name + '=([^&]*)')
                        .exec(window.location.search);
      return match ?
          decodeURIComponent(match[1].replace(/\+/g, ' '))
          : null;
    },

    _onReady: function() {
      var form = jQuery("#dataset-search-form");
      // CKAN 2.1
      if (!form.length) {
          form = $(".search-form");
      }

      // Add necessary fields to the search form if not already created
      jQuery(['ext_year_begin', 'ext_year_end']).each(function(index, item){
        if (jQuery("#" + item).length === 0) {
          jQuery('<input type="hidden" />').attr({'id': item, 'name': item}).appendTo(form);
        }
      });

      jQuery('#datepickerbegin').val(this._getParameterByName('ext_year_begin'))
      jQuery('#datepickerend').val(this._getParameterByName('ext_year_end'))
      jQuery('#ext_year_begin').val(this._getParameterByName('ext_year_begin'))
      jQuery('#ext_year_end').val(this._getParameterByName('ext_year_end'))

      jQuery('#datepickerbegin').on('changeDate', function(e) {
        var end_val = jQuery('#datepickerend').val();
        console.log(end_val)
        if (end_val && end_val < this.value) {
          jQuery('#datepickerend').val(this.value);
          this.value = end_val;
        }
        submitForm();
      });

      jQuery('#datepickerend').on('changeDate', function(e) {
        var begin_val = jQuery('#datepickerbegin').val();
        console.log(begin_val)
        if (begin_val && begin_val > this.value) {
          jQuery('#datepickerbegin').val(this.value);
          this.value = begin_val;
        }
        submitForm();
      });

      // Add the loading class and submit the form
      function submitForm() {
        jQuery('#ext_year_begin').val(jQuery('#datepickerbegin').val());
        jQuery('#ext_year_end').val(jQuery('#datepickerend').val());
        form.submit();
      }

    },
    teardown: function () {
      // Called before a module is removed from the page.
    }
  }
});
