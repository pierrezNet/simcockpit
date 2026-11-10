"""Mode développement : relance la fenêtre dès qu'un fichier du projet change.

Le programme tourne dans un processus enfant ; ce superviseur surveille la date de
modification des fichiers (aucune dépendance) et relance l'enfant après un changement.
Fermer la fenêtre arrête tout ; si le programme plante, on attend la correction suivante.
"""

import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
POLL = 0.5      # secondes entre deux vérifications
SETTLE = 0.3    # laisse l'éditeur finir d'écrire avant de relancer


def _snapshot(patterns):
    files = {}
    for pattern in patterns:
        for f in ROOT.glob(pattern):
            if "__pycache__" not in f.parts:
                try:
                    files[f] = f.stat().st_mtime_ns
                except FileNotFoundError:
                    pass
    return files


def _changed(old, new):
    return sorted(str(f.relative_to(ROOT)) for f in old.keys() | new.keys()
                  if old.get(f) != new.get(f))


def _stop(child):
    if child and child.poll() is None:
        child.terminate()
        try:
            child.wait(timeout=3)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()


def run(module, args, watch=("simcockpit/**/*.py",)):
    """Lance `python -m module args` et le relance à chaque modification des fichiers `watch`."""
    cmd = [sys.executable, "-m", module, *args]
    # arrêté par un signal (kill, fermeture du terminal) : on arrête aussi la fenêtre
    for sig in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt))
    print(f"[dev] surveillance de {', '.join(watch)} — fermez la fenêtre pour arrêter",
          flush=True)
    files = _snapshot(watch)
    child = subprocess.Popen(cmd, cwd=ROOT)
    waiting = False      # True : le programme a planté, on attend une correction
    try:
        while True:
            time.sleep(POLL)
            if child is not None and child.poll() is not None:
                if child.returncode == 0:
                    print("[dev] fenêtre fermée : arrêt", flush=True)
                    return 0
                if not waiting:
                    print(f"[dev] le programme s'est arrêté (code {child.returncode}) :"
                          " corrigez puis enregistrez, il sera relancé", flush=True)
                    waiting = True
            new = _snapshot(watch)
            changes = _changed(files, new)
            if not changes:
                continue
            time.sleep(SETTLE)
            files = _snapshot(watch)
            print(f"[dev] modifié : {', '.join(changes[:5])}"
                  f"{' …' if len(changes) > 5 else ''} — relance", flush=True)
            _stop(child)
            child = subprocess.Popen(cmd, cwd=ROOT)
            waiting = False
    except KeyboardInterrupt:
        _stop(child)
        return 0


def take_flag(argv):
    """Retire « --dev » de argv ; renvoie True s'il y était."""
    if "--dev" in argv:
        argv.remove("--dev")
        return True
    return False
