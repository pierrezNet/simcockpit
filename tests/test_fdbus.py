"""FDBUS : séquence d'initialisation et trames, comparées aux échanges vérifiés le 2026-11-17."""

import unittest

from simcockpit.hw import cards, fdbus


def pkt(*data):
    return bytes(data) + bytes(8 - len(data))


def params(index, values):
    """Réponses d'un module : une trame [fonction, n° du module, valeur] par paramètre."""
    return [pkt(fn, index, values.get(name, 0)) for fn, name in sorted(fdbus.PARAMS.items())]


X27 = {"Mini1": 0, "Maxi1": 255, "Offset1H": 0x02, "Offset1L": 0xC8,
       "FSMini1H": 0xEA, "FSMini1L": 0x84, "FSMaxi1H": 0x15, "FSMaxi1L": 0x7C, "Type1": 2}


class TestBusInit(unittest.TestCase):
    def test_sequence_du_driver(self):
        bus = fdbus.BusInit()
        self.assertEqual(bus.start(), [bytes(8)])
        # exploration : adresses vides, répétitions, module 251 de type 2, fin
        for p in (pkt(3, 195), pkt(3, 195), pkt(3, 196), pkt(1, 251, 2), pkt(1, 251, 2)):
            self.assertEqual(bus.feed(p), [])
        self.assertEqual([m.address for m in bus.modules], [251])
        out = bus.feed(pkt(0xFF))
        self.assertEqual([f.hex(" ") for f in out],
                         ["07 fb 00 00 00 00 00 00", "ff fb 00 00 00 00 00 00"])
        replies = params(0, X27)
        for p in replies[:-1]:
            self.assertEqual(bus.feed(p), [])
        self.assertEqual(bus.feed(replies[-1]), [fdbus.frame(0xFE)])
        self.assertEqual(bus.state, "ending")
        bus.feed(pkt(0xFE))
        self.assertEqual(bus.state, "ready")
        m = bus.modules[0]
        self.assertEqual(m.word("Offset1"), 0x02C8)
        self.assertEqual(m.fs_range(), (-5500, 5500))
        self.assertEqual(m.data_label, "offset 02C8 (vitesse verticale)")
        self.assertAlmostEqual(m.to_sim(0), -5500)
        self.assertAlmostEqual(m.to_sim(255), 5500)

    def test_deux_modules_interroges_l_un_apres_l_autre(self):
        bus = fdbus.BusInit()
        bus.start()
        bus.feed(pkt(1, 250, 49))
        bus.feed(pkt(1, 251, 2))
        self.assertEqual(bus.feed(pkt(0xFF))[1], fdbus.frame(0xFF, 250, 0))
        out = []
        for p in params(0, {"Mini1": 10, "Maxi1": 255}):
            out = bus.feed(p)
        self.assertEqual(out, [fdbus.frame(7, 251, 0), fdbus.frame(0xFF, 251, 1)])
        for p in params(1, X27):
            out = bus.feed(p)
        self.assertEqual(out, [fdbus.frame(0xFE)])
        self.assertEqual(bus.modules[0].limits(), (10, 255))
        self.assertEqual(bus.modules[0].rest_position(), 10)    # pas d'échelle : Mini
        self.assertEqual(bus.modules[1].rest_position(), 128)   # IVSI : 0 ft/min
        self.assertEqual(bus.duplicates(), [])

    def test_bus_vide(self):
        bus = fdbus.BusInit()
        bus.start()
        bus.feed(pkt(3, 200))
        self.assertEqual(bus.feed(pkt(0xFF)), [])
        self.assertEqual(bus.state, "empty")

    def test_parametre_d_un_autre_module_ignore(self):
        bus = fdbus.BusInit()
        bus.start()
        bus.feed(pkt(1, 251, 2))
        bus.feed(pkt(0xFF))
        bus.feed(pkt(150, 5, 99))
        self.assertNotIn("Mini1", bus.modules[0].params)


