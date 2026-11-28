# Protocoles

Les cartes OpenCockpits et EFDE se pilotent en HID brut (`/dev/hidraw*`), avec des rapports de 8 octets sans numéro de rapport. Le détail et les cas vérifiés se trouvent dans `pepit/hw/` et dans les tests, qui rejouent des captures réelles (`tests/data/`).

## Format « Master Card » (EFDE IO32, IOCardUSB)

La carte ne transmet ses entrées qu'après l'initialisation `3d 00 3a <nb cartes> 39 <nb axes> ff ff`. Seuls les changements sont transmis :

- octet 0 : bits 0 à 3 = Master Cards concernées ; bits 4 à 6 = numéro d'axe ; bit 7 = suite de la trame précédente ;
- un octet d'axe, si la trame en contient un ;
- un masque des groupes (« slots ») qui ont changé ;
- un octet de 8 entrées par groupe présent dans le masque ;
- un octet de « 9ᵉ entrées », où le bit *i* correspond au *i*-ème groupe **présent**.

Une entrée a le numéro 9 × groupe + bit (numérotation SIOC). Une entrée actionnée vaut 1 sur l'EFDE, 0 sur la Master Card.

## MCP OpenCockpits

**Entrées.** L'état complet des 64 entrées est envoyé toutes les 40 ms environ ; l'entrée *n* correspond au bit *n % 8* de l'octet *n / 8*. Chaque encodeur occupe deux entrées, en code Gray (00 → 01 → 11 → 10 dans le sens horaire).

**Sorties** (ce n'est pas le format Master Card). Une trame est lue comme 16 demi-octets *n0* à *n15* : l'octet *k* donne *n2k* (moitié basse) et *n2k+1* (moitié haute). *n12* est le numéro de page ; l'octet 7 la luminosité, à l'envers (`00` = maximum).

| Page | Contenu |
|---|---|
| 0 | CRS1 = n2 n1 n0 · IAS = n5 n4 n3 · HDG = n8 n7 n6 · ALT (2 premiers chiffres) = n10 n9 · n11 bit 3 = point décimal d'IAS |
| 1 | ALT (3 derniers chiffres) = n2 n1 n0 · CRS2 = n5 n4 n3 · V/S = n10 … n6 |
| 2 | voyants : 16 bits dans les octets 0 et 1 (voir `pepit/hw/mcp.py`) |

Codes des chiffres : 0 à 9 ; `a` = chiffre éteint ; `b` = signe moins.

## Radio OpenCockpits Airbus

Même réveil et mêmes entrées que le MCP. En écriture, deux sortes de trames, selon le bit 7 de l'octet 6 :

- **afficheurs** (bit 7 à 0) : 12 demi-octets dans les octets 0 à 5, ACTIVE = n5 … n0 et STANDBY = n11 … n6 (codes du MCP) ; les bits 0 à 5 de l'octet 6 allument les points décimaux ;
- **voyants** (octet 6 = `80`) : un bit par voyant dans l'octet 0 (VHF1, VHF2, SEL, VOR, ADF, BFO, NAV, ILS).

## CDU OpenCockpits

La carte reste muette tant qu'on ne lui a rien écrit. Ensuite, chaque appui envoie une trame dont l'octet 0 est le numéro de la touche (1 à 88) ; rien n'est envoyé au relâchement. En écriture, l'octet 0 est un masque des voyants : bit 0 OFST, 1 MSG, 2 EXEC, 3 DSPY, 4 FAIL. La table des touches est dans `pepit/hw/usbfmc.py`.

## DME EFDE

Protocole communiqué par EFDE, vérifié à la webcam. Le DME émet sans initialisation, même éteint ; l'octet 0 vaut `01` tant que SEL est enfoncé, `02` pour PWR, `0a` au repos. En écriture, l'octet 0 désigne la fonction :

| Fonction | Rôle | Paramètres |
|---|---|---|
| `01` | distance à gauche | octets 1-2 : dixièmes de NM ; dixième affiché sous 200 NM |
| `02` | texte à droite (identifiant) | octets 1-4 : 4 caractères ASCII |
| `03` | voyant 1, 2 ou 3 | octet 7 : 1 à 3, 0 = éteint |
| `04` | WPT ou NM | octet 5 : 1 = WPT, 2 = NM, 0 = éteint |
| `05` | HLD, KT, MIN ou ID | octet 6 : 1 à 4, 0 = éteint |
| `06` | texte libre | octet 1 : colonne 1 à 9 ; octets 2-5 : 4 caractères |
| `07` | efface l'écran | |
| `08` | rétroéclairage | octet 1 : 0 = cellule photo, 1 à 255 = valeur fixe |
| `09` / `0a` | éteint / allume (test des segments) | |

Complétez les textes avec des espaces : un octet `00` allume des segments parasites.

## Bus de jauges EFDE (FDBUS)

Structure communiquée par EFDE, séquence vérifiée à la webcam. Trames de 8 octets, octet 0 = fonction ; les modules sont aux adresses 195 à 254. Aucune commande de position n'est prise en compte sans l'initialisation complète :

1. `00 00 00 …` : la carte explore le bus. Réponses : `03 adr` (adresse vide), `01 adr type` (module trouvé), `ff` (fin).
2. Pour chaque module n° *i* : `07 adr 00` puis `ff adr i`. Le module renvoie ses paramètres, un par trame `[fonction 150 à 187, i, valeur]` (Mini, Maxi, offset, plage…).
3. `fe 00 00` : la carte répond `fe`, l'initialisation est terminée.

Ensuite, `03 adr pos` place l'aiguille de la sortie 1 (0 à 255, borné par Mini et Maxi du module) ; la première commande après l'initialisation est ignorée, Pepit l'envoie deux fois. `07 adr 00` ramène le moteur X27 en butée. Les fonctions 50 à 88 écrivent l'EEPROM du module : Pepit n'envoie que la 50 (changement d'adresse, `32 adr nouvelle`), sur demande.

## IOCP (cartes wifi)

Texte sur TCP, port 8092, une ligne par message, champs séparés par `:` :

| Sens | Message | Rôle |
|---|---|---|
| carte → Pepit | `Arn.Inicio:201:202:` | variables voulues |
| Pepit → carte | `Arn.Resp:201=3961:202=4129:` | valeurs, à l'annonce puis à chaque changement |
| Pepit → carte, carte → Pepit | `Arn.Vivo:` | la liaison est vivante |
| carte → Pepit | `Arn.Resp:5=1:` | une entrée de la carte |

## X-Plane

- **UDP**, port 49000 : `RREF` (abonnement, valeurs renvoyées en flottants), `DREF` (écriture), `CMND` (commande). Au plus 500 abonnements par port local ; une rafale de plus d'environ 1000 demandes est en partie perdue.
- **API web locale**, port 8086 (X-Plane 12.1.1 et suivants) : `GET /api/v2/datarefs?filter[name]=…` donne l'identifiant d'un dataref, et le WebSocket `/api/v2` pousse ses valeurs (`dataref_subscribe_values`). C'est la seule façon de lire en entier un dataref texte publié par un plugin : l'UDP n'en renvoie que le premier octet.

## Manettes Thrustmaster (evdev)

Le noyau décode ces joysticks : Pepit lit les événements d'axes de `/dev/input/eventN`, retrouvé à partir du nœud hidraw de la carte par sysfs. Rien n'est écrit au périphérique.
