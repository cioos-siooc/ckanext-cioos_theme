/* Filter box for the home page EOV columns (home/snippets/eov_ranked.html):
 * typing narrows the cards to those whose name contains the text, ignoring
 * case and accents ("temperature" matches "Température"). Every category
 * column stays in place, so the layout and card widths don't change; a
 * column with no match shows its "No match" line, and the status line
 * announces when nothing matches at all. The box is rendered hidden and only
 * shown here, so pages without JavaScript don't get an input that does
 * nothing.
 *
 * Options: no-match - the message for the status line when nothing matches.
 */
ckan.module('eov-filter', function ($) {
  function fold(text) {
    return text.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
  }

  return {
    options: {
      noMatch: 'No match'
    },

    initialize: function () {
      var noMatch = this.options.noMatch;
      var input = this.el.find('.eov-filter-input');
      var status = this.el.find('.eov-filter-status');
      var rows = this.el.find('.eov-row');
      var sections = this.el.find('.eov-category');
      var names = rows.map(function () {
        return fold($(this).find('.eov-row-label').text());
      }).get();

      input.on('input', function () {
        var query = fold(this.value.trim());
        rows.each(function (i) {
          this.hidden = query !== '' && names[i].indexOf(query) === -1;
        });
        var anyVisible = false;
        sections.each(function () {
          var visible = $(this).find('.eov-row').filter(function () {
            return !this.hidden;
          }).length > 0;
          $(this).find('.eov-ranked-none').prop('hidden', visible);
          anyVisible = anyVisible || visible;
        });
        status.text(anyVisible ? '' : noMatch);
      });

      this.el.find('.eov-filter').prop('hidden', false);
    }
  };
});
