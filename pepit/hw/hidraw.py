"""Accès direct à /dev/hidraw* via sysfs, sans dépendance externe."""

import glob
import os
import re
import select
from dataclasses import dataclass

SYSFS = "/sys/class/hidraw"
_USB_PORT = re.compile(r"^\d+-[\d.]+$")  # ex. « 1-14 » ou « 1-4.2 » (derrière un hub)


@dataclass(frozen=True)
class HidInfo:
    path: str          # /dev/hidrawN
    hid_name: str      # « EFDE USB32I04AD »
    product: str       # « USB32I04AD »
    manufacturer: str  # « EFDE »
    usb_port: str      # « 1-14 » : identifie la carte (pas de n° de série sur ces cartes)
    vid_pid: str       # « 0000:0000 »


def _read(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return ""


def _info(node):
    dev = os.path.realpath(os.path.join(node, "device"))
    uevent = dict(
        line.split("=", 1) for line in _read(os.path.join(dev, "uevent")).splitlines() if "=" in line
    )
    port, usbdir = "", ""
    for part in reversed(dev.split("/")):
        if _USB_PORT.match(part):
            port = part
            usbdir = dev[: dev.index("/" + part + "/") + len(part) + 1]
            break
    hid_id = uevent.get("HID_ID", "0:0:0").split(":")
    vid_pid = f"{int(hid_id[1], 16):04x}:{int(hid_id[2], 16):04x}" if len(hid_id) == 3 else "?"
    return HidInfo(
        path="/dev/" + os.path.basename(node),
        hid_name=uevent.get("HID_NAME", ""),
        product=_read(os.path.join(usbdir, "product")) if usbdir else "",
        manufacturer=_read(os.path.join(usbdir, "manufacturer")) if usbdir else "",
        usb_port=port,
        vid_pid=vid_pid,
    )


def enumerate_hid():
    """Liste tous les périphériques hidraw présents."""
    return [_info(n) for n in sorted(glob.glob(os.path.join(SYSFS, "hidraw*")))]


class HidDevice:
    """Périphérique hidraw ouvert. Les rapports n'ont pas de Report ID (cartes Master/EFDE)."""

    def __init__(self, path, writable=True):
        self.path = path
        self.fd = os.open(path, os.O_RDWR if writable else os.O_RDONLY)

    def write(self, report: bytes):
        # hidraw : le 1er octet est le n° de rapport ; 0 quand le périphérique n'en utilise pas
        return os.write(self.fd, b"\x00" + bytes(report))

    def read(self, timeout=1.0, size=64):
        """Retourne un rapport, ou None si rien n'arrive avant `timeout` secondes."""
        if select.select([self.fd], [], [], timeout)[0]:
            return os.read(self.fd, size)
        return None

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
