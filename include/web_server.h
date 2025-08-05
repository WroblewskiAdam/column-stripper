#ifndef WEB_SERVER_H
#define WEB_SERVER_H

#include <ESPAsyncWebServer.h>
#include <ArduinoJson.h>
#include <LittleFS.h>
#include "device.h"
#include "program.h"

// Deklaracja, że obiekty istnieją w innym pliku (main.cpp)
extern ProgramExecutor program_executor;
extern Program program;
extern ProgramLoader program_loader;

// Tworzymy obiekt serwera na porcie 80 (standardowy port HTTP)
AsyncWebServer server(80);

/**
 * @brief Obsługuje zapytanie o aktualny status urządzenia.
 * Zwraca dane w formacie JSON, dokładnie odzwierciedlając strukturę DeviceState.
 */
void handle_get_status(AsyncWebServerRequest *request) {
    StaticJsonDocument<512> doc;
    
    doc["pump_speed"] = device.device_state.pump_speed;
    doc["pump_volume"] = device.device_state.pump_volume;
    doc["program_step_idx"] = device.device_state.program_step_idx;
    doc["device_state"] = device.device_state.device_state;
    doc["reagent_valve_position"] = device.device_state.reagent_valve_position;
    doc["reagent_valve_state"] = device.device_state.reagent_valve_state;
    doc["column_valve_position"] = device.device_state.column_valve_position;
    doc["column_valve_state"] = device.device_state.column_valve_state;
    doc["running"] = device.device_state.running;
    doc["program_step_progress"] = device.device_state.program_step_progress;

    String output;
    serializeJson(doc, output);
    request->send(200, "application/json", output);
}

/**
 * @brief Obsługuje ręczne ustawianie pozycji zaworów.
 */
void handle_set_valves(AsyncWebServerRequest *request) {
    if (request->hasParam("reagent_valve_id", true) && request->hasParam("column_valve_id", true)) {
        uint8_t reagent_id = request->getParam("reagent_valve_id", true)->value().toInt();
        uint8_t column_id = request->getParam("column_valve_id", true)->value().toInt();
        device.set_valves(reagent_id, column_id);
        request->send(200, "text/plain", "OK: Valve position set.");
    } else {
        request->send(400, "text/plain", "Error: Missing parameters.");
    }
}

/**
 * @brief Obsługuje ręczne sterowanie pompą.
 */
void handle_set_pump(AsyncWebServerRequest *request) {
    if (request->hasParam("pump_cmd", true) && request->hasParam("acceleration", true)) {
        PumpCommand cmd;
        cmd.pump_cmd = request->getParam("pump_cmd", true)->value().toFloat();
        cmd.acceleration = request->getParam("acceleration", true)->value().toFloat();
        device.set_pump(cmd);
        request->send(200, "text/plain", "OK: Pump command sent.");
    } else {
        request->send(400, "text/plain", "Error: Missing parameters.");
    }
}

// --- NOWE HANDLERY DO OBSŁUGI PROGRAMU ---

/**
 * @brief Przyjmuje program w formacie JSON i ładuje go do pamięci.
 */
void handle_program_upload(AsyncWebServerRequest *request, uint8_t *data, size_t len, size_t index, size_t total) {
    // Przy pierwszym fragmencie danych, czyścimy stary program
    if (index == 0) {
        program.clear();
        program_loader.reset();
    }

    DynamicJsonDocument doc(4096); // Zwiększony bufor na program
    DeserializationError error = deserializeJson(doc, (const char*)data);

    if (error) {
        request->send(400, "text/plain", "Invalid JSON");
        return;
    }

    JsonArray steps = doc.as<JsonArray>();
    for (JsonObject step_json : steps) {
        ProgramStep new_step;
        bool step_valid = false;

        if (strcmp(step_json["type"], "flush") == 0) {
            new_step.reagent_valve_id = step_json["reagent"];
            new_step.column_valve_id = step_json["column"];
            new_step.flow_rate = step_json["pump_speed"];
            new_step.duration = (float)step_json["duration_ms"].as<uint32_t>() / 1000.0f;
            new_step.volume = INFINITY;
            new_step.unused = 0;
            step_valid = true;
        } 
        else if (strcmp(step_json["type"], "wait") == 0) {
            new_step.reagent_valve_id = 0xff;
            new_step.column_valve_id = 0xff;
            new_step.flow_rate = 0.0f;
            new_step.duration = (float)step_json["duration_ms"].as<uint32_t>() / 1000.0f;
            new_step.volume = INFINITY;
            new_step.unused = 0;
            step_valid = true;
        }

        if (step_valid) {
            uint16_t current_len = program.length();
            program.write_at(current_len, &new_step);
        }
    }

    // Po otrzymaniu ostatniego fragmentu danych, wysyłamy odpowiedź i zapisujemy program do pliku
    if (index + len == total) {
        program.saveToFile(); // ZAPIS DO PAMIĘCI FLASH
        request->send(200, "text/plain", "Program uploaded and saved successfully");
    }
}

