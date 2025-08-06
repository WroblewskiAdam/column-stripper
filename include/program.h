#ifndef PROGRAM_H
#define PROGRAM_H

#include <stdint.h>
#include <Arduino.h>
#include <LittleFS.h>
#include "device.h"

constexpr float kDefaultPumpAcceleration = 5.0;
const char* PROGRAM_FILENAME = "/program.bin";
const char* REAGENT_CONFIG_FILENAME = "/reagent_config.bin";

struct ProgramStep {
    uint8_t reagent_valve_id; // set any of valve ids to 0xff to keep the current valve positions
    uint8_t column_valve_id;  
    uint16_t unused;          // 2 bytes for future use and for float data alignment
    float flow_rate;          // mL/min.
    float volume;             // mL. Use float infinity for unlimited volume
    float duration;           // seconds. Use float infinity for unlimited time
};


class Program {
  public: 
    static constexpr int kMaxMemory = 65536;
    static constexpr uint16_t kMaxLen = kMaxMemory / sizeof(ProgramStep);
    static constexpr uint16_t kMaxReagents = 6;
    static constexpr uint16_t kMaxColumns = 6;
    static constexpr uint16_t kMaxReagentNameLen = 40;
    static constexpr uint16_t kMaxColumnNameLen = 40;
    void write_at(uint16_t idx, ProgramStep* step) {
        steps[idx] = *step;
        if (idx >= nSteps) {
            nSteps = idx + 1;
        }
    }
    void read_at(int idx, ProgramStep* step) {
        *step = steps[idx];
    }
    uint16_t length() { return nSteps; }
    void clear() { nSteps = 0; }
    void read_block(uint16_t start_idx, uint16_t nSteps, uint8_t* buffer) {
      memcpy(buffer, steps + start_idx, nSteps * sizeof(ProgramStep));
    }
    static void parse_step(uint8_t* buffer, ProgramStep* step) {
      Serial.println(sizeof(ProgramStep));
      Serial.print("Step data: ");
      for (int i = 0; i < sizeof(ProgramStep); i++) {
        Serial.print(buffer[i], HEX);
        Serial.print(" ");
      }
      Serial.println();
      memcpy(step, buffer, sizeof(ProgramStep));
    }
    void set_reagents(uint8_t* buffer) {
      memcpy(reagents, buffer, sizeof(reagents));
    }
    void set_columns(uint8_t* buffer) {
      memcpy(columns, buffer, sizeof(columns));
    }

    /**
     * @brief Zapisuje konfigurację reagentów do pliku w systemie LittleFS.
     * @return true jeśli zapis się powiódł, false w przeciwnym razie.
     */
    bool saveReagentConfigToFile() {
        File file = LittleFS.open(REAGENT_CONFIG_FILENAME, "w");
        if (!file) {
            Serial.println("Failed to open reagent config file for writing");
            return false;
        }
        // Zapisz tablicę nazw reagentów
        file.write((uint8_t*)reagents, sizeof(reagents));
        file.close();
        Serial.println("Reagent configuration saved to file.");
        return true;
    }

    /**
     * @brief Wczytuje konfigurację reagentów z pliku w systemie LittleFS.
     * @return true jeśli odczyt się powiódł, false w przeciwnym razie.
     */
    bool loadReagentConfigFromFile() {
        if (!LittleFS.exists(REAGENT_CONFIG_FILENAME)) {
            Serial.println("Reagent config file not found. Using default names.");
            // Ustaw domyślne nazwy reagentów
            for (int i = 0; i < kMaxReagents; i++) {
                snprintf(reagents[i], kMaxReagentNameLen, "Reagent_%d", i + 1);
            }
            return false;
        }
        File file = LittleFS.open(REAGENT_CONFIG_FILENAME, "r");
        if (!file) {
            Serial.println("Failed to open reagent config file for reading");
            return false;
        }
        // Odczytaj tablicę nazw reagentów
        file.read((uint8_t*)reagents, sizeof(reagents));
        file.close();
        Serial.println("Reagent configuration loaded from file.");
        return true;
    }

    /**
     * @brief Zapisuje aktualny program do pliku w systemie LittleFS.
     * @return true jeśli zapis się powiódł, false w przeciwnym razie.
     */
    bool saveToFile() {
        File file = LittleFS.open(PROGRAM_FILENAME, "w");
        if (!file) {
            Serial.println("Failed to open program file for writing");
            return false;
        }
        // Zapisz liczbę kroków
        file.write((uint8_t*)&nSteps, sizeof(nSteps));
        // Zapisz tablicę kroków
        file.write((uint8_t*)steps, nSteps * sizeof(ProgramStep));
        file.close();
        Serial.printf("Program saved to file with %d steps.\n", nSteps);
        return true;
    }

