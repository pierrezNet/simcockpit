"""Profils d'avion (dossiers de config/avions/) et choix du profil selon l'avion chargé.

Un profil déclare son avion dans sa section sim (`avion: B462`, ou une liste). Quand
X-Plane charge un avion, Pepit prend le profil qui le déclare.
"""

import glob
import os
from dataclasses import dataclass

import yaml

from .config import ConfigError, aircraft_codes

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PROFILES = "config/avions"


@dataclass(frozen=True)
class Profile:
    path: str            # « config/avions/bae146-jf », relatif à la racine du dépôt
    name: str            # « bae146-jf »
    aircraft: tuple      # codes OACI déclarés : ("B461", "B462", "B463")


def _declared(folder):
    """Codes OACI de la section sim du profil (lecture légère : sans tout charger)."""
    for path in sorted(glob.glob(os.path.join(folder, "*.yaml"))):
        try:
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except (OSError, yaml.YAMLError):
            continue
        sim = data.get("sim") if isinstance(data, dict) else None
        if isinstance(sim, dict) and "avion" in sim:
            try:
                return aircraft_codes(sim["avion"])
            except ConfigError:
                return ()
    return ()


def list_profiles(root=ROOT, folder=PROFILES):
    out = []
    for d in sorted(glob.glob(os.path.join(root, folder, "*", ""))):
        d = d.rstrip(os.sep)
        if glob.glob(os.path.join(d, "*.yaml")):
            out.append(Profile(os.path.relpath(d, root), os.path.basename(d), _declared(d)))
    return out


def profile_for(icao, profiles):
    """Le profil qui déclare cet avion, ou None."""
    icao = (icao or "").upper()
    return next((p for p in profiles if icao and icao in p.aircraft), None)


def same(a, b):
    """Deux chemins de profil désignent-ils le même dossier ? (« …/bae146-jf/ » compris)"""
    norm = lambda p: os.path.normpath(os.path.join(ROOT, p)) if p else ""   # noqa: E731
    return norm(a) == norm(b)
