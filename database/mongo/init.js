// database/mongo/init.js
// Initialisation MongoDB — Urban Data Explorer
// Compétence validée : C1.2 (base de données NoSQL)

db = db.getSiblingDB('urban_data_explorer');

// ══════════════════════════════════════════════════════════════════════
// COLLECTION 1 : indicateurs_custom
// Stocke les 4 scores composites par arrondissement
// Structure flexible → idéal pour MongoDB
// ══════════════════════════════════════════════════════════════════════
db.createCollection('indicateurs_custom', {
  validator: {
    $jsonSchema: {
      bsonType: 'object',
      required: ['arrondissement', 'score_global'],
      properties: {
        arrondissement:          { bsonType: 'int',    description: 'Numéro 1-20' },
        score_accessibilite:     { bsonType: 'double', description: 'Score 0-10' },
        score_qualite_vie:       { bsonType: 'double', description: 'Score 0-10' },
        score_securite:          { bsonType: 'double', description: 'Score 0-10' },
        score_accessibilite_immo:{ bsonType: 'double', description: 'Score 0-10' },
        score_global:            { bsonType: 'double', description: 'Moyenne 0-10' },
      }
    }
  }
});

db.indicateurs_custom.createIndex({ arrondissement: 1 }, { unique: true });
db.indicateurs_custom.createIndex({ score_global: -1 });

// ══════════════════════════════════════════════════════════════════════
// COLLECTION 2 : environnement
// Données qualité air, bruit, circulation, parcs
// Structure variable selon les sources disponibles → NoSQL parfait
// ══════════════════════════════════════════════════════════════════════
db.createCollection('environnement');
db.environnement.createIndex({ arrondissement: 1 }, { unique: true });
db.environnement.createIndex({ 'qualite_air.iqa_moyen': 1 });
db.environnement.createIndex({ 'bruit.score_bruit': 1 });

// ══════════════════════════════════════════════════════════════════════
// COLLECTION 3 : points_interet
// Commerces, transports, écoles, parcs (données OSM)
// Documents GeoJSON avec coordonnées → requêtes géospatiales MongoDB
// ══════════════════════════════════════════════════════════════════════
db.createCollection('points_interet');
db.points_interet.createIndex({ location: '2dsphere' });  // Index géospatial
db.points_interet.createIndex({ categorie: 1 });
db.points_interet.createIndex({ arrondissement: 1 });

// ══════════════════════════════════════════════════════════════════════
// COLLECTION 4 : stream_events
// Logs du micro-batch streaming (C2.2)
// Documents horodatés avec structure variable → MongoDB idéal
// ══════════════════════════════════════════════════════════════════════
db.createCollection('stream_events', {
  // TTL index : supprime automatiquement les événements après 30 jours
  // (démo de fonctionnalité MongoDB avancée pour la soutenance)
});
db.stream_events.createIndex({ timestamp: 1 }, { expireAfterSeconds: 2592000 });
db.stream_events.createIndex({ batch_id: 1 });
db.stream_events.createIndex({ arrondissement: 1 });

print('✓ Collections MongoDB créées : indicateurs_custom, environnement, points_interet, stream_events');
print('✓ Index créés (dont géospatial 2dsphere et TTL)');