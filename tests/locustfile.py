"""
tests/locustfile.py
Tests de charge de l'API — valide C1.4 (performance et scalabilité).
Usage :
    locust -f tests/locustfile.py --host=http://localhost:8000 --headless -u 20 -r 5 -t 60s
"""
from locust import HttpUser, task, between


class UrbanDataUser(HttpUser):
    wait_time = between(0.5, 2)
    headers = {"X-API-Key": "urban-explorer-dev-key"}

    @task(3)
    def get_prix_evolution(self):
        self.client.get("/prix/evolution", headers=self.headers)

    @task(2)
    def get_arrondissement_detail(self):
        import random
        arr = random.randint(1, 20)
        self.client.get(f"/arrondissements/{arr}?annee=2023", headers=self.headers)

    @task(2)
    def get_indicateurs(self):
        self.client.get("/indicateurs", headers=self.headers)

    @task(1)
    def get_comparaison(self):
        import random
        a1, a2 = random.sample(range(1, 21), 2)
        self.client.get(f"/comparaison?arr1={a1}&arr2={a2}&annee=2023", headers=self.headers)

    @task(1)
    def health_check(self):
        self.client.get("/health")

    @task(1)
    def get_geojson(self):
        self.client.get("/geojson", headers=self.headers)
