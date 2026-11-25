// Carte des vitesses du BAe 146 sur écran à encre LilyGo T5 4,7" (ESP32 + PSRAM, 960 x 540),
// présentée à la verticale. Remplace le programme « Alert Messages » écrit pour SIOC.
//
// La carte se connecte au PC qui fait tourner simcockpit (serveur IOCP, port 8092) et
// demande les variables 210 à 223. simcockpit choisit la page du livret selon la masse de
// l'avion (config/avions/bae146-jf/carte_vitesses.yaml) : les valeurs du livret sont donc
// sur le PC, pas ici. L'écran se contente de dessiner la page reçue, et ne se rafraîchit
// que lorsqu'une valeur change (une encre électronique clignote et s'use à chaque
// rafraîchissement).
//
// Avant de compiler : copier secrets.h.example en secrets.h et y mettre le wifi.
// Sens de montage : régler ROTATION (90 ou 270) si la carte apparaît à l'envers.

#ifndef BOARD_HAS_PSRAM
#error "Activer la PSRAM (BOARD_HAS_PSRAM)"
#endif

#include <Arduino.h>
#include <WiFi.h>
#include <ArduinoOTA.h>
#include "epd_driver.h"
#include "zlib/zlib.h"
#include "roboto.h"       // Roboto, 59 px d'interligne, avec le symbole degré
#include "roboto12.h"     // petits libellés
#include "secrets.h"      // WIFI_SSID, WIFI_PASSWORD (jamais publié)

// -------------------- VERSION 2.2.0 (BAe 146, simcockpit) ----------------------

// Réseau ************************************************************************/
const char* host = "esp32carte";
// Adresse fixe de l'écran : libre, hors de la plage DHCP de la box. (L'ancien programme
// donnait 192.168.1.500, qui n'existe pas : 255 au maximum.)
IPAddress ip(192, 168, 1, 51);
IPAddress gateway(192, 168, 1, 1);
IPAddress subnet(255, 255, 255, 0);
IPAddress myDns1(1, 1, 1, 1);
IPAddress myDns2(8, 8, 8, 8);
IPAddress serveriocp(192, 168, 1, 20);    // PC qui fait tourner simcockpit
const uint16_t portiocp = 8092;
WiFiClient client;

// Variables IOCP (voir carte_vitesses.yaml) **************************************/
enum {
  PAGE, VR_18, V2_18, VR_24, V2_24, VR_30, V2_30, VFTO, VER,
  VREF_33, VREF_30, VREF_24, VREF_18, VREF_0, NB_VALEURS
};
const int PREMIERE_VARIABLE = 210;        // PAGE = 210 … VREF_0 = 223
long valeur[NB_VALEURS];
bool recu = false;                        // au moins une valeur reçue
String ligne = "";

// Écran *************************************************************************/
#define ROTATION 90                       // 90 ou 270 : sens de montage vertical
const int W = 540, H = 960;               // la carte, à la verticale
const uint8_t NOIR = 0x0, BLANC = 0xF;
uint8_t* framebuffer;
bool aRedessiner = true;
unsigned long dernierChangement = 0;
bool etaitConnecte = false;

// Effacement de l'encre (cycles noir / blanc). L'ancien programme réécrivait son message
// « connection to IOCP server failed » au même endroit sans jamais effacer : l'encre en
// garde un fantôme blanc qui ressort à chaque rafraîchissement. Un nettoyage profond au
// démarrage l'use peu à peu ; si un fantôme persiste, redémarrer la carte quelques fois.
const int CYCLES_DEMARRAGE = 20;          // nettoyage profond, une fois au démarrage
const int CYCLES_PAGE = 6;                // à chaque nouvelle page (la bibliothèque : 4)

void point(int x, int y, uint8_t c) {
  if (x < 0 || y < 0 || x >= W || y >= H) return;
  int lx, ly;
#if ROTATION == 90
  lx = y; ly = W - 1 - x;
#else
  lx = H - 1 - y; ly = x;
#endif
  uint8_t* p = &framebuffer[ly * (EPD_WIDTH / 2) + lx / 2];
  if (lx & 1) *p = (*p & 0x0F) | (c << 4);
  else *p = (*p & 0xF0) | c;
}

