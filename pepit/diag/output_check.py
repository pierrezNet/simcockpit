"""Assistant de vérification des sorties : allume une sortie à la fois, l'utilisateur confirme.

Le codage vient de la lecture de libiocards.c ; la polarité (bit 1 = allumée ?) est
précisément ce que ce test établit. Rien n'est écrit sans confirmation préalable.
"""

import json
import os
import time

from ..hw.mastercard import FIRST_OUTPUT, output_location, output_report

ANSWERS = {"o": "allumée", "n": "éteinte", "i": "inversée", "": "éteinte"}


def segments_for(first, last):
    return sorted({output_location(n)[0] for n in range(first, last + 1)})


def run_wizard(card, first=FIRST_OUTPUT, last=None, report_dir="reports", ask=input):
    last = last if last is not None else FIRST_OUTPUT + card.type.outputs - 1
    segs = segments_for(first, last)
    print(f"Test des sorties {first} à {last} (segments {segs}).")
    print("ATTENTION : chaque sortie sera mise à 1, une par une. Ne branchez que des LED"
          " (avec résistance) : ni relais, ni moteur, ni afficheur pendant ce test.")
    if ask("Continuer ? [o/N] ").strip().lower() != "o":
        print("Annulé, rien n'a été écrit.")
        return None

    def all_zero():
        for s in segs:
            card.write(output_report(s, 0x00))
            time.sleep(0.02)

    all_zero()
    first_view = ask("Toutes les sorties viennent d'être mises à 0. Que voyez-vous ?"
                     " [e]teintes / [a]llumées : ").strip().lower()
    results = {}
    try:
        for n in range(first, last + 1):
            seg, bit = output_location(n)
            card.write(output_report(seg, 1 << bit))
            a = ask(f"  Sortie {n:2d} (bit {bit} du segment {seg}) : [o]allumée / [n]rien /"
                    f" [i]tout sauf elle / [q]uitter ? ").strip().lower()
            card.write(output_report(seg, 0x00))
            if a == "q":
                break
            results[n] = ANSWERS.get(a, a)
    finally:
        all_zero()

    lit = [n for n, r in results.items() if r == "allumée"]
    inverted = [n for n, r in results.items() if r == "inversée"]
    silent = [n for n, r in results.items() if r == "éteinte"]
    polarity = ("bit 1 = allumée" if lit and not inverted else
                "bit 1 = éteinte (inversée)" if inverted and not lit else "indéterminée")
    print(f"\nBilan : polarité {polarity}")
    print(f"  Allumées : {lit}")
    if inverted:
        print(f"  Inversées : {inverted}")
    if silent:
        print(f"  Sans effet visible : {silent}")
    os.makedirs(report_dir, exist_ok=True)
    path = os.path.join(report_dir, time.strftime(
        f"outputs_{card.info.product}_{card.info.usb_port}_%Y%m%d-%H%M%S.json"))
    with open(path, "w") as f:
        json.dump({"card": card.info.product, "usb_port": card.info.usb_port,
                   "all_zero_view": first_view, "polarity": polarity, "results": results},
                  f, indent=2, ensure_ascii=False)
    print(f"  Rapport : {path}")
    return results
