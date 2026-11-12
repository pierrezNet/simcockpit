# simcockpit

Pilotage libre, sous **Linux**, de cartes d'interface pour cockpit de simulateur de vol
(**OpenCockpits**, **EFDE**), écrit en Python. Une alternative à SIOC, le logiciel
officiel d'OpenCockpits, qui ne fonctionne que sous Windows.

- détecte et classe les cartes branchées en USB ;
- montre en direct chaque entrée (interrupteurs, poussoirs, encodeurs, axes) et permet de
  tester les sorties (voyants, afficheurs 7 segments) ;
- décrit la logique du cockpit dans un simple fichier YAML (transpondeur, pilote
  automatique…) et l'exécute ;
- se relie à **X-Plane 12** par son protocole UDP natif, sans plugin (MCP relié au
  Boeing 737-800 de Laminar).

> **État : preuve de concept.** Les protocoles ont été retrouvés par rétro-ingénierie
> sur du matériel réel (voir [Protocoles](#protocoles)). Ce projet n'est affilié ni à
> OpenCockpits ni à EFDE.

## Cartes prises en charge

| Carte | Nom USB | Entrées | Sorties |
|---|---|---|---|
| EFDE IO32 | `USB32I04AD` | ✅ 32 entrées, 4 axes | ✅ 32 sorties (testée sur une seule) |
| OpenCockpits MCP (pilote automatique 737) | `IOCard-MCP` | ✅ boutons, interrupteurs, 6 encodeurs | ✅ 6 afficheurs, 15 voyants, point décimal |
| EFDE DME (réplique Collins IND-42) | `DME USB` | ✅ boutons SEL et PWR | ✅ distance, texte, 9 voyants, rétroéclairage, marche/arrêt |
| OpenCockpits radio Airbus | `IOCard-RadioAirb` | ✅ 8 poussoirs, ON/OFF, double rotatif | ✅ 2 afficheurs de 6 chiffres, points décimaux, 8 voyants |
| OpenCockpits CDU 737 | `USBFMC V1.0` | ✅ 70 touches | ✅ 5 voyants (OFST, MSG, EXEC, DSPY, FAIL) |
| OpenCockpits USB Expansion + Master Card | `IOCardUSB` | ✅ 72 entrées (la Master Card doit être alimentée) | ⚠️ codage connu, non testé |

Une carte d'un de ces fabricants dont le modèle est inconnu est quand même détectée.
Elle est alors ouverte en **écoute seule** : rien ne lui est envoyé.

## Installation (Ubuntu / Debian)

Testé avec Python 3.14.

```sh
sudo apt install python3-venv
git clone https://github.com/pierrezNet/simcockpit.git && cd simcockpit
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Pour accéder aux cartes sans `sudo`, installez la règle udev, puis débranchez et
rebranchez les cartes. L'utilisateur doit être dans le groupe `plugdev`.

```sh
sudo cp udev/99-simcockpit.rules /etc/udev/rules.d/
sudo udevadm control --reload && sudo udevadm trigger
```

## Utilisation

### Fenêtre de test des cartes

```sh
bin/simcockpit-gui
```

Un onglet par carte détectée :
- une grille de toutes les entrées : une case s'allume quand on actionne la commande
  correspondante, et le numéro de la dernière entrée actionnée s'affiche en grand ;
- les axes analogiques ;
- les sorties. Leur écriture est verrouillée tant que la case « Autoriser l'écriture »
  n'est pas cochée.

Avec la case « Suivre la carte actionnée », l'onglet de la carte dont on vient d'actionner
une commande passe au premier plan.

Pour le MCP, l'onglet propose aussi un champ par afficheur et un bouton par voyant.
Pour le CDU, il affiche toutes les touches et un bouton par voyant.
Pour la radio Airbus, il propose un champ par afficheur (« 118.700 ») et un bouton par voyant.
Pour le DME, il propose la distance, le texte de droite, les voyants, le rétroéclairage
et la mise en marche ou l'arrêt.

### Panneau virtuel (logique du cockpit)

```sh
bin/cockpit-panel                                # Avro RJ85, logique simulée
bin/cockpit-panel config/avions/b738-laminar     # Boeing 737-800 de Laminar (X-Plane)
```

Le panneau connecte les cartes déclarées dans la configuration, applique la logique de
chaque instrument (un onglet par instrument), puis met à jour les afficheurs et les
voyants du matériel. Après une modification du fichier YAML, cliquez sur « Recharger la
configuration ».

> Les afficheurs du MCP ne restent allumés **que tant qu'un programme lit la carte**.
> Gardez donc `bin/cockpit-panel` ou `bin/simcockpit-gui` ouvert.

### Mode développement

```sh
bin/simcockpit-gui --dev
bin/cockpit-panel --dev [config/avions/…]
```

La fenêtre se relance d'elle-même dès qu'un fichier Python du projet est enregistré (et,
pour le panneau, un fichier YAML). Si le programme plante, il est relancé à la correction
suivante. Fermer la fenêtre arrête tout.

### Ligne de commande

```sh
bin/simcockpit list [--all]               # détecter et classer les cartes
bin/simcockpit watch [--axes]             # changements d'entrées (anti-rebond 50 ms)
bin/simcockpit diag -s 10                 # repérer les entrées instables
bin/simcockpit check                      # assistant : tester les entrées borne par borne
bin/simcockpit outputs                    # assistant : tester les sorties une par une
bin/simcockpit listen --port 1-14         # trames brutes, sans rien envoyer
bin/simcockpit send --port 1-14 "…"       # envoyer une trame brute (essais)
```

### Avec X-Plane 12

```sh
bin/cockpit-panel config/avions/b738-laminar     # MCP relié au Boeing 737-800 de Laminar
```

Lancez X-Plane (le port UDP 49000 est ouvert par défaut) et chargez l'avion. Le panneau
affiche « X-Plane : connecté » dès que le simulateur répond, et se reconnecte seul s'il
redémarre. À la connexion, la position des interrupteurs du MCP est envoyée à l'avion.

## Configuration : `config/`

```
config/
├── materiel.yaml           # cartes physiques, décrites une seule fois
└── avions/
    ├── rj85-simule/        # Avro RJ85, logique simulée (sans X-Plane)
    │   ├── dme.yaml
    │   ├── mcp.yaml
    │   └── transpondeur.yaml
    └── b738-laminar/       # Boeing 737-800 de Laminar (X-Plane 12)
        ├── mcp.yaml
        └── sim.yaml        # liaison X-Plane
```

- **`materiel.yaml`** déclare les cartes (section `cards`). Une carte est désignée par son
  nom USB ; ajoutez `usb_port` (affiché par `list`) si plusieurs cartes identiques sont
  branchées.
- **Un avion est un dossier.** Chaque fichier y apporte un ou plusieurs instruments
  (section `instruments`), et l'un d'eux peut déclarer la liaison simulateur (`sim`).
  Les onglets suivent l'ordre alphabétique des fichiers. Seules les cartes utilisées par
  l'avion sont ouvertes.
- Pour un nouvel avion, copiez un dossier et adaptez-le. Un fichier YAML unique et
  complet (`cards` + `instruments`) reste accepté.

Les numéros d'entrées sont ceux affichés par `simcockpit-gui`. Exemple d'instrument :

```yaml
instruments:
  mcp:
    label: MCP (pilote automatique)
    card: mcp
    controls:
      cap:
        type: encoder
        inputs: [6, 7]
        min: 0
        max: 359
        wrap: true            # 359 → 0
        display: HDG          # afficheur du MCP
        leading_zeros: true   # « 045 »
      at_arm:
        type: switch
        input: 30
        led: A/T ARM          # voyant du MCP
```

| Type | Rôle | Paramètres principaux |
|---|---|---|
| `switch` | interrupteur ou poussoir | `input` |
| `selector` | sélecteur à positions (la première position active l'emporte) | `positions`, `default` |
| `octal_digits` | chiffres codés en binaire sur 3 entrées (transpondeur) | `inputs` |
| `encoder` | encodeur rotatif | `inputs`, `min`, `max`, `step`, `wrap`, `invert`, `initial`, `accel` |
| `speed_encoder` | vitesse avec bascule IAS / Mach (bouton C/O) | `toggle_input`, `toggle_level`, `ias`, `mach`, `altitude_from` |
| `dme_indicator` | indicateur DME Collins IND-42C sur le DME EFDE | `channel`, `self_test`, `backlight` |
| `commands` | poussoirs → commandes X-Plane (`inputs: {entrée: commande}`) | `inputs`, `level` |
| `sim_leds` | voyants du MCP qui suivent des datarefs X-Plane | `leds` |
| `rj_autopilot` | modes du pilote automatique de l'Avro RJ sur le MCP (voyants compris) | `buttons`, `fd_left`, `fd_right`, `at_arm`, `disengage` |

Options communes à tous les types : `display` (afficheur), `led` (voyant), et pour
l'afficheur :
- `leading_zeros: true` : tous les chiffres remplis (cap « 045 ») ;
- `min_digits: 3` : au moins 3 chiffres (altitude 0 → « 000 », 10000 → « 10000 ») ;
- `blank_when: 0` : afficheur éteint pour cette valeur ;
- `blank_unless: <dataref>` : afficheur éteint tant que ce dataref vaut 0 (avec X-Plane
  connecté), par exemple la fenêtre V/S du 737 tant que le mode V/S n'est pas engagé.

Liaison X-Plane (section `sim: {type: xplane, host, port}` en tête du fichier) :
- `encoder` et `speed_encoder` : `dataref` (valeur écrite quand on tourne, et affichée
  quand elle change dans le simulateur) ; pour la vitesse, `mach_dataref` et
  `toggle_command` (bouton C/O) ;
- `switch` : `command_on` / `command_off`, ou `toggle_command` avec `state_dataref` et
  `state_on` pour un interrupteur que le simulateur ne connaît qu'en bascule ; `invert`.

Les noms de datarefs et de commandes se trouvent dans `X-Plane 12/Resources/plugins/`
(`DataRefs.txt`, `Commands.txt`) et, pour un avion qui définit les siens, dans ses
scripts (voir `config/avions/b738-laminar/mcp.yaml`).

À noter :
- Les valeurs codées sur plusieurs entrées (transpondeur, sélecteurs) sont filtrées en
  **groupe**. Sinon, les bits qui basculent à quelques millisecondes d'écart feraient
  apparaître des valeurs intermédiaires fausses.
- **Encodeurs :** un changement d'état correspond à un cran. Ils accélèrent quand les
  crans s'enchaînent vite (par défaut ×3 sous 0,15 s et ×10 sous 0,06 s).
- **`speed_encoder` :** avec `altitude_from`, le bouton C/O convertit la vitesse indiquée
  en Mach à l'altitude affichée (atmosphère standard, QNH 1013, vent nul), et
  inversement. Le Mach s'affiche `.78` sur le MCP.

- **`dme_indicator` :** à la mise sous tension, test des segments puis distance (NM) et
  identifiant de la station (ID). SEL fait défiler ID → KT (vitesse sol) → MIN (temps
  jusqu'à la station) ; PWR allume et éteint ; sans signal, des tirets. Le canal (voyant
  1, 2 ou 3) est fixe, comme sur l'IND-42C. Le HLD de l'avion (appui long sur SEL) n'est
  pas repris : le bouton du DME EFDE ne transmet pas la durée d'appui. En attendant
  X-Plane, le panneau virtuel simule la distance, la vitesse sol et l'identifiant.

- **`rj_autopilot` :** en attendant X-Plane, la logique est simulée. Les modes latéraux (HDG,
  NAV, LNAV) sont exclusifs entre eux, de même que les modes verticaux (ALT, VS, LVL CHG,
  VNAV). APP engage les deux axes. Un nouvel appui sur un mode engagé le désengage.
  CMD A et CMD B choisissent NAV1 ou NAV2 ; N1 et SPEED basculent THRUST. Les voyants
  CWS A et CWS B suivent les F/D gauche et droit, et A/T ARM suit son interrupteur. La
  barre DISENGAGE baissée coupe tout. Un appui sans effet (CWS avec F/D sur OFF, bouton
  avec la barre baissée) affiche une alerte dans le panneau.

## Protocoles

Toutes les cartes se pilotent en HID brut (`/dev/hidraw*`), avec des rapports de 8 octets
sans numéro de rapport. La carte ne transmet ses entrées qu'après l'initialisation
`3d 00 3a <nb cartes> 39 <nb axes> ff ff`.

**Entrées, format « Master Card » (EFDE IO32, IOCardUSB).** Seuls les changements sont
transmis :
- octet 0 : bits 0 à 3 = Master Cards concernées ; bits 4 à 6 = numéro d'axe ; bit 7 =
  suite de la trame précédente ;
- un octet d'axe, si la trame en contient un ;
- un masque des groupes (« slots ») qui ont changé ;
- un octet de 8 entrées par groupe présent dans le masque ;
- un octet de « 9ᵉ entrées », où le bit *i* correspond au *i*-ème groupe **présent**.

Une entrée a le numéro 9 × groupe + bit (numérotation SIOC). Une entrée actionnée vaut 1
sur l'EFDE, 0 sur la Master Card.

**Entrées du MCP.** L'état complet des 64 entrées est envoyé toutes les 40 ms environ ;
l'entrée *n* correspond au bit *n % 8* de l'octet *n / 8*. Chaque encodeur occupe deux
entrées, en code Gray (00 → 01 → 11 → 10 dans le sens horaire).

**Sorties du MCP** (ce n'est pas le format Master Card). Une trame est lue comme
16 demi-octets *n0* à *n15* : l'octet *k* donne *n2k* (moitié basse) et *n2k+1* (moitié
haute).

- *n12* : numéro de page.
- Octet 7 : luminosité, à l'envers (`00` = maximum).

| Page | Contenu |
|---|---|
| 0 | CRS1 = n2 n1 n0 · IAS = n5 n4 n3 · HDG = n8 n7 n6 · ALT (2 premiers chiffres) = n10 n9 · n11 bit 3 = point décimal d'IAS |
| 1 | ALT (3 derniers chiffres) = n2 n1 n0 · CRS2 = n5 n4 n3 · V/S = n10 … n6 |
| 2 | voyants : 16 bits dans les octets 0 et 1 (voir `simcockpit/hw/mcp.py`) |

Codes des chiffres : 0 à 9 ; `a` = chiffre éteint ; `b` = signe moins.

**DME EFDE** (protocole communiqué par EFDE, vérifié à la webcam). Le DME émet sans
initialisation, même éteint ; l'octet 0 vaut `01` tant que SEL est enfoncé, `02` pour
PWR, `0a` au repos. PWR éteint et rallume l'écran de lui-même. En
écriture, l'octet 0 désigne la fonction :

| Fonction | Rôle | Paramètres |
|---|---|---|
| `01` | distance à gauche | octets 1-2 : dixièmes de NM ; dixième affiché sous 200 NM, entier au-delà |
| `02` | texte à droite (identifiant de balise) | octets 1-4 : 4 caractères ASCII |
| `03` | voyant 1, 2 ou 3 | octet 7 : 1 à 3, 0 = éteint |
| `04` | WPT ou NM | octet 5 : 1 = WPT, 2 = NM, 0 = éteint |
| `05` | HLD, KT, MIN ou ID | octet 6 : 1 à 4, 0 = éteint |
| `06` | texte libre | octet 1 : colonne 1 à 9 ; octets 2-5 : 4 caractères |
| `07` | efface l'écran | |
| `08` | rétroéclairage | octet 1 : 0 = cellule photo (couverte : éteint), 1 à 255 = valeur fixe |
| `09` / `0a` | éteint / allume (test des segments) | |

Complétez les textes avec des espaces : un octet `00` allume des segments parasites.

**Radio OpenCockpits Airbus** (`IOCard-RadioAirb`). Même réveil et mêmes entrées que le
MCP. En écriture, deux sortes de trames, selon le bit 7 de l'octet 6 :
- **afficheurs** (bit 7 à 0) : 12 demi-octets dans les octets 0 à 5, ACTIVE = n5 … n0 et
  STANDBY = n11 … n6 (codes du MCP) ; les bits 0 à 5 de l'octet 6 allument les points
  décimaux (`02` : ACTIVE « 888.888 », `08` : STANDBY « 888.888 », voir
  `simcockpit/hw/radio_airbus.py`) ;
- **voyants** (octet 6 = `80`) : un bit par voyant dans l'octet 0 (VHF1, VHF2, SEL, VOR,
  ADF, BFO, NAV, ILS).

**CDU OpenCockpits** (`USBFMC V1.0`, fabricant USB « Opencockpits »). La carte reste muette
tant qu'on ne lui a rien écrit. Ensuite, chaque appui envoie une trame dont l'octet 0 est
le numéro de la touche (1 à 88) ; rien n'est envoyé au relâchement. En écriture, l'octet 0
est un masque des voyants : bit 0 OFST, 1 MSG, 2 EXEC, 3 DSPY, 4 FAIL. La table des touches
est dans `simcockpit/hw/usbfmc.py`.

Le détail et les cas vérifiés se trouvent dans `simcockpit/hw/` et dans les tests, qui
rejouent des captures réelles (`tests/data/`).

## Tests

```sh
.venv/bin/python -m unittest discover -s tests -t .
```

## Structure du projet

```
bin/                lanceurs : simcockpit-gui, cockpit-panel, simcockpit (ligne de commande)
config/             configuration : matériel et un dossier par avion
simcockpit/hw/      accès hidraw, registre des cartes, protocoles (mastercard, bitmap, mcp, dme, usbfmc, radio_airbus)
simcockpit/diag/    bruit, assistants de test des entrées et des sorties
simcockpit/logic/   configuration, types de commandes, moteur, atmosphère standard
simcockpit/gui/     fenêtre de test des cartes
simcockpit/panel/   panneau virtuel (logique du cockpit)
simcockpit/sim/     liaison X-Plane (UDP)
tests/              tests unitaires et captures réelles
udev/               règle d'accès aux cartes
iocard_test.py      script d'exploration d'origine (référence)
```

## Remerciements

Le format des entrées Master Card et le codage des sorties ont été établis en lisant le
code de [xpiocards](https://sourceforge.net/projects/xpiocards/) et de
[xpcockpit](https://github.com/retostockli/xpcockpit) (Reto Stöckli). simcockpit est une
réécriture indépendante : aucun code de ces projets n'a été copié. Le protocole de
sortie du MCP a été retrouvé par essais, en vérifiant chaque résultat à la webcam.

## Licence

simcockpit est un logiciel libre, distribué sous la **GNU General Public License,
version 3 ou toute version ultérieure** (GPL-3.0-or-later), comme xpcockpit, dont il
s'inspire. Voir le fichier [LICENSE](LICENSE).