void rectangle(int x, int y, int w, int h, uint8_t c) {
  for (int j = y; j < y + h; j++)
    for (int i = x; i < x + w; i++) point(i, j, c);
}

void cadre(int x, int y, int w, int h, int e, uint8_t c) {
  rectangle(x, y, w, e, c);
  rectangle(x, y + h - e, w, e, c);
  rectangle(x, y, e, h, c);
  rectangle(x + w - e, y, e, h, c);
}

// UTF-8 → point de code (ASCII et Latin-1 : « ° » = U+00B0)
uint32_t suivant(const char*& s) {
  uint8_t c = *s++;
  if (c < 0x80) return c;
  if ((c & 0xE0) == 0xC0 && *s) return ((c & 0x1F) << 6) | (*s++ & 0x3F);
  return '?';
}

int largeur(const GFXfont* f, const char* s) {
  int w = 0;
  while (*s) {
    GFXglyph* g = NULL;
    get_glyph(f, suivant(s), &g);
    if (g) w += g->advance_x;
  }
  return w;
}

// Texte à partir de x, ligne de base y ; fond `bg` pour le lissage des bords.
// `gras` > 0 : trait épaissi de `gras` pixels et sans lissage (texte blanc sur fond noir,
// qui paraît trop fin sur l'encre sinon).
void texte(const GFXfont* f, const char* s, int x, int y, uint8_t fg, uint8_t bg, int gras = 0) {
  while (*s) {
    GFXglyph* g = NULL;
    get_glyph(f, suivant(s), &g);
    if (!g) continue;
    int bw = g->width / 2 + g->width % 2;
    unsigned long taille = bw * g->height;
    uint8_t* bm;
    if (f->compressed) {
      bm = (uint8_t*)malloc(taille);
      uncompress(bm, &taille, &f->bitmap[g->data_offset], g->compressed_size);
    } else {
      bm = &f->bitmap[g->data_offset];
    }
    for (int j = 0; j < g->height; j++) {
      for (int i = 0; i < g->width; i++) {
        uint8_t v = bm[j * bw + i / 2];
        v = (i & 1) ? (v >> 4) : (v & 0x0F);
        if (!v) continue;
        int px = x + g->left + i, py = y - g->top + j;
        if (gras == 0) {
          point(px, py, bg + v * ((int)fg - (int)bg) / 15);
        } else if (v >= 5) {                       // pixel assez couvert : plein, épaissi
          for (int dy = 0; dy <= gras; dy++)
            for (int dx = 0; dx <= gras; dx++) point(px + dx, py + dy, fg);
        }
      }
    }
    if (f->compressed) free(bm);
    x += g->advance_x;
  }
}

// Texte centré dans un rectangle
void centre(const GFXfont* f, const char* s, int x, int y, int w, int h, uint8_t fg, uint8_t bg,
            int gras = 0) {
  int hauteur = f->ascender * 72 / 100;          // hauteur des majuscules et chiffres
  texte(f, s, x + (w - largeur(f, s)) / 2 - gras / 2, y + (h + hauteur) / 2 - gras / 2, fg, bg, gras);
}

const int GRAS = 2;                              // épaississement du texte blanc sur noir

// « V » avec indice (R, 2, REF, FTO, ER), blanc sur noir
void vitesse(const char* indice, int x, int y, int w, int h) {
  int lv = largeur(&Roboto, "V"), li = largeur(&Roboto12, indice);
  int x0 = x + (w - lv - li - 2 - GRAS) / 2;
  int base = y + (h + Roboto.ascender * 72 / 100) / 2 - GRAS / 2;
  texte(&Roboto, "V", x0, base, BLANC, NOIR, GRAS);
  texte(&Roboto12, indice, x0 + lv + 2 + GRAS, base + 6, BLANC, NOIR, GRAS);
}

