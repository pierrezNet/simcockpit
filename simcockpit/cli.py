"""Ligne de commande : python -m simcockpit <commande>."""

import argparse
import queue
import sys
import time

from .hw import manager
from .hw.device import Card
from .hw.hidraw import HidDevice


def _pick(args):
    d = manager.find(args.port)
    if d is None:
        where = f" sur le port {args.port}" if args.port else ""
        sys.exit(f"Aucune carte connue{where}. Voir : python -m simcockpit list --all")
    print(f"Carte : {d.label}  ({d.info.product}, port {d.info.usb_port}, {d.info.path})")
    return d


def cmd_list(args):
    found = manager.scan(include_unknown=args.all)
    if not found:
        print("Aucune carte de cockpit détectée.")
        return 1
    for d in found:
        i, t = d.info, d.type
        print(f"{i.path:14} port {i.usb_port:8} {i.manufacturer} {i.product}")
        print(f"{'':14} → {d.label}" + (
            f" : {t.inputs} entrées, {t.outputs} sorties, {t.axes} axes,"
            f" actif à {t.active_level} (vérifié : {t.verified or 'non'})" if d.known else ""))
    return 0


def cmd_listen(args):
    d = _pick(args)
    print("Écoute passive : rien n'est envoyé à la carte (sans init, elle n'envoie souvent que les axes).")
    n, t0 = 0, time.monotonic()
    with HidDevice(d.info.path, writable=False) as dev:
        try:
            while (t := time.monotonic() - t0) < args.seconds:
                pkt = dev.read(timeout=0.2)
                if pkt:
                    print(f"{t:8.3f}  RX {pkt.hex(' ')}")
                    n += 1
        except KeyboardInterrupt:
            pass
    print(f"{n} rapport(s) reçu(s)")
    return 0


def cmd_watch(args):
    d = _pick(args)
    card = Card(d.info, d.type, debounce=args.debounce / 1000).start()
    print(f"Anti-rebond {args.debounce:.0f} ms. Ctrl+C pour quitter.")
    try:
        while True:
            try:
                ev = card.events.get(timeout=0.5)
            except queue.Empty:
                continue
            if ev.kind == "ready":
                act = [i for i, v in enumerate(ev.value[:d.type.inputs]) if card.is_active(v)]
                print(f"{ev.t:8.3f}  état initial, entrées actionnées : {act}")
            elif ev.kind == "input":
                etat = "ACTIVÉE" if card.is_active(ev.value) else "repos"
                print(f"{ev.t:8.3f}  entrée {ev.index:2d} -> {etat} ({ev.value})")
            elif ev.kind == "axis" and args.axes:
                print(f"{ev.t:8.3f}  axe {ev.index} = {ev.value}")
            elif ev.kind == "error":
                print(f"{ev.t:8.3f}  ERREUR : {ev.value} (carte débranchée ?)")
                return 1
    except KeyboardInterrupt:
        pass
    finally:
        card.stop()
    return 0


def cmd_diag(args):
    from .diag import noise
    d = _pick(args)
    print(f"Ne touchez à rien pendant {args.seconds:.0f} s…")
    flips, state = noise.measure(d, args.seconds)
    print(noise.report(flips, state, d.type.inputs))
    return 0


def cmd_check(args):
    from .diag import input_check
    d = _pick(args)
    card = Card(d.info, d.type, debounce=0.03).start()
    try:
        input_check.run_wizard(card, args.first, args.last or d.type.inputs, timeout=args.timeout)
    except KeyboardInterrupt:
        print("\nInterrompu.")
    finally:
        card.stop()
    return 0


def cmd_outputs(args):
    from .diag import output_check
    d = _pick(args)
    card = Card(d.info, d.type).start()
    try:
        output_check.run_wizard(card, args.first, args.last)
    except (KeyboardInterrupt, EOFError):
        print("\nInterrompu.")
    finally:
        card.stop()
    return 0


