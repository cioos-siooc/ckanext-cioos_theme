/*
  home-v3-map — interactive Leaflet filter map for the v3 home page.

  Renders two togglable layers from server-aggregated data:

    1. Centroids — one CircleMarker per dataset (clustered with markercluster
       + chunkedLoading). Click highlights the dataset's bbox and links to
       the dataset page.

    2. Hex density — H3 cells colored by the count of datasets whose spatial
       footprint touches each cell. Hover shows the count; click navigates
       to /dataset?ext_geometry=<hex GeoJSON> for an exact polygon search
       (ckanext-spatial / PostGIS).

  A Leaflet baseLayers control toggles between them (radio — only one
  visible at a time, to keep the visual cognitive load down).

  Resolution + color ramp are driven by data-module-hex_config (server-side
  env-tunable via ckanext.cioos.hexmap.* config keys).
*/
ckan.module('home-v3-map', function (jQuery) {
  return {
    options: {
      // Option keys must match the data-module-<key> attribute names verbatim.
      // CKAN's loader auto-parses JSON-looking values, so array/object
      // attributes arrive parsed, not as strings.
      points: null,
      hex_cells: null,        // [[cell_id, count], ...]
      hex_config: null,       // {resolution, color_low, color_high, color_steps, opacity, stroke}
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

      var points = this._parseJsonOption('points') || [];
      var hexCells = this._parseJsonOption('hex_cells') || [];
      var hexConfig = this._parseJsonOption('hex_config') || {};

      console.debug(
        'home-v3-map: rendering', points.length, 'centroids,',
        hexCells.length, 'hex cells (res=' + (hexConfig.resolution || '?') + ')'
      );

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

      this._addFullscreenControl();

      // ── Centroid layer (markercluster) ──────────────────────────
      var centroidLayer = this._buildCentroidLayer(points);

      // ── Hex density layer ───────────────────────────────────────
      var hexLayer = this._buildHexLayer(hexCells, hexConfig);

      // Both layers go on the map; the layer control toggles visibility.
      // Default visible: centroids (preserves prior behaviour).
      centroidLayer.addTo(map);

      // Layer control. Using *baseLayers* (radio) makes the two layers
      // mutually exclusive — clicking one hides the other.
      var baseLayers = {};
      baseLayers[this._t('Dataset locations')] = centroidLayer;
      if (hexLayer) {
        baseLayers[this._t('Dataset density (hex)')] = hexLayer;
      }
      L.control.layers(baseLayers, null, {
        collapsed: false,
        position: 'topright'
      }).addTo(map);

      this._addDrawBboxControl();

      // The map lives inside a section that may render before its final size
      // (fonts, sidebars). Force a recalc once the layout settles.
      var self = this;
      setTimeout(function () { map.invalidateSize(); }, 50);
      jQuery(window).on('resize', function () { map.invalidateSize(); });
    },

    // CKAN auto-parses JSON-looking attributes, but if the heuristic missed
    // (e.g. attribute escaping fooled it) we parse defensively.
    _parseJsonOption: function (key) {
      var v = this.options[key];
      if (typeof v === 'string') {
        try { return JSON.parse(v); } catch (e) { return null; }
      }
      return v;
    },

    _t: function (s) {
      // CKAN's i18n is jQuery-based; if absent (e.g. test harness), pass through.
      return (this.i18n && this.i18n(s)) || s;
    },

    _addFullscreenControl: function () {
      // Custom L.Control using the standard Fullscreen API. Avoid the
      // leaflet.fullscreen plugin to keep the asset bundle small.
      var map = this.map;
      var fsTarget = this.el.parent()[0] || this.el[0];
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
    },

    _buildCentroidLayer: function (points) {
      var datasetUrl = this.options.dataset_url;
      var map = this.map;

      var cluster = L.markerClusterGroup({
        chunkedLoading: true,
        chunkInterval: 200,
        chunkDelay: 50,
        disableClusteringAtZoom: 8,
        spiderfyOnMaxZoom: true,
        showCoverageOnHover: false,
        maxClusterRadius: 60
      });

      // Tiny CircleMarker (canvas) for fast rendering at lowest zooms.
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
      function showBbox(name, title, bbox) {
        if (highlightLayer) { map.removeLayer(highlightLayer); highlightLayer = null; }
        if (!bbox || bbox.length !== 4) return;
        var west = bbox[0], south = bbox[1], east = bbox[2], north = bbox[3];
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

      // When the user toggles back to centroids, clear any leftover highlight
      // from a previous click so it doesn't ghost on top of the new layer.
      var self = this;
      cluster.on('remove', function () {
        if (highlightLayer) { map.removeLayer(highlightLayer); highlightLayer = null; }
      });

      return cluster;
    },

    _buildHexLayer: function (hexCells, hexConfig) {
      if (!hexCells || !hexCells.length) return null;
      if (typeof h3 === 'undefined' || !h3.cellToBoundary) {
        console.warn('home-v3-map: h3-js missing — hex layer disabled');
        return null;
      }

      var cfg = hexConfig || {};
      var opacity = (typeof cfg.opacity === 'number') ? cfg.opacity : 0.75;
      var stroke  = cfg.stroke || '#152f37';
      var accent  = cfg.accent_color || null;

      // Quantile breakpoints. Two paths:
      //   · explicit `color_quantiles` (e.g. [0.5, 0.8, 0.95, 0.99])
      //     → arbitrary-shaped percentile cuts. N quantiles → N+1 bins,
      //       so we override `color_steps` to match.
      //   · default uniform 1/steps split → equal-count bins.
      var customQuantiles = (cfg.color_quantiles && cfg.color_quantiles.length)
        ? cfg.color_quantiles.slice().sort(function (a, b) { return a - b; })
        : null;
      var steps = customQuantiles
        ? customQuantiles.length + 1
        : Math.max(2, parseInt(cfg.color_steps, 10) || 7);

      // Resolve palette stops: explicit array > preset name > legacy two-color.
      var stops;
      if (cfg.color_stops && cfg.color_stops.length >= 2) {
        stops = cfg.color_stops;
      } else if (cfg.color_preset && PRESETS[cfg.color_preset]) {
        stops = PRESETS[cfg.color_preset];
      } else {
        stops = [cfg.color_low || '#f3f0ec', cfg.color_high || '#152f37'];
      }
      var palette = buildPalette(stops, steps);

      // Sample the count distribution at the chosen percentiles to
      // produce concrete bin breakpoints.
      var counts = hexCells.map(function (c) { return c[1]; });
      var sorted = counts.slice().sort(function (a, b) { return a - b; });
      var thresholds = [];
      if (customQuantiles) {
        for (var qi = 0; qi < customQuantiles.length; qi++) {
          // Use Math.min to guard against q=1.0 producing an out-of-bounds
          // index when `sorted.length * q === sorted.length`.
          var idx = Math.min(sorted.length - 1, Math.floor(sorted.length * customQuantiles[qi]));
          thresholds.push(sorted[idx]);
        }
      } else {
        for (var i = 1; i < steps; i++) {
          thresholds.push(sorted[Math.floor(sorted.length * i / steps)]);
        }
      }
      // Dedupe — sparse data (e.g. many count=1 cells) can collapse
      // multiple breakpoints onto the same value. After dedupe we may
      // have fewer effective bins than `steps`.
      var uniqThresh = [];
      for (var k = 0; k < thresholds.length; k++) {
        if (k === 0 || thresholds[k] > thresholds[k - 1]) uniqThresh.push(thresholds[k]);
      }
      thresholds = uniqThresh;

      // Accent override — drop the gradient's last color in favor of
      // the explicit accent. This is what gives the densest cells a
      // true highlight pop instead of a muddy gradient-blended color.
      if (accent && palette.length > 0) {
        palette[palette.length - 1] = accent;
      }

      function bucketIndex(count) {
        // Map bucket position to palette index proportionally so we
        // still span the full color range even after threshold dedupe.
        var b = thresholds.length;
        for (var j = 0; j < thresholds.length; j++) {
          if (count <= thresholds[j]) { b = j; break; }
        }
        return Math.min(palette.length - 1, Math.round(b * (palette.length - 1) / thresholds.length));
      }

      // Convert each [cell_id, count] into a GeoJSON Feature.
      // h3.cellToBoundary(cell, true) → [[lng, lat], ...] in GeoJSON order.
      var features = [];
      for (var k = 0; k < hexCells.length; k++) {
        var cellId = hexCells[k][0];
        var count = hexCells[k][1];
        var ring;
        try {
          ring = h3.cellToBoundary(cellId, true);
        } catch (e) {
          continue;
        }
        if (!ring || ring.length < 3) continue;

        // Antimeridian guard: if any pair of consecutive vertices spans
        // more than 180° longitude, the polygon would render as a long
        // horizontal smear across the world. Skip those cells (rare for
        // CIOOS coverage; defensive).
        if (spansAntimeridian(ring)) continue;

        // GeoJSON polygons are closed (first == last); h3-js doesn't close
        // automatically.
        var closed = ring.slice();
        closed.push(ring[0]);

        features.push({
          type: 'Feature',
          properties: { cell_id: cellId, count: count },
          geometry: { type: 'Polygon', coordinates: [closed] }
        });
      }

      var searchUrl = this.options.search_url;
      var t = this._t.bind(this);

      // ── Legend control ────────────────────────────────────────────
      // One row per *effective* (post-dedupe) bin. Labels are derived
      // from the quantile breakpoints so users can see what counts each
      // color actually represents — accents at the top end of the ramp.
      var minCount = sorted.length ? sorted[0] : 0;
      var maxCount = sorted.length ? sorted[sorted.length - 1] : 0;
      var legendCtl = (function () {
        var Ctl = L.Control.extend({
          options: { position: 'bottomright' },
          onAdd: function () {
            var div = L.DomUtil.create('div', 'v3-hex-legend');
            var rows = ['<div class="v3-hex-legend-title">' + t('Datasets per hex') + '</div>'];
            // Walk the breakpoints + an appended max-sentinel so every
            // active bin (palette index) gets exactly one row.
            var breaks = thresholds.slice();
            breaks.push(maxCount);
            var prevHi = null;
            var seen = {};
            for (var i = 0; i < breaks.length; i++) {
              var idx = bucketIndex(breaks[i]);
              if (seen[idx]) continue;
              seen[idx] = true;
              var lo = (prevHi === null) ? minCount : (prevHi + 1);
              var hi = breaks[i];
              var label = (lo >= hi) ? String(hi) : (lo + '–' + hi);
              rows.push(
                '<div class="v3-hex-legend-row">' +
                '<span class="v3-hex-legend-swatch" style="background:' + palette[idx] + '"></span>' +
                '<span class="v3-hex-legend-label">' + label + '</span>' +
                '</div>'
              );
              prevHi = hi;
            }
            div.innerHTML = rows.join('');
            return div;
          }
        });
        return new Ctl();
      })();
      // Show legend only while the hex layer is visible.
      // (We can't reference `layer` yet — patched in via add/remove handlers below.)

      var layer = L.geoJSON(
        { type: 'FeatureCollection', features: features },
        {
          style: function (feature) {
            return {
              fillColor: palette[bucketIndex(feature.properties.count)],
              fillOpacity: opacity,
              // No resting stroke — cells read as a continuous density
              // surface rather than a tiled grid. The stroke comes back
              // briefly on hover (see mouseover handler below).
              stroke: false,
              weight: 0
            };
          },
          onEachFeature: function (feature, lyr) {
            var c = feature.properties.count;
            // Tooltip: count + click hint. Sticky = follows cursor.
            var label =
              '<strong>' + c + ' ' + t(c === 1 ? 'dataset' : 'datasets') + '</strong>' +
              '<br><span style="opacity:.7">' + t('Click to filter the catalogue') + '</span>';
            lyr.bindTooltip(label, {
              direction: 'top', sticky: true, className: 'v3-hex-tooltip'
            });
            lyr.on('mouseover', function () {
              // Re-enable stroke on hover so the active cell is clearly
              // outlined; resetStyle on mouseout returns to stroke:false.
              lyr.setStyle({ stroke: true, weight: 2, color: stroke, opacity: 1 });
              if (lyr.bringToFront) lyr.bringToFront();
            });
            lyr.on('mouseout', function () {
              layer.resetStyle(lyr);
            });
            lyr.on('click', function () {
              // Pass the hex polygon as ext_geometry — ckanext-spatial does
              // a PostGIS ST_Intersects against each dataset's `spatial`
              // for an exact polygon search.
              var geom = JSON.stringify(feature.geometry);
              window.location = searchUrl + '?ext_geometry=' + encodeURIComponent(geom);
            });
          }
        }
      );

      // Toggle the legend with the layer (so it doesn't ghost when the
      // user switches back to centroids).
      var mapRef = this.map;
      layer.on('add', function () { legendCtl.addTo(mapRef); });
      layer.on('remove', function () {
        try { mapRef.removeControl(legendCtl); } catch (e) { /* not added */ }
      });

      return layer;
    },

    _addDrawBboxControl: function () {
      // ckanext-spatial bundles leaflet.draw alongside Leaflet, so
      // L.Control.Draw is available here. We expose only the rectangle
      // tool; on completion we navigate to /dataset?ext_bbox=…
      var map = this.map;
      var searchUrl = this.options.search_url;

      if (!(L.Control && L.Control.Draw)) {
        console.warn('home-v3-map: leaflet.draw unavailable — draw tool disabled');
        return;
      }

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

      function bboxFromBounds(b) {
        return [
          b.getWest().toFixed(4),
          b.getSouth().toFixed(4),
          b.getEast().toFixed(4),
          b.getNorth().toFixed(4)
        ].join(',');
      }
      map.on(L.Draw.Event.CREATED, function (e) {
        drawnItems.clearLayers();
        drawnItems.addLayer(e.layer);
        window.location = searchUrl + '?ext_bbox=' + bboxFromBounds(e.layer.getBounds());
      });
    },

    teardown: function () {
      if (this.map) { this.map.remove(); this.map = null; }
    }
  };
});

// ── Module-private helpers ────────────────────────────────────────

function spansAntimeridian(ring) {
  for (var i = 1; i < ring.length; i++) {
    if (Math.abs(ring[i][0] - ring[i - 1][0]) > 180) return true;
  }
  return false;
}

// Built-in sequential palettes. ColorBrewer-derived where noted — these
// are perceptually-tuned multi-stop ramps that read well as choropleths.
// Each entry is an ordered list of stops; intermediate colors are
// interpolated in RGB space (good-enough for 7-step density maps).
var PRESETS = {
  // CIOOS brand: cream → teal → navy. Three clean stops with no muddy
  // intermediate. Accent (orange) is applied separately via the
  // `accent_color` config — it overrides the topmost bin instead of
  // being part of the gradient interpolation, so the highest-density
  // cells always pop without polluting the lower bins.
  cioos:    ['#f3f0ec', '#52a79b', '#152f37'],
  // ColorBrewer YlGnBu — classic for ocean/density data.
  ylgnbu:   ['#ffffd9', '#edf8b1', '#c7e9b4', '#7fcdbb', '#41b6c4', '#1d91c0', '#225ea8', '#0c2c84'],
  // ColorBrewer YlOrRd — warm, high-contrast.
  ylorrd:   ['#ffffb2', '#fed976', '#feb24c', '#fd8d3c', '#fc4e2a', '#e31a1c', '#b10026'],
  // ColorBrewer Oranges.
  oranges:  ['#fff5eb', '#fee6ce', '#fdd0a2', '#fdae6b', '#fd8d3c', '#f16913', '#d94801', '#8c2d04'],
  // ColorBrewer Purples.
  purples:  ['#fcfbfd', '#efedf5', '#dadaeb', '#bcbddc', '#9e9ac8', '#807dba', '#6a51a3', '#4a1486'],
  // Approximate viridis (perceptually uniform, colorblind-safe).
  viridis:  ['#440154', '#482878', '#3e4989', '#31688e', '#26828e', '#1f9e89', '#35b779', '#6ece58', '#b5de2b', '#fde725'],
  // Approximate magma — dark base, warm tail.
  magma:    ['#000004', '#1c1044', '#4f127b', '#812581', '#b5367a', '#e55063', '#fb8761', '#fec287', '#fcfdbf']
};

function buildPalette(stops, steps) {
  // Multi-stop linear interpolation in RGB space. Given N input stops and
  // M requested output steps, walks the ramp evenly across all segments
  // so every stop influences the final palette.
  if (!stops || stops.length === 0) stops = ['#f3f0ec', '#152f37'];
  if (stops.length === 1) {
    var solo = [];
    for (var z = 0; z < steps; z++) solo.push(stops[0]);
    return solo;
  }
  var rgbs = stops.map(hexToRgb);
  var out = [];
  for (var i = 0; i < steps; i++) {
    var t = steps === 1 ? 0 : i / (steps - 1);
    // Find which segment this t falls into and the local interpolation
    // factor within that segment.
    var segCount = rgbs.length - 1;
    var segIdx = Math.min(segCount - 1, Math.floor(t * segCount));
    var segT = (t * segCount) - segIdx;
    var a = rgbs[segIdx], b = rgbs[segIdx + 1];
    out.push(rgbToHex(
      Math.round(a[0] + (b[0] - a[0]) * segT),
      Math.round(a[1] + (b[1] - a[1]) * segT),
      Math.round(a[2] + (b[2] - a[2]) * segT)
    ));
  }
  return out;
}

function hexToRgb(h) {
  var s = h.replace('#', '');
  if (s.length === 3) s = s[0] + s[0] + s[1] + s[1] + s[2] + s[2];
  return [
    parseInt(s.slice(0, 2), 16),
    parseInt(s.slice(2, 4), 16),
    parseInt(s.slice(4, 6), 16)
  ];
}

function rgbToHex(r, g, b) {
  return '#' + [r, g, b].map(function (v) {
    var x = v.toString(16);
    return x.length === 1 ? '0' + x : x;
  }).join('');
}