// Case blanche encadrée, avec un nombre (ou un tiret si absent)
void caseNombre(long v, int x, int y, int w, int h) {
  cadre(x, y, w, h, 3, NOIR);
  char t[12];
  if (v > 0) snprintf(t, sizeof t, "%ld", v);
  else snprintf(t, sizeof t, "-");
  centre(&Roboto, t, x, y, w, h, NOIR, BLANC);
}

void caseTexte(const char* s, int x, int y, int w, int h) {
  cadre(x, y, w, h, 3, NOIR);
  centre(&Roboto, s, x, y, w, h, NOIR, BLANC);
}

void bandeau(int x, int y, int w, int h) {
  rectangle(x, y, w, h, NOIR);
}

void deuxLignes(const char* a, const char* b, int x, int y, int w, int h) {
  centre(&Roboto12, a, x, y, w, h / 2, BLANC, NOIR, GRAS);
  centre(&Roboto12, b, x, y + h / 2 - 4, w, h / 2, BLANC, NOIR, GRAS);
}

void dessinerCarte() {
  memset(framebuffer, 0xFF, EPD_WIDTH * EPD_HEIGHT / 2);
  const int M = 18, X = M, TW = W - 2 * M, C = TW / 3, LH = 66, HH = 64;
  int y = M;

  // Masse de la page
  char masse[24];
  if (!client.connected()) snprintf(masse, sizeof masse, "attente IOCP");
  else if (!recu) snprintf(masse, sizeof masse, "attente X-Plane");
  else snprintf(masse, sizeof masse, "%ld kg", valeur[PAGE]);
  cadre(X, y, TW, 96, 4, NOIR);
  centre(&Roboto, masse, X, y, TW, 96, NOIR, BLANC);
  y += 96 + 16;

  // Décollage
  bandeau(X, y, TW, HH);
  deuxLignes("TAKE-OFF", "FLAPS", X, y, C, HH);
  rectangle(X + C, y, 3, HH, BLANC);
  vitesse("R", X + C, y, C, HH);
  rectangle(X + 2 * C, y, 3, HH, BLANC);
  vitesse("2", X + 2 * C, y, C, HH);
  y += HH;
  const char* volets[] = {"18\xC2\xB0", "24\xC2\xB0", "30\xC2\xB0", "-"};
  long vr[] = {valeur[VR_18], valeur[VR_24], valeur[VR_30], 0};
  long v2[] = {valeur[V2_18], valeur[V2_24], valeur[V2_30], 0};
  for (int i = 0; i < 4; i++) {
    caseTexte(volets[i], X, y, C, LH);
    caseNombre(vr[i], X + C - 3, y, C + 3, LH);
    caseNombre(v2[i], X + 2 * C - 3, y, C + 3, LH);
    y += LH - 3;
  }
  y += 12;

  // VFTO et VER
  int Q = TW / 4;
  bandeau(X, y, Q, LH);
  vitesse("FTO", X, y, Q, LH);
  caseNombre(valeur[VFTO], X + Q, y, Q, LH);
  bandeau(X + 2 * Q, y, Q, LH);
  vitesse("ER", X + 2 * Q, y, Q, LH);
  caseNombre(valeur[VER], X + 3 * Q, y, TW - 3 * Q, LH);
  y += LH + 12;

  // Atterrissage
  bandeau(X, y, TW, HH);
  deuxLignes("LANDING", "FLAPS", X, y, C, HH);
  rectangle(X + C, y, 3, HH, BLANC);
  vitesse("REF", X + C, y, TW - C, HH);
  y += HH;
  const char* voletsAtt[] = {"33\xC2\xB0", "30\xC2\xB0", "24\xC2\xB0", "18\xC2\xB0", "0\xC2\xB0"};
  long vref[] = {valeur[VREF_33], valeur[VREF_30], valeur[VREF_24], valeur[VREF_18], valeur[VREF_0]};
  for (int i = 0; i < 5; i++) {
    caseTexte(voletsAtt[i], X, y, C, LH);
    caseNombre(vref[i], X + C - 3, y, TW - C + 3, LH);
    y += LH - 3;
  }

  epd_poweron();
  epd_clear_area_cycles(epd_full_screen(), CYCLES_PAGE, 50);
  epd_draw_grayscale_image(epd_full_screen(), framebuffer);
  // Couper TOUTE l'alimentation de l'écran une fois l'image posée (l'encre la garde) :
  // avec seulement epd_poweroff(), une coupure de courant de la carte laissait des traînées
  // blanches sur l'image (comme le faisait déjà l'ancien programme).
  epd_poweroff_all();
}

