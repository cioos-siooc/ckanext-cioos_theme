/* Popover for the machine-translation icon (snippets/translation_icon.html).
 *
 * A hover tooltip closes as soon as the pointer leaves the icon, so the links
 * in the translation method could never be clicked. This popover opens on
 * hover, focus or click and stays open while the pointer or keyboard focus
 * is on the icon or inside the popover, which is rendered inside the
 * module's element so its links follow the icon in the tab order.
 */
this.ckan.module("translation-method", function () {
  return {
    initialize: function () {
      var group = this.el[0];
      var button = group.querySelector("[data-bs-content]");
      var popover = bootstrap.Popover.getOrCreateInstance(button, {
        trigger: "manual",
        html: true,
        container: group,
        customClass: "translation-popover",
      });
      var hideTimer;
      function show() {
        clearTimeout(hideTimer);
        popover.show();
      }
      function hideSoon() {
        clearTimeout(hideTimer);
        hideTimer = setTimeout(function () {
          popover.hide();
        }, 200);
      }

      group.addEventListener("mouseenter", show);
      group.addEventListener("mouseleave", hideSoon);
      button.addEventListener("focus", show);
      button.addEventListener("click", function (event) {
        event.preventDefault();
        show();
      });
      group.addEventListener("focusout", function (event) {
        if (!group.contains(event.relatedTarget)) hideSoon();
      });
      group.addEventListener("keydown", function (event) {
        if (event.key === "Escape") {
          popover.hide();
          button.focus();
        }
      });
      document.addEventListener("click", function (event) {
        if (!group.contains(event.target)) popover.hide();
      });
    },
  };
});
