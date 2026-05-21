// dashboard/js/app.js — Orchestration principale v2

(async () => {

  // ── Status API ─────────────────────────────────────────────────────
  const dot  = document.getElementById("status-dot");
  const txt  = document.getElementById("status-text");
  try {
    const h = await API.health();
    if (h?.status === "ok") {
      dot.className = "status-dot ok";
      const pg  = h.databases?.postgresql?.includes("connected") ? "PG ✓" : "PG —";
      const mdb = h.databases?.mongodb?.includes("connected")    ? "MDB ✓" : "MDB —";
      txt.textContent = `API connectée · ${pg} · ${mdb}`;
    }
  } catch {
    dot.className = "status-dot err";
    txt.textContent = "API hors ligne";
  }

  // ── Remplir les selects ────────────────────────────────────────────
  function fillSelect(id, includeAll = false) {
    const el = document.getElementById(id);
    if (!el) return;
    if (includeAll) el.innerHTML = `<option value="all">Tous Paris</option>`;
    CONFIG.ARRONDISSEMENTS.forEach(a => {
      el.innerHTML += `<option value="${a.value}">${a.label}</option>`;
    });
  }
  fillSelect("select-arr", true);
  fillSelect("compare-arr1");
  fillSelect("compare-arr2");
  fillSelect("evo-arr-filter", true);
  const ca2 = document.getElementById("compare-arr2");
  if (ca2) ca2.value = "2";

  // ── Init carte ─────────────────────────────────────────────────────
  MapModule.init();

  // ── Tabs ───────────────────────────────────────────────────────────
  const tabs   = document.querySelectorAll(".nav-btn");
  const panels = document.querySelectorAll(".tab-panel");
  const loaded = {};

  tabs.forEach(tab => {
    tab.addEventListener("click", async () => {
      tabs.forEach(t => t.classList.remove("active"));
      panels.forEach(p => p.classList.remove("active"));
      tab.classList.add("active");
      const id = "tab-" + tab.dataset.tab;
      document.getElementById(id)?.classList.add("active");

      if (tab.dataset.tab === "evolution" && !loaded.evolution) {
        loaded.evolution = true;
        await Charts.buildEvolution();
        await Charts.buildVolume();
        await Charts.buildDistribution();
      }
      if (tab.dataset.tab === "indicateurs" && !loaded.indicateurs) {
        loaded.indicateurs = true;
        await Charts.buildRadar();
        await Charts.buildRanking();
      }
    });
  });

  // ── Slider année ───────────────────────────────────────────────────
  const slider = document.getElementById("slider-annee");
  const lblAnn = document.getElementById("label-annee");

  slider.addEventListener("input", () => {
    const annee = parseInt(slider.value);
    lblAnn.textContent = annee;
    MapModule.update(annee, document.getElementById("select-indicateur").value);
    updateKPIs(annee);
  });

  // ── Select arrondissement ──────────────────────────────────────────
  document.getElementById("select-arr").addEventListener("change", async e => {
    const arr = e.target.value;
    const annee = parseInt(slider.value);
    MapModule.update(annee, document.getElementById("select-indicateur").value);
    await updateKPIs(annee, arr === "all" ? null : parseInt(arr));
  });

  // ── Select indicateur ──────────────────────────────────────────────
  document.getElementById("select-indicateur").addEventListener("change", e => {
    const annee = parseInt(slider.value);
    MapModule.update(annee, e.target.value);
  });

  // ── Filtre évolution ───────────────────────────────────────────────
  document.getElementById("evo-arr-filter")?.addEventListener("change", e => {
    Charts.buildEvolution(e.target.value);
  });

  // ── KPIs ───────────────────────────────────────────────────────────
  async function updateKPIs(annee, arrondissement = null) {
    try {
      const data = await API.getPrix({ arrondissement, anneeMin: annee, anneeMax: annee });
      const titre = document.getElementById("kpi-titre");

      titre.textContent = arrondissement
        ? `${arrondissement}${arrondissement===1?"er":"e"} arr. — ${annee}`
        : `Paris — ${annee}`;

      if (!data?.length) {
        ["kpi-prix","kpi-variation","kpi-ls","kpi-transactions"]
          .forEach(id => document.getElementById(id).textContent = "—");
        return;
      }

      const med = v => {
        const a = v.filter(Boolean).sort((a,b)=>a-b);
        return a.length ? a[Math.floor(a.length/2)] : null;
      };

      const prixMed = arrondissement ? data[0]?.prix_m2_median : med(data.map(d=>d.prix_m2_median));
      const varPct  = arrondissement ? data[0]?.prix_m2_variation_pct : med(data.map(d=>d.prix_m2_variation_pct).filter(v=>v!=null));
      const totalTx = data.reduce((s,d) => s + (d.nb_transactions||0), 0);

      const setPrix = document.getElementById("kpi-prix");
      const setVar  = document.getElementById("kpi-variation");
      const setTx   = document.getElementById("kpi-transactions");

      setPrix.textContent = prixMed ? Math.round(prixMed).toLocaleString("fr-FR") + " €" : "—";
      setTx.textContent   = totalTx ? totalTx.toLocaleString("fr-FR") : "—";

      if (varPct != null && !isNaN(varPct)) {
        setVar.textContent = (varPct > 0 ? "+" : "") + varPct.toFixed(1) + "%";
        setVar.style.color = varPct > 0 ? "var(--red)" : "var(--green)";
      } else {
        setVar.textContent = "—";
        setVar.style.color = "";
      }

      // Logements sociaux
      try {
        const ls = await API.getLogementsSociaux(arrondissement);
        const lsRows = ls.filter(d => d.annee == annee) || ls;
        const pct = arrondissement
          ? lsRows[0]?.part_logements_sociaux_pct
          : med(lsRows.map(d=>d.part_logements_sociaux_pct).filter(v=>v!=null));
        const elLs = document.getElementById("kpi-ls");
        elLs.textContent = pct != null && !isNaN(pct)
          ? (pct > 100 ? Math.round(pct).toLocaleString("fr-FR") : pct.toFixed(1) + "%")
          : "—";
      } catch { document.getElementById("kpi-ls").textContent = "—"; }

    } catch(e) { console.warn("KPI:", e.message); }
  }

  // ── Timeline play ──────────────────────────────────────────────────
  let playInterval = null;
  const btnPlay = document.getElementById("btn-play");
  const playIcon = document.getElementById("play-icon");
  const stopIcon = document.getElementById("stop-icon");

  btnPlay.addEventListener("click", () => {
    if (playInterval) {
      clearInterval(playInterval);
      playInterval = null;
      btnPlay.classList.remove("playing");
      playIcon.style.display = "";
      stopIcon.style.display = "none";
      return;
    }
    btnPlay.classList.add("playing");
    playIcon.style.display = "none";
    stopIcon.style.display = "";

    let cur = parseInt(slider.min);
    playInterval = setInterval(() => {
      slider.value = cur;
      slider.dispatchEvent(new Event("input"));
      cur++;
      if (cur > parseInt(slider.max)) {
        clearInterval(playInterval);
        playInterval = null;
        btnPlay.classList.remove("playing");
        playIcon.style.display = "";
        stopIcon.style.display = "none";
      }
    }, 1400);
  });

  // ── Comparaison ────────────────────────────────────────────────────
  document.getElementById("btn-compare")?.addEventListener("click", async () => {
    const arr1  = parseInt(document.getElementById("compare-arr1").value);
    const arr2  = parseInt(document.getElementById("compare-arr2").value);
    const annee = parseInt(slider.value);
    await Charts.buildComparaison(arr1, arr2, annee);
  });

  // ── Panneau détail (clic carte) ────────────────────────────────────
  window.openDetailPanel = async (arr, annee) => {
    const panel = document.getElementById("detail-panel");
    const num   = document.getElementById("detail-num");
    const name  = document.getElementById("detail-name");
    const body  = document.getElementById("detail-body");

    num.textContent  = arr;
    name.textContent = `${arr}${arr===1?"er":"e"} Arrondissement · ${annee}`;
    body.innerHTML   = `<div class="loading-pulse">Chargement…</div>`;
    panel.classList.add("open");

    try {
      const [prixArr, indicArr, lsArr] = await Promise.all([
        API.getPrix({ arrondissement: arr, anneeMin: annee, anneeMax: annee }),
        API.getIndicateurs(arr),
        API.getLogementsSociaux(arr),
      ]);
      const p  = prixArr?.[0] || {};
      const ind = indicArr?.[0] || {};
      const ls = lsArr?.find(d => d.annee == annee) || lsArr?.[0] || {};

      const SCORES = [
        ["Accessibilité",   ind.score_accessibilite],
        ["Qualité de vie",  ind.score_qualite_vie],
        ["Sécurité",        ind.score_securite],
        ["Accès. immo.",    ind.score_accessibilite_immo],
      ];

      body.innerHTML = `
        <div class="detail-metric">
          <span class="detail-metric-label">Prix/m² médian</span>
          <span class="detail-metric-val">${p.prix_m2_median ? Math.round(p.prix_m2_median).toLocaleString("fr-FR") + " €" : "—"}</span>
        </div>
        <div class="detail-metric">
          <span class="detail-metric-label">Variation annuelle</span>
          <span class="detail-metric-val ${(p.prix_m2_variation_pct||0) > 0 ? 'bad' : 'good'}">
            ${p.prix_m2_variation_pct != null ? (p.prix_m2_variation_pct > 0 ? "+" : "") + p.prix_m2_variation_pct.toFixed(1) + "%" : "—"}
          </span>
        </div>
        <div class="detail-metric">
          <span class="detail-metric-label">Transactions</span>
          <span class="detail-metric-val">${p.nb_transactions ? Math.round(p.nb_transactions).toLocaleString("fr-FR") : "—"}</span>
        </div>
        <div class="detail-metric">
          <span class="detail-metric-label">Logements sociaux</span>
          <span class="detail-metric-val">${ls.part_logements_sociaux_pct != null ? ls.part_logements_sociaux_pct.toFixed(1) + "%" : "—"}</span>
        </div>
        <div style="margin-top:4px">
          ${SCORES.map(([lbl, val]) => val != null ? `
            <div class="score-bar-wrap">
              <div class="score-bar-label"><span>${lbl}</span><span>${val.toFixed(1)}/10</span></div>
              <div class="score-bar"><div class="score-bar-fill" style="width:${val*10}%"></div></div>
            </div>
          ` : "").join("")}
        </div>
        ${ind.score_global != null ? `
          <div class="detail-metric" style="margin-top:4px">
            <span class="detail-metric-label">Score global</span>
            <span class="detail-metric-val ${ind.score_global >= 6 ? 'good' : ind.score_global <= 4 ? 'bad' : ''}">${ind.score_global.toFixed(1)} /10</span>
          </div>
        ` : ""}
      `;
    } catch(e) {
      body.innerHTML = `<div style="color:var(--red);font-size:12px">Erreur : ${e.message}</div>`;
    }
  };

  document.getElementById("detail-close")?.addEventListener("click", () => {
    document.getElementById("detail-panel")?.classList.remove("open");
  });

  // ── Init ───────────────────────────────────────────────────────────
  await updateKPIs(2023);

})();