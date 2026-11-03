/* Turns the home page EOV category chips (home/snippets/eov_category_chips.html)
 * into filters: choosing a category shows only the [data-eov-filter-item]
 * category sections whose data-category matches; "All" shows every one.
 * Without this module the chips are plain links to the category anchors.
 */
ckan.module('eov-categories', function ($) {
  return {
    initialize: function () {
      var chips = this.el.find('.eov-chip');
      var items = this.el.find('[data-eov-filter-item]');

      function select(category) {
        chips.each(function () {
          this.setAttribute('aria-pressed', String(this.dataset.category === category));
        });
        items.each(function () {
          this.hidden = category !== '' && this.dataset.category !== category;
        });
      }

      chips
        .attr('role', 'button')
        .on('click', function (event) {
          event.preventDefault();
          select(this.dataset.category);
        })
        // Links only activate on Enter; buttons also activate on Space.
        .on('keydown', function (event) {
          if (event.key === ' ') {
            event.preventDefault();
            select(this.dataset.category);
          }
        });

      select('');
    }
  };
});
