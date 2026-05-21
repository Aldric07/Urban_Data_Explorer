// dashboard/js/charts.js — Graphiques Chart.js redesign

const Charts = (() => {
  let chartEvo = null, chartVol = null, chartDist = null;
  let chartRadar = null, chartRank = null;

  // Defaults Chart.js
  Chart.defaults.color = "#64748b";
  Chart.defaults.font.family = "'DM Sans', sans-serif";
  Chart.defaults.font.size = 12;

  const gridColor = "rgba(99,130,190,0.1)";

  // ── Évolution prix/m² ───────────────────────────────────────────────
  async function buildEvolution(arrFilter = "all") {
    const canvas = document.getElementById("chart-evolution");
    if (!canvas) return;
    const raw = await API.getEvolution();

    // Groupe par arrondissement
    const byArr = {};
    raw.forEach(d => {
      if (!byArr[d.arrondissement]) byArr[d.arrondissement] = {};
      byArr[d.arrondissement][d.annee] = d.prix_m2_median;
    });

    // Sélection des arrondissements à afficher
    let arrs;
    if (arrFilter !== "all" && !isNaN(Number(arrFilter))) {
      arrs = [Number(arrFilter)];
    } else {
      // Top 5 par prix 2024
      arrs = Object.entries(byArr)
        .sort((a,b) => (b[1][2024]||0) - (a[1][2024]||0))
        .slice(0,5).map(([k]) => Number(k));
    }

    const datasets = arrs.map((arr, i) => ({
      label: `${arr}e arr.`,
      data: CONFIG.ANNEES.map(a => byArr[arr]?.[a] ?? null),
      borderColor: CONFIG.CHART_COLORS[i],
      backgroundColor: CONFIG.CHART_COLORS[i] + "18",
      tension: 0.4,
      pointRadius: 5,
      pointHoverRadius: 8,
      borderWidth: 2.5,
      fill: true,
    }));

    if (chartEvo) chartEvo.destroy();
    chartEvo = new Chart(canvas, {
      type: "line",
      data: { labels: CONFIG.ANNEES, datasets },
      options: {
        responsive: true, maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: { labels: { color: "#94a3b8", boxWidth: 10, padding: 16 } },
          tooltip: {
            backgroundColor: "#111827",
            borderColor: "rgba(99,130,190,0.3)",
            borderWidth: 1,
            callbacks: {
              label: ctx => ` ${ctx.dataset.label} : ${Math.round(ctx.parsed.y).toLocaleString("fr-FR")} €/m²`
            }
          }
        },
        scales: {
          y: { grid: { color: gridColor }, ticks: { callback: v => (v/1000).toFixed(0) + "k €" } },
          x: { grid: { color: gridColor } },
        }
      }
    });
  }

  // ── Volume de transactions ──────────────────────────────────────────
  async function buildVolume() {
    const canvas = document.getElementById("chart-volume");
    if (!canvas) return;
    const raw = await API.getEvolution();

    const byAnnee = {};
    raw.forEach(d => { byAnnee[d.annee] = (byAnnee[d.annee]||0) + (d.nb_transactions||0); });

    if (chartVol) chartVol.destroy();
    chartVol = new Chart(canvas, {
      type: "bar",
      data: {
        labels: CONFIG.ANNEES,
        datasets: [{
          data: CONFIG.ANNEES.map(a => byAnnee[a]||0),
          backgroundColor: CONFIG.ANNEES.map((_, i) =>
            `rgba(59,130,246,${0.4 + i * 0.15})`),
          borderColor: CONFIG.ANNEES.map(() => "#3b82f6"),
          borderWidth: 1,
          borderRadius: 6,
        }]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: "#111827",
            borderColor: "rgba(99,130,190,0.3)",
            borderWidth: 1,
            callbacks: { label: ctx => ` ${ctx.parsed.y.toLocaleString("fr-FR")} transactions` }
          }
        },
        scales: {
          y: { grid: { color: gridColor }, ticks: { callback: v => v.toLocaleString("fr-FR") } },
          x: { grid: { display: false } },
        }
      }
    });
  }

  // ── Distribution prix 2024 ──────────────────────────────────────────
  async function buildDistribution() {
    const canvas = document.getElementById("chart-distribution");
    if (!canvas) return;
    const raw = await API.getEvolution();

    const prix2024 = raw
      .filter(d => d.annee === 2024 && d.prix_m2_median)
      .sort((a,b) => a.prix_m2_median - b.prix_m2_median);

    if (chartDist) chartDist.destroy();
    chartDist = new Chart(canvas, {
      type: "bar",
      data: {
        labels: prix2024.map(d => `${d.arrondissement}e`),
        datasets: [{
          data: prix2024.map(d => d.prix_m2_median),
          backgroundColor: prix2024.map((d,i) => {
            const pct = i / (prix2024.length - 1);
            if (pct < 0.33) return "rgba(16,185,129,0.7)";
            if (pct < 0.66) return "rgba(59,130,246,0.7)";
            return "rgba(239,68,68,0.7)";
          }),
          borderRadius: 4,
        }]
      },
      options: {
        indexAxis: "y",
        responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: "#111827",
            borderColor: "rgba(99,130,190,0.3)",
            borderWidth: 1,
            callbacks: { label: ctx => ` ${Math.round(ctx.parsed.x).toLocaleString("fr-FR")} €/m²` }
          }
        },
        scales: {
          x: { grid: { color: gridColor }, ticks: { callback: v => (v/1000).toFixed(0)+"k" } },
          y: { grid: { display: false } },
        }
      }
    });
  }

  // ── Radar indicateurs ───────────────────────────────────────────────
  async function buildRadar() {
    const canvas = document.getElementById("chart-radar");
    if (!canvas) return;
    const raw = await API.getIndicateurs();

    const KEYS = ["score_accessibilite","score_qualite_vie","score_securite","score_accessibilite_immo"];
    const labels = KEYS.map(k => CONFIG.INDICATEURS_LABELS[k]);

    const top5 = [...raw].sort((a,b) => (b.score_global||0) - (a.score_global||0)).slice(0,5);

    if (chartRadar) chartRadar.destroy();
    chartRadar = new Chart(canvas, {
      type: "radar",
      data: {
        labels,
        datasets: top5.map((d, i) => ({
          label: `${d.arrondissement}e`,
          data: KEYS.map(k => d[k]??0),
          borderColor: CONFIG.CHART_COLORS[i],
          backgroundColor: CONFIG.CHART_COLORS[i] + "20",
          pointBackgroundColor: CONFIG.CHART_COLORS[i],
          borderWidth: 2,
          pointRadius: 3,
        }))
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        scales: {
          r: {
            min: 0, max: 10,
            grid: { color: "rgba(99,130,190,0.15)" },
            pointLabels: { color: "#94a3b8", font: { size: 11 } },
            ticks: { display: false },
            angleLines: { color: "rgba(99,130,190,0.1)" },
          }
        },
        plugins: { legend: { labels: { color: "#94a3b8", boxWidth: 10 } } }
      }
    });
  }

  // ── Ranking score global ────────────────────────────────────────────
  async function buildRanking() {
    const canvas = document.getElementById("chart-ranking");
    if (!canvas) return;
    const raw = await API.getIndicateurs();

    const sorted = [...raw].sort((a,b) => (b.score_global||0) - (a.score_global||0));
    const colors = sorted.map((_, i) =>
      i < 3 ? "rgba(16,185,129,0.8)" :
      i >= sorted.length - 3 ? "rgba(239,68,68,0.8)" :
      "rgba(59,130,246,0.65)"
    );

    if (chartRank) chartRank.destroy();
    chartRank = new Chart(canvas, {
      type: "bar",
      data: {
        labels: sorted.map(d => `${d.arrondissement}e`),
        datasets: [{
          data: sorted.map(d => d.score_global?.toFixed(2)??0),
          backgroundColor: colors,
          borderRadius: 5,
          borderSkipped: false,
        }]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: "#111827",
            borderColor: "rgba(99,130,190,0.3)",
            borderWidth: 1,
            callbacks: { label: ctx => ` Score : ${ctx.parsed.y} /10` }
          }
        },
        scales: {
          x: { grid: { display: false } },
          y: { min: 0, max: 10, grid: { color: gridColor } },
        }
      }
    });
  }

  // ── Comparaison ─────────────────────────────────────────────────────
  async function buildComparaison(arr1, arr2, annee = 2024) {
    const container = document.getElementById("compare-result");
    container.innerHTML = `<div class="loading-pulse" style="grid-column:span 2">Chargement comparaison…</div>`;

    try {
      const data = await API.getComparaison(arr1, arr2, annee);
      const p1 = data.prix?.find(d => d.arrondissement == arr1) || {};
      const p2 = data.prix?.find(d => d.arrondissement == arr2) || {};
      const i1 = data.indicateurs?.find(d => d.arrondissement == arr1) || {};
      const i2 = data.indicateurs?.find(d => d.arrondissement == arr2) || {};

      const metrics = [
        { label:"Prix/m² médian",   v1:p1.prix_m2_median,    v2:p2.prix_m2_median,    fmt:v=>Math.round(v).toLocaleString("fr-FR")+" €", lower:true },
        { label:"Transactions",     v1:p1.nb_transactions,   v2:p2.nb_transactions,   fmt:v=>Math.round(v).toLocaleString("fr-FR"),        lower:false },
        { label:"Accessibilité",    v1:i1.score_accessibilite,v2:i2.score_accessibilite,fmt:v=>v?.toFixed(1)+" /10", lower:false },
        { label:"Qualité de vie",   v1:i1.score_qualite_vie,  v2:i2.score_qualite_vie,  fmt:v=>v?.toFixed(1)+" /10", lower:false },
        { label:"Sécurité",         v1:i1.score_securite,     v2:i2.score_securite,     fmt:v=>v?.toFixed(1)+" /10", lower:false },
        { label:"Score global",     v1:i1.score_global,       v2:i2.score_global,       fmt:v=>v?.toFixed(1)+" /10", lower:false },
      ];

      const renderCard = (arr, vals, others) => `
        <div class="compare-card">
          <div class="compare-card-header">
            <div class="compare-card-num">${arr}<sup style="font-size:18px">${arr===1?"er":"e"}</sup></div>
            <div class="compare-card-label">arrondissement · ${annee}</div>
          </div>
          <div class="compare-card-body">
            ${metrics.map(m => {
              const v = vals[metrics.indexOf(m)];
              const o = others[metrics.indexOf(m)];
              let cls = "";
              if (v != null && o != null) {
                cls = (m.lower ? v < o : v > o) ? "better" : "worse";
              }
              return `<div class="compare-row">
                <span class="label">${m.label}</span>
                <span class="val ${cls}">${v != null ? m.fmt(v) : "—"}</span>
              </div>`;
            }).join("")}
          </div>
        </div>
      `;

      const v1 = metrics.map(m => m.v1);
      const v2 = metrics.map(m => m.v2);
      container.innerHTML = renderCard(arr1, v1, v2) + renderCard(arr2, v2, v1);
    } catch(e) {
      container.innerHTML = `<div class="loading-pulse" style="grid-column:span 2;color:#ef4444">Erreur : ${e.message}</div>`;
    }
  }

  return { buildEvolution, buildVolume, buildDistribution, buildRadar, buildRanking, buildComparaison };
})();