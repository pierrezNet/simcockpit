# Cartes USB

| Carte | Nom USB | Entrées | Sorties |
|---|---|---|---|
| EFDE IO32 | `USB32I04AD` | ✅ 32 entrées, 4 axes | ✅ 32 sorties (testée sur une seule) |
| OpenCockpits MCP (pilote automatique 737) | `IOCard-MCP` | ✅ boutons, interrupteurs, 6 encodeurs | ✅ 6 afficheurs, 15 voyants, point décimal |
| OpenCockpits radio Airbus | `IOCard-RadioAirb` | ✅ 8 poussoirs, ON/OFF, double rotatif | ✅ 2 afficheurs de 6 chiffres, points décimaux, 8 voyants |
| OpenCockpits CDU 737 | `USBFMC V1.0` | ✅ 70 touches | ✅ 5 voyants (OFST, MSG, EXEC, DSPY, FAIL) |
| EFDE DME (réplique Collins IND-42) | `DME USB` | ✅ boutons SEL et PWR | ✅ distance, texte, 9 voyants, rétroéclairage |
| EFDE FDBUS (bus de jauges) | `FDBUS` | — | ✅ modules moteur X27 et analogique 12 V |
| Thrustmaster TCA Q-Eng 1&2 | `TCA Q-Eng 1&2` | ✅ 2 manettes (axes) | — |
| OpenCockpits USB Expansion + Master Card | `IOCardUSB` | ✅ 72 entrées | ⚠️ codage connu, non testé |
| Cartes wifi écrites pour SIOC | `IOCP` | — | ✅ voir [Cartes wifi](cartes-wifi.md) |

Une carte OpenCockpits ou EFDE dont le modèle est inconnu est quand même détectée. Elle est ouverte en **écoute seule** : rien ne lui est envoyé, et `bin/pepit listen` montre ses trames.

## Particularités

**EFDE IO32.** Une entrée actionnée vaut 1 (sur la Master Card OpenCockpits, c'est l'inverse : 1 au repos). Les entrées sont numérotées comme sous SIOC (9 × groupe + bit).

**MCP OpenCockpits.** L'état complet des 64 entrées arrive toutes les 40 ms environ. Chaque encodeur occupe deux entrées, en code Gray. Les afficheurs s'éteignent si plus aucun programme ne lit la carte.

**CDU OpenCockpits.** La carte reste muette tant qu'on ne lui a rien écrit ; Pepit la réveille à l'ouverture. Chaque appui envoie le numéro de la touche (rien au relâchement). Son écran est un écran d'ordinateur séparé : voir [l'écran physique du CDU](../utilisation/cockpit.md#lecran-physique-du-cdu).

**Radio Airbus.** Même réveil et mêmes entrées que le MCP ; afficheurs et voyants dans deux sortes de trames.

**DME EFDE.** Émet sans initialisation, même éteint. Protocole communiqué par EFDE et vérifié.

**Bus de jauges FDBUS.** Une carte USB et des modules sur un bus RS485 (adresses 195 à 254) : moteur pas à pas X27 (IVSI…), module analogique 12 V (volets…).

- **Deux modules livrés à la même adresse** se répondent l'un sur l'autre : un seul apparaît, illisible. Renumérotez l'un d'eux au banc de test (strap de configuration en place), puis coupez l'alimentation du bus.
- **Sans le 5 V du bus**, le module X27 s'annonce avec un type 0.
- **L'étalonnage** se fait au [banc de test](../utilisation/banc.md#les-jauges-du-bus-fdbus) et reste sur le PC.

**Thrustmaster TCA Q-Eng 1&2.** Lu par l'interface joystick de Linux (evdev), sans règle udev, et jamais écrit. Manette gauche = axe 0, droite = axe 1 ; 0 = plein gaz (tout en avant), 1 = fond de la reverse ; le cran de reverse tombe vers 0,72. Voir le type [`throttle_axis`](../configuration/types.md#manettes-des-gaz-throttle_axis) pour répartir deux manettes sur quatre moteurs.

## Alimentation USB

Certaines cartes tirent beaucoup de courant (le Saitek B.I.P. demande 450 mA). Derrière un hub qui ne fournit pas assez, la carte répond sur l'USB mais ses voyants ou moteurs restent éteints. En cas de doute, branchez-la directement sur le PC.

## Non pris en charge

**Saitek Pro Flight B.I.P.** (panneau de 24 voyants). La carte est reconnue et accepte les commandes de son pilote libre connu (vérifié sur le bus USB), mais ses voyants ne réagissent pas. La règle udev lui donne l'accès, pour une reprise éventuelle.
