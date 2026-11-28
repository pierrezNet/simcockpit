# Contribuer

## Tests

```sh
.venv/bin/python -m unittest discover -s tests -t .
```

Les tests n'ont besoin ni des cartes ni d'X-Plane : ils rejouent des captures réelles (`tests/data/`) et simulent le simulateur.

## Structure du projet

```
arduino/        programmes des cartes Arduino / ESP (identifiants wifi dans secrets.h, non publié)
bin/            lanceurs : pepit (ligne de commande), pepit-simulateur, pepit-cartes,
                pepit-peripheriques ; pepit-installer (droits matériels, une fois, sudo)
config/         configuration : matériel, dictionnaire, un dossier par avion
docs/           ce site (MkDocs Material)
pepit/app/      l'application : une seule instance, trois pages, icône de la barre du haut
pepit/hw/       accès aux cartes et protocoles (hidraw, evdev, serveur IOCP…), concentrateur,
                périphériques USB et autorisations
pepit/diag/     bruit, assistants de test des entrées et des sorties
pepit/logic/    configuration, dictionnaire des fonctions, types de commandes, moteur
pepit/sim/      liaison X-Plane (UDP et API web), lancement d'X-Plane
pepit/gui/      pages Cartes (banc de test) et Périphériques
pepit/panel/    page Simulateur (le cockpit, écran physique du CDU)
tests/          tests unitaires et captures réelles
udev/           règle d'accès aux cartes, assistant d'autorisation et sa règle polkit
```

## La règle d'architecture

**L'affichage n'affiche que.** Les protocoles et les calculs vivent dans `pepit/hw/`, la logique et la liaison au simulateur dans `pepit/logic/` et le YAML. Les fenêtres (`gui/`, `panel/`) ne font qu'afficher et appeler ces fonctions. Les cartes Arduino suivent la même règle : elles dessinent ce qu'on leur envoie, les données restent dans le YAML.

Si une fenêtre a besoin d'un calcul, il descend d'abord dans `hw/` ou `logic/`, avec un test.

## Ajouter une carte

1. Capturer ses trames sans rien lui envoyer : `bin/pepit listen --port …`.
2. Écrire le décodage dans `pepit/hw/` et le rejouer dans un test sur la capture.
3. Déclarer son type dans `pepit/hw/cards.py` (nom USB, entrées, sorties, ce qui est vérifié).
4. Ne rien écrire à une carte avant d'avoir compris son protocole.

## Ajouter un avion

1. Copier un dossier de `config/avions/`.
2. Relever les commandes et datarefs propres à l'avion (lecture seule) et les mettre dans son `fonctions.yaml`.
3. Citer ces fonctions dans les fichiers d'instruments.
4. N'ajouter au dictionnaire de base (`config/dictionnaire/xplane.yaml`) que des branchements essayés, avec la date et l'avion dans `verifie`.

## La documentation

Les pages sont dans `docs/`, en Markdown. Pour les voir en local :

```sh
.venv/bin/pip install -r requirements-docs.txt
.venv/bin/mkdocs serve
```

Le site est publié automatiquement par une action GitHub à chaque modification de `docs/` sur la branche `main`.

## Remerciements

Le format des entrées Master Card et le codage des sorties ont été établis en lisant le code de [xpiocards](https://sourceforge.net/projects/xpiocards/) et de [xpcockpit](https://github.com/retostockli/xpcockpit) (Reto Stöckli). Pepit est une réécriture indépendante : aucun code de ces projets n'a été copié. Les protocoles du DME et du bus de jauges ont été communiqués par EFDE.

## Licence

Pepit est un logiciel libre, distribué sous la **GNU General Public License, version 3 ou toute version ultérieure** (GPL-3.0-or-later), comme xpcockpit, dont il s'inspire.
