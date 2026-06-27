// dashboard/js/app.js v2

(async () => {

  // ── API status ──────────────────────────────────────────────────────────
  const statusEl = document.getElementById("api-status");
  try {
    const h = await API.health();
    if (h?.status === "ok") {
      statusEl.innerHTML = `<span class="status-dot"></span>${h.gold_ready ? "API connectée" : "Données partielles"}`;
      statusEl.className = "api-status " + (h.gold_ready ? "ok" : "");
    }
  } catch {
    statusEl.innerHTML = `<span class="status-dot"></span>Mode démo`;
    statusEl.className = "api-status err";
  }

  // ── Theme toggle ─────────────────────────────────────────────────────────
  const themeBtn = document.getElementById("theme-toggle");
  function _applyTheme(light) {
    document.body.classList.toggle("light-mode", light);
    themeBtn.textContent = light ? "☀️" : "🌙";
    themeBtn.title = light ? "Passer en mode sombre" : "Passer en mode clair";
  }
  _applyTheme(document.body.classList.contains("light-mode")); // sync icon with FOUC class
  themeBtn.addEventListener("click", () => {
    const goLight = !document.body.classList.contains("light-mode");
    _applyTheme(goLight);
    localStorage.setItem("theme", goLight ? "light" : "dark");
    MapModule.setTheme(goLight);
  });

  // ── Selects arrondissements ─────────────────────────────────────────────
  function fillArrSelect(id, includeAll = false) {
    const el = document.getElementById(id);
    if (!el) return;
    if (includeAll) el.innerHTML = `<option value="all">Tous les arrondissements</option>`;
    else el.innerHTML = "";
    CONFIG.ARRONDISSEMENTS.forEach(a => {
      el.innerHTML += `<option value="${a.value}">${a.label}</option>`;
    });
  }

  fillArrSelect("select-arr", true);
  fillArrSelect("compare-arr1");
  fillArrSelect("compare-arr2");
  document.getElementById("compare-arr2").value = "2";

  // Filtrage dynamique : désactive dans chaque dropdown la valeur sélectionnée dans l'autre
  function _syncCompareOptions() {
    const sel1 = document.getElementById("compare-arr1");
    const sel2 = document.getElementById("compare-arr2");
    Array.from(sel2.options).forEach(o => { o.disabled = o.value === sel1.value; });
    Array.from(sel1.options).forEach(o => { o.disabled = o.value === sel2.value; });
  }
  _syncCompareOptions();

  document.getElementById("compare-arr1").addEventListener("change", () => {
    const sel1 = document.getElementById("compare-arr1");
    const sel2 = document.getElementById("compare-arr2");
    // Si le second a la même valeur, passer au premier disponible
    if (sel2.value === sel1.value) {
      const next = Array.from(sel2.options).find(o => o.value !== sel1.value);
      if (next) sel2.value = next.value;
    }
    _syncCompareOptions();
    document.getElementById("compare-error").style.display = "none";
  });

  document.getElementById("compare-arr2").addEventListener("change", () => {
    const sel1 = document.getElementById("compare-arr1");
    const sel2 = document.getElementById("compare-arr2");
    if (sel1.value === sel2.value) {
      const next = Array.from(sel1.options).find(o => o.value !== sel2.value);
      if (next) sel1.value = next.value;
    }
    _syncCompareOptions();
    document.getElementById("compare-error").style.display = "none";
  });

  // ── Carte ────────────────────────────────────────────────────────────────
  MapModule.init();

  // ── Sidebar toggle ───────────────────────────────────────────────────────
  const sidebar      = document.getElementById("sidebar");
  const sidebarBtn   = document.getElementById("sidebar-toggle");
  const expandBtn    = document.getElementById("map-expand-btn");

  function toggleSidebar(forceOpen) {
    const shouldCollapse = forceOpen === true ? false
                         : forceOpen === false ? true
                         : !sidebar.classList.contains("collapsed");
    sidebar.classList.toggle("collapsed", shouldCollapse);
    if (expandBtn) expandBtn.style.display = shouldCollapse ? "flex" : "none";
    if (sidebarBtn) {
      sidebarBtn.querySelector("svg").style.transform = shouldCollapse ? "rotate(180deg)" : "";
    }
  }

  sidebarBtn?.addEventListener("click", () => toggleSidebar());
  expandBtn?.addEventListener("click", () => toggleSidebar(true));

  // ── Tabs ─────────────────────────────────────────────────────────────────
  const tabs   = document.querySelectorAll(".tab");
  const panels = document.querySelectorAll(".tab-panel");
  let chartsLoaded = {};

  tabs.forEach(tab => {
    tab.addEventListener("click", async () => {
      tabs.forEach(t => t.classList.remove("active"));
      panels.forEach(p => p.classList.remove("active"));
      tab.classList.add("active");
      document.getElementById("tab-" + tab.dataset.tab).classList.add("active");

      // Resync WebGL after the tab panel becomes visible
      if (tab.dataset.tab === "carte") {
        requestAnimationFrame(() => MapModule.resize());
      }

      if (tab.dataset.tab === "evolution" && !chartsLoaded.evolution) {
        chartsLoaded.evolution = true;
        await Charts.buildEvolution();
        await Charts.buildVolume();
      }
      if (tab.dataset.tab === "indicateurs" && !chartsLoaded.indicateurs) {
        chartsLoaded.indicateurs = true;
        await Charts.buildRadar();
        await Charts.buildRanking();
      }
      if (tab.dataset.tab === "comparaison" && !chartsLoaded.comparaison) {
        chartsLoaded.comparaison = true;
        const a1 = parseInt(document.getElementById("compare-arr1").value);
        const a2 = parseInt(document.getElementById("compare-arr2").value);
        await Charts.buildComparaison(a1, a2, parseInt(sliderAnnee.value));
      }
    });
  });

  // ── Slider année ──────────────────────────────────────────────────────────
  const sliderAnnee = document.getElementById("slider-annee");
  const labelAnnee  = document.getElementById("label-annee");

  sliderAnnee.addEventListener("input", () => {
    const annee = parseInt(sliderAnnee.value);
    labelAnnee.textContent = annee;
    MapModule.update(annee, document.getElementById("select-indicateur").value);
    updateKPIs(annee, currentArr());
  });

  document.getElementById("select-arr").addEventListener("change", async () => {
    const annee = parseInt(sliderAnnee.value);
    MapModule.update(annee, document.getElementById("select-indicateur").value);
    await updateKPIs(annee, currentArr());
  });

  document.getElementById("select-indicateur").addEventListener("change", e => {
    MapModule.update(parseInt(sliderAnnee.value), e.target.value);
  });

  function currentArr() {
    const v = document.getElementById("select-arr").value;
    return v === "all" ? null : parseInt(v);
  }

  // ── KPIs avec animation ───────────────────────────────────────────────────
  function animateValue(el, to, fmt) {
    const from = parseFloat(el.dataset.raw) || 0;
    if (isNaN(from) || isNaN(to)) { el.textContent = fmt(to); return; }
    const start = performance.now();
    const dur   = 550;
    (function tick(now) {
      const p = Math.min((now - start) / dur, 1);
      const ease = 1 - Math.pow(1 - p, 3);
      el.textContent = fmt(from + (to - from) * ease);
      if (p < 1) requestAnimationFrame(tick);
    })(start);
    el.dataset.raw = to;
  }

  async function updateKPIs(annee, arrondissement = null) {
    const titre = document.getElementById("kpi-titre");
    titre.textContent = arrondissement
      ? `${arrondissement}${arrondissement === 1 ? "er" : "e"} arr. — ${annee}`
      : `Paris — ${annee}`;

    try {
      const data = await API.getPrix({ arrondissement, anneeMin: annee, anneeMax: annee });
      if (!data?.length) {
        ["kpi-prix","kpi-variation","kpi-ls","kpi-transactions"].forEach(id => {
          document.getElementById(id).textContent = "—";
        });
        return;
      }

      const prixMedian = median(data.map(d => d.prix_m2_median).filter(Boolean));
      const variation  = arrondissement
        ? data[0]?.prix_m2_variation_pct
        : median(data.map(d => d.prix_m2_variation_pct).filter(v => v != null));
      const totalTx = data.reduce((s, d) => s + (d.nb_transactions || 0), 0);

      const elPrix = document.getElementById("kpi-prix");
      const elVar  = document.getElementById("kpi-variation");
      const elTx   = document.getElementById("kpi-transactions");

      if (prixMedian) {
        animateValue(elPrix, prixMedian, v => Math.round(v).toLocaleString("fr-FR") + " €");
      } else { elPrix.textContent = "—"; delete elPrix.dataset.raw; }

      if (variation != null) {
        const sign = variation > 0 ? "+" : "";
        elVar.textContent = sign + variation.toFixed(1) + "%";
        elVar.className   = "kpi-value " + (variation > 0 ? "positive" : variation < 0 ? "negative" : "");
      } else { elVar.textContent = "—"; elVar.className = "kpi-value"; }

      if (totalTx) {
        animateValue(elTx, totalTx, v => Math.round(v).toLocaleString("fr-FR"));
      } else { elTx.textContent = "—"; delete elTx.dataset.raw; }

      // Logements sociaux
      try {
        const ls = await API.getLogementsSociaux(arrondissement);
        let rows = ls.filter(d => d.annee == annee);
        if (!rows.length) rows = ls;
        const pct = arrondissement
          ? (rows[0]?.part_logements_sociaux_pct ?? rows[0]?.nb_logements_sociaux)
          : median(rows.map(d => d.part_logements_sociaux_pct).filter(v => v != null));
        const elLs = document.getElementById("kpi-ls");
        if (pct != null && !isNaN(pct)) {
          elLs.textContent = pct > 100
            ? Math.round(pct).toLocaleString("fr-FR")
            : pct.toFixed(1) + "%";
        } else { elLs.textContent = "—"; }
      } catch { document.getElementById("kpi-ls").textContent = "—"; }

    } catch (e) { console.warn("KPI update failed:", e.message); }
  }

  // ── Timeline play ─────────────────────────────────────────────────────────
  let playInterval = null;
  const btnPlay    = document.getElementById("btn-play");
  const playIcon   = document.getElementById("play-icon");
  const playLabel  = document.getElementById("play-label");

  const ICON_PLAY = '<polygon points="5 3 19 12 5 21 5 3"/>';
  const ICON_STOP = '<rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/>';

  btnPlay.addEventListener("click", () => {
    if (playInterval) {
      clearInterval(playInterval);
      playInterval = null;
      btnPlay.classList.remove("playing");
      playIcon.innerHTML = ICON_PLAY;
      playLabel.textContent = "Lecture timeline";
      return;
    }
    btnPlay.classList.add("playing");
    playIcon.innerHTML = ICON_STOP;
    playLabel.textContent = "Arrêter";
    let cur = parseInt(sliderAnnee.min);
    playInterval = setInterval(() => {
      sliderAnnee.value = cur;
      sliderAnnee.dispatchEvent(new Event("input"));
      cur++;
      if (cur > parseInt(sliderAnnee.max)) {
        clearInterval(playInterval);
        playInterval = null;
        btnPlay.classList.remove("playing");
        playIcon.innerHTML = ICON_PLAY;
        playLabel.textContent = "Lecture timeline";
      }
    }, 1200);
  });

  // ── Comparaison ───────────────────────────────────────────────────────────
  document.getElementById("btn-compare").addEventListener("click", async () => {
    const arr1     = parseInt(document.getElementById("compare-arr1").value);
    const arr2     = parseInt(document.getElementById("compare-arr2").value);
    const errorEl  = document.getElementById("compare-error");

    if (arr1 === arr2) {
      errorEl.style.display = "block";
      return;
    }
    errorEl.style.display = "none";
    chartsLoaded.comparaison = true;
    await Charts.buildComparaison(arr1, arr2, parseInt(sliderAnnee.value));
  });

  // ── Utilitaires ───────────────────────────────────────────────────────────
  function median(arr) {
    if (!arr.length) return null;
    const s = [...arr].sort((a, b) => a - b);
    const m = Math.floor(s.length / 2);
    return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
  }

  // ── Init ──────────────────────────────────────────────────────────────────
  await updateKPIs(2023);

  // ── Air Quality streaming ─────────────────────────────────────────────────
  const AQ_POLL_MS   = 30_000;   // poll toutes les 30s
  let   aqMarkers    = [];       // marqueurs MapLibre actifs
  let   aqPollTimer  = null;

  const aqBadge      = document.getElementById("aq-badge");
  const aqStatus     = document.getElementById("aq-status");
  const aqAlertsList = document.getElementById("aq-alerts-list");
  const aqUpdated    = document.getElementById("aq-updated");
  const aqSource     = document.getElementById("aq-source");

  const ARR_CENTERS = {
    1:[2.3475,48.8603], 2:[2.3494,48.8678], 3:[2.3604,48.8637], 4:[2.3538,48.8534],
    5:[2.3499,48.8463], 6:[2.3336,48.8491], 7:[2.3137,48.8566], 8:[2.3097,48.8742],
    9:[2.3384,48.8769], 10:[2.3606,48.8773], 11:[2.3790,48.8594], 12:[2.3999,48.8409],
    13:[2.3652,48.8282], 14:[2.3266,48.8286], 15:[2.2959,48.8422], 16:[2.2685,48.8638],
    17:[2.3127,48.8847], 18:[2.3470,48.8919], 19:[2.3873,48.8830], 20:[2.3980,48.8647],
  };

  function _aqArrLabel(arr) {
    return `${arr}${arr === 1 ? "er" : "e"}`;
  }

  function clearAqMarkers() {
    aqMarkers.forEach(m => m.remove());
    aqMarkers = [];
  }

  function renderAqMarkers(alerts) {
    clearAqMarkers();
    if (!window.MapModule || !MapModule.getMap) return;
    const map = MapModule.getMap ? MapModule.getMap() : null;
    if (!map) return;

    alerts.forEach(alert => {
      const center = ARR_CENTERS[alert.arrondissement];
      if (!center) return;

      const el = document.createElement("div");
      el.className = `aq-map-marker ${alert.alert_level}`;
      el.title = `${_aqArrLabel(alert.arrondissement)} arr. — IQA ${Math.round(alert.iqa)} (${alert.alert_level})`;

      try {
        const { maplibregl } = window;
        if (maplibregl) {
          const marker = new maplibregl.Marker({ element: el })
            .setLngLat(center)
            .addTo(map);
          aqMarkers.push(marker);
        }
      } catch (_) {}
    });
  }

  function renderAqWidget(data) {
    const n = data.alerts_active || 0;

    // Badge dans le titre de la section
    if (n === 0) {
      aqBadge.style.display = "none";
      aqStatus.className    = "aq-status-ok";
      aqStatus.textContent  = "Qualité de l'air : bonne";
    } else {
      const worstLevel = data.alerts.some(a => a.alert_level === "rouge") ? "rouge" : "orange";
      aqBadge.className   = `aq-badge ${worstLevel}`;
      aqBadge.textContent = `${n} alerte${n > 1 ? "s" : ""}`;
      aqBadge.style.display = "inline-flex";
      aqStatus.className  = "aq-status-alert";
      aqStatus.textContent = worstLevel === "rouge"
        ? `${n} arrondissement${n > 1 ? "s" : ""} en alerte rouge`
        : `${n} arrondissement${n > 1 ? "s" : ""} en alerte orange`;
    }

    // Liste des alertes
    aqAlertsList.innerHTML = "";
    if (data.alerts && data.alerts.length) {
      const wrap = document.createElement("div");
      wrap.className = "aq-alerts-list";
      data.alerts.forEach(a => {
        const row = document.createElement("div");
        row.className = `aq-alert-row ${a.alert_level}`;
        row.innerHTML = `
          <span class="aq-dot ${a.alert_level}"></span>
          <span class="aq-arr-name">${_aqArrLabel(a.arrondissement)} arr.</span>
          <span class="aq-iqa ${a.alert_level}">IQA ${Math.round(a.iqa)}</span>
        `;
        wrap.appendChild(row);
      });
      aqAlertsList.appendChild(wrap);
    }

    // Horodatage
    if (data.updated_at) {
      const d = new Date(data.updated_at);
      aqUpdated.textContent = `Mise à jour : ${d.toLocaleTimeString("fr-FR")}`;
    }

    // Source des données
    if (aqSource) {
      if (data.source === "airparif_live") {
        aqSource.textContent  = "⬤ Airparif WFS (données réelles)";
        aqSource.className    = "aq-source live";
      } else if (data.source === "bronze_fallback") {
        aqSource.textContent  = "⬤ Simulation Bronze (fallback)";
        aqSource.className    = "aq-source fallback";
      } else {
        aqSource.textContent  = "";
        aqSource.className    = "aq-source";
      }
    }

    // Marqueurs carte
    renderAqMarkers(data.alerts || []);
  }

  async function pollAirQuality() {
    try {
      const data = await API.getAirQuality({ hours: 24 });
      renderAqWidget(data);
    } catch (err) {
      aqStatus.className   = "aq-status-error";
      aqStatus.textContent = err.name === "AbortError"
        ? "Données indisponibles (délai dépassé)"
        : "Données indisponibles";
      aqBadge.style.display = "none";
    }
  }

  // Premier appel immédiat, puis polling
  await pollAirQuality();
  aqPollTimer = setInterval(pollAirQuality, AQ_POLL_MS);

})();
