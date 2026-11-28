# Avro RJ85 simulé

```sh
bin/pepit-cockpit                         # profil par défaut
bin/pepit-cockpit config/avions/rj85-simule
```

Le profil `config/avions/rj85-simule/` fait fonctionner le matériel **sans simulateur**. La logique de l'avion est simulée par Pepit, ce qui permet de tester un cockpit sans lancer X-Plane. Le RJ85 n'existe pas pour X-Plane ; le cockpit pour lequel Pepit a été écrit est celui d'un RJ85.

| Fichier | Matériel | Ce qu'il fait |
|---|---|---|
| `mcp.yaml` | MCP OpenCockpits | molettes et afficheurs, modes du pilote automatique de l'Avro RJ simulés (type `rj_autopilot`) |
| `dme.yaml` | DME EFDE | indicateur Collins IND-42C : test des segments, ID / KT / MIN, marche-arrêt |
| `transpondeur.yaml` | EFDE IO32 | code et mode du transpondeur |

Comme il n'y a pas de simulateur, les données sont saisies dans le cockpit : distance, vitesse sol et identifiant de la balise DME, avec une option « voler vers la station » qui fait décroître la distance.

La logique du pilote automatique RJ est décrite dans [Types de commandes](../configuration/types.md#pilote-automatique-simule-rj_autopilot).
