ckan.module('truncate', function (jQuery) {
  return {
    initialize: function() {
      console.log("I've been initialized for element: ", this.el);
      $.proxyAll(this, /_on/);
      this.el.ready(this._onReady);
    },

    _onReady: function() {
      options = $('.notes').data()
      delete options.module
      jQuery(".notes").truncate(options);
    },

    teardown: function () {
      // Called before a module is removed from the page.
    }

  };
});
