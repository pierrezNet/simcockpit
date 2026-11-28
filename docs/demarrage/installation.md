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

## L'accès aux cartes sans `sudo`

Les cartes OpenCockpits et EFDE sont des périphériques HID que Linux réserve à `root`. La règle udev de Pepit les ouvre aux membres du groupe `plugdev` :

```sh
sudo cp udev/99-pepit.rules /etc/udev/rules.d/
sudo udevadm control --reload && sudo udevadm trigger
```

Débranchez puis rebranchez les cartes. Vérifiez que vous êtes dans le groupe `plugdev` avec la commande `id` ; sinon, ajoutez-vous avec `sudo usermod -aG plugdev $USER`, puis fermez et rouvrez votre session.

Les manettes Thrustmaster n'ont pas besoin de cette règle : Pepit les lit par l'interface joystick de Linux, déjà accessible à l'utilisateur de la session.

## Les fenêtres sous GNOME Wayland

Les fenêtres de Pepit retiennent leur taille. Pour qu'elles retiennent aussi leur position et leur écran (par exemple l'écran du CDU), elles passent par XWayland, qui demande ces bibliothèques :

```sh
sudo apt install libxcb-cursor0 libxcb-icccm4 libxcb-keysyms1 libxcb-xkb1 libxkbcommon-x11-0
```

## Pour programmer des cartes Arduino ou ESP

Seulement si vous utilisez des [cartes wifi](../materiel/cartes-wifi.md) :

- installez **PlatformIO** (extension de VS Code, ou en ligne de commande) ;
- pour téléverser par le câble USB, ajoutez-vous au groupe `dialout` : `sudo usermod -aG dialout $USER`, puis fermez et rouvrez votre session.

## Vérifier

```sh
bin/pepit list
```

La commande affiche les cartes de cockpit branchées, leur type et leur port USB. Si une carte manque, voyez le [banc de test](../utilisation/banc.md) : il signale une carte présente mais inaccessible.
