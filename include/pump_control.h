#ifndef PUMP_CONTROL_H
#define PUMP_CONTROL_H

#include <Arduino.h>
#include "pumped_volume_counter.h"

struct PumpCommand {
  float pump_cmd;
  float acceleration;
};


constexpr float kMaxSpeed = 10.0; // ml / min
constexpr uint32_t kMaxStepDelayUs = 100000;

struct PumpControlConfig {
    uint8_t enable_pin;
    uint8_t direction_pin;
    uint8_t step_pin;
    float dt;
    bool invert_direction;
    uint32_t steps_per_revolution;
    float volume_per_step; // uL / step
};

class PumpControl {
  public:
    PumpControl(PumpControlConfig config) : config_(config) , volume_counter_(config.volume_per_step) {
      step_time_to_speed_coeff_ = 30000 * config.volume_per_step; // Based on unit conversions
    }

    void initialize() {
      pinMode(config_.enable_pin, OUTPUT);
      pinMode(config_.direction_pin, OUTPUT);
      pinMode(config_.step_pin, OUTPUT);
    }

    void set_pump(PumpCommand pump_cmd) {
      /*
      Don't call this method directly, it won't be synchronized with the valves
      Use device.set_pump() instead.
      */

      acceleration_ = pump_cmd.acceleration;
      if (pump_cmd.pump_cmd > kMaxSpeed) {
        pump_cmd.pump_cmd = kMaxSpeed;
      } else if (pump_cmd.pump_cmd < -kMaxSpeed) {
        pump_cmd.pump_cmd = -kMaxSpeed;
      }
      target_speed_ = pump_cmd.pump_cmd;
    }

    void enable() {
      digitalWrite(config_.enable_pin, LOW);
      enable_ = true;
    }

    void disable() {
      digitalWrite(config_.enable_pin, HIGH);
      enable_ = false;
    }

    void update_speed() {
      if (fabs(target_speed_ - current_speed_) < acceleration_ * config_.dt) {
        current_speed_ = target_speed_;
      } else if (target_speed_ > current_speed_) {
        current_speed_ += acceleration_ * config_.dt;
      } else if (target_speed_ < current_speed_) {
        current_speed_ -= acceleration_ * config_.dt;
      }

      if (fabs(current_speed_) < 1e-6) {
        half_step_delay_us_ = kMaxStepDelayUs;
        if (enable_) {
          disable();
        }
      } else {
        if (!enable_) {
          enable();
        }
        uint32_t delay = step_time_to_speed_coeff_ / fabs(current_speed_);
        if (delay > kMaxStepDelayUs) {
          half_step_delay_us_ = kMaxStepDelayUs;
        } else {
          half_step_delay_us_ = delay;
        }
      }

    }

    // Returns the next delay in microseconds, or kMaxStepDelayUs if no step should be taken
    uint32_t step() {
        if (!enable_) {
            return kMaxStepDelayUs; // Don't step if disabled
        }
        if (fabs(current_speed_) < 1e-6) {
            return kMaxStepDelayUs; // Don't step if speed is too low
        }
        
        if (current_speed_ > 0) {
            digitalWrite(config_.direction_pin, !config_.invert_direction);
        } else {
            digitalWrite(config_.direction_pin, config_.invert_direction);
        }
        step_state_ = !step_state_;
        digitalWrite(config_.step_pin, step_state_);

        if (step_state_ == HIGH) {
          volume_counter_.increment(); // only increment once per full step
        }

        // Return next delay in microseconds
        return half_step_delay_us_;
    }

    bool is_stopped() {
      return fabs(current_speed_) < 1e-6;
    }

    float get_volume() const {
      return volume_counter_.get_volume();
    }

    void reset_volume() {
      volume_counter_.reset();
    }

    float get_current_speed() const {
      return current_speed_;
    }

  private:
    float target_speed_ = 0;
    float current_speed_ = 0;
    float acceleration_ = 0;
    uint32_t half_step_delay_us_ = kMaxStepDelayUs;
    PumpedVolumeCounter volume_counter_;
    PumpControlConfig config_;
    bool enable_ = false;
    uint8_t step_state_ = LOW;
    float step_time_to_speed_coeff_; // uS / step
};

#endif // PUMP_CONTROL_H