# Pepit

**Pepit** pilote, sous **Linux**, les cartes d'interface d'un cockpit de simulateur de vol et les relie à **X-Plane 12**. C'est une alternative libre à SIOC, le logiciel d'OpenCockpits, qui ne fonctionne que sous Windows.

Pepit est écrit en Python et décrit le cockpit dans de simples fichiers YAML.

## Ce que fait Pepit

- **Détecte et classe** les cartes branchées en USB (OpenCockpits, EFDE, manettes Thrustmaster) et accueille les cartes **wifi** écrites pour SIOC (Arduino, ESP8266, ESP32).
- **Montre en direct** chaque entrée (interrupteurs, poussoirs, encodeurs, axes) et permet de tester les sorties (voyants, afficheurs, aiguilles de jauges) : c'est le [banc de test](utilisation/banc.md).
- **Exécute la logique du cockpit** décrite en YAML : transpondeur, pilote automatique, radios, CDU, jauges, manettes des gaz. C'est le [cockpit](utilisation/cockpit.md).
- **Se relie à X-Plane 12** sans plugin, par son protocole UDP et son API web locale.

## Deux façons de s'en servir

**Clé en main.** Vous avez le même matériel et le même avion qu'un profil existant ? Branchez, installez, lancez : les profils du [BAe 146](avions/bae146.md) et du [Boeing 737-800](avions/b737.md) relient déjà le MCP, le CDU, la radio, le transpondeur, les jauges et les manettes.

**Une méthode pour votre cockpit.** Votre matériel ou votre avion sont différents ? Pepit sépare trois couches, et chaque pièce suit le même chemin :

1. **le matériel** : la carte et la voie où la pièce est branchée, vérifiées au banc de test ;
2. **la logique** : ce que fait la pièce (un sélecteur, un encodeur, une jauge), décrit en YAML sans parler du simulateur ;
3. **le simulateur** : le [dictionnaire des fonctions](configuration/dictionnaire.md) traduit « transpondeur.code » ou « pa.mode.hdg » en dataref ou en commande.

Changer d'avion ou de simulateur ne touche que la troisième couche.

## Par où commencer

- [Installer Pepit](demarrage/installation.md) sur Ubuntu ou Debian.
- Suivre les [premiers pas](demarrage/premiers-pas.md) : une carte, un interrupteur, un voyant, puis X-Plane.
- Voir les [cartes prises en charge](materiel/cartes.md).

!!! note "État du projet"
    Pepit sert chaque jour sur un cockpit réel, mais reste un projet personnel. Les protocoles ont été retrouvés par rétro-ingénierie sur du matériel réel, ou communiqués par les fabricants. Pepit n'est affilié ni à OpenCockpits, ni à EFDE, ni à Laminar Research.

Le code est sur [GitHub](https://github.com/pierrezNet/pepit), sous licence GPL-3.0-or-later.
