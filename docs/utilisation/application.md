# L'application Pepit

Pepit est **une seule application**, qui tourne en fond, avec trois pages. Chaque lanceur ouvre une page :

```sh
bin/pepit-simulateur      # le cockpit, relié à X-Plane
bin/pepit-cartes          # le banc de test des cartes
bin/pepit-peripheriques   # les périphériques USB, leur accès et leur historique
```

Si Pepit tourne déjà, le lanceur n'ouvre pas un second programme : il ajoute sa page à celui qui est ouvert, puis s'arrête. Lancer `pepit-cartes` puis `pepit-peripheriques` donne donc une seule application avec deux pages.

| Page | Ce qu'elle montre | Détails |
|---|---|---|
| **Simulateur** | le cockpit : la logique de chaque instrument, la liaison avec X-Plane, le bouton « Lancer X-Plane » | [La page Simulateur](cockpit.md) |
| **Cartes** | chaque carte telle qu'elle est : entrées, axes, sorties, jauges | [La page Cartes](banc.md) |
| **Périphériques** | tout ce qui est branché en USB, l'accès de Pepit, l'historique, le bouton « Autoriser » | [La page Périphériques](peripheriques.md) |

## Fermer, ce n'est pas quitter

Pepit pose une icône dans la barre du haut de l'écran. Fermer une page la cache seulement : le cockpit continue de tourner, relié aux cartes et à X-Plane. L'icône rouvre les pages, lance X-Plane, et son menu « Quitter Pepit » arrête tout.

Sans barre d'icônes (certains bureaux), fermer la dernière page arrête Pepit.

## Les cartes partagées

Chaque carte n'est ouverte qu'une fois, pour toutes les pages : on peut regarder le banc de test pendant que le cockpit tourne, sans que l'un dérange l'autre. Dans la page Cartes, une carte pilotée par le cockpit porte une pastille bleue et un bandeau le rappelle ; une carte qu'il ne fait que lire (manettes des gaz), une pastille bleu clair.

## Démarrer sans fenêtre

```sh
bin/pepit-simulateur --fond
```

Pepit démarre alors avec la seule icône de la barre du haut : le cockpit tourne, les pages s'ouvrent à la demande. Pour qu'il démarre avec la session, créez le fichier `~/.config/autostart/pepit.desktop` (en remplaçant le chemin par celui de votre dossier Pepit) :

```ini
[Desktop Entry]
Type=Application
Name=Pepit
Exec=/home/vous/pepit/bin/pepit-simulateur --fond
X-GNOME-Autostart-enabled=true
```

## Mode développement

```sh
bin/pepit-simulateur --dev config/avions/bae146-jf
```

Pepit se relance tout seul à chaque modification d'un fichier Python ou YAML du projet. S'il plante, il est relancé à la correction suivante.

!!! note "Anciens lanceurs"
    `bin/pepit-banc` et `bin/pepit-cockpit` existent encore : ils ouvrent la page Cartes et la page Simulateur.
