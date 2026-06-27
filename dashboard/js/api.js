// dashboard/js/api.js
// Couche d'accès à l'API FastAPI — toutes les requêtes passent ici

const API = {
  _cache: {},

  _headers() {
    return {
      "X-API-Key": CONFIG.API_KEY,
      "Content-Type": "application/json",
    };
  },

  async _get(endpoint) {
    if (this._cache[endpoint]) return this._cache[endpoint];
    const url = CONFIG.API_BASE + endpoint;
    const r = await fetch(url, { headers: this._headers() });
    if (!r.ok) throw new Error(`API ${r.status}: ${endpoint}`);
    const data = await r.json();
    this._cache[endpoint] = data;
    return data;
  },

  /** Vérifie que l'API répond */
  async health() {
    const r = await fetch(CONFIG.API_BASE + "/health");
    return r.ok ? await r.json() : null;
  },

  /** Prix par arrondissement × année */
  async getPrix({ arrondissement, anneeMin = 2019, anneeMax = 2023 } = {}) {
    let url = `/prix?annee_min=${anneeMin}&annee_max=${anneeMax}`;
    if (arrondissement) url += `&arrondissement=${arrondissement}`;
    return this._get(url);
  },

  /** Évolution toutes années tous arrondissements */
  async getEvolution() {
    return this._get("/prix/evolution");
  },

  /** Indicateurs custom par arrondissement */
  async getIndicateurs(arrondissement = null) {
    const url = arrondissement
      ? `/indicateurs?arrondissement=${arrondissement}`
      : "/indicateurs";
    return this._get(url);
  },

  /** Comparaison deux arrondissements */
  async getComparaison(arr1, arr2, annee = 2023) {
    // Pas de cache pour la comparaison (combinaisons variables)
    const url = `${CONFIG.API_BASE}/comparaison?arr1=${arr1}&arr2=${arr2}&annee=${annee}`;
    const r = await fetch(url, { headers: this._headers() });
    if (!r.ok) throw new Error(`Comparaison impossible (${r.status})`);
    return r.json();
  },

  /** GeoJSON arrondissements */
  async getGeoJSON() {
    return this._get("/geojson");
  },

  /** Logements sociaux */
  async getLogementsSociaux(arrondissement = null) {
    const url = arrondissement
      ? `/logements-sociaux?arrondissement=${arrondissement}`
      : "/logements-sociaux";
    return this._get(url);
  },

  /** Prix pour un arrondissement et une année */
  async getPrixAnnee(arrondissement, annee) {
    const data = await this.getPrix({ arrondissement, anneeMin: annee, anneeMax: annee });
    return data[0] || null;
  },

  /** Qualité de l'air temps réel (pas de cache — données streaming) */
  async getAirQuality({ hours = 24, alertOnly = false } = {}) {
    let url = `/stream/air-quality?hours=${hours}`;
    if (alertOnly) url += "&alert_only=true";
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 8000);
    try {
      const r = await fetch(CONFIG.API_BASE + url, {
        headers: this._headers(),
        signal: controller.signal,
      });
      if (!r.ok) throw new Error(`Air quality API ${r.status}`);
      return await r.json();
    } finally {
      clearTimeout(timer);
    }
  },

  /** Rapport du dernier batch DVF (pas de cache) */
  async getBatchStatus() {
    const r = await fetch(CONFIG.API_BASE + "/batch/status");
    if (!r.ok) throw new Error(`Batch status API ${r.status}`);
    return r.json();
  },

  /** Invalidate cache (ex: après changement d'année) */
  clearCache() {
    this._cache = {};
  },
};
