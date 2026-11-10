"""Carte ouverte : fil de lecture, décodage, anti-rebond, file d'événements."""

import queue
import threading
import time
from dataclasses import dataclass

from . import bitmap, dme, mastercard
from .cards import CardType
from .debounce import Debouncer
from .hidraw import HidDevice, HidInfo


@dataclass
class Event:
    kind: str        # « raw », « input », « axis », « ready », « error »
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
        self.t0 = time.monotonic()

    @property
    def name(self):
        return f"{self.type.label} [{self.info.usb_port}]"

    def is_active(self, value):
        return value == self.type.active_level

    def start(self):
        passive = not self.type.send_init
        self.dev = HidDevice(self.info.path, writable=not passive)
        if not passive and self.type.init:
            self.dev.write(mastercard.init_packet(ncards=1, naxes=self.type.axes))
        self._thread = threading.Thread(target=self._run, name=self.name, daemon=True)
        self._thread.start()
        return self

    def write(self, report: bytes):
        if not self.type.send_init:
            raise PermissionError("carte inconnue : écriture interdite (écoute passive)")
        return self.dev.write(report)

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
                if not ready and self.debouncer.ready():
                    ready = True
                    self._emit("ready", value=list(self.debouncer.stable))
        except OSError as e:  # carte débranchée, erreur USB…
            self._emit("error", value=str(e))
