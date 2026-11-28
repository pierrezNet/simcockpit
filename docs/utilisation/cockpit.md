# Le cockpit et X-Plane

```sh
bin/pepit-cockpit                                # Avro RJ85, logique simulée, sans X-Plane
bin/pepit-cockpit config/avions/b738-laminar     # Boeing 737-800 de Laminar
bin/pepit-cockpit config/avions/bae146-jf        # BAe 146 de Just Flight
```

Le cockpit ouvre les cartes déclarées par le profil d'avion, exécute la logique de chaque instrument, met à jour les afficheurs, voyants et aiguilles, et dialogue avec X-Plane.

## La fenêtre

- **En haut**, l'état de chaque carte (connectée, non trouvée, en attente) et de X-Plane, avec l'avion chargé.
- **Un onglet par instrument** : afficheurs, voyants, écran du CDU, jauges, manettes, tels que la logique les voit. Les boutons qui remplacent le matériel absent sont rangés dans « Commandes virtuelles ».
- **En bas**, le journal de la logique.

Après une modification d'un YAML, cliquez sur « Recharger la configuration », ou lancez le cockpit en mode développement :

```sh
bin/pepit-cockpit --dev config/avions/bae146-jf
```

Il se relance alors tout seul à chaque modification d'un fichier Python ou YAML.

!!! note "Afficheurs du MCP"
    Les afficheurs du MCP OpenCockpits ne restent allumés que tant qu'un programme lit la carte : gardez le cockpit ou le banc de test ouvert.

## X-Plane 12

Lancez X-Plane et chargez l'avion : le cockpit affiche « X-Plane : connecté » dès que le simulateur répond, et se reconnecte seul s'il redémarre. Rien n'est à installer dans X-Plane.

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
