# Le banc de test

```sh
bin/pepit-banc
```

Le banc de test montre les cartes **telles qu'elles sont**, sans logique ni simulateur. C'est l'outil pour vérifier un câblage, trouver le numéro d'une entrée ou d'une sortie, et diagnostiquer une pièce.

## Un onglet par carte

- **Les entrées** : une grille de toutes les entrées. Une case s'allume quand l'entrée s'écarte de son état de repos (mémorisé au démarrage, quelle que soit la polarité de la carte), et le numéro de la dernière entrée actionnée s'affiche en grand.
- **Les axes** analogiques, en direct.
- **Les sorties**. Leur écriture est verrouillée tant que la case « Autoriser l'écriture » n'est pas cochée.

Avec « Suivre la carte actionnée », l'onglet de la carte dont on vient d'actionner une commande passe au premier plan.

Selon la carte, l'onglet propose en plus :

| Carte | Ce que propose l'onglet |
|---|---|
| MCP | un champ par afficheur, un bouton par voyant |
| CDU | toutes les touches, un bouton par voyant |
| Radio Airbus | un champ par afficheur (« 118.700 »), un bouton par voyant |
| DME | la distance, le texte de droite, les voyants, le rétroéclairage, la mise en marche |
| FDBUS | une colonne par jauge, avec l'étalonnage (ci-dessous) |

## Les jauges du bus FDBUS

L'initialisation du bus se fait seule au branchement. L'onglet montre ensuite une colonne par jauge trouvée :

- la **valeur du cadran** dans son unité, un champ pour y placer l'aiguille et un bouton par repère ;
- l'**étalonnage**, repère par repère : on amène l'aiguille sur un repère du cadran au curseur, on saisit la valeur lue, on enregistre. Un repère qui casse le sens de la courbe apparaît en rouge ;
- le **nom et l'unité** de la jauge branchée sur la sortie : rien n'est figé dans le code, une autre jauge se règle de la même façon ;
- les paramètres du module, sa remise à zéro et le **changement d'adresse** (strap de configuration en place ; c'est la seule écriture en EEPROM que fait Pepit).

Le nom, l'unité et l'étalonnage sont gardés dans `config/fdbus.yaml`, jamais dans les modules.

!!! warning "Une seule application sur le bus"
    Le bus FDBUS ne doit être piloté que par une seule application. Fermez le banc de test avant de lancer un cockpit qui utilise des jauges.

## Mode développement

```sh
bin/pepit-banc --dev
```

La fenêtre se relance d'elle-même dès qu'un fichier Python du projet est enregistré. Si le programme plante, il est relancé à la correction suivante.
