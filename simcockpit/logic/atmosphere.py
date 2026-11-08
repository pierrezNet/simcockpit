"""Atmosphère standard (ISA) : conversion vitesse conventionnelle (CAS ≈ IAS) ↔ Mach.

Hypothèses : QNH 1013,25 hPa (l'altitude affichée est donc l'altitude pression),
atmosphère standard, vent sans effet (le Mach ne dépend que de l'air). Formules
compressibles classiques (Saint-Venant), valables en subsonique.
"""

import math

P0 = 1013.25          # hPa, pression standard au niveau de la mer
A0 = 661.4786         # kt, vitesse du son au niveau de la mer (ISA)
TROPOPAUSE_FT = 36089.24


def pressure_hpa(alt_ft):
    """Pression statique ISA à l'altitude pression donnée (pieds)."""
    if alt_ft <= TROPOPAUSE_FT:
        return P0 * (1 - 6.8755856e-6 * alt_ft) ** 5.2558797
    p11 = P0 * (1 - 6.8755856e-6 * TROPOPAUSE_FT) ** 5.2558797
    return p11 * math.exp(-(alt_ft - TROPOPAUSE_FT) / 20805.8)


def cas_to_mach(cas_kt, alt_ft):
    qc = P0 * ((1 + 0.2 * (cas_kt / A0) ** 2) ** 3.5 - 1)        # pression d'impact
    return math.sqrt(5 * ((qc / pressure_hpa(alt_ft) + 1) ** (2 / 7) - 1))


def mach_to_cas(mach, alt_ft):
    qc = pressure_hpa(alt_ft) * ((1 + 0.2 * mach ** 2) ** 3.5 - 1)
    return A0 * math.sqrt(5 * ((qc / P0 + 1) ** (2 / 7) - 1))
