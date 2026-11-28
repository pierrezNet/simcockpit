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
    """Une carte physique. Les événements arrivent dans `self.events` (queue.Queue)."""

    def __init__(self, info: HidInfo, ctype: CardType, debounce=0.05, raw_events=False,
                 state_events=False):
        self.info, self.type = info, ctype
        self.events = queue.Queue()
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

    def _emit(self, kind, **kw):
        self.events.put(Event(kind, time.monotonic() - self.t0, **kw))

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
        """Axes en 0..1 (« axis » : index = n° d'axe evdev) ; position initiale émise d'emblée."""
        dev = self.dev
        try:
            for axis, raw in sorted(dev.initial.items()):
                self.axes[axis] = dev.axis_value(axis, raw)
                self._emit("axis", index=axis, value=self.axes[axis])
            self._emit("ready", value=[0] * mastercard.INPUTS)
            while not self._stop.is_set():
                for typ, code, raw in dev.read(timeout=0.05):
                    if typ == evdev.EV_ABS:
                        value = dev.axis_value(code, raw)
                        if self.axes.get(code) != value:
                            self.axes[code] = value
                            self._emit("axis", index=code, value=value)
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
