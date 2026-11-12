"""Registre des types de cartes connus et classification par nom de produit.

Les valeurs « vérifié » ont été observées sur du matériel réel ; les autres viennent
de la lecture de xpiocards (libiocards.c) et restent à confirmer.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class CardType:
    key: str
    label: str
    products: tuple          # chaînes USB « product » reconnues
    protocol: str            # « mastercard » ou « unknown »
    active_level: int        # valeur rapportée quand une entrée est actionnée
    inputs: int              # nombre d'entrées utilisables (numérotation SIOC 0..)
    outputs: int
    axes: int
    max_cards: int = 1       # Master Cards derrière une USB Expansion
    send_init: bool = True   # False = écoute passive uniquement (rien n'est écrit)
    init: bool = True        # False = la carte émet sans trame d'initialisation
    verified: str = ""
    displays: int = 0        # positions de chiffres 7 segments pilotables (0 = aucune)
    out_protocol: str = ""   # protocole de sortie spécifique (ex. « mcp ») ; vide = Master


MASTERCARD = CardType(
    key="oc_usbexpansion",
    label="OpenCockpits USB Expansion + Master Card",
    products=("IOCardUSB",),
    protocol="mastercard",
    active_level=0,            # vérifié : 1 au repos quand la Master est alimentée
    inputs=72, outputs=45, axes=4, max_cards=4,
    verified="entrées (1 Master)",
)

EFDE_IO32 = CardType(
    key="efde_io32",
    label="EFDE IO32",
    products=("USB32I04AD",),
    protocol="mastercard",     # vérifié : même protocole que la Master OpenCockpits
    active_level=1,            # vérifié : 0 au repos, 1 actionnée
    inputs=32, outputs=32, axes=4,
    verified="entrées 0-13, axes, sortie 42",
)

OC_MCP = CardType(
    key="oc_mcp",
    label="OpenCockpits MCP",
    products=("IOCard-MCP",),
    protocol="bitmap",         # vérifié : état complet de 64 bits toutes les ~40 ms
    active_level=1,            # vérifié sur 2 poussoirs et 1 interrupteur
    inputs=64, outputs=0, axes=0,   # pas de sorties « Master » : voir out_protocol
    out_protocol="mcp",             # afficheurs + LED : protocole propre (hw/mcp.py)
    verified="entrées ; 6 afficheurs et 15 LED (protocole MCP, validé à la webcam)",
)

EFDE_DME = CardType(
    key="efde_dme",
    label="EFDE DME",
    products=("DME USB",),
    protocol="dme",            # vérifié : octet 0 = 0x01 SEL, 0x02 PWR ; écran : hw/dme.py
    active_level=1,
    inputs=2, outputs=0, axes=0,
    init=False,                # vérifié : émet sans initialisation
    out_protocol="dme",
    verified="boutons SEL et PWR ; écran et voyants (protocole EFDE, validé à la webcam)",
)

OC_USBFMC = CardType(
    key="oc_usbfmc",
    label="OpenCockpits CDU",
    products=("USBFMC V1.0",),
    protocol="keys",           # vérifié : une trame par appui, octet 0 = n° de touche
    active_level=1,
    inputs=88, outputs=0, axes=0,
    init=False,                # réveillée par une trame de voyants (hw/usbfmc.py)
    out_protocol="usbfmc",     # vérifié : octet 0 = masque des 5 voyants
    verified="touches (7 vérifiées, table de l'ancien script SIOC) ; 5 voyants (webcam)",
)

UNKNOWN = CardType(
    key="unknown", label="Carte inconnue", products=(), protocol="unknown",
    active_level=1, inputs=0, outputs=0, axes=0, send_init=False,
)

KNOWN = (MASTERCARD, EFDE_IO32, OC_MCP, EFDE_DME, OC_USBFMC)


def classify(product: str) -> CardType:
    for card in KNOWN:
        if product in card.products:
            return card
    return UNKNOWN


# Fabricants de cartes de cockpit : une carte inconnue de ces fabricants est montrée
# (en écoute seule) au lieu d'être ignorée comme un clavier ou une souris.
# Les cartes OpenCockpits récentes (USBFMC) s'annoncent « Opencockpits », les autres « Manuel Velez ».
# Le bus des jauges EFDE (FDBUS) s'annonce « E.F.D.E. », les autres cartes EFDE « EFDE ».
COCKPIT_MAKERS = {"Manuel Velez": "OpenCockpits", "Opencockpits": "OpenCockpits", "EFDE": "EFDE",
                  "E.F.D.E.": "EFDE"}


def maker(manufacturer: str):
    """Nom commercial du fabricant si c'est un fabricant de cartes de cockpit, sinon None."""
    for key, name in COCKPIT_MAKERS.items():
        if manufacturer.strip().startswith(key):
            return name
    return None
