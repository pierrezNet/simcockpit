"""Carte ouverte : fil de lecture, décodage, anti-rebond, file d'événements."""

import queue
import threading
import time
from dataclasses import dataclass

from . import bitmap, dme, evdev, fdbus, mastercard, usbfmc
from .cards import CardType
from .debounce import Debouncer
from .hidraw import HidDevice, HidInfo


@dataclass
class Event:
    kind: str        # « raw », « input », « axis », « key », « ready », « state », « error »,
                     # FDBUS : « log », « module », « init_failed » (et « ready » = liste des modules)
    t: float
    index: int = None
    value: object = None
    old: object = None


class Card:
    """Une carte physique, partagée entre plusieurs abonnés (le cockpit, le banc).

    Chaque abonné obtient sa propre file par `listen()` et la rend par `unlisten()` ;
    `self.events` est la file d'une carte non partagée (outils en ligne de commande) ; le
    concentrateur ouvre ses cartes avec `shared=True`, sans cette file. Un abonné
    arrivé tard reçoit d'abord l'état courant : entrées, axes, modules du bus.
    """

    def __init__(self, info: HidInfo, ctype: CardType, debounce=0.05, raw_events=False,
                 state_events=False, shared=False):
        self.info, self.type = info, ctype
        self._events = None
        self._queues = []
        self._qlock = threading.Lock()          # abonnés et état rejoué, pour les deux fils
        self._replay = {"ready": None, "state": None, "modules": [], "failed": None,
                        "error": None}
        self.raw_events = raw_events
        self.state_events = state_events   # « state » : état brut complet à chaque trame d'entrées
        self.decoder = (bitmap.BitmapDecoder() if ctype.protocol == "bitmap"
                        else mastercard.Decoder())
        self.debouncer = Debouncer(mastercard.INPUTS, debounce)
        self.axes = {}
        self.dev = None
        self._stop = threading.Event()
        self._thread = None
        self._wlock = threading.Lock()          # écritures du fil de lecture et de l'interface
        self._init_request = threading.Event()  # FDBUS : (re)lancer l'initialisation du bus
        self.fdbus = None                       # FDBUS : automate d'initialisation (modules)
        self.t0 = time.monotonic()
        if not shared:
            self._events = self.listen()

    @property
    def name(self):
        return f"{self.type.label} [{self.info.usb_port}]"

    def is_active(self, value):
        return value == self.type.active_level

    def start(self):
        if self.type.protocol == "evdev":       # joystick : lu par evdev, jamais écrit
            node = evdev.event_node(self.info.path)
            if node is None:
                raise OSError(f"pas de nœud evdev pour {self.info.path}")
            self.dev = evdev.EvdevDevice(node)
            self._thread = threading.Thread(target=self._run_evdev, name=self.name, daemon=True)
            self._thread.start()
            return self
        passive = not self.type.send_init
        self.dev = HidDevice(self.info.path, writable=not passive)
        if not passive and self.type.init:
            self.dev.write(mastercard.init_packet(ncards=1, naxes=self.type.axes))
        elif not passive and self.type.protocol == "keys":
            self.dev.write(usbfmc.led_frame())   # toute écriture réveille la carte ; voyants éteints
        run = self._run
        if self.type.protocol == "fdbus":
            run = self._run_fdbus
            self._init_request.set()
        self._thread = threading.Thread(target=run, name=self.name, daemon=True)
        self._thread.start()
        return self

    def write(self, report: bytes):
        if not self.type.send_init:
            raise PermissionError("carte inconnue : écriture interdite (écoute passive)")
        if self.dev is None:
            raise OSError("carte non ouverte")
        with self._wlock:
            return self.dev.write(report)

    def request_init(self):
        """FDBUS : relance l'exploration du bus et la lecture des paramètres des modules."""
        self._init_request.set()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        if self.dev:
            self.dev.close()

    @property
    def events(self):
        if self._events is None:
            self._events = self.listen()
        return self._events

    @property
    def alive(self):
        """Fil de lecture en marche (faux après une erreur : carte débranchée…)."""
        return self._thread is not None and self._thread.is_alive()

    def listen(self):
        """Nouvelle file d'événements, préremplie de l'état courant de la carte."""
        q = queue.Queue()
        with self._qlock:
            for ev in self._snapshot():
                q.put(ev)
            self._queues.append(q)
        return q

    def unlisten(self, q):
        with self._qlock:
            if q in self._queues:
                self._queues.remove(q)

    def _snapshot(self):
        r, t = self._replay, time.monotonic() - self.t0
        out = [Event("module", t, index=m.address, value=m) for m in r["modules"]]
        out += [Event("axis", t, index=i, value=v) for i, v in sorted(self.axes.items())]
        if r["state"] is not None:
            out.append(Event("state", t, value=list(r["state"])))
        if r["ready"] is not None:
            out.append(Event("ready", t, value=list(r["ready"])))
        if r["failed"] is not None:
            out.append(Event("init_failed", t, value=r["failed"]))
        if r["error"] is not None:
            out.append(Event("error", t, value=r["error"]))
        return out

    def _remember(self, ev):
        r = self._replay
        if ev.kind == "ready":
            r["ready"], r["failed"] = list(ev.value), None
        elif ev.kind == "input" and r["ready"] is not None and ev.index < len(r["ready"]):
            r["ready"][ev.index] = ev.value          # état stable tenu à jour
        elif ev.kind == "state":
            r["state"] = ev.value
        elif ev.kind == "module":
            r["modules"].append(ev.value)
        elif ev.kind == "log" and ev.value.startswith("exploration"):
            r["modules"], r["ready"], r["failed"] = [], None, None   # bus réexploré
        elif ev.kind == "init_failed":
            r["failed"] = ev.value
        elif ev.kind == "error":
            r["error"] = ev.value

    def _emit(self, kind, **kw):
        ev = Event(kind, time.monotonic() - self.t0, **kw)
        with self._qlock:
            self._remember(ev)
            for q in self._queues:
                q.put(ev)

    def _run(self):
        ready = False
        try:
            while not self._stop.is_set():
                pkt = self.dev.read(timeout=0.02)
                t = time.monotonic() - self.t0
                if pkt:
                    if self.raw_events:
                        self._emit("raw", value=pkt)
                    if self.type.protocol in ("mastercard", "bitmap"):
                        upd = self.decoder.feed(pkt)
                        if upd.axis and self.axes.get(upd.axis[0]) != upd.axis[1]:
                            self.axes[upd.axis[0]] = upd.axis[1]
                            self._emit("axis", index=upd.axis[0], value=upd.axis[1])
                        if upd.inputs_changed:
                            self.debouncer.update(self.decoder.inputs(), t)
                            if self.state_events:
                                self._emit("state", value=self.decoder.inputs())
                    elif self.type.protocol == "keys":
                        for code in usbfmc.keys_pressed(pkt):
                            self._emit("key", index=code, value=usbfmc.key_name(code))
                    elif self.type.protocol == "dme":
                        pressed = dme.buttons(pkt)
                        state = pressed + [0] * (mastercard.INPUTS - len(pressed))
                        self.debouncer.update(state, t)
                        # le DME émet toutes les 3 ms : état transmis seulement s'il change
                        if self.state_events and pressed != getattr(self, "_dme_last", None):
                            self._dme_last = pressed
                            self._emit("state", value=state)
                for i, old, new in self.debouncer.poll(t):
                    if old is not None:
                        self._emit("input", index=i, value=new, old=old)
                if not ready and self.type.protocol == "keys":   # pas d'état : prête d'emblée
                    ready = True
                    self._emit("ready", value=[0] * mastercard.INPUTS)
                if not ready and self.debouncer.ready():
                    ready = True
                    self._emit("ready", value=list(self.debouncer.stable))
        except OSError as e:  # carte débranchée, erreur USB…
            self._emit("error", value=str(e))

    def _run_evdev(self):
        """Axes en 0..1 (« axis » : index = n° d'axe evdev) ; boutons en entrées (« input »,
        index = rang du bouton), déjà anti-rebondis par le noyau. Positions initiales
        (interrupteurs compris) émises d'emblée."""
        dev = self.dev
        slot = {code: i for i, code in enumerate(dev.keys[:mastercard.INPUTS])}
        state = [0] * mastercard.INPUTS
        for code, i in slot.items():
            state[i] = dev.initial_keys.get(code, 0)
        try:
            for axis, raw in sorted(dev.initial.items()):
                self.axes[axis] = dev.axis_value(axis, raw)
                self._emit("axis", index=axis, value=self.axes[axis])
            if self.state_events:
                self._emit("state", value=list(state))
            self._emit("ready", value=list(state))
            while not self._stop.is_set():
                changed = False
                for typ, code, raw in dev.read(timeout=0.05):
                    if typ == evdev.EV_ABS:
                        value = dev.axis_value(code, raw)
                        if self.axes.get(code) != value:
                            self.axes[code] = value
                            self._emit("axis", index=code, value=value)
                    elif typ == evdev.EV_KEY and code in slot and raw in (0, 1):
                        i = slot[code]                       # raw 2 = répétition : ignorée
                        if state[i] != raw:
                            old, state[i], changed = state[i], raw, True
                            self._emit("input", index=i, value=raw, old=old)
                if changed and self.state_events:
                    self._emit("state", value=list(state))
        except OSError as e:
            self._emit("error", value=str(e))

    # délai sans nouvelle trame au-delà duquel une étape de l'initialisation FDBUS échoue
    FDBUS_TIMEOUTS = {"explore": 6.0, "params": 3.0, "ending": 2.0}

    def _run_fdbus(self):
        bus = self.fdbus = fdbus.BusInit()
        last, since = None, 0.0

        def send(frames):
            for f in frames:
                with self._wlock:
                    self.dev.write(f)
                self._emit("log", value="→ " + f[:3].hex(" "))
                time.sleep(0.005)

        try:
            while not self._stop.is_set():
                now = time.monotonic()
                if self._init_request.is_set():
                    self._init_request.clear()
                    self._emit("log", value="exploration du bus (adresses 195 à 254)…")
                    send(bus.start())
                    last, since = None, now
                pkt = self.dev.read(timeout=0.02)
                if bus.state not in self.FDBUS_TIMEOUTS:
                    continue      # prêt : la carte répète sa dernière trame, on la lit sans plus
                if pkt and pkt != last:
                    last, since = pkt, now
                    count, state = len(bus.modules), bus.state
                    out = bus.feed(pkt)
                    for m in bus.modules[count:]:
                        self._emit("module", index=m.address, value=m)
                    if state == "params" and bus.state != "params":
                        self._emit("log", value=f"paramètres lus ({len(bus.modules)} module(s))")
                    send(out)
                    if bus.state == "ready":
                        self._emit("log", value="← fe : initialisation terminée")
                        self._emit("ready", value=list(bus.modules))
                    elif bus.state == "empty":
                        self._emit("ready", value=[])
                elif now - since > self.FDBUS_TIMEOUTS[bus.state]:
                    step = {"explore": "exploration", "params": "lecture des paramètres",
                            "ending": "fin d'initialisation"}[bus.state]
                    bus.state = "failed"
                    self._emit("init_failed", value=f"pas de réponse pendant l'étape « {step} »")
        except OSError as e:
            self._emit("error", value=str(e))
