# Installation

Pepit fonctionne sous Linux. Il est testé sur **Ubuntu** avec **Python 3.14** et **X-Plane 12**.

## Le programme

```sh
sudo apt install python3-venv git
git clone https://github.com/pierrezNet/pepit.git && cd pepit
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

`requirements.txt` n'installe que deux bibliothèques : PySide6 (les fenêtres) et PyYAML (la configuration). L'accès aux cartes et la ligne de commande n'utilisent que la bibliothèque standard de Python.

## L'accès aux cartes

Les cartes OpenCockpits et EFDE sont des périphériques HID que Linux réserve à `root`. Une installation unique, avec `sudo`, règle l'accès aux cartes connues et prépare le bouton « Autoriser » de la [page Périphériques](../utilisation/peripheriques.md), qui ouvre ensuite l'accès à tout autre périphérique sans mot de passe.

Lisez d'abord le script, puis lancez-le :

```sh
less bin/pepit-installer
sudo bin/pepit-installer
```

Il installe :

| Fichier | Rôle |
|---|---|
| `/etc/udev/rules.d/99-pepit.rules` | l'accès aux cartes OpenCockpits et EFDE pour le groupe `plugdev` |
| `/usr/local/libexec/pepit-autoriser` | l'assistant du bouton « Autoriser », propriété de `root` ; Pepit n'appelle jamais la copie du dépôt |
| `/usr/share/polkit-1/actions/org.pepit.autoriser.policy` | la règle polkit : l'assistant se lance sans mot de passe pour l'utilisateur assis devant le PC, jamais pour une session distante |
| `/etc/udev/rules.d/70-pepit-autorises.rules` | les modèles autorisés par le bouton, vide au départ |

Débranchez puis rebranchez les cartes. Vérifiez que vous êtes dans le groupe `plugdev` avec la commande `id` ; sinon, ajoutez-vous avec `sudo usermod -aG plugdev $USER`, puis fermez et rouvrez votre session.

`sudo bin/pepit-installer --desinstaller` retire l'assistant et la règle polkit.

Les manettes Thrustmaster et autres joysticks n'ont besoin de rien : Pepit les lit par l'interface joystick de Linux, déjà accessible à l'utilisateur de la session.

## Les fenêtres sous GNOME Wayland

Les fenêtres de Pepit retiennent leur taille. Pour qu'elles retiennent aussi leur position et leur écran (par exemple l'écran du CDU), elles passent par XWayland, qui demande ces bibliothèques :

```sh
sudo apt install libxcb-cursor0 libxcb-icccm4 libxcb-keysyms1 libxcb-xkb1 libxkbcommon-x11-0
```

## Pour programmer des cartes Arduino ou ESP

Seulement si vous utilisez des [cartes wifi](../materiel/cartes-wifi.md) :

- installez **PlatformIO** (extension de VS Code, ou en ligne de commande) ;
- pour téléverser par le câble USB, la carte doit être accessible : bouton « Autoriser » de la [page Périphériques](../utilisation/peripheriques.md), ou groupe `dialout` (`sudo usermod -aG dialout $USER`, puis fermez et rouvrez votre session).

## Vérifier

```sh
bin/pepit list
```

La commande affiche les cartes de cockpit branchées, leur type et leur port USB. Si une carte manque, ouvrez la page Périphériques : elle montre chaque périphérique branché et si Pepit y a accès.

```sh
bin/pepit-peripheriques
```
