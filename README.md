# Pepit

Pilotage libre, sous **Linux**, des cartes d'interface d'un cockpit de simulateur de vol (**OpenCockpits**, **EFDE**, manettes Thrustmaster, cartes **Arduino / ESP** en wifi), relié à **X-Plane 12** sans plugin. Une alternative à SIOC, qui ne fonctionne que sous Windows.

La logique du cockpit se décrit en YAML : transpondeur, pilote automatique, radios, CDU, jauges, manettes des gaz. Des profils complets relient le BAe 146 de Just Flight et le Boeing 737-800 de Laminar.

**Documentation : https://pierreznet.github.io/pepit/**

## Installation (Ubuntu / Debian)

```sh
sudo apt install python3-venv git
git clone https://github.com/pierrezNet/pepit.git && cd pepit
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
sudo bin/pepit-installer        # une fois, après l'avoir lu : accès aux cartes, bouton « Autoriser »
```

## Démarrer

```sh
bin/pepit-simulateur config/avions/bae146-jf    # le cockpit, relié à X-Plane (bouton « Lancer X-Plane »)
bin/pepit-cartes                                # le banc de test : entrées, sorties, jauges
bin/pepit-peripheriques                         # les périphériques USB, leur accès, leur historique
```

Les trois lanceurs ouvrent les pages d'**une seule application**, qui tourne en fond avec une icône dans la barre du haut : lancer `pepit-cartes` alors que Pepit tourne ajoute la page Cartes au Pepit ouvert. Le banc et le cockpit partagent les cartes. `bin/pepit list` liste les cartes branchées en ligne de commande.

Suite : [premiers pas](https://pierreznet.github.io/pepit/demarrage/premiers-pas/), [cartes prises en charge](https://pierreznet.github.io/pepit/materiel/cartes/), [configuration](https://pierreznet.github.io/pepit/configuration/).

> Projet personnel, utilisé sur un cockpit réel. Les protocoles ont été retrouvés sur du matériel réel ou communiqués par les fabricants. Pepit n'est affilié ni à OpenCockpits, ni à EFDE, ni à Laminar Research.

## Licence

Logiciel libre sous **GPL-3.0-or-later**. Voir [LICENSE](LICENSE).
