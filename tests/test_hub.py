"""Cartes partagées : plusieurs abonnés, état rejoué, concentrateur (sans matériel)."""

import queue
import unittest
from types import SimpleNamespace

from pepit.hw.cards import classify
from pepit.hw.device import Card
from pepit.hw.hub import DeviceHub


def info(path="/dev/hidraw7", product="USB32I04AD", port="1-2"):
    return SimpleNamespace(path=path, product=product, usb_port=port, manufacturer="Opencockpits")


def drain(q):
    out = []
    while True:
        try:
            out.append(q.get_nowait())
        except queue.Empty:
            return out


class TestSubscribers(unittest.TestCase):
    def card(self, product="USB32I04AD", shared=True):
        return Card(info(product=product), classify(product), state_events=True, shared=shared)

    def test_deux_abonnes_recoivent_les_memes_evenements(self):
        card = self.card()
        a, b = card.listen(), card.listen()
        card._emit("input", index=3, value=1, old=0)
        self.assertEqual([(e.kind, e.index) for e in drain(a)], [("input", 3)])
        self.assertEqual([(e.kind, e.index) for e in drain(b)], [("input", 3)])

    def test_desabonne_ne_recoit_plus_rien(self):
        card = self.card()
        a = card.listen()
        card.unlisten(a)
        card._emit("input", index=3, value=1, old=0)
        self.assertEqual(drain(a), [])

    def test_abonne_tardif_recoit_l_etat_courant(self):
        card = self.card()
        state = [0] * 72
        card._emit("state", value=list(state))
        card._emit("ready", value=list(state))
        card._emit("input", index=5, value=1, old=0)    # l'état stable a changé depuis
        card.axes[0] = 0.4
        late = {e.kind: e for e in drain(card.listen())}
        self.assertEqual(late["ready"].value[5], 1)
        self.assertEqual(late["axis"].value, 0.4)
        self.assertIn("state", late)
        self.assertNotIn("input", late)                 # pas d'historique, l'état seul

    def test_bus_fdbus_rejoue_modules_puis_pret(self):
        card = self.card("FDBUS")
        m = SimpleNamespace(address=201)
        card._emit("module", index=201, value=m)
        card._emit("ready", value=[m])
        kinds = [(e.kind, e.index) for e in drain(card.listen())]
        self.assertEqual(kinds, [("module", 201), ("ready", None)])
        card._emit("log", value="exploration du bus (adresses 195 à 254)…")   # bus relancé
        self.assertEqual(drain(card.listen()), [])

    def test_carte_non_partagee_garde_sa_file(self):
        card = self.card(shared=False)
        card._emit("input", index=1, value=1, old=0)
        self.assertEqual(card.events.get_nowait().index, 1)

    def test_ecriture_sur_carte_non_ouverte(self):
        with self.assertRaises(OSError):
            self.card().write(b"\x00")


class FakeCard:
    def __init__(self, detected):
        self.info = detected.info
        self.alive, self.started, self.stopped = False, False, False

    def start(self):
        self.alive = self.started = True
        return self

    def stop(self):
        self.alive, self.stopped = False, True


class TestHub(unittest.TestCase):
    def setUp(self):
        self.present = [SimpleNamespace(info=info())]
        self.made = []

        def make(d):
            self.made.append(FakeCard(d))
            return self.made[-1]

        self.hub = DeviceHub(scan=lambda: list(self.present), make_card=make)

    def test_une_seule_ouverture_pour_deux_pages(self):
        d = self.hub.refresh()[0]
        self.assertIs(self.hub.open(d), self.hub.open(d))
        self.assertEqual(len(self.made), 1)

    def test_carte_debranchee_fermee(self):
        card = self.hub.open(self.hub.refresh()[0])
        self.present = []
        self.hub.refresh()
        self.assertTrue(card.stopped)
        self.assertEqual(self.hub.cards, {})

    def test_autre_carte_sur_le_meme_noeud_rouverte(self):
        first = self.hub.open(self.hub.refresh()[0])
        self.present = [SimpleNamespace(info=info(product="MCP"))]
        second = self.hub.open(self.hub.refresh()[0])
        self.assertTrue(first.stopped)
        self.assertIsNot(first, second)

    def test_carte_perdue_rouverte(self):
        d = self.hub.refresh()[0]
        first = self.hub.open(d)
        first.alive = False                              # erreur de lecture
        self.assertIsNot(self.hub.open(d), first)

    def test_qui_pilote(self):
        card = self.hub.open(self.hub.refresh()[0])
        self.hub.claim(card, "cockpit")
        self.assertEqual(self.hub.drivers(card), {"cockpit"})
        self.hub.release(card, "cockpit")
        self.assertEqual(self.hub.drivers(card), set())

    def test_echec_d_ouverture_rien_retenu(self):
        def boom(d):
            raise PermissionError("accès refusé")
        hub = DeviceHub(scan=lambda: list(self.present), make_card=boom)
        with self.assertRaises(PermissionError):
            hub.open(hub.refresh()[0])
        self.assertEqual(hub.cards, {})

    def test_fermeture(self):
        card = self.hub.open(self.hub.refresh()[0])
        self.hub.close()
        self.assertTrue(card.stopped)


if __name__ == "__main__":
    unittest.main()
