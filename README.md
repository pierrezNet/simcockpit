# simcockpit

Pilotage libre, sous **Linux**, de cartes d'interface pour cockpit de simulateur de vol
(**OpenCockpits**, **EFDE**), écrit en Python. Une alternative à SIOC, le logiciel
officiel d'OpenCockpits, qui ne fonctionne que sous Windows.

- détecte et classe les cartes branchées en USB ;
- montre en direct chaque entrée (interrupteurs, poussoirs, encodeurs, axes) et permet de
  tester les sorties (voyants, afficheurs 7 segments) ;
- décrit la logique du cockpit dans un simple fichier YAML (transpondeur, pilote
  automatique…) et l'exécute ;
- connexion à **X-Plane 12** : prévue, pas encore écrite.

> **État : preuve de concept.** Les protocoles ont été retrouvés par rétro-ingénierie
> sur du matériel réel (voir [Protocoles](#protocoles)). Ce projet n'est affilié ni à
> OpenCockpits ni à EFDE.

## Cartes prises en charge

| Carte | Nom USB | Entrées | Sorties |
|---|---|---|---|
| EFDE IO32 | `USB32I04AD` | ✅ 32 entrées, 4 axes | ✅ 32 sorties (testée sur une seule) |
| OpenCockpits MCP (pilote automatique 737) | `IOCard-MCP` | ✅ boutons, interrupteurs, 6 encodeurs | ✅ 6 afficheurs, 15 voyants, point décimal |
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
./simcockpit-gui
```

Un onglet par carte détectée :
- une grille de toutes les entrées : une case s'allume quand on actionne la commande
  correspondante, et le numéro de la dernière entrée actionnée s'affiche en grand ;
- les axes analogiques ;
- les sorties. Leur écriture est verrouillée tant que la case « Autoriser l'écriture »
  n'est pas cochée.

Pour le MCP, l'onglet propose aussi un champ par afficheur et un bouton par voyant.

### Panneau virtuel (logique du cockpit)

```sh
./cockpit-panel            # lit cockpit.yaml
./cockpit-panel autre.yaml
```

Le panneau connecte les cartes déclarées dans la configuration, applique la logique de
chaque instrument (un onglet par instrument), puis met à jour les afficheurs et les
voyants du matériel. Après une modification du fichier YAML, cliquez sur « Recharger la
configuration ».

> Les afficheurs du MCP ne restent allumés **que tant qu'un programme lit la carte**.
> Gardez donc `cockpit-panel` ou `simcockpit-gui` ouvert.

### Ligne de commande

```sh
python3 -m simcockpit list [--all]        # détecter et classer les cartes
python3 -m simcockpit watch [--axes]      # changements d'entrées (anti-rebond 50 ms)
python3 -m simcockpit diag -s 10          # repérer les entrées instables
python3 -m simcockpit check               # assistant : tester les entrées borne par borne
python3 -m simcockpit outputs             # assistant : tester les sorties une par une
python3 -m simcockpit listen --port 1-14  # trames brutes, sans rien envoyer
python3 -m simcockpit send --port 1-14 "…" # envoyer une trame brute (essais)
```

## Configuration : `cockpit.yaml`

Une carte est désignée par son nom USB. Ajoutez son port USB (`usb_port`, affiché par
`list`) si plusieurs cartes identiques sont branchées. Les numéros d'entrées sont ceux
affichés par `simcockpit-gui`.

```yaml
cards:
  mcp:
    product: IOCard-MCP

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

Options communes à tous les types : `display` (afficheur), `led` (voyant), `leading_zeros`.

À noter :
- Les valeurs codées sur plusieurs entrées (transpondeur, sélecteurs) sont filtrées en
  **groupe**. Sinon, les bits qui basculent à quelques millisecondes d'écart feraient
  apparaître des valeurs intermédiaires fausses.
- **Encodeurs :** un changement d'état correspond à un cran. Ils accélèrent quand les
  crans s'enchaînent vite (par défaut ×3 sous 0,15 s et ×10 sous 0,06 s).
- **`speed_encoder` :** avec `altitude_from`, le bouton C/O convertit la vitesse indiquée
  en Mach à l'altitude affichée (atmosphère standard, QNH 1013, vent nul), et
  inversement. Le Mach s'affiche `.78` sur le MCP.

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

Le détail et les cas vérifiés se trouvent dans `simcockpit/hw/` et dans les tests, qui
rejouent des captures réelles (`tests/data/`).

## Tests

```sh
.venv/bin/python -m unittest discover -s tests -t .
```

## Structure du projet

```
simcockpit/hw/      accès hidraw, registre des cartes, protocoles (mastercard, bitmap, mcp)
simcockpit/diag/    bruit, assistants de test des entrées et des sorties
simcockpit/logic/   configuration, types de commandes, moteur, atmosphère standard
simcockpit/gui/     fenêtre de test des cartes
simcockpit/panel/   panneau virtuel (logique du cockpit)
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
