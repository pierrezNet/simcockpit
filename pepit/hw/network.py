"""Cartes wifi (IOCP) connectées à Pepit : qui elles sont, d'où elles viennent.

Une carte IOCP n'annonce ni nom ni numéro de série. On sait d'elle :
- son adresse IP (donnée par la box : elle peut changer) ;
- son adresse MAC, lue dans la table ARP du PC (/proc/net/arp) : stable, propre à la
  carte, c'est son identité dans l'historique ;
- les variables IOCP qu'elle demande, qui disent à quoi elle sert ;
- les cartes du profil d'avion qu'elle sert (celles dont elle demande les variables).

Même interface que usb.UsbDevice pour l'historique (key, name, port, pepit…).
"""

from dataclasses import dataclass

ARP = "/proc/net/arp"

# premiers octets d'adresse MAC (OUI) des fabricants qu'on croise sur un cockpit
VENDORS = {
    "Espressif (ESP8266 / ESP32)": (
        "18:fe:34", "24:0a:c4", "24:62:ab", "24:6f:28", "24:a1:60", "24:b2:de", "2c:3a:e8",
        "2c:f4:32", "30:ae:a4", "34:86:5d", "34:94:54", "3c:61:05", "3c:71:bf", "40:22:d8",
        "40:91:51", "40:f5:20", "48:3f:da", "48:55:19", "4c:11:ae", "4c:75:25", "50:02:91",
        "54:43:b2", "58:bf:25", "5c:cf:7f", "60:01:94", "68:c6:3a", "70:03:9f", "78:21:84",
        "78:e3:6d", "7c:9e:bd", "7c:df:a1", "80:7d:3a", "84:0d:8e", "84:cc:a8", "84:f3:eb",
        "8c:aa:b5", "8c:ce:4e", "94:b9:7e", "98:cd:ac", "98:f4:ab", "9c:9c:1f", "a0:20:a6",
        "a4:7b:9d", "a4:cf:12", "a4:e5:7c", "a8:48:fa", "ac:67:b2", "b4:8a:0a", "b4:e6:2d",
        "bc:dd:c2", "bc:ff:4d", "c4:4f:33", "c4:5b:be", "c8:2b:96", "c8:c9:a3", "cc:50:e3",
        "d8:a0:1d", "d8:bf:c0", "d8:f1:5b", "dc:4f:22", "e0:98:06", "e8:68:e7", "e8:db:84",
        "ec:62:60", "ec:94:cb", "ec:fa:bc", "f0:08:d1", "f4:cf:a2", "fc:f5:c4"),
    "Arduino": ("a8:61:0a",),
    "Raspberry Pi": ("b8:27:eb", "dc:a6:32", "e4:5f:01", "d8:3a:dd", "2c:cf:67"),
}
_OUI = {prefix: name for name, prefixes in VENDORS.items() for prefix in prefixes}


def arp_table(path=ARP):
    """{IP: MAC} des machines du réseau local que le PC a vues récemment."""
    out = {}
    try:
        with open(path) as f:
            next(f, None)                                  # ligne d'en-tête
            for line in f:
                parts = line.split()
                if len(parts) >= 4 and parts[3] != "00:00:00:00:00:00":
                    out[parts[0]] = parts[3].lower()
    except OSError:
        pass
    return out


def vendor(mac):
    return _OUI.get((mac or "")[:8].lower(), "")


def ranges(numbers):
    """[201, 202, 203, 210] → « 201 à 203, 210 »."""
    out, nums = [], sorted(numbers)
    i = 0
    while i < len(nums):
        j = i
        while j + 1 < len(nums) and nums[j + 1] == nums[j] + 1:
            j += 1
        out.append(f"{nums[i]} à {nums[j]}" if j - i >= 2 else
                   ", ".join(str(n) for n in nums[i:j + 1]))
        i = j + 1
    return ", ".join(out)


@dataclass(frozen=True)
class NetDevice:
    ip: str
    mac: str             # « » si la table ARP ne la connaît pas (encore)
    tcp_port: int        # port du serveur IOCP de Pepit
    variables: tuple     # variables IOCP demandées par la carte
    cards: tuple = ()    # cartes du profil qu'elle sert (« ecran_vitesses »)

    kind = "wifi"
    cockpit = True
    access = "ok"
    nodes = ()

    @property
    def key(self):
        return f"wifi:{self.mac}" if self.mac else f"wifi@{self.ip}"

    @property
    def name(self):
        return ", ".join(self.cards) if self.cards else "carte IOCP non déclarée"

    @property
    def port(self):                  # pour l'historique : adresses IP successives
        return self.ip

    @property
    def vid_pid(self):
        return ""

    @property
    def serial(self):
        return self.mac

    @property
    def vendor(self):
        return vendor(self.mac)

    @property
    def pepit(self):
        return (f"carte IOCP, variables {ranges(self.variables)}" if self.variables
                else "carte IOCP (n'a encore rien demandé)")

    @property
    def extra(self):
        """Ce que l'historique garde en plus pour une carte wifi."""
        return {"mac": self.mac, "fabricant": self.vendor,
                "variables": ranges(self.variables), "cartes": ", ".join(self.cards),
                "port_iocp": self.tcp_port}
