// Afficheur carburant du BAe 146 : ESP8266 + écran OLED SSD1306 128x64, en wifi.
// Adapté du programme écrit pour le MD-80 sous SIOC (version 1.0.0).
//
// La carte se connecte au PC qui fait tourner Pepit (serveur IOCP, port 8092),
// comme elle le faisait avec SIOC, et demande trois variables :
//   201 = aile gauche (LFT), 202 = aile droite (RGT), 203 = réservoir central (CTR)
// Pepit les envoie directement en kg (config/avions/bae146-jf/carburant.yaml) :
// plus de conversion à faire ici. Le total est calculé par la carte.
//
// Carte : « Generic ESP8266 Module ». Mise à jour possible en wifi (OTA, nom esp8266fuel).
// Avant de compiler : copier secrets.h.example en secrets.h et y mettre le wifi.

#include <SPI.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <ESP8266WiFi.h>
#include <ESP8266mDNS.h>
#include <WiFiUdp.h>
#include <ArduinoOTA.h>
#include "secrets.h"            // WIFI_SSID, WIFI_PASSWORD (jamais publié)

// -------------------- VERSION 2.0.0 (BAe 146, Pepit) ----------------------

// Réseau ************************************************************************/
const char* host = "esp8266fuel";

// Adresse fixe de la carte : une adresse libre du réseau, hors de la plage DHCP de la
// box. (L'ancien programme donnait 192.168.1.500, qui n'existe pas : 255 au maximum.)
IPAddress ip(192, 168, 1, 50);
IPAddress gateway(192, 168, 1, 1);
IPAddress subnet(255, 255, 255, 0);
IPAddress myDns1(1, 1, 1, 1);
IPAddress myDns2(8, 8, 8, 8);

// PC qui fait tourner Pepit (relevé le 2026-11-25 : 192.168.1.20)
IPAddress serveriocp(192, 168, 1, 20);
const uint16_t portiocp = 8092;

WiFiClient client;

// Écran *************************************************************************/
#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64
#define OLED_RESET -1
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, OLED_RESET);

// Variables IOCP ****************************************************************/
const int VARIABLES[] = {201, 202, 203};          // aile gauche, aile droite, central
const int NB_VARIABLES = sizeof(VARIABLES) / sizeof(VARIABLES[0]);
long valeur[NB_VARIABLES];                         // kg
bool recu[NB_VARIABLES];                           // valeur reçue au moins une fois
String ligne = "";
bool debug = false;

// Affichage d'un message centré sur fond inversé (attente, connexion…)
void message(const __FlashStringHelper* l1, const __FlashStringHelper* l2) {
  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SSD1306_BLACK, SSD1306_WHITE);
  display.setCursor(30, 20);
  display.println(l1);
  display.setCursor(15, 28);
  display.println(l2);
  display.setTextColor(SSD1306_WHITE);
  display.display();
}

// Connexion au serveur IOCP (Pepit) et annonce des variables voulues
void connecterIOCP() {
  message(F("Waiting IOCP"), F("server connection"));
  while (!client.connect(serveriocp, portiocp)) {
    Serial.println("connection to IOCP server failed");
    for (int i = 0; i < 20; i++) {                 // 2 s, en restant joignable en OTA
      ArduinoOTA.handle();
      delay(100);
    }
  }
  Serial.print("connected to ");
  Serial.println(client.remoteIP());
  client.print("Arn.Inicio:");
  for (int i = 0; i < NB_VARIABLES; i++) {
    client.print(VARIABLES[i]);
    client.print(":");
  }
  client.println("");
  ligne = "";
}

// « Arn.Resp:201=3961:202=4129:203=998: » → valeurs ; « Arn.Vivo: » → réponse
void traiterLigne(const String& l) {
  if (debug) Serial.println(l);
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
    int numero = l.substring(pos, egal).toInt();
    long v = l.substring(egal + 1, fin).toInt();
    for (int i = 0; i < NB_VARIABLES; i++) {
      if (VARIABLES[i] == numero) {
        valeur[i] = v;
        recu[i] = true;
      }
    }
    pos = fin + 1;
  }
}

// Lit ce qui est arrivé, sans bloquer ; reconnecte si le serveur a disparu
void lireIOCP() {
  if (!client.connected()) {
    client.stop();
    connecterIOCP();
    return;
  }
  while (client.available()) {
    char c = client.read();
    if (c == '\n') {
      traiterLigne(ligne);
      ligne = "";
    } else if (c != '\r' && ligne.length() < 200) {
      ligne += c;
    }
  }
}

// Valeur en gros caractères, ou tirets tant que le simulateur n'a rien envoyé
void afficherValeur(int x, int y, int i) {
  display.setCursor(x, y);
  display.setTextSize(2);
  if (recu[i]) display.println(valeur[i]);
  else display.println(F("----"));
}

void setup() {
  Serial.begin(115200);
  if (!display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
    Serial.println(F("SSD1306 allocation failed"));
    for (;;);
  }

  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(0, 0);
  display.println(F("ESP MAC Address: "));
  display.println(WiFi.macAddress());
  display.display();

  WiFi.mode(WIFI_STA);
  WiFi.hostname(host);
  if (!WiFi.config(ip, gateway, subnet, myDns1, myDns2)) {
    Serial.println("STA Failed to configure");
  }
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  while (WiFi.waitForConnectResult() != WL_CONNECTED) {
    Serial.println("Connection Failed! Rebooting...");
    delay(5000);
    ESP.restart();
  }

  display.clearDisplay();
  display.setCursor(0, 0);
  display.println(F("Connected to: "));
  display.println(WIFI_SSID);
  display.println(F(" "));
  display.println(F("IP address: "));
  display.println(WiFi.localIP());
  display.display();
  delay(3000);

  ArduinoOTA.setHostname(host);
  ArduinoOTA.begin();

  for (int i = 0; i < NB_VARIABLES; i++) {
    valeur[i] = 0;
    recu[i] = false;
  }
  connecterIOCP();
}

void loop() {
  ArduinoOTA.handle();
  lireIOCP();

  long total = valeur[0] + valeur[1] + valeur[2];
  bool complet = recu[0] && recu[1] && recu[2];

  // Même mise en page que l'afficheur du MD-80 ; quantités en kg
  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SSD1306_BLACK, SSD1306_WHITE);
  display.setCursor(30, 0);
  display.println(F(" FUEL QTY "));
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(8, 3);
  display.println(F("LFT"));
  display.setCursor(96, 3);
  display.println(F("RGT"));
  afficherValeur(4, 14, 0);
  afficherValeur(77, 14, 1);
  display.setCursor(0, 40);
  display.setTextSize(1);
  display.println(F("CTR"));
  afficherValeur(46, 32, 2);
  display.setCursor(0, 57);
  display.setTextSize(1);
  display.println(F("Tot. fuel"));
  display.setCursor(64, 50);
  display.setTextSize(2);
  if (complet) display.println(total);
  else display.println(F("----"));
  display.display();

  delay(50);                                       // ~20 images par seconde
}
