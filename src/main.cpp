#include <Arduino.h>
#include <LittleFS.h>
#include "esp_timer.h"
#include <ESPmDNS.h>

// Poprawka: Dodano brakujący plik nagłówkowy i uporządkowano kolejność
#include "device.h"
#include "program.h"
#include "connection.h"
#include "wifi_setup.h"
#include "web_server.h"

SerialConnection connection;
Program program;
ProgramLoader program_loader(&program);
ProgramExecutor program_executor(&program);

TaskHandle_t Task_Communication_Handle = NULL;
TaskHandle_t Task_DeviceControlLoop_Handle = NULL;

esp_timer_handle_t pump_step_timer_handle = nullptr;
esp_timer_handle_t reagent_valve_step_timer_handle = nullptr;
esp_timer_handle_t column_valve_step_timer_handle = nullptr;

static void IRAM_ATTR pump_step_timer_callback(void* arg) {
  uint32_t next_delay = device.pump.step();
  esp_timer_start_once(pump_step_timer_handle, next_delay);
}

static void IRAM_ATTR reagent_valve_step_timer_callback(void* arg) {
  uint32_t next_delay = device.reagent_valve.update();
  esp_timer_start_once(reagent_valve_step_timer_handle, next_delay);
}

static void IRAM_ATTR column_valve_step_timer_callback(void* arg) {
  uint32_t next_delay = device.column_valve.update();
  esp_timer_start_once(column_valve_step_timer_handle, next_delay);
}

// Zadanie do obsługi komunikacji (Serial) - uruchamiane na Rdzeniu 1
void Task_Communication(void *pvParameters) {
  connection.init();
  while (1) {
    handle_communication(connection, program, program_loader, program_executor);
    // Dajemy szansę innym zadaniom na tym rdzeniu (np. web server)
    vTaskDelay(pdMS_TO_TICKS(10)); 
  }
}

// Główne zadanie sterujące logiką urządzenia - uruchamiane na Rdzeniu 0
void Task_DeviceControlLoop(void *pvParameters) {
  device.pump.enable();
  
  esp_timer_create_args_t pump_timer_args = {
    .callback = &pump_step_timer_callback,
    .arg = nullptr,
    .name = "pump_step_timer"
  };
  esp_timer_create(&pump_timer_args, &pump_step_timer_handle);
  esp_timer_start_once(pump_step_timer_handle, 10000);

  esp_timer_create_args_t reagent_valve_timer_args = {
    .callback = &reagent_valve_step_timer_callback,
    .arg = nullptr,
    .name = "reagent_valve_step_timer"
  };
  esp_timer_create(&reagent_valve_timer_args, &reagent_valve_step_timer_handle);
  esp_timer_start_once(reagent_valve_step_timer_handle, 10000);

  esp_timer_create_args_t column_valve_timer_args = {
    .callback = &column_valve_step_timer_callback,
    .arg = nullptr,
    .name = "column_valve_step_timer"
  };
  esp_timer_create(&column_valve_timer_args, &column_valve_step_timer_handle);
  esp_timer_start_once(column_valve_step_timer_handle, 10000);

  while (1) {
    // Kluczowe operacje sterujące w jednej pętli
    device.pump.update_speed(); 
    device.update();
    handle_execution(program, program_executor);
    
    vTaskDelay(pdMS_TO_TICKS(10));
  }
}


void setup() {
  Serial.begin(115200);

  if(!LittleFS.begin(true)){
      Serial.println("An Error has occurred while mounting LittleFS");
      return;
  }
  
  device.initialize();
  program.loadFromFile();
  program.loadReagentConfigFromFile();

  setup_wifi();
  setup_web_server();

  // Uruchomienie serwera mDNS
  if (!MDNS.begin("chromatograf")) { // Możesz tu wpisać dowolną nazwę
    Serial.println("Error setting up MDNS responder!");
  } else {
    Serial.println("MDNS responder started. You can now connect to http://chromatograf.local");
    // Opcjonalnie: ogłoś usługę serwera WWW, co może pomóc niektórym aplikacjom
    // w automatycznym wykrywaniu urządzenia
    MDNS.addService("http", "tcp", 80);
  }


  // Przypisanie zadań do odpowiednich rdzeni
  xTaskCreatePinnedToCore(
    Task_Communication,
    "Task_Communication",
    10000,
    NULL,
    1, // Priorytet 1
    &Task_Communication_Handle,
    1); // <-- Uruchom na Rdzeniu 1 (dla komunikacji)

  xTaskCreatePinnedToCore(
    Task_DeviceControlLoop,
    "Task_DeviceControlLoop",
    10000,
    NULL,
    2, // Wyższy priorytet 2 dla pętli sterującej
    &Task_DeviceControlLoop_Handle,
    0); // <-- Uruchom na Rdzeniu 0 (dla sterowania w czasie rzeczywistym)
}

void loop() {
  // Główna pętla jest teraz pusta. Cała logika została przeniesiona do zadań FreeRTOS.
  vTaskDelay(pdMS_TO_TICKS(1000));
}