// dashboard/js/config.js — Urban Data Explorer v2

const CONFIG = {
  API_BASE: "http://localhost:8000",
  API_KEY:  "urban-explorer-dev-key",

  ANNEES: [2021, 2022, 2023, 2024],

  // Palette choroplèthe prix — bleu froid → ambre → rouge
  COLORS_PRIX: [
    "#0f3460","#1a5276","#1f618d",
    "#2980b9","#5dade2","#f4d03f",
    "#e67e22","#e74c3c","#922b21"
  ],

  // Palette scores — rouge → vert
  COLORS_SCORE: [
    "#7b0000","#c0392b","#e74c3c",
    "#e67e22","#f4d03f","#82e0aa",
    "#27ae60","#1e8449","#0b5345"
  ],

  ARRONDISSEMENTS: Array.from({length: 20}, (_, i) => ({
    value: i + 1,
    label: `${i + 1}${i === 0 ? "er" : "e"} arr.`
  })),

  INDICATEURS_LABELS: {
    prix_m2_median:             "Prix/m² médian",
    part_logements_sociaux_pct: "Logements sociaux (%)",
    score_accessibilite:        "Accessibilité urbaine",
    score_qualite_vie:          "Qualité de vie",
    score_securite:             "Sécurité",
    score_accessibilite_immo:   "Accessibilité immo.",
    score_global:               "Score global",
  },

  CHART_COLORS: [
    "#3b82f6","#10b981","#f59e0b","#ef4444","#8b5cf6",
    "#06b6d4","#84cc16","#ec4899","#6366f1","#14b8a6",
    "#f97316","#a78bfa","#34d399","#fbbf24","#60a5fa",
    "#fb7185","#4ade80","#e879f9","#38bdf8","#a3e635"
  ],
};