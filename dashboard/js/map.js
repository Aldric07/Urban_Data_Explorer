// dashboard/js/map.js — carte choroplèthe MapLibre GL JS
// Fix logements sociaux : part_logements_sociaux_pct vient du Gold directement

const MapModule = (() => {
  let map = null;
  let prixData  = {};   // "arr_annee" → données DVF
  let indicData = {};   // arr → scores custom
  let lsData    = {};   // arr → part_logements_sociaux_pct

  // GeoJSON Paris embarqué (fallback si API indisponible)
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

  // ── Init ──────────────────────────────────────────────────────────────
  function init() {
    map = new maplibregl.Map({
      container: "map",
      style: {
        version: 8,
        sources: {
          "carto-dark": {
            type: "raster",
            tiles: ["https://basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"],
            tileSize: 256,
            attribution: "© CartoDB © OpenStreetMap",
          },
        },
        layers: [{ id: "background", type: "raster", source: "carto-dark" }],
      },
      center: [2.3488, 48.8534],
      zoom: 11.5,
    });
    map.on("load", loadData);
  }

  // ── Chargement données ─────────────────────────────────────────────────
  async function loadData() {
    try {
      // GeoJSON
      let geo = null;
      try {
        geo = await API.getGeoJSON();
        if (!geo?.features?.length) throw new Error("vide");
      } catch {
        console.warn("GeoJSON API indisponible — GeoJSON embarqué utilisé");
        geo = PARIS_GEOJSON;
      }

      geo.features.forEach(f => {
        f.properties._arr = extractArr(f.properties);
      });
      window._geojsonData = geo;

      // Chargement parallèle : prix, indicateurs, logements sociaux
      const [prix, indic, ls] = await Promise.all([
        API.getEvolution(),
        API.getIndicateurs(),
        API.getLogementsSociaux(),
      ]);

      // Index prix par "arr_annee"
      prix.forEach(d => {
        prixData[`${d.arrondissement}_${d.annee}`] = d;
      });

      // Index indicateurs par arrondissement
      indic.forEach(d => {
        indicData[d.arrondissement] = d;
      });

      // Index logements sociaux par arrondissement
      // part_logements_sociaux_pct est identique pour toutes les années (RPLS 2022)
      ls.forEach(d => {
        if (d.part_logements_sociaux_pct != null) {
          lsData[d.arrondissement] = d.part_logements_sociaux_pct;
        }
      });

      console.log("lsData chargé :", lsData);

      buildChoropleth(2023, "prix_m2_median");
    } catch (e) {
      console.error("Erreur loadData:", e);
    }
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

  // ── Récupère la valeur selon l'indicateur ──────────────────────────────
  function getValue(arr, annee, indicateur) {
    if (!arr) return null;

    // Scores composites → indicData
    if (indicateur.startsWith("score_")) {
      return indicData[arr]?.[indicateur] ?? null;
    }

    // Logements sociaux → lsData (indépendant de l'année)
    if (indicateur === "part_logements_sociaux_pct") {
      return lsData[arr] ?? null;
    }

    // Prix et données DVF → prixData
    return prixData[`${arr}_${annee}`]?.[indicateur] ?? null;
  }

  // ── Choroplèthe ────────────────────────────────────────────────────────
  function buildChoropleth(annee, indicateur) {
    const geo = window._geojsonData;
    if (!geo || !map) return;

    const enriched = JSON.parse(JSON.stringify(geo));
    enriched.features.forEach(f => {
      const arr = f.properties._arr;
      const val = getValue(arr, annee, indicateur);

      // Copie toutes les données utiles pour le tooltip
      if (arr) {
        Object.assign(f.properties, prixData[`${arr}_${annee}`] || {});
        Object.assign(f.properties, indicData[arr] || {});
        f.properties.part_logements_sociaux_pct = lsData[arr] ?? null;
      }
      f.properties._arr   = arr;
      f.properties._value = (val != null && !isNaN(Number(val))) ? Number(val) : null;
    });

    // Supprime couches existantes
    ["fill-arr","line-arr","fill-hover"].forEach(id => {
      if (map.getLayer(id)) map.removeLayer(id);
    });
    if (map.getSource("arr")) map.removeSource("arr");

    const values = enriched.features
      .map(f => f.properties._value)
      .filter(v => v != null);

    if (!values.length) {
      console.warn("Aucune valeur pour l'indicateur:", indicateur);
      return;
    }

    const min = Math.min(...values);
    const max = Math.max(...values);

    map.addSource("arr", { type: "geojson", data: enriched });

    map.addLayer({
      id: "fill-arr", type: "fill", source: "arr",
      paint: {
        "fill-color": buildColorExpr(min, max, indicateur),
        "fill-opacity": 0.78,
      },
    });
    map.addLayer({
      id: "line-arr", type: "line", source: "arr",
      paint: { "line-color": "#ffffff", "line-width": 1.5, "line-opacity": 0.6 },
    });
    map.addLayer({
      id: "fill-hover", type: "fill", source: "arr",
      filter: ["==", ["get", "_arr"], -1],
      paint: { "fill-color": "#ffffff", "fill-opacity": 0.2 },
    });

    setupHover(indicateur);
    buildLegende(min, max, indicateur);
  }

  // ── Palette couleur ────────────────────────────────────────────────────
  function buildColorExpr(min, max, indicateur) {
    const colors = indicateur.startsWith("score_")
      ? CONFIG.COLORS_SCORE : CONFIG.COLORS_PRIX;
    const step = (max - min) / (colors.length - 1 || 1);
    const stops = colors.flatMap((c, i) => [min + i * step, c]);
    return ["interpolate", ["linear"],
      ["coalesce", ["get", "_value"], min], ...stops];
  }

  // ── Légende ────────────────────────────────────────────────────────────
  function buildLegende(min, max, indicateur) {
    const el = document.getElementById("legende-container");
    if (!el) return;
    const colors = indicateur.startsWith("score_")
      ? CONFIG.COLORS_SCORE : CONFIG.COLORS_PRIX;
    const step = (max - min) / (colors.length - 1 || 1);
    el.innerHTML = colors.map((c, i) =>
      `<div class="legende-item">
        <div class="legende-color" style="background:${c}"></div>
        <span>${fmt(min + i * step, indicateur)}</span>
      </div>`
    ).join("");
  }

  // ── Hover tooltip ──────────────────────────────────────────────────────
  function setupHover(indicateur) {
    const tip = document.getElementById("tooltip");
    map.on("mousemove", "fill-arr", e => {
      map.getCanvas().style.cursor = "pointer";
      const p   = e.features[0].properties;
      const arr = p._arr;
      if (!arr) return;
      map.setFilter("fill-hover", ["==", ["get", "_arr"], arr]);

      const varPct = p.prix_m2_variation_pct;
      const ls_pct = p.part_logements_sociaux_pct;
      tip.innerHTML = `
        <h3>${arr}${arr === 1 ? "er" : "e"} arrondissement</h3>
        <div class="tt-row">
          <span>${CONFIG.INDICATEURS_LABELS[indicateur] || indicateur}</span>
          <span>${fmt(p._value, indicateur)}</span>
        </div>
        ${p.prix_m2_median ? `<div class="tt-row"><span>Prix/m²</span><span>${Math.round(p.prix_m2_median).toLocaleString("fr-FR")} €</span></div>` : ""}
        ${ls_pct != null ? `<div class="tt-row"><span>Log. sociaux</span><span>${Number(ls_pct).toFixed(1)}%</span></div>` : ""}
        ${p.nb_transactions ? `<div class="tt-row"><span>Transactions</span><span>${Math.round(p.nb_transactions).toLocaleString("fr-FR")}</span></div>` : ""}
        ${varPct != null && !isNaN(varPct) ? `<div class="tt-row"><span>Variation</span><span>${Number(varPct) > 0 ? "+" : ""}${Number(varPct).toFixed(1)}%</span></div>` : ""}
      `;
      tip.style.left = (e.point.x + 12) + "px";
      tip.style.top  = (e.point.y - 10) + "px";
      tip.classList.add("visible");
    });
    map.on("mouseleave", "fill-arr", () => {
      map.getCanvas().style.cursor = "";
      map.setFilter("fill-hover", ["==", ["get", "_arr"], -1]);
      tip.classList.remove("visible");
    });
    map.on("click", "fill-arr", e => {
      const arr   = e.features[0].properties._arr;
      const annee = parseInt(document.getElementById("slider-annee")?.value || 2023);
      if (!arr) return;
      // Met à jour le select
      const sel = document.getElementById("select-arr");
      if (sel) { sel.value = arr; sel.dispatchEvent(new Event("change")); }
      // Ouvre le panneau détail
      if (typeof window.openDetailPanel === "function") {
        window.openDetailPanel(arr, annee);
      }
    });
  }

  // ── Formatage valeur ───────────────────────────────────────────────────
  function fmt(val, ind) {
    if (val == null || isNaN(Number(val))) return "—";
    const v = Number(val);
    if (ind === "prix_m2_median" || ind === "prix_m2_moyen")
      return v.toLocaleString("fr-FR", {maximumFractionDigits:0}) + " €/m²";
    if (ind.includes("pct") || ind.includes("sociaux"))
      return v.toFixed(1) + "%";
    if (ind.startsWith("score_"))
      return v.toFixed(1) + " /10";
    return v.toLocaleString("fr-FR", {maximumFractionDigits:0});
  }

  return {
    init,
    update(annee, indicateur) { buildChoropleth(annee, indicateur); },
  };
})();