#ifndef DEVICE_H
#define DEVICE_H

#include <stdint.h>
#include <Arduino.h>
#include "weight_sensor.h"
#include "pump_control.h"
#include "radial_valve_control.h"

#define DEVICE_STATE_INITIALIZING 0
#define DEVICE_STATE_PUMPING 1 
#define DEVICE_STATE_STOPPING 2
#define DEVICE_STATE_SETTING_VALVES 3

constexpr int kMaxReagents = 6;
constexpr int kMaxColumns = 6;

struct DeviceState {
    float pump_speed;
    float pump_volume;
    uint16_t program_step_idx;
    uint8_t device_state;           // 0: initialized, 1: pumping, 2: stopping, 3: setting valves
    uint8_t reagent_valve_position; // 0-5
    uint8_t reagent_valve_state;    // 0: idle, 1: homing, 2: stopped, 3: moving
    uint8_t column_valve_position;  // 0-5
    uint8_t column_valve_state;     // 0: idle, 1: homing, 2: stopped, 3: moving
    uint8_t running;                // 0: stopped, 1: running
    uint8_t program_step_progress;  // 0-255
    uint8_t padding[3];             // 3 bytes for future use
};

struct DeviceConfig {
  PumpControlConfig pump_config;
  RadialValveControlConfig reagent_valve_config;
  RadialValveControlConfig column_valve_config;
};

constexpr RadialValveControlConfig reagent_valve_config{
  .enable_pin = 14,
  .direction_pin = 26,
  .step_pin = 27,
  .limit_switch_pin = 15,
  .steps_per_revolution = 200 * 8,
  .invert_direction = true,
  .home_offset = 365,
  .position_mapping = {0, 5, 4, 3, 2, 1},
};

constexpr RadialValveControlConfig column_valve_config{
  .enable_pin = 4,
  .direction_pin = 17,
  .step_pin = 16,
  .limit_switch_pin = 2,
  .steps_per_revolution = 200 * 8,
  .invert_direction = true,
  .home_offset = 365,
  .position_mapping = {3, 2, 1, 0, 5, 4},
};

constexpr PumpControlConfig pump_config{
  .enable_pin = 25,
  .direction_pin = 32,
  .step_pin = 33,
  .dt = 0.01,
  .invert_direction = true,
  .volume_per_step = 0.0752192, // uL / step (approximate value, need to be calibrated)
};

constexpr DeviceConfig device_config{
  .pump_config = pump_config,
  .reagent_valve_config = reagent_valve_config,
  .column_valve_config = column_valve_config,
};


class Device {
  public:
    DeviceState device_state;

    Device(DeviceConfig config) : 
      config_(config),
      pump(config.pump_config),
      reagent_valve(config.reagent_valve_config),
      column_valve(config.column_valve_config) {}

    void initialize() {
      pump.initialize();
      reagent_valve.initialize();
      column_valve.initialize();
    }

    void set_valves(uint8_t reagent_valve_id, uint8_t column_valve_id) {
      reagent_valve_id_ = reagent_valve_id;
      column_valve_id_ = column_valve_id;
      fsm_state_ = DEVICE_STATE_STOPPING;
    }

    void set_pump(PumpCommand pump_cmd) {
      pump_cmd_ = pump_cmd;
    }

    void update() {
      device_state.pump_speed = pump.get_current_speed();
      device_state.pump_volume = pump.get_volume();
      device_state.reagent_valve_position = reagent_valve.get_position();
      device_state.reagent_valve_state = reagent_valve.get_state();
      device_state.column_valve_position = column_valve.get_position();
      device_state.column_valve_state = column_valve.get_state();
      device_state.device_state = fsm_state_;
      switch (fsm_state_) {
        case DEVICE_STATE_PUMPING:
          pump.set_pump(pump_cmd_);
          break;
        case DEVICE_STATE_STOPPING:
          pump.set_pump(PumpCommand{.pump_cmd = 0, .acceleration = 10.0});
          if (pump.is_stopped()) {
            fsm_state_ = DEVICE_STATE_SETTING_VALVES;
            reagent_valve.set_position(reagent_valve_id_);
            column_valve.set_position(column_valve_id_);
          }
          break;
        case DEVICE_STATE_SETTING_VALVES:
          if (reagent_valve.reached_target() && column_valve.reached_target()) {
            fsm_state_ = DEVICE_STATE_PUMPING;
          }
          break;
      }
    }

    PumpControl pump;
    RadialValveControl reagent_valve;
    RadialValveControl column_valve;

  private:
    DeviceConfig config_;
    PumpCommand pump_cmd_;
    uint8_t reagent_valve_id_;
    uint8_t column_valve_id_;
    uint8_t fsm_state_ = DEVICE_STATE_PUMPING;
};

static Device device(device_config);


#endif // DEVICE_H