(function () {
  'use strict';

  var currentMap = null;

  function init() {
    var previewCol = document.getElementById('dataset-preview-col');
    var backdrop = document.getElementById('dataset-preview-backdrop');
    if (!previewCol) return;

    var listRoot = document.querySelector('.dataset-list');
    if (!listRoot) return;

    listRoot.addEventListener('click', function (event) {
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button === 1) {
        return;
      }
      // Only meta-line anchors (license, DOI) and explicit buttons should pass through.
      // Title link clicks fall to the row handler so we can show the preview instead.
      if (event.target.closest('.db-row-meta a, .db-row-meta button, button')) return;

      var row = event.target.closest('.db-row[data-package-name]');
      if (!row || !listRoot.contains(row)) return;

      event.preventDefault();
      activate(row, listRoot, previewCol, backdrop);
    });

    listRoot.addEventListener('keydown', function (event) {
      if (event.key !== 'Enter' && event.key !== ' ') return;
      var row = event.target.closest('.db-row[data-package-name]');
      if (!row || row !== event.target) return;
      event.preventDefault();
      activate(row, listRoot, previewCol, backdrop);
    });

    previewCol.addEventListener('click', function (event) {
      var closeBtn = event.target.closest('.db-preview-close');
      if (!closeBtn) return;
      closePreview(listRoot, previewCol, backdrop);
    });

    if (backdrop) {
      backdrop.addEventListener('click', function () {
        closePreview(listRoot, previewCol, backdrop);
      });
    }

    document.addEventListener('keydown', function (event) {
      if (event.key === 'Escape' && previewCol.classList.contains('is-open')) {
        closePreview(listRoot, previewCol, backdrop);
      }
    });
  }

  function activate(row, listRoot, previewCol, backdrop) {
    var name = row.getAttribute('data-package-name');
    if (!name) return;

    listRoot.querySelectorAll('.db-row.is-active').forEach(function (r) {
      r.classList.remove('is-active');
    });
    row.classList.add('is-active');
    previewCol.classList.add('is-open');
    if (backdrop) backdrop.classList.add('is-visible');
    document.body.classList.add('preview-open');

    teardownMap();
    previewCol.setAttribute('data-loading', '1');

    fetch('/dataset/' + encodeURIComponent(name) + '.preview', {
      credentials: 'same-origin',
      headers: { 'Accept': 'text/html' },
    })
      .then(function (res) {
        if (!res.ok) throw new Error('preview fetch failed: ' + res.status);
        return res.text();
      })
      .then(function (html) {
        previewCol.innerHTML = html;
        previewCol.removeAttribute('data-loading');
        initPreviewMap(previewCol);
      })
      .catch(function () {
        previewCol.removeAttribute('data-loading');
        closePreview(listRoot, previewCol, backdrop);
      });
  }

  function closePreview(listRoot, previewCol, backdrop) {
    listRoot.querySelectorAll('.db-row.is-active').forEach(function (r) {
      r.classList.remove('is-active');
    });
    previewCol.classList.remove('is-open');
    if (backdrop) backdrop.classList.remove('is-visible');
    document.body.classList.remove('preview-open');
    teardownMap();
    setTimeout(function () {
      if (!previewCol.classList.contains('is-open')) previewCol.innerHTML = '';
    }, 250);
  }

  function teardownMap() {
    if (currentMap) {
      try { currentMap.remove(); } catch (e) { /* swallow */ }
      currentMap = null;
    }
  }

  function initPreviewMap(previewCol) {
    var mapEl = previewCol.querySelector('.db-preview-map[data-spatial]');
    if (!mapEl || typeof L === 'undefined') return;

    var spatial;
    try {
      spatial = JSON.parse(mapEl.getAttribute('data-spatial'));
    } catch (e) {
      return;
    }
    if (!spatial) return;

    // Make sure the empty-state placeholder doesn't sit over the map.
    var empty = mapEl.querySelector('.db-preview-map-empty');
    if (empty) empty.remove();

    var map = L.map(mapEl, {
      zoomControl: false,
      attributionControl: true,
      scrollWheelZoom: false,
      dragging: false,
      doubleClickZoom: false,
      boxZoom: false,
      touchZoom: false,
      keyboard: false,
      tap: false,
    });
    currentMap = map;

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '© OpenStreetMap',
      maxZoom: 13,
    }).addTo(map);

    var layer = L.geoJSON(spatial, {
      interactive: false,
      style: {
        color: '#3f8a80',
        weight: 2,
        fillColor: '#52A79B',
        fillOpacity: 0.22,
      },
      pointToLayer: function (feature, latlng) {
        return L.circleMarker(latlng, {
          radius: 6,
          color: 'white',
          weight: 2,
          fillColor: '#52A79B',
          fillOpacity: 1,
          interactive: false,
        });
      },
    }).addTo(map);

    try {
      var bounds = layer.getBounds();
      if (bounds.isValid()) {
        map.fitBounds(bounds.pad(0.25), { animate: false, maxZoom: 9 });
      } else {
        map.setView([55, -100], 3);
      }
    } catch (e) {
      map.setView([55, -100], 3);
    }

    // Leaflet sometimes mis-measures container size when the panel slides in.
    setTimeout(function () { map.invalidateSize(); }, 280);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
