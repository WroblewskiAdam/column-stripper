#ifndef RADIAL_VALVE_CONTROL_H
#define RADIAL_VALVE_CONTROL_H

#include <Arduino.h>

#define STATE_RESET 0
#define STATE_HOME 1
#define STATE_STOP 2
#define STATE_MOVE 3

constexpr uint8_t kNumValvePorts = 6;

struct RadialValveControlConfig {
    uint8_t enable_pin;
    uint8_t direction_pin;
    uint8_t step_pin;
    uint8_t limit_switch_pin;
    uint16_t steps_per_revolution;
    bool invert_direction;
    uint16_t home_offset;
    uint8_t position_mapping[kNumValvePorts]; // Maps port numbers to position indices
};



class RadialValveControl {
  public:
    RadialValveControl(RadialValveControlConfig config) : config_(config) {}
    void initialize() {
        pinMode(config_.enable_pin, OUTPUT);
        pinMode(config_.direction_pin, OUTPUT);
        pinMode(config_.step_pin, OUTPUT);
        pinMode(config_.limit_switch_pin, INPUT);
        digitalWrite(config_.enable_pin, HIGH);
        digitalWrite(config_.direction_pin, config_.invert_direction);
        steps_per_position_ = config_.steps_per_revolution / kNumValvePorts;
    }

    uint32_t update() {
        state_machine();
        return step_time_;
    }

    void home() {
        state_ = STATE_HOME;
        digitalWrite(config_.enable_pin, LOW);
        step_time_ = max_step_time_; // Reset step time so that the valve starts slow
    }

    void set_position(uint8_t port) {
        /*
        Don't call this method directly, it won't be synchronized with the pump
        Use device.set_valves() instead.
        */
        position_ = port;
        if (!is_homed_) {
            home();
        }
        step_time_ = max_step_time_; // Reset step time so that the valve starts slow
        target_raw_position_ = position_to_raw(config_.position_mapping[port]);
    }

    bool reached_target() {
        return state_ == STATE_STOP || state_ == STATE_RESET;
    }

    uint8_t get_position() {
        return position_;
    }

    uint8_t get_state() {
        return state_;
    }

  private:
    uint16_t current_raw_position_ = 0;
    uint16_t target_raw_position_ = 0;
    uint16_t steps_per_position_ = 0;
    bool is_homed_ = false;
    bool step_state_ = false;
    uint8_t position_ = 255;
    const uint32_t min_step_time_ = 500;
    const uint32_t max_step_time_ = 30000;
    const uint32_t smoothness_factor_ = 100;
    uint32_t step_time_ = max_step_time_;
    uint8_t state_ = 0;
    RadialValveControlConfig config_;


    void step() {
        if (!step_state_) {
            // Only increment step once every step cycle
            ++current_raw_position_;
            if (current_raw_position_ == config_.steps_per_revolution) {
                current_raw_position_ = 0;
            }
        }
        step_state_ = !step_state_;
        digitalWrite(config_.step_pin, step_state_);
    }

    void state_machine() {
        switch (state_) {
            case STATE_RESET:
                break;

            case STATE_HOME:
                if (digitalRead(config_.limit_switch_pin) == HIGH) {
                    digitalWrite(config_.enable_pin, HIGH);
                    state_ = STATE_STOP;
                    is_homed_ = true;
                    current_raw_position_ = config_.home_offset;
                } else {
                    speed_up_a_bit();
                    step();
                }
                break;

            case STATE_STOP:
                if (current_raw_position_ != target_raw_position_) {
                    digitalWrite(config_.enable_pin, LOW);
                    state_ = STATE_MOVE;
                };
                break;

            case STATE_MOVE:
                if (current_raw_position_ == target_raw_position_) {
                    state_ = STATE_STOP;
                    digitalWrite(config_.enable_pin, HIGH);
                } else {
                    speed_up_a_bit();
                    step();
                }
                break;
        }
    }

    void speed_up_a_bit() {
        if (step_time_ > min_step_time_) {
            step_time_ -= step_time_ / smoothness_factor_;
        }
        if (step_time_ < min_step_time_) {
            step_time_ = min_step_time_;
        }
    }


    uint16_t position_to_raw(uint8_t position) {
        return position * steps_per_position_;
    }

};


#endif // RADIAL_VALVE_CONTROL_H