def cmd_send(args):
    """Envoie des trames brutes (essais de rétro-ingénierie)."""
    import time as _t
    from .hw import mastercard
    d = manager.find(args.port)
    if d is None:
        sys.exit(f"Aucune carte sur le port {args.port}")
    reports = []
    for text in args.reports:
        data = bytes.fromhex(text)
        if len(data) == 2 and args.repeat:
            data = data * 4                      # une seule commande par trame
        if len(data) != 8:
            sys.exit(f"« {text} » : il faut 8 octets (ou 2 avec --repeat)")
        reports.append(data)
    def pause(dev, seconds):
        # Lit les rapports de la carte pendant l'attente : certaines cartes (MCP) ne
        # traitent correctement les écritures que si l'on consomme leurs rapports.
        end = _t.monotonic() + seconds
        n = 0
        while _t.monotonic() < end:
            if dev.read(timeout=max(0.0, min(0.05, end - _t.monotonic()))):
                n += 1
        return n

    with HidDevice(d.info.path) as dev:
        pause(dev, args.settle)
        if args.init:
            dev.write(mastercard.init_packet(1, d.type.axes))
            print("init :", mastercard.init_packet(1, d.type.axes).hex(" "))
            pause(dev, args.gap)
        for r in reports:
            dev.write(r)
            print(f"envoyé {r.hex(' ')}  → {d.label} [{d.info.usb_port}]")
            pause(dev, args.gap)
        n = pause(dev, args.hold)
        print(f"(carte lue pendant l'envoi ; {n} rapport(s) dans les {args.hold:.1f} s finales)")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="simcockpit", description="Cartes de home cockpit sous Linux")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("list", help="détecter et classer les cartes")
    s.add_argument("--all", action="store_true", help="inclure les périphériques HID inconnus")
    s.set_defaults(func=cmd_list)

    for name, func, helptext in (
        ("listen", cmd_listen, "trames brutes, sans rien envoyer"),
        ("watch", cmd_watch, "changements d'entrées filtrés"),
        ("diag", cmd_diag, "bilan des entrées instables"),
    ):
        s = sub.add_parser(name, help=helptext)
        s.add_argument("--port", help="port USB de la carte (ex. 1-14), voir « list »")
        s.set_defaults(func=func)
        if name in ("listen", "diag"):
            s.add_argument("-s", "--seconds", type=float, default=10.0)
        if name == "watch":
            s.add_argument("--debounce", type=float, default=50.0, help="en ms (défaut 50)")
            s.add_argument("--axes", action="store_true", help="afficher aussi les axes")

    s = sub.add_parser("send", help="envoyer des trames brutes (essais)")
    s.add_argument("reports", nargs="+", help="trame hexa de 8 octets, ex. \"0b 00 0b 00 0b 00 0b 00\"")
    s.add_argument("--port", required=True, help="port USB de la carte (ex. 1-4.4)")
    s.add_argument("--repeat", action="store_true", help="2 octets répétés 4 fois")
    s.add_argument("--init", action="store_true", help="envoyer d'abord l'init Master")
    s.add_argument("--gap", type=float, default=0.1, help="s entre deux trames (défaut 0.1)")
    s.add_argument("--settle", type=float, default=0.5, help="s de lecture avant d'envoyer")
    s.add_argument("--hold", type=float, default=1.5, help="s de lecture après l'envoi")
    s.set_defaults(func=cmd_send)

    s = sub.add_parser("check", help="assistant : vérifier les entrées borne par borne")
    s.add_argument("--port")
    s.add_argument("--first", type=int, default=1, help="première borne (défaut 1)")
    s.add_argument("--last", type=int, help="dernière borne (défaut : nb d'entrées de la carte)")
    s.add_argument("--timeout", type=float, default=20.0, help="s d'attente par borne")
    s.set_defaults(func=cmd_check)

    s = sub.add_parser("outputs", help="assistant : vérifier les sorties une par une")
    s.add_argument("--port")
    s.add_argument("--first", type=int, default=11, help="première sortie SIOC (défaut 11)")
    s.add_argument("--last", type=int, help="dernière sortie (défaut : selon la carte)")
    s.set_defaults(func=cmd_outputs)

    args = p.parse_args(argv)
    return args.func(args)
