/*
  home-v3-map — interactive Leaflet filter map for the v3 home page.

  Reads centroids from a `data-points` attribute (JSON: [[name, lon, lat], ...]),
  renders them with markercluster (chunkedLoading) so 10k+ points stay responsive,
  and exposes a "filter by bbox" button that links to the dataset search page
  using ckanext-spatial's ext_bbox parameter.
*/
ckan.module('home-v3-map', function (jQuery) {
  return {
    options: {
      // Option keys must match the data-module-<key> attribute names verbatim.
      // CKAN's loader auto-parses JSON-looking values, so `points` arrives
      // as a parsed array, not a string.
      points: null,
      dataset_url: '/dataset/',
      search_url: '/dataset/',
      tileUrl: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
      tileAttribution: '© OpenStreetMap contributors'
    },

    initialize: function () {
      jQuery.proxyAll(this, /_on/);
      // Leaflet is loaded by ckanext-spatial; if it isn't present yet we wait
      // for window load (asset bundles are async on slower connections).
      if (typeof L === 'undefined') {
        jQuery(window).on('load', this._onReady);
      } else {
        this._onReady();
      }
    },

    _onReady: function () {
      if (typeof L === 'undefined' || !L.markerClusterGroup) {
        // markercluster not loaded — fail soft: leave the placeholder visible.
        console.warn('home-v3-map: Leaflet or markercluster missing');
        return;
      }

      // CKAN parses JSON-looking strings automatically, but if it arrived
      // as a string anyway (e.g. attribute escaping fooled the heuristic),
      // parse defensively.
      var points = this.options.points;
      if (typeof points === 'string') {
        try { points = JSON.parse(points); } catch (e) { points = []; }
      }
      points = points || [];
      console.debug('home-v3-map: rendering', points.length, 'centroids');
      var map = L.map(this.el[0], {
        center: [55, -95],
        zoom: 3,
        worldCopyJump: true,
        scrollWheelZoom: false,    // avoid hijacking page scroll
        attributionControl: false  // suppress Leaflet 1.9+ Ukraine-flag badge
      });

      // Minimal text-only attribution so OSM is still credited.
      L.control.attribution({ prefix: false }).addTo(map);

      L.tileLayer(this.options.tileUrl, {
        attribution: this.options.tileAttribution,
        maxZoom: 12,
        minZoom: 2
      }).addTo(map);

      this.map = map;

      // ── Fullscreen toggle ─────────────────────────────────────
      // Custom L.Control using the standard Fullscreen API. We avoid
      // the leaflet.fullscreen plugin to keep the asset bundle small;
      // the API works in all evergreen browsers.
      var fsTarget = this.el.parent()[0] || this.el[0];  // expand the wrapper, not just the map div
      var FullscreenCtl = L.Control.extend({
        options: { position: 'topleft' },
        onAdd: function () {
          var c = L.DomUtil.create(
            'div', 'leaflet-bar leaflet-control v3-map-fs'
          );
          var a = L.DomUtil.create('a', '', c);
          a.href = '#';
          a.title = 'Toggle fullscreen';
          a.setAttribute('role', 'button');
          a.setAttribute('aria-label', 'Toggle fullscreen');
          a.innerHTML = '⛶';
          L.DomEvent.on(a, 'click', L.DomEvent.stop)
                    .on(a, 'click', function () {
            var fsEl = document.fullscreenElement || document.webkitFullscreenElement;
            if (fsEl) {
              (document.exitFullscreen || document.webkitExitFullscreen).call(document);
            } else {
              var req = fsTarget.requestFullscreen || fsTarget.webkitRequestFullscreen;
              if (req) req.call(fsTarget);
            }
          });
          return c;
        }
      });
      map.addControl(new FullscreenCtl());

      // When entering/leaving fullscreen, the map container resizes — Leaflet
      // doesn't notice without an explicit invalidateSize() call.
      function onFsChange() {
        setTimeout(function () { map.invalidateSize(); }, 50);
      }
      document.addEventListener('fullscreenchange', onFsChange);
      document.addEventListener('webkitfullscreenchange', onFsChange);

      var datasetUrl = this.options.dataset_url;
      var cluster = L.markerClusterGroup({
        chunkedLoading: true,
        chunkInterval: 200,
        chunkDelay: 50,
        disableClusteringAtZoom: 8,
        spiderfyOnMaxZoom: true,
        showCoverageOnHover: false,
        maxClusterRadius: 60
      });

      // Use a tiny CircleMarker (canvas) for fast rendering at lowest zooms.
      var renderer = L.canvas({ padding: 0.5 });
      var dotStyle = {
        radius: 4,
        weight: 1,
        color: '#152f37',
        fillColor: '#52a79b',
        fillOpacity: 0.9,
        renderer: renderer
      };

      // Layer for the currently-selected dataset's bbox; replaced on each click.
      var highlightLayer = null;
      var self = this;
      function showBbox(name, title, bbox) {
        if (highlightLayer) { map.removeLayer(highlightLayer); highlightLayer = null; }
        if (!bbox || bbox.length !== 4) return;
        var west = bbox[0], south = bbox[1], east = bbox[2], north = bbox[3];
        // Degenerate bbox (Point geometry): drop a marker instead of an empty rect.
        if (west === east && south === north) {
          highlightLayer = L.circleMarker([south, west], {
            radius: 7, weight: 2, color: '#d97c4a',
            fillColor: '#d97c4a', fillOpacity: 0.6
          });
        } else {
          highlightLayer = L.rectangle(
            [[south, west], [north, east]],
            { color: '#d97c4a', weight: 2, fillOpacity: 0.15 }
          );
        }
        var popupHtml =
          '<strong>' + escapeHtml(title || name) + '</strong>' +
          '<br><a href="' + datasetUrl + encodeURIComponent(name) + '">' +
          'View dataset →</a>';
        highlightLayer.bindPopup(popupHtml);
        highlightLayer.addTo(map);
        highlightLayer.openPopup();
        // Pan so the highlighted geometry fits comfortably in view.
        try { map.fitBounds(highlightLayer.getBounds(), { padding: [40, 40], maxZoom: 9 }); }
        catch (e) { /* CircleMarker has no getBounds — ignore */ }
      }

      function escapeHtml(s) {
        return String(s).replace(/[&<>"']/g, function (c) {
          return { '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' }[c];
        });
      }

      for (var i = 0; i < points.length; i++) {
        var p = points[i];
        // p = [name, title, lon, lat, [west, south, east, north]]
        var name = p[0], title = p[1], lon = p[2], lat = p[3], bbox = p[4];
        if (typeof lat !== 'number' || typeof lon !== 'number') continue;
        var marker = L.circleMarker([lat, lon], dotStyle);
        marker.bindTooltip(title || name, { direction: 'top', sticky: true });
        marker.on('click', (function (n, t, bb) {
          return function () { showBbox(n, t, bb); };
        })(name, title, bbox));
        cluster.addLayer(marker);
      }
      map.addLayer(cluster);
      this.cluster = cluster;
      this._clearHighlight = function () {
        if (highlightLayer) { map.removeLayer(highlightLayer); highlightLayer = null; }
      };
      // Clicking empty map area clears the highlight.
      map.on('click', function (e) {
        if (e.originalEvent && e.originalEvent.target &&
            e.originalEvent.target.tagName === 'CANVAS') {
          // canvas click that didn't hit a marker (Leaflet bubbles map clicks
          // through the canvas renderer) — nothing to do, marker handlers
          // already fired if a hit happened.
        }
      });

      var searchUrl = this.options.search_url;
      function bboxFromBounds(b) {
        return [
          b.getWest().toFixed(4),
          b.getSouth().toFixed(4),
          b.getEast().toFixed(4),
          b.getNorth().toFixed(4)
        ].join(',');
      }
      function gotoSearch(bbox) {
        window.location = searchUrl + '?ext_bbox=' + bbox;
      }

      // ── Draw-a-bbox-to-filter tool ──────────────────────────────
      // ckanext-spatial bundles leaflet.draw alongside Leaflet, so
      // L.Control.Draw is available here. We expose only the rectangle
      // tool; on completion we navigate to /dataset?ext_bbox=…
      if (L.Control && L.Control.Draw) {
        var drawnItems = new L.FeatureGroup();
        map.addLayer(drawnItems);
        var drawControl = new L.Control.Draw({
          position: 'topright',
          draw: {
            polyline: false,
            polygon: false,
            circle: false,
            marker: false,
            circlemarker: false,
            rectangle: {
              shapeOptions: {
                color: '#d97c4a', weight: 2, fillOpacity: 0.15
              }
            }
          },
          edit: { featureGroup: drawnItems, remove: false, edit: false }
        });
        map.addControl(drawControl);

        map.on(L.Draw.Event.CREATED, function (e) {
          drawnItems.clearLayers();
          drawnItems.addLayer(e.layer);
          gotoSearch(bboxFromBounds(e.layer.getBounds()));
        });
      } else {
        console.warn('home-v3-map: leaflet.draw unavailable — draw tool disabled');
      }

      // The map lives inside a section that may render before its final size
      // (fonts, sidebars). Force a recalc once the layout settles.
      setTimeout(function () { map.invalidateSize(); }, 50);
      jQuery(window).on('resize', function () { map.invalidateSize(); });
    },

    teardown: function () {
      if (this.map) { this.map.remove(); this.map = null; }
    }
  };
});
