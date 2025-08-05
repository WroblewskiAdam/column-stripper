#ifndef MULTI_HX711_H
#define MULTI_HX711_H

#include <Arduino.h>

constexpr int kNumHX711 = 8;

#define HX711_GAIN_128 1
#define HX711_GAIN_64 2
#define HX711_GAIN_32 3

struct HX711Config {
    uint8_t data_pin;
    float scale_factor;
    float offset;
};

struct MultiHX711Config {
    uint8_t gain;
    uint8_t clock_pin;
    HX711Config channels[kNumHX711];
};

class MultiHX711 {
    /*
    Class for handling multiple HX711 load cells.
    Each load cell has its own data pin, clock pin, scale factor, and offset.
    The load cells are read simultaneously using a single clock pin.
    */
  public:
    MultiHX711(MultiHX711Config config) : config_(config) {}
    void initialize();
    void measure();
    float get_weight(int channel);
    void set_offset(int channel, float offset);
    void set_scale_factor(int channel, float scale_factor);
    void set_gain(uint8_t gain);
    bool is_ready(int channel);
    bool is_ready();
    void wait_ready();
    float raw_to_grams(int32_t raw_value, int channel);
    int32_t grams_to_raw(float grams, int channel);

  private:
    MultiHX711Config config_;
    int32_t rawBuffer_[kNumHX711];
    float outputBuffer_[kNumHX711];
    void shiftIn(uint8_t byte_index);

};



#endif