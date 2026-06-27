// Exécuté au premier démarrage du conteneur mongo (root user).
// Crée la base urban_data, les collections et un user applicatif limité.

db = db.getSiblingDB("urban_data");

db.createCollection("bronze_raw");
db.createCollection("data_catalog");
db.createCollection("stream_events");

// Index initiaux (les load scripts s'assureront que ceux-ci existent aussi)
db.bronze_raw.createIndex({ source: 1, ingested_at: -1 });
db.data_catalog.createIndex({ source: 1 }, { unique: true });
db.stream_events.createIndex({ ingested_at: 1 }, { expireAfterSeconds: 2592000 });
db.stream_events.createIndex({ arrondissement: 1, annee: -1 });

print("✓ Mongo: collections urban_data initialisées");
