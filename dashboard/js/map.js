// dashboard/js/map.js — carte choroplèthe MapLibre GL JS

const MapModule = (() => {
  let map  = null;
  let prixData  = {};
  let indicData = {};
  let lsData    = {};
  let _dataLoaded  = false;
  let _hoverReady  = false;
  let _currentAnnee = 2023;
  let _currentIndicator = "prix_m2_median";
  let _isLightMode  = localStorage.getItem("theme") === "light";

  // Tuiles raster CARTO — seule chose swappée au toggle thème
  const TILE_URLS = {
    dark: [
      "https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
      "https://b.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
      "https://c.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
    ],
    light: [
      "https://a.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png",
      "https://b.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png",
      "https://c.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png",
    ],
  };

  // Style de base minimal — jamais remplacé via setStyle()
  const BASE_STYLE = {
    version: 8,
    sources: {},
    layers: [],
    glyphs: "https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf",
  };

  // GeoJSON embarqué (fallback si API indisponible)
  const PARIS_GEOJSON = {
    type: "FeatureCollection",
    features: [
      { type:"Feature", properties:{arrondissement:1},  geometry:{type:"Polygon", coordinates:[[[2.3387,48.8600],[2.3387,48.8650],[2.3530,48.8650],[2.3530,48.8600],[2.3387,48.8600]]]}},
      { type:"Feature", properties:{arrondissement:2},  geometry:{type:"Polygon", coordinates:[[[2.3387,48.8650],[2.3387,48.8700],[2.3530,48.8700],[2.3530,48.8650],[2.3387,48.8650]]]}},
      { type:"Feature", properties:{arrondissement:3},  geometry:{type:"Polygon", coordinates:[[[2.3530,48.8600],[2.3530,48.8680],[2.3640,48.8680],[2.3640,48.8600],[2.3530,48.8600]]]}},
      { type:"Feature", properties:{arrondissement:4},  geometry:{type:"Polygon", coordinates:[[[2.3387,48.8520],[2.3387,48.8600],[2.3530,48.8600],[2.3530,48.8520],[2.3387,48.8520]]]}},
      { type:"Feature", properties:{arrondissement:5},  geometry:{type:"Polygon", coordinates:[[[2.3450,48.8450],[2.3450,48.8520],[2.3620,48.8520],[2.3620,48.8450],[2.3450,48.8450]]]}},
      { type:"Feature", properties:{arrondissement:6},  geometry:{type:"Polygon", coordinates:[[[2.3280,48.8450],[2.3280,48.8530],[2.3450,48.8530],[2.3450,48.8450],[2.3280,48.8450]]]}},
      { type:"Feature", properties:{arrondissement:7},  geometry:{type:"Polygon", coordinates:[[[2.2980,48.8480],[2.2980,48.8600],[2.3280,48.8600],[2.3280,48.8480],[2.2980,48.8480]]]}},
      { type:"Feature", properties:{arrondissement:8},  geometry:{type:"Polygon", coordinates:[[[2.2980,48.8650],[2.2980,48.8800],[2.3250,48.8800],[2.3250,48.8650],[2.2980,48.8650]]]}},
      { type:"Feature", properties:{arrondissement:9},  geometry:{type:"Polygon", coordinates:[[[2.3250,48.8700],[2.3250,48.8800],[2.3500,48.8800],[2.3500,48.8700],[2.3250,48.8700]]]}},
      { type:"Feature", properties:{arrondissement:10}, geometry:{type:"Polygon", coordinates:[[[2.3500,48.8680],[2.3500,48.8820],[2.3680,48.8820],[2.3680,48.8680],[2.3500,48.8680]]]}},
      { type:"Feature", properties:{arrondissement:11}, geometry:{type:"Polygon", coordinates:[[[2.3640,48.8520],[2.3640,48.8680],[2.3880,48.8680],[2.3880,48.8520],[2.3640,48.8520]]]}},
      { type:"Feature", properties:{arrondissement:12}, geometry:{type:"Polygon", coordinates:[[[2.3620,48.8380],[2.3620,48.8520],[2.4050,48.8520],[2.4050,48.8380],[2.3620,48.8380]]]}},
      { type:"Feature", properties:{arrondissement:13}, geometry:{type:"Polygon", coordinates:[[[2.3450,48.8230],[2.3450,48.8400],[2.3750,48.8400],[2.3750,48.8230],[2.3450,48.8230]]]}},
      { type:"Feature", properties:{arrondissement:14}, geometry:{type:"Polygon", coordinates:[[[2.3080,48.8230],[2.3080,48.8430],[2.3450,48.8430],[2.3450,48.8230],[2.3080,48.8230]]]}},
      { type:"Feature", properties:{arrondissement:15}, geometry:{type:"Polygon", coordinates:[[[2.2780,48.8320],[2.2780,48.8530],[2.3080,48.8530],[2.3080,48.8320],[2.2780,48.8320]]]}},
      { type:"Feature", properties:{arrondissement:16}, geometry:{type:"Polygon", coordinates:[[[2.2480,48.8450],[2.2480,48.8820],[2.2980,48.8820],[2.2980,48.8450],[2.2480,48.8450]]]}},
      { type:"Feature", properties:{arrondissement:17}, geometry:{type:"Polygon", coordinates:[[[2.2980,48.8800],[2.2980,48.8950],[2.3350,48.8950],[2.3350,48.8800],[2.2980,48.8800]]]}},
      { type:"Feature", properties:{arrondissement:18}, geometry:{type:"Polygon", coordinates:[[[2.3350,48.8820],[2.3350,48.9000],[2.3700,48.9000],[2.3700,48.8820],[2.3350,48.8820]]]}},
      { type:"Feature", properties:{arrondissement:19}, geometry:{type:"Polygon", coordinates:[[[2.3700,48.8750],[2.3700,48.9000],[2.4050,48.9000],[2.4050,48.8750],[2.3700,48.8750]]]}},
      { type:"Feature", properties:{arrondissement:20}, geometry:{type:"Polygon", coordinates:[[[2.3880,48.8520],[2.3880,48.8750],[2.4150,48.8750],[2.4150,48.8520],[2.3880,48.8520]]]}},
    ]
  };

  function _tileSrc(isLight) {
    return {
      type: "raster",
      tiles: isLight ? TILE_URLS.light : TILE_URLS.dark,
      tileSize: 256,
      attribution: "© CARTO © OpenStreetMap contributors",
    };
  }

  // ── Init ──────────────────────────────────────────────────────────────
  function init() {
    showLoader(true);

    map = new maplibregl.Map({
      container: "map",
      style: BASE_STYLE,
      center: [2.3488, 48.8534],
      zoom: 11.6,
      pitch: 0,
      bearing: 0,
      maxZoom: 16,
      minZoom: 10,
    });

    map.on("load", () => {
      console.log("MAP LOADED");
      // 1. Fond de carte raster selon localStorage (dark ou light)
      map.addSource("tiles-bg", _tileSrc(_isLightMode));
      map.addLayer({ id: "layer-tiles-bg", type: "raster", source: "tiles-bg" });

      // 2. GeoJSON choroplèthe par-dessus (jamais supprimé ensuite)
      map.resize();
      loadData();
    });

    map.on("error", e => {
      console.error("ERREUR MapLibre:", e.error || e);
    });

    map.getCanvas().addEventListener("webglcontextlost", () => {
      console.warn("WebGL context lost — tentative de récupération");
    });
    map.getCanvas().addEventListener("webglcontextrestored", () => {
      console.log("WebGL context restored");
      map.resize();
    });
  }

  // ── Loader overlay ─────────────────────────────────────────────────────
  function showLoader(visible) {
    const el = document.getElementById("map-loader");
    if (!el) return;
    if (visible) {
      el.style.opacity = "1";
      el.style.pointerEvents = "all";
    } else {
      el.style.opacity = "0";
      el.style.pointerEvents = "none";
    }
  }

  function ordinal(n) { return n === 1 ? "1er" : `${n}e`; }

  // ── Chargement données — résilient par endpoint ────────────────────────
  async function loadData() {
    let geo = null;
    try {
      geo = await API.getGeoJSON();
      if (!geo?.features?.length) throw new Error("vide");
    } catch {
      geo = PARIS_GEOJSON;
    }
    geo.features.forEach(f => { f.properties._arr = extractArr(f.properties); });
    window._geojsonData = geo;

    const [prixRes, indicRes, lsRes] = await Promise.allSettled([
      API.getEvolution(),
      API.getIndicateurs(),
      API.getLogementsSociaux(),
    ]);

    if (prixRes.status === "fulfilled") {
      prixRes.value.forEach(d => {
        prixData[`${d.arrondissement}_${d.annee}`] = d;
      });
    } else {
      console.warn("Prix indisponibles:", prixRes.reason?.message);
    }

    if (indicRes.status === "fulfilled") {
      indicRes.value.forEach(d => { indicData[d.arrondissement] = d; });
    } else {
      console.warn("Indicateurs indisponibles:", indicRes.reason?.message);
    }

    if (lsRes.status === "fulfilled") {
      lsRes.value.forEach(d => {
        if (d.part_logements_sociaux_pct != null) {
          lsData[d.arrondissement] = d.part_logements_sociaux_pct;
        }
      });
    } else {
      console.warn("Logements sociaux indisponibles:", lsRes.reason?.message);
    }

    console.log("DATA LOADED", { prixData, indicData, lsData, geo: window._geojsonData });
    _dataLoaded = true;
    buildChoropleth(2023, "prix_m2_median");
    showLoader(false);
  }

  // ── Extraction numéro arrondissement ───────────────────────────────────
  function extractArr(props) {
    for (const key of ["arrondissement","c_ar","C_AR","num_arr","numero","code","l_ar","n_sq_ar"]) {
      const val = props[key];
      if (val == null) continue;
      const n = parseInt(String(val).replace(/\D/g, ""), 10);
      if (n >= 1 && n <= 20) return n;
    }
    for (const val of Object.values(props)) {
      if (val == null) continue;
      const n = parseInt(String(val).replace(/\D/g, ""), 10);
      if (n >= 1 && n <= 20) return n;
    }
    return null;
  }

  // ── Valeur selon l'indicateur ──────────────────────────────────────────
  function getValue(arr, annee, indicateur) {
    if (!arr) return null;
    if (indicateur.startsWith("score_"))             return indicData[arr]?.[indicateur] ?? null;
    if (indicateur === "part_logements_sociaux_pct") return lsData[arr] ?? null;
    return prixData[`${arr}_${annee}`]?.[indicateur] ?? null;
  }

  // ── Choroplèthe ────────────────────────────────────────────────────────
  function buildChoropleth(annee, indicateur) {
    _currentAnnee = annee;
    const geo = window._geojsonData;
    if (!geo || !map) return;

    const enriched = JSON.parse(JSON.stringify(geo));
    enriched.features.forEach(f => {
      const arr = f.properties._arr;
      const val = getValue(arr, annee, indicateur);
      if (arr) {
        Object.assign(f.properties, prixData[`${arr}_${annee}`] || {});
        Object.assign(f.properties, indicData[arr] || {});
        f.properties.part_logements_sociaux_pct = lsData[arr] ?? null;
      }
      f.properties._arr   = arr;
      f.properties._value = (val != null && !isNaN(Number(val))) ? Number(val) : null;
    });

    const values = enriched.features.map(f => f.properties._value).filter(v => v != null);

    if (!values.length) {
      const fallbackExpr = _isLightMode ? "#c8cce8" : "#2d3355";
      if (map.getSource("arr")) {
        map.getSource("arr").setData(enriched);
        map.setPaintProperty("fill-arr", "fill-color", fallbackExpr);
      } else {
        _addLayers(enriched, fallbackExpr);
      }
      console.warn("Aucune valeur pour:", indicateur);
      return;
    }

    const min = Math.min(...values);
    const max = Math.max(...values);
    const colorExpr = buildColorExpr(min, max, indicateur);

    if (map.getSource("arr")) {
      map.getSource("arr").setData(enriched);
      map.setPaintProperty("fill-arr", "fill-color", colorExpr);
      buildLegende(min, max, indicateur);
      _currentIndicator = indicateur;
      return;
    }

    _addLayers(enriched, colorExpr);
    _currentIndicator = indicateur;
    buildLegende(min, max, indicateur);
  }

  function _addLayers(enriched, colorExpr) {
    console.log("ADD LAYERS CALLED", { features: enriched?.features?.length, colorExpr });
    map.addSource("arr", { type: "geojson", data: enriched });

    // Halo hover
    map.addLayer({
      id: "line-halo", type: "line", source: "arr",
      filter: ["==", ["get", "_arr"], -1],
      paint: {
        "line-color": "#a5b4fc",
        "line-width": 8,
        "line-blur": 6,
        "line-opacity": 0.85,
      },
    });

    // Remplissage choroplèthe
    map.addLayer({
      id: "fill-arr", type: "fill", source: "arr",
      paint: {
        "fill-color": colorExpr,
        "fill-opacity": 0.78,
        "fill-opacity-transition": { duration: 350, delay: 0 },
        "fill-color-transition": { duration: 600, delay: 0 },
      },
    });

    // Highlight hover
    map.addLayer({
      id: "fill-hover", type: "fill", source: "arr",
      filter: ["==", ["get", "_arr"], -1],
      paint: { "fill-color": "#ffffff", "fill-opacity": 0.12 },
    });

    // Bordures
    map.addLayer({
      id: "line-arr", type: "line", source: "arr",
      paint: {
        "line-color": _isLightMode ? "rgba(60,60,120,0.35)" : "rgba(255,255,255,0.55)",
        "line-width": 1,
        "line-width-transition": { duration: 250, delay: 0 },
      },
    });

    // Labels arrondissements
    map.addLayer({
      id: "labels-arr", type: "symbol", source: "arr",
      layout: {
        "text-field": [
          "case",
          ["==", ["get", "_arr"], 1], "1er",
          ["concat", ["to-string", ["get", "_arr"]], "e"],
        ],
        "text-font": ["Noto Sans Regular"],
        "text-size": ["interpolate", ["linear"], ["zoom"], 10, 9, 12, 13, 14, 17],
        "text-allow-overlap": false,
        "symbol-placement": "point",
      },
      paint: {
        "text-color":       _isLightMode ? "rgba(20,24,56,0.9)"    : "rgba(255,255,255,0.9)",
        "text-halo-color":  _isLightMode ? "rgba(255,255,255,0.9)" : "rgba(0,0,0,0.7)",
        "text-halo-width": 1.5,
        "text-halo-blur": 0.5,
      },
    });

    if (!_hoverReady) {
      setupHover();
      _hoverReady = true;
    }
  }

  // ── Palette couleur ────────────────────────────────────────────────────
  function buildColorExpr(min, max, indicateur) {
    const colors = indicateur.startsWith("score_")
      ? CONFIG.COLORS_SCORE : CONFIG.COLORS_PRIX;
    const step = (max - min) / (colors.length - 1 || 1);
    const stops = colors.flatMap((c, i) => [min + i * step, c]);
    return ["interpolate", ["linear"], ["coalesce", ["get", "_value"], min], ...stops];
  }

  // ── Légende ────────────────────────────────────────────────────────────
  function buildLegende(min, max, indicateur) {
    const el = document.getElementById("legende-container");
    if (!el) return;
    const colors = indicateur.startsWith("score_")
      ? CONFIG.COLORS_SCORE : CONFIG.COLORS_PRIX;
    const stops = colors.map((c, i) =>
      `${c} ${(i / (colors.length - 1) * 100).toFixed(1)}%`
    ).join(",");
    const mid = (min + max) / 2;
    el.innerHTML = `
      <div class="legende-gradient" style="background:linear-gradient(to top, ${stops})"></div>
      <div class="legende-ticks">
        <span>${fmt(max, indicateur)}</span>
        <span>${fmt(mid, indicateur)}</span>
        <span>${fmt(min, indicateur)}</span>
      </div>
    `;
  }

  // ── Tooltip au hover ───────────────────────────────────────────────────
  function setupHover() {
    const tip = document.getElementById("tooltip");

    map.on("mousemove", "fill-arr", e => {
      map.getCanvas().style.cursor = "pointer";
      const p   = e.features[0].properties;
      const arr = p._arr;
      if (!arr) return;

      map.setFilter("fill-hover", ["==", ["get", "_arr"], arr]);
      map.setFilter("line-halo",  ["==", ["get", "_arr"], arr]);
      map.setPaintProperty("line-arr", "line-width", [
        "case", ["==", ["get", "_arr"], arr], 2, 1,
      ]);

      const indicateur = _currentIndicator;
      const varPct = p.prix_m2_variation_pct;
      const ls_pct = p.part_logements_sociaux_pct;
      const trend  = (varPct != null && !isNaN(varPct))
        ? (Number(varPct) > 0 ? "up" : Number(varPct) < 0 ? "down" : "flat")
        : null;

      const secDetail = indicateur === "score_securite" ? `
        <div class="tt-separator"></div>
        <div class="tt-section-label">Détail sécurité</div>
        ${p.nb_faits != null ? `<div class="tt-row"><span>⚠ Faits crim.</span><span>${Math.round(p.nb_faits).toLocaleString("fr-FR")}</span></div>` : ""}
        ${p.nb_commissariats != null ? `<div class="tt-row"><span>🚔 Commissariats</span><span>${p.nb_commissariats}</span></div>` : ""}
        ${p.nb_casernes != null ? `<div class="tt-row"><span>🚒 Casernes pompiers</span><span>${p.nb_casernes}</span></div>` : ""}
      ` : "";

      tip.innerHTML = `
        <h3>
          <span class="tt-arr-badge">${arr}${arr === 1 ? "er" : "e"}</span>
          arrondissement
        </h3>
        <div class="tt-highlight">
          <div class="tt-row">
            <span>${CONFIG.INDICATEURS_LABELS[indicateur] || indicateur}</span>
            <span>${fmt(p._value, indicateur)}</span>
          </div>
        </div>
        ${p.prix_m2_median ? `<div class="tt-row"><span>Prix/m²</span><span>${Math.round(p.prix_m2_median).toLocaleString("fr-FR")} €</span></div>` : ""}
        ${ls_pct != null ? `<div class="tt-row"><span>Log. sociaux</span><span>${Number(ls_pct).toFixed(1)}%</span></div>` : ""}
        ${p.nb_transactions ? `<div class="tt-row"><span>Transactions</span><span>${Math.round(p.nb_transactions).toLocaleString("fr-FR")}</span></div>` : ""}
        ${trend ? `<div class="tt-row"><span>Variation</span><span class="tt-trend tt-${trend}">${Number(varPct) > 0 ? "+" : ""}${Number(varPct).toFixed(1)}%</span></div>` : ""}
        ${secDetail}
      `;

      const tw = 240, th = 200;
      const x  = e.point.x + 16;
      const y  = e.point.y - 12;
      const mapW = map.getContainer().offsetWidth;
      const mapH = map.getContainer().offsetHeight;
      tip.style.left = (x + tw > mapW ? e.point.x - tw - 8 : x) + "px";
      tip.style.top  = (y + th > mapH ? e.point.y - th   : y) + "px";
      tip.classList.add("visible");
    });

    map.on("mouseleave", "fill-arr", () => {
      map.getCanvas().style.cursor = "";
      map.setFilter("fill-hover", ["==", ["get", "_arr"], -1]);
      map.setFilter("line-halo",  ["==", ["get", "_arr"], -1]);
      map.setPaintProperty("line-arr", "line-width", 1);
      tip.classList.remove("visible");
    });

    map.on("click", "fill-arr", e => {
      const arr = e.features[0].properties._arr;
      if (!arr) return;
      const sel = document.getElementById("select-arr");
      if (sel) { sel.value = arr; sel.dispatchEvent(new Event("change")); }
    });
  }

  // ── Formatage ──────────────────────────────────────────────────────────
  function fmt(val, ind) {
    if (val == null || isNaN(Number(val))) return "—";
    const v = Number(val);
    if (ind === "prix_m2_median" || ind === "prix_m2_moyen")
      return v.toLocaleString("fr-FR", { maximumFractionDigits: 0 }) + " €/m²";
    if (ind.includes("pct") || ind.includes("sociaux"))
      return v.toFixed(1) + "%";
    if (ind.startsWith("score_"))
      return v.toFixed(1) + " /10";
    return v.toLocaleString("fr-FR", { maximumFractionDigits: 0 });
  }

  // ── Changement de thème — UNIQUEMENT les tuiles raster ────────────────
  function setTheme(isLight) {
    if (!map) return;
    _isLightMode = isLight;

    // Swap uniquement la source/layer de fond raster
    if (map.getLayer("layer-tiles-bg")) map.removeLayer("layer-tiles-bg");
    if (map.getSource("tiles-bg"))      map.removeSource("tiles-bg");

    map.addSource("tiles-bg", _tileSrc(isLight));
    // Insérer AVANT le premier layer GeoJSON pour rester en fond
    map.addLayer(
      { id: "layer-tiles-bg", type: "raster", source: "tiles-bg" },
      map.getLayer("line-halo") ? "line-halo" : undefined,
    );

    // Adapter les couleurs bordures et labels au nouveau thème
    if (map.getLayer("line-arr")) {
      map.setPaintProperty("line-arr", "line-color",
        isLight ? "rgba(60,60,120,0.35)" : "rgba(255,255,255,0.55)"
      );
    }
    if (map.getLayer("labels-arr")) {
      map.setPaintProperty("labels-arr", "text-color",
        isLight ? "rgba(20,24,56,0.9)" : "rgba(255,255,255,0.9)"
      );
      map.setPaintProperty("labels-arr", "text-halo-color",
        isLight ? "rgba(255,255,255,0.9)" : "rgba(0,0,0,0.7)"
      );
    }
    // Layers GeoJSON (arr, fill-arr, fill-hover, line-halo, labels-arr) → jamais touchés
  }

  return {
    init,
    update(annee, indicateur) {
      if (!_dataLoaded) return;
      buildChoropleth(annee, indicateur);
    },
    resize() {
      if (map) {
        map.resize();
        if (_dataLoaded && window._geojsonData && map.getSource("arr")) {
          map.triggerRepaint();
        }
      }
    },
    setTheme,
    getMap() { return map; },
  };
})();
