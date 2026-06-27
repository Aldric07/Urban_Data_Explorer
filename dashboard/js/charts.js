// dashboard/js/charts.js v2

const Charts = (() => {
  let chartEvolution = null;
  let chartVolume    = null;
  let chartRadar     = null;
  let chartRanking   = null;

  // Defaults Chart.js
  Chart.defaults.color          = "#7c82a0";
  Chart.defaults.font.family    = "'Inter', -apple-system, BlinkMacSystemFont, sans-serif";
  Chart.defaults.font.size      = 12;
  Chart.defaults.font.weight    = "500";
  Chart.defaults.borderColor    = "rgba(255,255,255,0.06)";

  const GRID = { color: "rgba(255,255,255,0.05)", drawBorder: false };
  const TOOLTIP_STYLE = {
    backgroundColor: "rgba(7,11,20,0.92)",
    borderColor: "rgba(255,255,255,0.1)",
    borderWidth: 1,
    titleColor: "#eef0f8",
    bodyColor: "#7c82a0",
    padding: 12,
    cornerRadius: 10,
    titleFont: { weight: "700", size: 13 },
    bodyFont:  { size: 12 },
    displayColors: true,
    boxWidth: 8, boxHeight: 8, boxPadding: 4,
  };

  // ── Évolution prix/m² ─────────────────────────────────────────────────
  async function buildEvolution() {
    const canvas = document.getElementById("chart-evolution");
    if (!canvas) return;

    const raw = await API.getEvolution();
    const byArr = {};
    raw.forEach(d => {
      if (!byArr[d.arrondissement]) byArr[d.arrondissement] = {};
      byArr[d.arrondissement][d.annee] = d.prix_m2_median;
    });

    const annees   = CONFIG.ANNEES;
    const datasets = Object.entries(byArr).map(([arr, vals], i) => {
      const color = CONFIG.CHART_COLORS[i % CONFIG.CHART_COLORS.length];
      return {
        label: `${arr}e`,
        data: annees.map(a => vals[a] ?? null),
        borderColor: color,
        backgroundColor: color + "18",
        fill: false,
        tension: 0.38,
        pointRadius: 3.5,
        pointHoverRadius: 6,
        borderWidth: 1.8,
        pointBackgroundColor: color,
        pointBorderColor: "var(--bg)",
        pointBorderWidth: 1.5,
      };
    });

    if (chartEvolution) chartEvolution.destroy();
    chartEvolution = new Chart(canvas, {
      type: "line",
      data: { labels: annees, datasets },
      options: {
        responsive: true, maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: { display: false },
          tooltip: {
            ...TOOLTIP_STYLE,
            callbacks: {
              title: ctx => `Année ${ctx[0].label}`,
              label: ctx => ` ${ctx.dataset.label} : ${Math.round(ctx.parsed.y).toLocaleString("fr-FR")} €/m²`,
            },
          },
        },
        scales: {
          y: {
            grid: GRID,
            ticks: { callback: v => Math.round(v / 1000) + "k €", color: "#7c82a0" },
            border: { display: false },
          },
          x: {
            grid: { ...GRID, display: false },
            ticks: { color: "#7c82a0" },
            border: { display: false },
          },
        },
      },
    });
  }

  // ── Volume de transactions ────────────────────────────────────────────
  async function buildVolume() {
    const canvas = document.getElementById("chart-volume");
    if (!canvas) return;

    const raw = await API.getEvolution();
    const byAnnee = {};
    raw.forEach(d => {
      byAnnee[d.annee] = (byAnnee[d.annee] || 0) + (d.nb_transactions || 0);
    });

    const annees  = CONFIG.ANNEES.filter(a => byAnnee[a]);
    const volumes = annees.map(a => byAnnee[a] || 0);
    const maxVol  = Math.max(...volumes);

    const bgColors = volumes.map(v => {
      const ratio = v / maxVol;
      return `rgba(99,102,241,${0.25 + ratio * 0.55})`;
    });

    if (chartVolume) chartVolume.destroy();
    chartVolume = new Chart(canvas, {
      type: "bar",
      data: {
        labels: annees,
        datasets: [{
          label: "Transactions",
          data: volumes,
          backgroundColor: bgColors,
          borderColor: "rgba(99,102,241,0.6)",
          borderWidth: 1,
          borderRadius: 6,
          borderSkipped: false,
        }],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            ...TOOLTIP_STYLE,
            callbacks: {
              label: ctx => ` ${ctx.parsed.y.toLocaleString("fr-FR")} transactions`,
            },
          },
        },
        scales: {
          y: {
            grid: GRID,
            ticks: { callback: v => v.toLocaleString("fr-FR"), color: "#7c82a0" },
            border: { display: false },
          },
          x: {
            grid: { ...GRID, display: false },
            ticks: { color: "#7c82a0" },
            border: { display: false },
          },
        },
      },
    });
  }

  // ── Radar indicateurs ─────────────────────────────────────────────────
  async function buildRadar(arrondissement = null) {
    const canvas = document.getElementById("chart-radar");
    if (!canvas) return;

    const raw = await API.getIndicateurs(arrondissement);
    const SCORE_KEYS = [
      "score_accessibilite",
      "score_qualite_vie",
      "score_securite",
      "score_accessibilite_immo",
    ];
    const labels = SCORE_KEYS.map(k => CONFIG.INDICATEURS_LABELS[k] || k);

    const items = arrondissement
      ? raw.filter(d => d.arrondissement == arrondissement)
      : raw.sort((a, b) => (b.score_global || 0) - (a.score_global || 0)).slice(0, 5);

    const datasets = items.map((d, i) => {
      const color = CONFIG.CHART_COLORS[i];
      return {
        label: `${d.arrondissement}e arr.`,
        data: SCORE_KEYS.map(k => d[k] ?? 0),
        borderColor: color,
        backgroundColor: color + "20",
        pointBackgroundColor: color,
        pointBorderColor: "var(--bg)",
        pointBorderWidth: 1.5,
        pointRadius: 4,
        borderWidth: 1.8,
      };
    });

    if (chartRadar) chartRadar.destroy();
    chartRadar = new Chart(canvas, {
      type: "radar",
      data: { labels, datasets },
      options: {
        responsive: true, maintainAspectRatio: false,
        scales: {
          r: {
            min: 0, max: 10,
            grid: { color: "rgba(255,255,255,0.06)" },
            angleLines: { color: "rgba(255,255,255,0.05)" },
            pointLabels: { color: "#7c82a0", font: { size: 11, weight: "600" }, padding: 8 },
            ticks: { display: false, stepSize: 2 },
          },
        },
        plugins: {
          legend: {
            labels: {
              color: "#7c82a0", boxWidth: 8, boxHeight: 8,
              padding: 14, font: { size: 11, weight: "600" },
            },
          },
          tooltip: { ...TOOLTIP_STYLE },
        },
      },
    });
  }

  // ── Ranking score global ──────────────────────────────────────────────
  async function buildRanking() {
    const canvas = document.getElementById("chart-ranking");
    if (!canvas) return;

    const raw    = await API.getIndicateurs();
    const sorted = [...raw].sort((a, b) => (b.score_global || 0) - (a.score_global || 0));
    const n      = sorted.length;

    const bgColors = sorted.map((_, i) =>
      i < 3           ? "rgba(16,185,129,0.28)"  :
      i >= n - 3      ? "rgba(239,68,68,0.22)"   :
                        "rgba(99,102,241,0.22)"
    );
    const bdColors = sorted.map((_, i) =>
      i < 3           ? "#10b981" :
      i >= n - 3      ? "#ef4444" :
                        "#6366f1"
    );

    if (chartRanking) chartRanking.destroy();
    chartRanking = new Chart(canvas, {
      type: "bar",
      data: {
        labels: sorted.map(d => `${d.arrondissement}e`),
        datasets: [{
          data: sorted.map(d => d.score_global?.toFixed(2) ?? 0),
          backgroundColor: bgColors,
          borderColor: bdColors,
          borderWidth: 1.5,
          borderRadius: 5,
          borderSkipped: false,
        }],
      },
      options: {
        indexAxis: "y",
        responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            ...TOOLTIP_STYLE,
            callbacks: {
              label: ctx => ` Score global : ${ctx.parsed.x} /10`,
            },
          },
        },
        scales: {
          x: {
            min: 0, max: 10,
            grid: GRID,
            ticks: { callback: v => v + "/10", color: "#7c82a0", stepSize: 2 },
            border: { display: false },
          },
          y: {
            grid: { display: false },
            ticks: { color: "#7c82a0", font: { size: 11 } },
            border: { display: false },
          },
        },
      },
    });
  }

  // ── Comparaison ───────────────────────────────────────────────────────
  async function buildComparaison(arr1, arr2, annee = 2023) {
    const container = document.getElementById("compare-result");
    container.innerHTML = `<div class="loading">Chargement de la comparaison…</div>`;

    try {
      const data = await API.getComparaison(arr1, arr2, annee);
      const p1 = data.prix?.find(d => d.arrondissement == arr1) || {};
      const p2 = data.prix?.find(d => d.arrondissement == arr2) || {};
      const i1 = data.indicateurs?.find(d => d.arrondissement == arr1) || {};
      const i2 = data.indicateurs?.find(d => d.arrondissement == arr2) || {};

      const metrics = [
        { label: "Prix/m² médian",        k: "prix_m2_median",             src: "prix",  fmt: v => Math.round(v).toLocaleString("fr-FR") + " €", lower: true,  sep: false },
        { label: "Transactions",          k: "nb_transactions",             src: "prix",  fmt: v => Math.round(v).toLocaleString("fr-FR"),          lower: false, sep: false },
        { label: "Log. sociaux",          k: "part_logements_sociaux_pct",  src: "prix",  fmt: v => v?.toFixed(1) + "%",                            lower: false, sep: false },
        { label: "Accessibilité",         k: "score_accessibilite",         src: "indic", fmt: v => v?.toFixed(2) + " /10",                         lower: false, sep: false },
        { label: "Qualité de vie",        k: "score_qualite_vie",           src: "indic", fmt: v => v?.toFixed(2) + " /10",                         lower: false, sep: false },
        // ── Sécurité — score composite + 3 composantes ───────────────────────
        { label: "🔒 Sécurité (score)",   k: "score_securite",              src: "indic", fmt: v => v?.toFixed(2) + " /10",                         lower: false, sep: true  },
        { label: "↳ Faits criminalité",   k: "nb_faits",                    src: "indic", fmt: v => Math.round(v).toLocaleString("fr-FR"),           lower: true,  sep: false },
        { label: "↳ Commissariats",       k: "nb_commissariats",            src: "indic", fmt: v => Math.round(v).toString(),                        lower: false, sep: false },
        { label: "↳ Casernes pompiers",   k: "nb_casernes",                 src: "indic", fmt: v => Math.round(v).toString(),                        lower: false, sep: false },
        // ─────────────────────────────────────────────────────────────────────
        { label: "Score global",          k: "score_global",                src: "indic", fmt: v => v?.toFixed(2) + " /10",                         lower: false, sep: true  },
      ];

      function getVal(m, isFirst) {
        const obj = m.src === "prix"
          ? (isFirst ? p1 : p2)
          : (isFirst ? i1 : i2);
        return obj[m.k];
      }

      function renderCard(isFirst) {
        const arr    = isFirst ? arr1 : arr2;
        const ordSuf = arr === 1 ? "er" : "e";
        const rows   = metrics.map(m => {
          // Séparateur visuel avant certaines sections
          const sepHtml = m.sep ? `<div class="compare-separator"></div>` : "";

          const v     = getVal(m, isFirst);
          const other = getVal(m, !isFirst);
          // Les sous-composantes (↳) n'ont pas de badge car c'est informatif
          const isSub = m.label.startsWith("↳");
          let cls = ""; let badge = "";
          if (!isSub && v != null && other != null && !isNaN(v) && !isNaN(other)) {
            const better = m.lower ? Number(v) < Number(other) : Number(v) > Number(other);
            cls   = better ? "better" : "worse";
            badge = better
              ? `<span class="badge better">✓ Meilleur</span>`
              : `<span class="badge worse">▼ Inférieur</span>`;
          }
          return `${sepHtml}<div class="compare-metric${isSub ? " compare-sub" : ""}">
            <span class="label">${m.label}</span>
            <span class="value ${cls}">${v != null ? m.fmt(v) : "—"} ${badge}</span>
          </div>`;
        }).join("");

        return `<div class="compare-card">
          <div class="compare-card-header">
            <span class="compare-arr-badge">${arr}${ordSuf} arrondissement</span>
          </div>
          ${rows}
        </div>`;
      }

      container.innerHTML = renderCard(true) + renderCard(false);

    } catch (e) {
      container.innerHTML = `<div class="loading" style="color:#ef4444;grid-column:span 2">Erreur : ${e.message}</div>`;
    }
  }

  return { buildEvolution, buildVolume, buildRadar, buildRanking, buildComparaison };
})();
