# La page Simulateur

```sh
bin/pepit-simulateur                                # le dernier profil utilisé
bin/pepit-simulateur config/avions/b738-laminar     # Boeing 737-800 de Laminar
bin/pepit-simulateur config/avions/bae146-jf        # BAe 146 de Just Flight
bin/pepit-simulateur config/avions/rj85-simule      # Avro RJ85, logique simulée, sans X-Plane
```

La page Simulateur, c'est le cockpit : elle ouvre les cartes déclarées par le profil d'avion, exécute la logique de chaque instrument, met à jour les afficheurs, voyants et aiguilles, et dialogue avec X-Plane. Elle tourne même cachée (voir [L'application](application.md)).

## La page

- **En haut** :
    - le **profil** d'avion, choisi dans la liste des dossiers de `config/avions/` (avec les avions que chacun déclare) ;
    - la case **« Selon l'avion chargé dans X-Plane »** (ci-dessous) ;
    - le bouton **« Lancer X-Plane »** et, à côté, « … » pour choisir son exécutable ;
    - l'état de chaque carte (connectée, non trouvée, en attente) et de X-Plane, avec l'avion chargé.
- **Un onglet par instrument** : afficheurs, voyants, écran du CDU, jauges, manettes, tels que la logique les voit. Les boutons qui remplacent le matériel absent sont rangés dans « Commandes virtuelles ».
- **En bas**, le journal de la logique.

Après une modification d'un YAML, cliquez sur « Recharger la configuration », ou lancez Pepit en mode développement :

```sh
bin/pepit-simulateur --dev config/avions/bae146-jf
```

Il se relance alors tout seul à chaque modification d'un fichier Python ou YAML.

!!! note "Afficheurs du MCP"
    Les afficheurs du MCP OpenCockpits ne restent allumés que tant qu'un programme lit la carte : c'est le cas tant que Pepit tourne, même page fermée.

## Lancer X-Plane

« Lancer X-Plane » (aussi dans le menu de l'icône de la barre du haut) démarre X-Plane depuis son dossier. Pepit le trouve dans `~/X-Plane 12/` ; sinon, choisissez l'exécutable avec « … ». Le bouton se grise dès que X-Plane tourne, avant même la fin de son chargement. Quitter Pepit n'arrête pas X-Plane.

## Le profil selon l'avion chargé

Un profil déclare son avion dans `sim.yaml` par son code OACI :

```yaml
sim:
  type: xplane
  avion: [B461, B462, B463]   # ou une seule valeur : avion: B738
```

Case cochée, quand X-Plane charge un avion, Pepit prend le profil qui le déclare. Il ne réagit qu'au **changement** d'avion : un profil choisi à la main reste en place tant que l'avion ne change pas. Un avion qu'aucun profil ne déclare est signalé dans le journal, et le profil reste le même.

## X-Plane 12

Une fois X-Plane lancé et l'avion chargé, la page affiche « X-Plane : connecté » dès que le simulateur répond, et se reconnecte seule s'il redémarre. Rien n'est à installer dans X-Plane.

- **UDP (port 49000)**, ouvert par défaut : lecture des valeurs, écriture, commandes. X-Plane ne sert que 500 abonnements par client et perd une partie d'une grosse rafale de demandes : Pepit répartit ses abonnements sur plusieurs ports locaux et relance ceux qui restent sans réponse.
- **API web locale (port 8086)**, X-Plane 12.1.1 et suivants, active par défaut : lecture des textes publiés par un plugin (l'écran du FMC du BAe 146), dont l'UDP ne renvoie que le premier caractère.

À la connexion, la position des interrupteurs physiques (F/D, transpondeur…) est envoyée à l'avion : c'est le matériel qui fait foi.

## L'écran physique du CDU

Un CDU OpenCockpits peut avoir son propre écran derrière la façade (par exemple un écran 1024 × 768 sur une seconde carte graphique). Dans l'onglet du CDU, « Écran physique du CDU » :

- choisit la **sortie vidéo** de cet écran (`xrandr --listmonitors` donne leurs noms) ;
- ouvre une fenêtre sans bordure ni curseur, posée sur toute cette sortie, qui reprend l'écran du CDU lu dans X-Plane ;
- règle les **marges** pour caler l'image dans la découpe de la façade, avec une **mire** (cadre et grille) pour s'aider.

Le réglage est gardé dans `config/ecrans.yaml`, et la fenêtre se rouvre seule aux lancements suivants.

!!! tip "Pas de vrai plein écran"
    Sur une seconde carte graphique, une fenêtre en vrai plein écran restait figée sur sa première image sous GNOME. Pepit pose donc une fenêtre sans bordure sur toute la sortie, ce qui donne le même résultat à l'œil.
