# Types de commandes

Chaque commande d'un instrument a un `type`, qui dit comment lire les entrées de la carte et ce qu'elles produisent.

## Vue d'ensemble

| Type | Rôle | Paramètres principaux |
|---|---|---|
| `switch` | interrupteur ou poussoir | `input`, `invert`, `command_on`, `command_off`, `toggle_command`, `state_dataref`, `state_on` |
| `selector` | sélecteur à positions (la première position active l'emporte) | `positions`, `default`, `dataref`, `dataref_values` |
| `octal_digits` | chiffres codés en binaire sur 3 entrées (transpondeur) | `inputs`, `dataref` |
| `encoder` | encodeur rotatif | `inputs`, `min`, `max`, `step`, `wrap`, `invert`, `initial`, `accel`, `dataref` |
| `speed_encoder` | vitesse avec bascule IAS / Mach (bouton C/O) | `toggle_input`, `toggle_level`, `ias`, `mach`, `altitude_from`, `mach_dataref`, `toggle_command` |
| `commands` | poussoirs → commandes du simulateur | `inputs` (`{entrée: commande}`), `level` |
| `sim_leds` | voyants qui suivent des valeurs du simulateur | `leds` (`{voyant: dataref}`) |
| `keypad` | clavier (CDU) : chaque touche déclenche une commande | `keys` |
| `cdu_screen` | écran du FMS standard d'X-Plane (16 × 24 caractères, couleurs) | `side` (1 commandant, 2 copilote) |
| `ufmc_screen` | écran de l'UFMC de FJCC (FMC du BAe 146), lu par l'API web | — |
| `radio_panel` | boîtier radio (radio Airbus) : sources COM/NAV/ADF, bagues, transfert | `sources`, `outer`, `inner`, `transfer`, `power`, `power_on`, `button_level` |
| `dme_indicator` | indicateur DME Collins IND-42C sur le DME EFDE | `channel`, `self_test`, `backlight` |
| `gauge` | jauge du bus FDBUS | `gauge`, `dataref`, `scale`, `rest` |
| `throttle_axis` | manette des gaz : un axe pilote la poussée d'un ou plusieurs moteurs | `axis`, `datarefs`, `ralenti`, `plein_gaz`, `coupure`, `valeur_coupure` |
| `iocp_outputs` | valeurs du simulateur envoyées à une carte wifi | `variables`, `echelle` |
| `iocp_lookup` | page d'un livret choisie selon une valeur du simulateur, envoyée à une carte wifi | `source`, `choix`, `variables`, `pages` |
| `rj_autopilot` | modes du pilote automatique de l'Avro RJ, simulés | `buttons`, `fd_left`, `fd_right`, `at_arm`, `disengage` |

Partout où un dataref ou une commande est attendu, on peut écrire un nom du [dictionnaire des fonctions](dictionnaire.md), ou `fonction:` pour tout le branchement.

## Options communes : afficheurs et voyants

Sur une carte à afficheurs (MCP), une commande peut piloter un afficheur (`display: HDG`) ou un voyant (`led: A/T ARM`). Pour l'afficheur :

- `leading_zeros: true` : tous les chiffres remplis (cap « 045 ») ;
- `min_digits: 3` : au moins 3 chiffres (altitude 0 → « 000 ») ;
- `blank_when: 0` : afficheur éteint pour cette valeur ;
- `blank_unless: <dataref>` : afficheur éteint tant que ce dataref vaut 0, par exemple la fenêtre V/S du 737 tant que le mode V/S n'est pas engagé.

## Interrupteurs, sélecteurs, chiffres

```yaml
fd_gauche:
  type: switch
  input: 15
  command_on: sim/autopilot/fdir_command_bars_on
  command_off: sim/autopilot/fdir_command_bars_off
```

- `command_on` / `command_off` sont envoyées à chaque changement de position, et à la connexion du simulateur.
- `toggle_command` + `state_dataref` + `state_on` : pour un interrupteur que le simulateur ne connaît qu'en bascule ; la commande est répétée tant que l'avion n'est pas dans la position du matériel.
- `command_on` / `command_off` + `state_dataref` : interrupteur à commandes haut / bas (FD BARS du BAe 146) ; la commande n'est envoyée que si l'avion n'est pas déjà dans la bonne position, au plus trois fois.
- `invert: true` : la position « on » est l'entrée au repos (barre DISENGAGE baissée).

Les **sélecteurs** et les **chiffres codés** (`octal_digits`, transpondeur) sont filtrés en **groupe** : sinon, les bits qui basculent à quelques millisecondes d'écart feraient apparaître des valeurs intermédiaires fausses. Leur position est poussée vers le simulateur à chaque changement et à la connexion.

## Encodeurs

```yaml
cap:
  type: encoder
  inputs: [6, 7]
  min: 0
  max: 359
  wrap: true            # 359 → 0
  display: HDG
  leading_zeros: true
  fonction: pa.cap
```

Un changement d'état est un cran. Les encodeurs accélèrent quand les crans s'enchaînent vite (par défaut ×3 sous 0,15 s et ×10 sous 0,06 s ; réglable avec `accel`). Avec un `dataref`, la valeur est écrite quand on tourne et suit le simulateur quand elle y change.

Le **`speed_encoder`** ajoute la bascule IAS / Mach : avec `altitude_from`, le bouton C/O convertit la vitesse à l'altitude affichée (atmosphère standard, QNH 1013, vent nul). Le Mach s'affiche `.78` sur le MCP.

## Jauges FDBUS : `gauge`

```yaml
vitesse_verticale:
  type: gauge
  gauge: Vitesse verticale      # nom donné au banc de test
  fonction: vitesse_verticale
```

Le nom renvoie, dans `config/fdbus.yaml`, au module, à la sortie et à l'étalonnage réglés au [banc de test](../utilisation/banc.md). Le profil dit seulement quelle valeur la jauge indique (`dataref`, multipliée par `scale` si besoin). Sans simulateur, l'aiguille revient au repos (`rest`, 0 par défaut). Un module absent, ou d'un autre type que celui étalonné, est signalé et ne reçoit rien.

## Manettes des gaz : `throttle_axis`

```yaml
gauche:
  type: throttle_axis
  axis: 0
  datarefs: [moteur1.manette, moteur2.manette]   # une manette pour deux moteurs
  ralenti: 0.70
  plein_gaz: 0.03
  coupure: 0.80          # au-delà : position OFF
  valeur_coupure: -0.1
```

La position de l'axe (0 à 1) devient une poussée entre `ralenti` (0) et `plein_gaz` (1), dans un sens ou dans l'autre. Au-delà du ralenti, la poussée reste nulle. Avec `coupure`, une position encore plus loin donne `valeur_coupure` : la position OFF (carburant coupé) des avions sans inverseur ; on en ressort en revenant un peu vers le cran, pour qu'une vibration ne coupe pas le moteur.

!!! warning "Désaffecter les axes dans X-Plane"
    Les axes utilisés par Pepit doivent être sur « None » dans les réglages joystick d'X-Plane, sinon les deux écrivent la poussée.

## Cartes wifi : `iocp_outputs` et `iocp_lookup`

```yaml
afficheur:
  type: iocp_outputs
  variables:
    201: carburant.aile_gauche
    202: carburant.aile_droite
```

```yaml
livret:
  type: iocp_lookup
  source: masse.totale
  choix: superieur              # page de la masse immédiatement supérieure (ou « proche »)
  variables: {page: 210, vr_18: 211, v2_18: 212}
  pages:
    38000: {vr_18: 128, v2_18: 134}
```

Voir [Cartes wifi (IOCP)](../materiel/cartes-wifi.md).

## DME : `dme_indicator`

À la mise sous tension, test des segments puis distance (NM) et identifiant de la station. SEL fait défiler ID → KT (vitesse sol) → MIN (temps jusqu'à la station) ; PWR allume et éteint ; sans signal, des tirets. Le canal (voyant 1, 2 ou 3) est fixe, comme sur l'IND-42C. Le HLD (appui long sur SEL) n'est pas repris : le bouton du DME EFDE ne transmet pas la durée d'appui.

## Pilote automatique simulé : `rj_autopilot`

Logique de l'Avro RJ, en attendant un avion qui la fournisse. Les modes latéraux (HDG, NAV, LNAV) sont exclusifs entre eux, de même que les modes verticaux (ALT, VS, LVL CHG, VNAV). APP engage les deux axes ; un nouvel appui désengage. CMD A et CMD B choisissent NAV1 ou NAV2 ; N1 et SPEED basculent THRUST ; la barre DISENGAGE baissée coupe tout. Un appui sans effet affiche une alerte.
