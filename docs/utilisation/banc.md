# La page Cartes

```sh
bin/pepit-cartes
```

La page Cartes, le banc de test, montre les cartes **telles qu'elles sont**, sans logique ni simulateur. C'est l'outil pour vérifier un câblage, trouver le numéro d'une entrée ou d'une sortie, et diagnostiquer une pièce.

## La liste des cartes

À gauche, une ligne par carte détectée, avec son port USB et une pastille :

- **verte** : connectée ;
- **bleue** : pilotée par le cockpit (page Simulateur), qui écrit à ses sorties ou afficheurs ;
- **bleu clair** : lue par le cockpit, pour une carte à laquelle rien n'est jamais écrit (manettes des gaz) ;
- **rouge** : en erreur (accès refusé, carte perdue, bus FDBUS qui ne répond pas). Le détail s'affiche au survol.

Une carte nommée dans la [page Périphériques](peripheriques.md#nommer-un-peripherique) apparaît sous ce nom. La carte choisie s'affiche à droite. La liste défile quel que soit le nombre de cartes, et la carte choisie est retenue d'un lancement à l'autre. Avec « Suivre la carte actionnée », la carte dont on vient d'actionner une commande est choisie toute seule.

Une carte branchée ou débranchée apparaît ou disparaît d'elle-même. « Rechercher les cartes » relit la liste à la demande.

## La vue d'une carte

- **Les entrées** : une grille de toutes les entrées. Une case s'allume quand l'entrée s'écarte de son état de repos (mémorisé au démarrage, quelle que soit la polarité de la carte), et le numéro de la dernière entrée actionnée s'affiche en grand.
- **Les axes** analogiques, en direct.
- **Les sorties**. Leur écriture est verrouillée tant que la case « Autoriser l'écriture » n'est pas cochée.

Selon la carte, la vue propose en plus :

| Carte | Ce que propose la vue |
|---|---|
| MCP | un champ par afficheur, un bouton par voyant |
| CDU | toutes les touches, un bouton par voyant |
| Radio Airbus | un champ par afficheur (« 118.700 »), un bouton par voyant |
| DME | la distance, le texte de droite, les voyants, le rétroéclairage, la mise en marche |
| FDBUS | une colonne par jauge, avec l'étalonnage (ci-dessous) |
| Manettes Thrustmaster | tous les boutons et interrupteurs (dans leur position dès l'ouverture), les axes de 0 à 1 |

!!! note "Carte pilotée par le cockpit"
    Le banc et le cockpit partagent la même carte. Quand le cockpit la pilote, un bandeau jaune le rappelle : ce que vous écrivez au banc est remplacé par les sorties du cockpit. Les entrées, elles, s'affichent normalement. Une carte que le cockpit ne fait que lire porte un bandeau bleu clair.

## Les jauges du bus FDBUS

L'initialisation du bus se fait seule au branchement. La vue montre ensuite une colonne par jauge trouvée :

- la **valeur du cadran** dans son unité, un champ pour y placer l'aiguille et un bouton par repère ;
- l'**étalonnage**, repère par repère : on amène l'aiguille sur un repère du cadran au curseur, on saisit la valeur lue, on enregistre. Un repère qui casse le sens de la courbe apparaît en rouge ;
- le **nom et l'unité** de la jauge branchée sur la sortie : rien n'est figé dans le code, une autre jauge se règle de la même façon ;
- les paramètres du module, sa remise à zéro et le **changement d'adresse** (strap de configuration en place ; c'est la seule écriture en EEPROM que fait Pepit).

Le nom, l'unité et l'étalonnage sont gardés dans `config/fdbus.yaml`, jamais dans les modules.

Ouvrir la page pendant que le cockpit tourne ne relance pas l'initialisation du bus, et les aiguilles tenues par le cockpit ne sont pas ramenées au repos.

## Mode développement

```sh
bin/pepit-cartes --dev
```

Pepit se relance de lui-même dès qu'un fichier Python du projet est enregistré.
