# Dictionnaire des fonctions

Un profil d'avion désigne ce qu'il pilote par le **nom logique** d'une fonction de l'avion (`transpondeur.code`, `pa.mode.hdg`, `volets.angle`) plutôt que par un dataref ou une commande X-Plane. Le dictionnaire dit comment chaque fonction s'obtient dans le simulateur.

C'est ce qui rend un profil réutilisable : changer d'avion ou de simulateur ne touche que le dictionnaire, pas la description du matériel.

## Deux niveaux

- **`config/dictionnaire/xplane.yaml`** : les datarefs et commandes standard d'X-Plane, valables pour tous les avions qui utilisent ses systèmes. Chaque entrée dit où elle a été vérifiée (champ `verifie`) ; une entrée sans `verifie` n'a pas encore été essayée sur un avion.
- **La section `fonctions:` du dossier de l'avion** ajoute des fonctions (les boutons propres à l'avion) ou en remplace (une fonction standard qui s'obtient autrement sur cet avion).

```yaml
# config/dictionnaire/xplane.yaml
fonctions:
  transpondeur.mode:
    description: mode du transpondeur
    dataref: sim/cockpit2/radios/actuators/transponder_mode
    valeurs: {"OFF": 0, STBY: 1, "ON": 2, ALT: 3}
    verifie: 2026-11-14, Boeing 737-800 Laminar

# config/avions/bae146-jf/fonctions.yaml
fonctions:
  pa.mode.hdg:
    description: mode HDG (cap affiché)
    commande: thranda/buttons/Button15
  pa.mode.hdg.voyant:
    dataref: thranda/TCAS/AnnLtA[337]
```

## Champs d'une entrée

| Champ | Rôle |
|---|---|
| `dataref` | valeur lue ou écrite dans le simulateur |
| `valeurs` | correspondance libellé → nombre (`"ON": 2`) |
| `commande` | commande déclenchée (bouton) |
| `commande_on`, `commande_off` | commandes d'un interrupteur, dans chaque sens |
| `bascule` | commande unique qui inverse un état |
| `etat`, `etat_on` | dataref de l'état et sa valeur « ON », pour corriger un interrupteur à commandes haut / bas |
| `echelle` | facteur appliqué à la valeur |
| `description`, `unite`, `verifie` | documentation, ignorée par le moteur |

## Citer une fonction dans un profil

**Tout le branchement d'une commande**, avec `fonction:` : ses paramètres (`dataref`, `dataref_values`, `command_on`…) viennent du dictionnaire, sauf ceux que la commande donne elle-même.

```yaml
      mode:
        type: selector
        positions: {"ON": 12, STBY: 13}
        fonction: transpondeur.mode
```

**À la place d'un dataref ou d'une commande**, partout où l'un d'eux est attendu :

```yaml
      boutons:
        type: commands
        inputs:
          25: pa.mode.hdg              # poussoir HDG SEL du MCP
      voyants:
        type: sim_leds
        leds:
          HDG SEL: pa.mode.hdg.voyant
      disengage:
        type: switch
        input: 14
        command_on: pa.deconnexion
```

Un nom qui contient `/` est un vrai dataref ou une vraie commande, gardé tel quel : les profils écrits sans le dictionnaire fonctionnent toujours. Un nom inconnu est refusé au chargement, avec les noms proches (« vouliez-vous pa.mode.hdg ? »).

## Consulter le dictionnaire

```sh
bin/pepit fonctions                                   # base X-Plane
bin/pepit fonctions config/avions/bae146-jf           # base + fonctions du 146
bin/pepit fonctions config/avions/bae146-jf --filtre pa.mode
```

```
pa.mode.hdg
    mode HDG (cap affiché)
    commande     thranda/buttons/Button15
    source       bae146-jf/fonctions.yaml
```

## Trouver les noms dans X-Plane

- Les datarefs et commandes standard sont listés dans `X-Plane 12/Resources/plugins/DataRefs.txt` et `Commands.txt`.
- Un avion qui définit les siens les cite dans ses objets 3D (`objects/*.obj`, lignes `ATTR_manip`) ; on peut aussi les relever en lecture seule pendant qu'on clique dans le cockpit 3D.
- N'ajoutez au dictionnaire de base que des branchements essayés sur un avion, avec la date et l'avion dans `verifie`.
