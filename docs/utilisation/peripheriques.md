# La page Périphériques

```sh
bin/pepit-peripheriques
```

La page Périphériques montre tout ce qui est branché en USB : où, depuis quand, et si Pepit peut s'en servir. Elle sert à comprendre pourquoi une carte n'apparaît pas, et à lui ouvrir l'accès d'un clic.

## Le tableau

Une ligne par périphérique déjà vu, les branchés en tête (matériel de simulation d'abord), les débranchés grisés :

| Colonne | Contenu |
|---|---|
| pastille | **vert** accessible, **orange** accès partiel, **rouge** accès refusé, **gris** branché sans nœud utile (concentrateur, webcam), **gris foncé** débranché |
| Périphérique | fabricant et produit, tels que le périphérique les annonce |
| Accès | « ouvert », « autorisé » (par le bouton ci-dessous), ou le bouton **Autoriser** |
| Pour Pepit | ce que Pepit en fait : « OpenCockpits MCP », « joystick (lu par le simulateur) », « concentrateur USB »… |
| VID:PID, Port | identifiants USB et prise (`1-4.4` : prise 4 du concentrateur branché en 4) |
| Vitesse, Courant | vitesse USB et courant demandé : un périphérique gourmand derrière un concentrateur non alimenté peut mal fonctionner |
| Branché, Première fois, Dernière fois | l'historique |
| Nœuds | les fichiers de `/dev` du périphérique (`hidraw3 ✓`, `event23 ✓`, `ttyUSB0 ✗`) ; le chemin complet au survol |

L'accès ne porte que sur les nœuds dont Pepit se sert : une manette Thrustmaster se lit par son nœud joystick (`event`), même si son nœud `hidraw` est fermé. Tout joystick, manette des gaz ou palonnier compte comme matériel de simulation, quel que soit son fabricant.

« Matériel de simulation seulement » cache le reste (clavier, souris, webcam…) ; « Montrer les débranchés » montre l'historique.

En bas, le **journal** note chaque branchement, débranchement et changement d'accès depuis le lancement de Pepit.

## En fond

Pepit suit les branchements en direct, page ouverte ou non (par les événements du noyau, sans droit particulier). Quand une carte de cockpit est branchée :

- la page Cartes se met à jour ;
- si Pepit n'y a pas accès, une bulle de la barre du haut le signale.

L'historique est gardé dans `~/.local/state/pepit/peripheriques.yaml` : première et dernière fois, ports successifs, nombre de branchements. Une carte sans numéro de série (le cas des cartes OpenCockpits et EFDE) y est reconnue par sa prise : branchée ailleurs, elle compte comme une autre carte.

## Autoriser un périphérique

Sous Linux, beaucoup de périphériques ne sont accessibles qu'à `root`. Le bouton **Autoriser** ouvre l'accès à un modèle de périphérique (son VID:PID) pour l'utilisateur assis devant le PC, sans mot de passe et sans rebrancher.

Il demande une **installation unique** (voir [Installation](../demarrage/installation.md#lacces-aux-cartes)) : tant qu'elle n'est pas faite, un bandeau jaune le rappelle et les boutons sont grisés.

- Le bouton n'apparaît que sur les lignes dont un nœud utile est fermé, et n'ouvre que ces nœuds-là.
- Pour un périphérique qui n'est pas du matériel de simulation, Pepit demande confirmation : un clavier autorisé serait lisible par tout programme de votre session.
- Le résultat s'inscrit dans le journal, et la pastille passe au vert.

Les modèles autorisés sont rangés dans `/etc/udev/rules.d/70-pepit-autorises.rules`, une ligne par modèle et par type de nœud. Pour en retirer un :

```sh
pkexec /usr/local/libexec/pepit-autoriser retirer VID PID     # ex. retirer 10c4 ea60
```

Le retrait vaut au prochain branchement du périphérique.
