#ifndef WIFI_SETUP_H
#define WIFI_SETUP_H

#include <WiFi.h>
#include <WiFiManager.h>

/**
 * @brief Konfiguruje i łączy z siecią Wi-Fi za pomocą WiFiManager.
 * * Przy pierwszym uruchomieniu tworzy punkt dostępowy "ChromatographyControlAP"
 * w celu umożliwienia użytkownikowi konfiguracji sieci przez przeglądarkę.
 */
void setup_wifi() {
  WiFiManager wm;
  // wm.resetSettings(); // Odkomentuj, aby zresetować zapisane ustawienia Wi-Fi
  
 // Ustawia limit czasu (w sekundach) na próbę połączenia z zapisaną siecią.
  // Jeśli w tym czasie sieć nie zostanie znaleziona, uruchomi się Access Point.
  wm.setConnectTimeout(20);

  // Ustawia limit czasu (w sekundach), przez jaki portal konfiguracyjny (Access Point)
  // będzie aktywny. Jeśli użytkownik nie skonfiguruje sieci w tym czasie,
  // urządzenie się zrestartuje. 300 sekund = 5 minut.
  wm.setConfigPortalTimeout(300);

  // Ta linia próbuje połączyć się z siecią, a jeśli to się nie uda,
  // uruchamia AP o podanej nazwie.
  bool res = wm.autoConnect("ChromatographyControlAP");
  
  // Jeśli konfiguracja przez portal nie powiodła się (użytkownik nie podał danych
  // lub minął limit czasu), urządzenie się zrestartuje, aby spróbować ponownie.
  if(!res) {
      Serial.println("Failed to connect and configure WiFi. Restarting...");
      ESP.restart();
  } 
  
  // Jeśli wszystko się udało, jesteśmy połączeni.
  else {
      Serial.println("Connected to WiFi!");
      Serial.print("IP Address: ");
      Serial.println(WiFi.localIP());
  }
}

#endif // WIFI_SETUP_H