/**
 * @brief Uruchamia załadowany program.
 */
void handle_program_run(AsyncWebServerRequest *request) {
    program_executor.execute();
    request->send(200, "text/plain", "Program started");
}

/**
 * @brief Zatrzymuje aktualnie wykonywany program.
 */
void handle_program_stop(AsyncWebServerRequest *request) {
    program_executor.abort();
    request->send(200, "text/plain", "Program stopped");
}

/**
 * @brief Zwraca aktualnie załadowany program w formacie JSON.
 */
void handle_get_program(AsyncWebServerRequest *request) {
    if (program.length() == 0) {
        request->send(200, "application/json", "[]");
        return;
    }

    DynamicJsonDocument doc(4096);
    JsonArray steps_array = doc.to<JsonArray>();

    for (uint16_t i = 0; i < program.length(); i++) {
        ProgramStep step;
        program.read_at(i, &step);
        JsonObject step_json = steps_array.createNestedObject();

        if (step.flow_rate == 0.0f && step.reagent_valve_id == 0xff) {
            step_json["type"] = "wait";
            step_json["duration_ms"] = (uint32_t)(step.duration * 1000.0f);
        } else {
            step_json["type"] = "flush";
            step_json["reagent"] = step.reagent_valve_id;
            step_json["column"] = step.column_valve_id;
            step_json["pump_speed"] = step.flow_rate;
            step_json["duration_ms"] = (uint32_t)(step.duration * 1000.0f);
        }
    }

    String output;
    serializeJson(doc, output);
    request->send(200, "application/json", output);
}


void handle_not_found(AsyncWebServerRequest *request) {
    request->send(404, "text/plain", "Not found");
}

/**
 * @brief Konfiguruje wszystkie punkty końcowe API i uruchamia serwer.
 */
void setup_web_server() {
    // Inicjalizacja LittleFS została przeniesiona do setup() w main.cpp

    // --- Rejestracja API ---
    server.on("/api/status", HTTP_GET, handle_get_status);
    server.on("/api/manual/valves", HTTP_POST, handle_set_valves);
    server.on("/api/manual/pump", HTTP_POST, handle_set_pump);

    // Nowe endpointy do obsługi programu
    server.on("/api/program/run", HTTP_POST, handle_program_run);
    server.on("/api/program/stop", HTTP_POST, handle_program_stop);
    server.on("/api/program/get", HTTP_GET, handle_get_program);
    
    server.on(
        "/api/program/upload", 
        HTTP_POST, 
        [](AsyncWebServerRequest *request){},
        NULL, 
        handle_program_upload
    );

    // --- Jawne serwowanie plików interfejsu ---
    server.on("/", HTTP_GET, [](AsyncWebServerRequest *request){
        request->send(LittleFS, "/index.html", "text/html");
    });
    server.on("/style.css", HTTP_GET, [](AsyncWebServerRequest *request){
        request->send(LittleFS, "/style.css", "text/css");
    });
    server.on("/script.js", HTTP_GET, [](AsyncWebServerRequest *request){
        request->send(LittleFS, "/script.js", "text/javascript");
    });
    
    server.onNotFound(handle_not_found);
    server.begin();
    Serial.println("Web server started.");
}

#endif // WEB_SERVER_H