    /**
     * @brief Wczytuje program z pliku w systemie LittleFS.
     * @return true jeśli odczyt się powiódł, false w przeciwnym razie.
     */
    bool loadFromFile() {
        if (!LittleFS.exists(PROGRAM_FILENAME)) {
            Serial.println("Program file not found. Starting with an empty program.");
            return false;
        }
        File file = LittleFS.open(PROGRAM_FILENAME, "r");
        if (!file) {
            Serial.println("Failed to open program file for reading");
            return false;
        }
        // Odczytaj liczbę kroków
        file.read((uint8_t*)&nSteps, sizeof(nSteps));
        // Sprawdź, czy liczba kroków jest prawidłowa
        if (nSteps > kMaxLen) {
            Serial.println("Invalid number of steps in program file. Clearing program.");
            nSteps = 0;
            file.close();
            return false;
        }
        // Odczytaj tablicę kroków
        file.read((uint8_t*)steps, nSteps * sizeof(ProgramStep));
        file.close();
        Serial.printf("Program loaded from file with %d steps.\n", nSteps);
        return true;
    }

    char reagents[kMaxReagents][kMaxReagentNameLen];
    char columns[kMaxColumns][kMaxColumnNameLen];
  private:
    ProgramStep steps[kMaxLen];
    uint16_t nSteps;
};

class ProgramLoader {
  public:
  ProgramLoader(Program* program) : program_(program) {}
  void load_from_buffer(uint8_t* buffer, uint16_t len) {
      uint16_t nSteps = len / sizeof(ProgramStep);
      Serial.print("loading ");
      Serial.print(nSteps);
      Serial.println(" steps from buffer");
      ProgramStep step;
      for (uint16_t i = 0; i < nSteps; i++) {
          Serial.print("Parsing step ");
          Serial.print(i);
          Serial.println("...");
          Program::parse_step(buffer + i * sizeof(ProgramStep), &step);
          program_->write_at(step_idx++, &step);
          Serial.print("step ");
          Serial.print(step_idx);
          Serial.print(": ");
          Serial.print(step.reagent_valve_id);
          Serial.print(", ");
          Serial.print(step.column_valve_id);
          Serial.print(", ");
          Serial.print(step.flow_rate);
          Serial.print(", ");
          Serial.print(step.duration);
          Serial.print(", ");
          Serial.print(step.volume);
          Serial.print(" written at ");
          Serial.println(step_idx);
      }
  }
  void reset() {
      step_idx = 0;
      program_->clear(); }
  private:
    Program* program_;
    uint16_t step_idx;
};

class ProgramExecutor {
  public:
    ProgramExecutor(Program* program) : program_(program) {}
    void execute() {
      running = true;
      step_idx = 0;
      program_->read_at(step_idx, &current_step);
      enter_step(&current_step);
    }
    void step() {
      device.device_state.program_step_idx = step_idx;
      device.device_state.running = running;
      if (!running) {
        return;
      }
      // uint8_t progress = 0;
      if (check_step_termination(&current_step, &(device.device_state.program_step_progress))) {
        ++step_idx;
        if (step_idx >= program_->length()) {
          running = false;
          Serial.println("Program finished");
          device.set_pump(PumpCommand{.pump_cmd = 0, .acceleration = kDefaultPumpAcceleration});
          return;
        }
        program_->read_at(step_idx, &current_step);
        enter_step(&current_step);
      }
    }
    void abort() {
      running = false;
      device.set_pump(PumpCommand{.pump_cmd = 0, .acceleration = kDefaultPumpAcceleration});
    }
    bool is_running() { return running; }
  private:
    ProgramStep current_step;
    Program* program_;
    uint16_t step_idx = 0;
    bool running = false;
    unsigned long step_end_time = 0;
    float step_end_volume = 0;

    void enter_step(ProgramStep* step) {
      device.pump.reset_volume();
      if (step->reagent_valve_id != 0xff && step->column_valve_id != 0xff) {
        device.set_valves(step->reagent_valve_id, step->column_valve_id);
      }
      device.set_pump(PumpCommand{.pump_cmd = step->flow_rate, .acceleration = kDefaultPumpAcceleration});
      if (isinf(step->duration)) {
        step_end_time = uint32_t(INFINITY);
      } else {
        step_end_time = millis() + uint32_t(step->duration * 1000.0f);
      }
      step_end_volume = step->volume * 1000.0f; // convert mL to uL

      Serial.print("Entered step: ");
      Serial.print(step->reagent_valve_id);
      Serial.print(", ");
      Serial.print(step->column_valve_id);
      Serial.print(", ");
      Serial.print(step->flow_rate);
      Serial.print(", ");
      Serial.print(step->volume);
      Serial.print(", ");
      Serial.println(step->duration);
    }

    bool check_step_termination(ProgramStep* step, uint8_t* progress) {
      unsigned long now = millis();
      if (step_end_time < now) {
        *progress = 255;
        return true;
      }
      uint8_t time_progress = 0;
      if (isinf(step->duration)) {
        time_progress = 0;
      } else {
        time_progress = 255 * (1 - float(step_end_time - now) / (step->duration * 1000.0f));
      }
      if (device.pump.get_volume() >= step_end_volume) {
        *progress = 255;
        return true;
      }
      uint8_t volume_progress = 255 * device.pump.get_volume() / step_end_volume;
      *progress = max(time_progress, volume_progress);
      return false;
    }
};

void handle_execution(Program& program, ProgramExecutor& program_executor) {
  program_executor.step();
}

#endif // PROGRAM_H
