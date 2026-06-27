// dashboard/js/config.js
// Configuration globale du dashboard

const CONFIG = {
  API_BASE: "http://localhost:8000",
  API_KEY:  "urban-explorer-dev-key",

  // Palette choroplèthe — prix/m² (magma-like : violet profond → jaune lumineux)
  COLORS_PRIX: [
    "#1a0033", "#3b0f6e", "#641a80", "#8c2981",
    "#b73779", "#dd4968", "#f1605d", "#fb8861",
    "#febc6a", "#fde2a3"
  ],

  // Palette score 0-10 (turquoise → vert lime, type viridis inversé)
  COLORS_SCORE: [
    "#440154", "#482878", "#3e4989", "#31688e",
    "#26828e", "#1f9e89", "#35b779", "#6ece58",
    "#b5de2b", "#fde725"
  ],

  // Arrondissements parisiens
  ARRONDISSEMENTS: Array.from({length: 20}, (_, i) => ({
    value: i + 1,
    label: `${i + 1}${i === 0 ? "er" : "e"} arr.`
  })),

  // Années disponibles
  ANNEES: [2019, 2020, 2021, 2022, 2023],

  // Labels indicateurs
  INDICATEURS_LABELS: {
    prix_m2_median:              "Prix/m² médian",
    part_logements_sociaux_pct:  "Logements sociaux (%)",
    score_accessibilite:         "Accessibilité urbaine",
    score_qualite_vie:           "Qualité de vie",
    score_securite:              "Sécurité (criminalité + police + pompiers)",
    score_accessibilite_immo:    "Accessibilité immo.",
    score_global:                "Score global",
    // Sous-composantes sécurité (affichées dans le tooltip et la comparaison)
    nb_faits:                    "Faits de criminalité",
    nb_commissariats:            "Commissariats de police",
    nb_casernes:                 "Casernes de pompiers",
  },

  // Couleurs Chart.js pour les arrondissements (20 couleurs distinctes)
  CHART_COLORS: [
    "#5b8dee","#3ecf8e","#e05252","#e09e52","#a78bfa",
    "#f59e0b","#10b981","#ef4444","#8b5cf6","#06b6d4",
    "#f97316","#84cc16","#ec4899","#14b8a6","#6366f1",
    "#d97706","#65a30d","#dc2626","#7c3aed","#0891b2"
  ],
};
