# Cartes wifi (IOCP)

Pepit parle **IOCP**, le protocole réseau de SIOC. Les cartes Arduino, ESP8266 ou ESP32 en wifi écrites à l'origine pour SIOC se connectent donc à Pepit comme elles se connectaient à SIOC.

## Le principe

1. La carte se connecte au PC sur le **port 8092** et annonce les variables qu'elle veut recevoir :
   `Arn.Inicio:201:202:203:`
2. Pepit lui envoie leurs valeurs (des entiers), à l'annonce puis à chaque changement :
   `Arn.Resp:201=3961:202=4129:203=998:`
3. Pepit envoie régulièrement `Arn.Vivo:` ; la carte répond `Arn.Vivo:`.

Plusieurs cartes partagent le même serveur : chacune ne reçoit que les variables qu'elle a demandées.

## Déclarer une carte

Dans `config/materiel.yaml` :

```yaml
cards:
  arduino_carburant:
    product: IOCP
    port: 8092
```

Puis, dans le profil d'avion, relier ses variables au simulateur. Pour des valeurs directes, avec [`iocp_outputs`](../configuration/types.md#cartes-wifi-iocp_outputs-et-iocp_lookup) :

```yaml
instruments:
  carburant:
    label: Carburant (afficheur wifi)
    card: arduino_carburant
    controls:
      afficheur:
        type: iocp_outputs
        variables:
          201: carburant.aile_gauche
          202: carburant.aile_droite
          203: carburant.central
```

Pour une page d'un livret choisie selon une valeur (une page par masse), avec `iocp_lookup` : voir la carte des vitesses du [BAe 146](../avions/bae146.md#carte-des-vitesses).

La carte ne fait qu'afficher. Les valeurs, les unités et les choix (quelle page, quel arrondi) restent dans le YAML : on corrige une donnée sans reprogrammer la carte.

## Les programmes des cartes

Ils sont dans le dossier `arduino/` du dépôt, un projet PlatformIO par carte :

| Dossier | Carte | Rôle |
|---|---|---|
| `arduino/carburant_bae146/` | ESP8266 + écran OLED 128 × 64 | quantités de carburant gauche, droite, centrale et total, en kg |
| `arduino/carte_vitesses_bae146/` | LilyGo T5 4,7" (ESP32, encre électronique) | carte des vitesses du BAe 146, à la verticale |

Pour en programmer une :

1. copier `secrets.h.example` en `secrets.h` (copier, pas renommer) et y mettre le nom et le mot de passe du wifi ;
2. vérifier dans le programme l'adresse du PC qui fait tourner Pepit, et l'adresse fixe de la carte ;
3. compiler et téléverser, la première fois par le câble USB :

```sh
cd arduino/carte_vitesses_bae146
~/.platformio/penv/bin/pio run -e usb -t upload
```

Ensuite, le téléversement passe par le wifi (OTA) : `pio run -e ota -t upload`, avec l'adresse de la carte dans `platformio.ini`.

## Pièges rencontrés en reprenant des cartes SIOC

- **Annoncer ses variables.** Une carte qui n'envoie pas `Arn.Inicio` ne reçoit rien.
- **Une adresse IP valide.** Un octet va de 0 à 255 : « 192.168.1.500 » n'existe pas, et l'ESP le ramène en silence à 192.168.1.244.
- **Le mot de passe wifi hors du programme.** Il va dans `secrets.h`, que git ignore : il n'est jamais publié.
- **Le droit sur le port série.** Le téléversement par câble demande le groupe `dialout`. Sans fermer sa session, `sg dialout -c "…"` lance une commande avec ce groupe.
- **LilyGo T5 4,7".** Sa bibliothèque (LilyGo-EPD47) ne compile pas sur ESP32 avec les dernières versions de la plateforme : `platformio.ini` impose `espressif32@6.12.0`. Si la compilation réclame le module Python `intelhex`, installez-le dans l'environnement de PlatformIO : `~/.platformio/penv/bin/python -m pip install intelhex`.
- **Encre électronique.**
    - Coupez toute son alimentation après chaque dessin (`epd_poweroff_all`), sinon une coupure de courant peut laisser des traînées.
    - Un programme qui réécrit sans cesse le même texte sans effacer l'écran laisse un fantôme durable. Plusieurs cycles d'effacement au démarrage l'usent.
    - Ne rafraîchissez l'écran que quand une valeur change.
