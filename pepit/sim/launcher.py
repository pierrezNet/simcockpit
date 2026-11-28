"""Lancer X-Plane depuis Pepit, et savoir s'il tourne déjà.

X-Plane est lancé détaché (sa propre session) : quitter Pepit ne l'arrête pas. On sait
qu'il tourne en cherchant son processus, ce qui marche dès le lancement, bien avant que
sa liaison UDP réponde (le chargement prend plusieurs minutes).
"""

import os
import subprocess

CANDIDATES = ("~/X-Plane 12/X-Plane-x86_64", "~/X-Plane 11/X-Plane-x86_64")


def find():
    """Chemin de l'exécutable d'X-Plane dans les dossiers habituels, ou « »."""
    for c in CANDIDATES:
        path = os.path.expanduser(c)
        if os.access(path, os.X_OK):
            return path
    return ""


def usable(path):
    return bool(path) and os.path.isfile(path) and os.access(path, os.X_OK)


def running(path, proc="/proc"):
    """Un processus de cet exécutable tourne-t-il (pour ce compte ou un autre) ?"""
    name = os.path.basename(path or "")[:15]          # /proc/PID/comm : 15 caractères au plus
    if not name:
        return False
    try:
        pids = [p for p in os.listdir(proc) if p.isdigit()]
    except OSError:
        return False
    for pid in pids:
        try:
            with open(os.path.join(proc, pid, "comm")) as f:
                if f.read().strip() == name:
                    return True
        except OSError:
            continue
    return False


def launch(path):
    """Démarre X-Plane, détaché, depuis son dossier. Lève OSError si c'est impossible."""
    if not usable(path):
        raise OSError(f"exécutable introuvable : {path or '(non réglé)'}")
    return subprocess.Popen([path], cwd=os.path.dirname(path), start_new_session=True,
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
