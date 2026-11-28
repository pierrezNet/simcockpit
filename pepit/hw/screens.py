"""Écrans physiques du cockpit (écran du CDU…) : sortie vidéo et cadrage.

Un écran physique est une sortie vidéo du PC (nom donné par xrandr, ex. « HDMI-2 ») placée
derrière la façade d'un équipement. Le cadrage (marges en pixels) fait tomber l'image dans
la découpe de la façade. Tout se règle dans le panneau et reste dans config/ecrans.yaml :
rien n'est figé dans le code.
"""

from dataclasses import dataclass, field
from pathlib import Path

SCREENS_FILE = Path(__file__).resolve().parents[2] / "config" / "ecrans.yaml"
MIN_SIZE = 40          # px : taille minimale de la zone utile, quelles que soient les marges
_HEADER = """\
# Écrans physiques du cockpit, écrit par le panneau (onglet de l'équipement).
# sortie : nom de la sortie vidéo (xrandr --listmonitors), marges : gauche, haut, droite,
# bas en pixels, pour faire tomber l'image dans la découpe de la façade.
"""


@dataclass
class ScreenSetup:
    output: str = ""                                   # "" = pas d'écran physique
    margins: list = field(default_factory=lambda: [0, 0, 0, 0])   # gauche, haut, droite, bas


def content_rect(width, height, margins):
    """Zone utile (x, y, largeur, hauteur) d'un écran de `width` × `height` une fois les
    marges retirées ; jamais plus petite que MIN_SIZE."""
    left, top, right, bottom = (max(0, int(m)) for m in margins)
    w = max(MIN_SIZE, width - left - right)
    h = max(MIN_SIZE, height - top - bottom)
    return min(left, max(0, width - w)), min(top, max(0, height - h)), w, h


def load_screens(path=SCREENS_FILE):
    """{équipement: ScreenSetup} ; vide si le fichier n'existe pas."""
    import yaml
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except FileNotFoundError:
        return {}
    out = {}
    for name, spec in data.items():
        spec = spec or {}
        margins = list(spec.get("marges") or [0, 0, 0, 0])[:4]
        margins += [0] * (4 - len(margins))
        out[str(name)] = ScreenSetup(str(spec.get("sortie") or ""), [int(m) for m in margins])
    return out


def save_screens(screens, path=SCREENS_FILE):
    import yaml
    data = {name: {"sortie": s.output, "marges": [int(m) for m in s.margins]}
            for name, s in sorted(screens.items()) if s.output}
    with open(path, "w", encoding="utf-8") as f:
        f.write(_HEADER)
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True, default_flow_style=None)
