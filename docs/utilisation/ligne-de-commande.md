# Ligne de commande

```sh
bin/pepit list [--all]               # détecter et classer les cartes
bin/pepit watch [--axes]             # changements d'entrées (anti-rebond 50 ms)
bin/pepit diag -s 10                 # repérer les entrées instables
bin/pepit check                      # assistant : tester les entrées borne par borne
bin/pepit outputs                    # assistant : tester les sorties une par une
bin/pepit listen --port 1-14         # trames brutes, sans rien envoyer
bin/pepit send --port 1-14 "…"       # envoyer une trame brute (essais)
bin/pepit fonctions [dossier d'avion] [--filtre hdg]   # dictionnaire des fonctions
```

| Commande | Usage |
|---|---|
| `list` | Les cartes de cockpit branchées, leur type et leur port USB. `--all` ajoute les autres périphériques HID (claviers, joysticks…). |
| `watch` | Chaque changement d'entrée, filtré par l'anti-rebond. `--axes` montre aussi les axes. |
| `diag` | Écoute pendant quelques secondes sans rien toucher et signale les entrées qui changent d'elles-mêmes (fil mal serré, parasites). |
| `check` | Demande d'actionner chaque borne à son tour et dresse le bilan : correspondance borne → numéro, entrées mortes, pontées ou instables. |
| `outputs` | Allume les sorties une par une, avec confirmation, pour repérer chaque voyant. |
| `listen` | Les trames brutes reçues, sans rien envoyer à la carte : l'outil de rétro-ingénierie. |
| `send` | Envoie une trame brute à une carte (essais de protocole). |
| `fonctions` | Le [dictionnaire des fonctions](../configuration/dictionnaire.md) : nom, description, branchement, source. |

`--port` désigne une carte par son port USB, utile quand plusieurs cartes sont branchées.
