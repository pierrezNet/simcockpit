# Premiers pas

Ce tutoriel relie un interrupteur et un voyant branchés sur une carte EFDE IO32, d'abord sans simulateur, puis à X-Plane. La même démarche vaut pour toute autre pièce : on vérifie le matériel, on décrit la logique, puis on la relie au simulateur.

## 1. Voir la carte

Branchez la carte et lancez :

```sh
bin/pepit list
```

```
/dev/hidraw4   port 1-14     EFDE USB32I04AD
               → EFDE IO32 : 32 entrées, 32 sorties, 4 axes, actif à 1
```

Le **port USB** (ici `1-14`) identifie la carte. Ces cartes n'ont pas de numéro de série : si vous en avez deux identiques, branchez-les toujours sur les mêmes prises.

## 2. Trouver le numéro de l'interrupteur

```sh
bin/pepit-banc
```

L'onglet de la carte montre toutes ses entrées. Basculez l'interrupteur : sa case s'allume et son numéro s'affiche en grand. Notez-le, par exemple **12**.

Pour le voyant, ouvrez la partie « Sorties », cochez « Autoriser l'écriture » et allumez les sorties une à une jusqu'à trouver la vôtre, par exemple **42**.

## 3. Déclarer la carte

Dans `config/materiel.yaml`, chaque carte est décrite une seule fois, sous un nom de votre choix :

```yaml
cards:
  io32:
    product: USB32I04AD     # nom USB affiché par « bin/pepit list »
```

## 4. Décrire la pièce

Créez un dossier d'avion, par exemple `config/avions/essai/`, et un fichier `essai.yaml` :

```yaml
instruments:
  essai:
    label: Essai
    card: io32
    controls:
      batterie:
        type: switch
        input: 12
```

Lancez le cockpit sur ce dossier :

```sh
bin/pepit-cockpit --dev config/avions/essai
```

L'onglet « Essai » montre l'état de l'interrupteur, et le journal note chaque bascule. Avec `--dev`, le cockpit se relance tout seul à chaque modification du YAML.

## 5. Relier au simulateur

Ajoutez la liaison X-Plane dans un fichier `sim.yaml` du même dossier :

```yaml
sim:
  type: xplane
  host: 127.0.0.1
  port: 49000
```

Puis dites ce que fait l'interrupteur dans X-Plane :

```yaml
      batterie:
        type: switch
        input: 12
        command_on: sim/electrical/battery_1_on
        command_off: sim/electrical/battery_1_off
```

Lancez X-Plane, chargez un avion : la barre du cockpit passe à « X-Plane : connecté », et l'interrupteur commande la batterie.

!!! tip "Noms logiques"
    Plutôt qu'écrire les commandes X-Plane dans chaque fichier, on peut citer une fonction du [dictionnaire](../configuration/dictionnaire.md) : `fonction: transpondeur.mode`. Le profil reste alors valable pour d'autres avions.

## Pour aller plus loin

- Les [types de commandes](../configuration/types.md) : sélecteurs, encodeurs, afficheurs, jauges, manettes.
- Les profils complets du [BAe 146](../avions/bae146.md) et du [737](../avions/b737.md), à recopier et adapter.