class TestFrames(unittest.TestCase):
    def test_eeprom_interdite(self):
        for fn in (50, 51, 88):
            with self.assertRaises(PermissionError):
                fdbus.frame(fn, 251, 1)
        fdbus.frame(49)
        fdbus.frame(89)

    def test_positions_bornees_doublee_puis_seulement_si_changement(self):
        m = fdbus.Module(251, 49, 0, {"Mini1": 10, "Maxi1": 255})
        out = fdbus.FdbusOutputs()
        self.assertEqual(out.position(m, 0), [fdbus.frame(3, 251, 10)] * 2)   # borné à Mini1
        self.assertEqual(out.position(m, 10), [])
        self.assertEqual(out.position(m, 196), [bytes([3, 0xFB, 196]) + bytes(5)])
        self.assertEqual(out.position(m, 300), [fdbus.frame(3, 251, 255)])
        self.assertEqual(out.reset(m), [fdbus.frame(7, 251, 0)])
        self.assertEqual(len(out.position(m, 196)), 2)

    def test_changement_d_adresse_seule_ecriture_eeprom_permise(self):
        m = fdbus.Module(251, 49, 0)
        self.assertEqual(fdbus.address_frame(m, 250).hex(" "), "32 fb fa 00 00 00 00 00")
        for bad in (251, 194, 255):
            with self.assertRaises(ValueError):
                fdbus.address_frame(m, bad)

    def test_retroeclairage(self):
        self.assertEqual(fdbus.FdbusOutputs.backlight(15), [fdbus.frame(6, 0x32, 255)])
        with self.assertRaises(ValueError):
            fdbus.FdbusOutputs.backlight(16)

    def test_carte_reconnue(self):
        self.assertIs(cards.classify("FDBUS"), cards.EFDE_FDBUS)


class TestCalibration(unittest.TestCase):
    def test_interpolation_bornee(self):
        cal = fdbus.Calibration({-5000: 0, 0: 133, 5000: 255})   # IVSI, relevé du 2026-11-17
        self.assertEqual(cal.position(0), 133)
        self.assertEqual(cal.position(-2500), 66)
        self.assertEqual(cal.position(2500), 194)
        self.assertEqual(cal.position(-9000), 0)
        self.assertEqual(cal.position(9000), 255)
        self.assertAlmostEqual(cal.value(133), 0)
        self.assertIsNone(fdbus.Calibration({0: 133}).position(0))

    def test_fichier(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "fdbus.yaml"
            self.assertEqual(fdbus.load_calibrations(path), {})
            cals = {(251, 1): fdbus.Calibration({0: 133, -5000: 0}, module_type=2),
                    (250, 1): fdbus.Calibration()}
            fdbus.save_calibrations(cals, path)
            back = fdbus.load_calibrations(path)
            self.assertEqual(list(back), [(251, 1)])
            self.assertEqual(back[(251, 1)].points, {-5000: 0, 0: 133})
            self.assertEqual(back[(251, 1)].module_type, 2)


class TestGaugeSettings(unittest.TestCase):
    def test_reperes_incoherents(self):
        ivsi = fdbus.Calibration({-1000: 93, 0: 133, 2000: 197, 3000: 141, 4000: 239})
        self.assertEqual(ivsi.incoherent(), [3000])
        flaps = fdbus.Calibration({0: 10, 18: 158, 24: 202, 33: 255, 39: 230})
        self.assertEqual(flaps.incoherent(), [39])
        inverse = fdbus.Calibration({0: 200, 10: 100, 20: 0})   # jauge montée à l'envers
        self.assertEqual(inverse.incoherent(), [])

    def test_nom_et_unite_enregistres_et_ancien_format_relu(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "fdbus.yaml"
            path.write_text("modules:\n  250:\n    type: 49\n    sortie1:\n      0: 10\n"
                            "      33: 255\n", encoding="utf-8")
            cals = fdbus.load_calibrations(path)
            self.assertEqual(cals[(250, 1)].points, {0: 10, 33: 255})
            cals[(250, 1)].name, cals[(250, 1)].unit = "Volets", "°"
            cals[(249, 1)] = fdbus.Calibration(name="Essence", unit="%")   # sans repère
            fdbus.save_calibrations(cals, path)
            back = fdbus.load_calibrations(path)
            self.assertEqual((back[(250, 1)].name, back[(250, 1)].unit), ("Volets", "°"))
            self.assertEqual(back[(250, 1)].points, {0: 10, 33: 255})
            self.assertEqual(back[(249, 1)].name, "Essence")


if __name__ == "__main__":
    unittest.main()
