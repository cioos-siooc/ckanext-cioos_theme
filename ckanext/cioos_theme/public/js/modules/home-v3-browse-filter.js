/* Client-side substring filter for home v3 "Browse by …" sections.
 *
 * Wire on a wrapper element via:
 *   data-module="home-v3-browse-filter"
 *   data-module-target=".v3-org-item"   (CSS selector for filterable rows)
 *   data-module-label-selector=".v3-org-name"   (CSS selector inside each row
 *                                                that holds the searchable text)
 *
 * Filters items in-place by toggling a `.is-hidden` class on each match
 * candidate — no DOM removal, so the original order is preserved when the
 * input is cleared.
 */
this.ckan.module("home-v3-browse-filter", function ($) {
  "use strict";
  return {
    options: {
      target: "li",
      labelSelector: null,
    },

    initialize: function () {
      var module = this;
      var input = this.el.find("input.v3-browse-filter-input");
      if (!input.length) {
        return;
      }

      // Cache normalized labels once on init — keeps every keystroke O(n)
      // string-compare instead of re-walking children + re-normalizing each
      // time. Important when an admin grows the list past a few hundred items.
      var $items = this.el.find(this.options.target);
      var labelSelector = this.options.labelSelector;
      var entries = $items
        .map(function () {
          var $node = $(this);
          var text = labelSelector
            ? $node.find(labelSelector).text()
            : $node.text();
          return { $node: $node, label: module._normalize(text) };
        })
        .get();

      var $empty = this.el.find(".v3-browse-filter-empty");

      var apply = function () {
        var query = module._normalize(input.val());
        var visibleCount = 0;
        for (var i = 0; i < entries.length; i++) {
          var match = !query || entries[i].label.indexOf(query) !== -1;
          entries[i].$node.toggleClass("is-hidden", !match);
          if (match) {
            visibleCount++;
          }
        }
        if ($empty.length) {
          $empty.toggleClass("is-hidden", visibleCount > 0);
        }
      };

      input.on("input", apply);

      // Esc clears the field — common UX expectation for a filter input.
      input.on("keydown", function (e) {
        if (e.key === "Escape" && input.val() !== "") {
          input.val("");
          apply();
          e.preventDefault();
        }
      });
    },

    _normalize: function (text) {
      if (!text) {
        return "";
      }
      // NFD splits accented chars into base + combining mark; the regex
      // strips marks in U+0300..U+036F. Result: "Réseau" → "reseau",
      // letting unaccented queries still match. Lowercased for case-insensitive compare.
      return String(text)
        .normalize("NFD")
        .replace(/[̀-ͯ]/g, "")
        .toLowerCase()
        .trim();
    },
  };
});