// IOCP **************************************************************************/
void connecterIOCP() {
  if (!client.connect(serveriocp, portiocp)) return;
  client.print("Arn.Inicio:");
  for (int i = 0; i < NB_VALEURS; i++) {
    client.print(PREMIERE_VARIABLE + i);
    client.print(":");
  }
  client.println("");
  ligne = "";
}

// « Arn.Resp:210=38000:211=125: » → valeurs ; « Arn.Vivo: » → réponse
void traiterLigne(const String& l) {
  if (l.indexOf("Vivo:") >= 0) {
    client.println("Arn.Vivo:");
    return;
  }
  int pos = l.indexOf("Resp:");
  if (pos < 0) return;
  pos += 5;
  while (pos < (int)l.length()) {
    int egal = l.indexOf('=', pos);
    if (egal < 0) break;
    int fin = l.indexOf(':', egal);
    if (fin < 0) fin = l.length();
    int i = l.substring(pos, egal).toInt() - PREMIERE_VARIABLE;
    long v = l.substring(egal + 1, fin).toInt();
    if (i >= 0 && i < NB_VALEURS && valeur[i] != v) {
      valeur[i] = v;
      aRedessiner = true;
      dernierChangement = millis();
    }
    recu = true;
    pos = fin + 1;
  }
}

void lireIOCP() {
  while (client.available()) {
    char c = client.read();
    if (c == '\n') {
      traiterLigne(ligne);
      ligne = "";
    } else if (c != '\r' && ligne.length() < 300) {
      ligne += c;
    }
  }
}

// Programme *********************************************************************/
void setup() {
  Serial.begin(115200);
  epd_init();
  framebuffer = (uint8_t*)ps_calloc(1, EPD_WIDTH * EPD_HEIGHT / 2);
  if (!framebuffer) {
    Serial.println("mémoire PSRAM insuffisante");
    while (true) delay(1000);
  }
  for (int i = 0; i < NB_VALEURS; i++) valeur[i] = 0;

  epd_poweron();                          // nettoyage profond de l'encre (fantômes)
  epd_clear_area_cycles(epd_full_screen(), CYCLES_DEMARRAGE, 50);
  epd_poweroff_all();

  WiFi.mode(WIFI_STA);
  WiFi.setHostname(host);
  WiFi.config(ip, gateway, subnet, myDns1, myDns2);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  while (WiFi.waitForConnectResult() != WL_CONNECTED) {
    Serial.println("wifi : échec, nouvel essai");
    delay(5000);
    ESP.restart();
  }
  ArduinoOTA.setHostname(host);
  ArduinoOTA.begin();
  connecterIOCP();
  etaitConnecte = client.connected();
  dessinerCarte();
  aRedessiner = false;
}

void loop() {
  ArduinoOTA.handle();
  static unsigned long dernierEssai = 0;
  if (!client.connected() && millis() - dernierEssai > 3000) {
    dernierEssai = millis();
    client.stop();
    connecterIOCP();
  }
  if (client.connected() != etaitConnecte) {          // connexion gagnée ou perdue
    etaitConnecte = client.connected();
    aRedessiner = true;
    dernierChangement = millis();
  }
  lireIOCP();
  // on attend une seconde sans changement : une page arrive en un seul message, mais une
  // masse qui varie (pleins) ne doit pas faire clignoter l'écran en continu
  if (aRedessiner && millis() - dernierChangement > 1000) {
    aRedessiner = false;
    dessinerCarte();
  }
  delay(20);
}
