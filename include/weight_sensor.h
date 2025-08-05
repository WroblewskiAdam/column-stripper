#ifndef WEIGHT_SENSOR_H
#define WEIGHT_SENSOR_H

#include <Arduino.h>
#include "multi_HX711.h"
#include "circular_buffer.h"

constexpr int kNumWeightSensors = 8;
constexpr int kFilterWindowSize = 1;

MultiHX711Config config = {
    .clock_pin = 23,
    .channels = {
      {.data_pin = 15, .scale_factor = -959.8163, .offset = 0},
      {.data_pin = 4, .scale_factor = -959.8163, .offset = 0},
      {.data_pin = 17, .scale_factor = -959.8163, .offset = 0},
      {.data_pin = 18, .scale_factor = -959.8163, .offset = 0},
      {.data_pin = 2, .scale_factor = -959.8163, .offset = 0},
      {.data_pin = 16, .scale_factor = -959.8163, .offset = 0},
      {.data_pin = 5, .scale_factor = -959.8163, .offset = 0},
      {.data_pin = 19, .scale_factor = -959.8163, .offset = 0},
    }
};


class WeightSensor {
    public:
        WeightSensor() : multiHX711_(config), circular_buffer_({
            CircularBuffer(kFilterWindowSize),
            CircularBuffer(kFilterWindowSize),
            CircularBuffer(kFilterWindowSize),
            CircularBuffer(kFilterWindowSize),
            CircularBuffer(kFilterWindowSize),
            CircularBuffer(kFilterWindowSize),
            CircularBuffer(kFilterWindowSize),
            CircularBuffer(kFilterWindowSize),
        }) {}

        void initialize() {
            multiHX711_.initialize();
            for (int i = 0; i < kNumWeightSensors; i++) {
                circular_buffer_[i] = CircularBuffer(kFilterWindowSize);
            }
        }

        void update() {
            // multiHX711_.wait_ready();
            multiHX711_.measure();
            for (int i = 0; i < kNumWeightSensors; i++) {
                circular_buffer_[i].push_back(multiHX711_.get_weight(i));
            }
        }

        float get_weight(int channel) {
            return multiHX711_.get_weight(channel);
        }

        float get_weight_filtered(int channel) {
            return circular_buffer_[channel].get_average();
        }

        void tare(int channel) {
            float weight = get_weight_filtered(channel);
            int32_t raw_offset = multiHX711_.grams_to_raw(weight, channel);
            multiHX711_.set_offset(channel, raw_offset);
        }

    private:
        MultiHX711 multiHX711_;
        CircularBuffer circular_buffer_[kNumWeightSensors];
};

#endif // WEIGHT_SENSOR_H