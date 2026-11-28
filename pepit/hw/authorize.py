"""Bouton « Autoriser » : ouvrir l'accès à un modèle de périphérique USB, sans mot de passe.

Pepit n'écrit jamais lui-même les règles udev : il demande à pkexec de lancer l'assistant
installé une fois en root par `sudo bin/pepit-installer` (voir udev/pepit-autoriser).
Ce module prépare la demande ; l'interface la lance et affiche le résultat.
"""

import os
import re

HELPER = "/usr/local/libexec/pepit-autoriser"
POLICY = "/usr/share/polkit-1/actions/org.pepit.autoriser.policy"
RULES = "/etc/udev/rules.d/70-pepit-autorises.rules"
PKEXEC = "/usr/bin/pkexec"
_LINE = re.compile(r"# pepit ([0-9a-f]{4}):([0-9a-f]{4}) (hidraw|serie|evdev)\s*$")


def installed(helper=HELPER, policy=POLICY, pkexec=PKEXEC):
    """L'assistant est-il installé (sudo bin/pepit-installer) ?"""
    return os.access(helper, os.X_OK) and os.path.exists(policy) and os.access(pkexec, os.X_OK)


def kinds_needed(device):
    """Types de nœuds à ouvrir pour que Pepit puisse se servir de `device` (usb.UsbDevice)."""
    return sorted({n.kind for n in device.useful_nodes if not n.access})


def command(device):
    """Commande pkexec pour ouvrir ce modèle, ou None s'il n'y a rien à ouvrir."""
    kinds = kinds_needed(device)
    if not kinds:
        return None
    return [PKEXEC, HELPER, "ajouter", device.vid.lower(), device.pid.lower(), *kinds]


def revoke_command(vid, pid):
    return [PKEXEC, HELPER, "retirer", vid.lower(), pid.lower()]


def authorized(path=RULES):
    """{(vid, pid): {types}} déjà autorisés (le fichier des règles est lisible par tous)."""
    out = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                m = _LINE.search(line)
                if m:
                    out.setdefault((m.group(1), m.group(2)), set()).add(m.group(3))
    except OSError:
        pass
    return out


def warning(device):
    """Mise en garde à montrer avant d'autoriser, ou None. Un périphérique qui n'est pas
    du matériel de simulation (clavier, souris…) lisible par tout programme de la session
    pourrait servir à espionner la frappe."""
    if device.cockpit:
        return None
    return (f"« {device.name} » n'est pas reconnu comme matériel de simulation. S'il s'agit"
            " d'un clavier ou d'une souris, l'autoriser permettrait à tout programme de votre"
            " session de lire ce que vous tapez. Autoriser quand même ?")
