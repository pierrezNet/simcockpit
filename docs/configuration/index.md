# Organisation de la configuration

Toute la configuration est dans le dossier `config/`, en YAML :

```
config/
├── materiel.yaml           # les cartes physiques, décrites une seule fois
├── fdbus.yaml              # jauges FDBUS : nom, unité, étalonnage (écrit par le banc de test)
├── ecrans.yaml             # écrans physiques (écran du CDU) : sortie vidéo, marges (écrit par le cockpit)
├── dictionnaire/
│   └── xplane.yaml         # fonctions → datarefs et commandes standard d'X-Plane
└── avions/
    ├── bae146-jf/          # un dossier par avion
    ├── b738-laminar/
    └── rj85-simule/
```

## Le matériel : `materiel.yaml`

Chaque carte y est déclarée une fois, sous un nom de votre choix, repris ensuite par les profils d'avion :

```yaml
cards:
  io32:
    product: USB32I04AD       # EFDE IO32 (transpondeur)
  mcp:
    product: IOCard-MCP       # OpenCockpits MCP
  tq:
    product: TCA Q-Eng 1&2    # Thrustmaster (manettes des gaz)
  arduino_carburant:
    product: IOCP             # carte wifi écrite pour SIOC
    port: 8092
```

- `product` est le nom USB affiché par `bin/pepit list` (ou `IOCP` pour une [carte wifi](../materiel/cartes-wifi.md)).
- `usb_port` (par exemple `"1-14"`) distingue deux cartes identiques : branchez-les toujours sur les mêmes prises.

## Un avion est un dossier

Chaque fichier YAML du dossier apporte un ou plusieurs **instruments** (un onglet du cockpit), avec la carte qu'ils utilisent et leurs **commandes** :

```yaml
instruments:
  transpondeur:
    label: Transpondeur
    card: io32
    controls:
      code:
        type: octal_digits
        inputs: [[0, 1, 2], [3, 4, 5], [6, 7, 8], [9, 10, 11]]
        fonction: transpondeur.code
      mode:
        type: selector
        positions:
          "ON": 12
          STBY: 13
        default: "OFF"
        fonction: transpondeur.mode
```

Dans le même dossier, on trouve aussi :

- **`sim:`**, la liaison au simulateur, dans un des fichiers (en général `sim.yaml`) ;
- **`fonctions:`**, les fonctions propres à l'avion, qui complètent le [dictionnaire](dictionnaire.md) (en général `fonctions.yaml`).

Les onglets suivent l'ordre alphabétique des fichiers. Seules les cartes utilisées par l'avion sont ouvertes. Pour un nouvel avion, copiez un dossier existant et adaptez-le.

Les numéros d'entrées et de sorties sont ceux affichés par le [banc de test](../utilisation/banc.md).

!!! warning "Les pièges du YAML"
    - **`ON`, `OFF`, `YES`, `NO` sans guillemets deviennent des booléens.** Écrivez `"ON"` et `"OFF"` entre guillemets.
    - **Pas de tabulation** dans l'indentation, seulement des espaces. Pepit refuse le fichier en donnant la ligne.
    - **Une description qui contient « : »** doit être entre guillemets.

Une erreur de configuration est signalée en rouge dans le cockpit, avec le fichier, l'instrument et la commande en cause.
