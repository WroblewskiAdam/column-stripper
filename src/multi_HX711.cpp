#include <multi_HX711.h>



void MultiHX711::initialize() {
    pinMode(config_.clock_pin, OUTPUT);
    for (int i = 0; i < kNumHX711; i++) {
        pinMode(config_.channels[i].data_pin, INPUT);
    }
}


bool MultiHX711::is_ready(int channel) {
    return digitalRead(config_.channels[channel].data_pin) == LOW;
}

bool MultiHX711::is_ready() {
    for (int i = 0; i < kNumHX711; i++) {
        if (!is_ready(i)) {
            return false;
        }
    }
    return true;
}

void MultiHX711::set_gain(uint8_t gain) {
    config_.gain = gain;
}

void MultiHX711::set_offset(int channel, float offset) {
    config_.channels[channel].offset = offset;
}

void MultiHX711::set_scale_factor(int channel, float scale_factor) {
    config_.channels[channel].scale_factor = scale_factor;
}


void MultiHX711::measure() {
    uint8_t filler = 0x00; 

    portMUX_TYPE mux = portMUX_INITIALIZER_UNLOCKED; // Disable interrupts to ensure good timing
    portENTER_CRITICAL(&mux);

    shiftIn(2);
    shiftIn(1);
    shiftIn(0);

    for (int i = 0; i < config_.gain; ++i) {
        digitalWrite(config_.clock_pin, HIGH);
        delayMicroseconds(1);
        digitalWrite(config_.clock_pin, LOW);
        delayMicroseconds(1);
    }

    portEXIT_CRITICAL(&mux);

    for (int i = 0; i < kNumHX711; i++) { // Pad the MSB byte (make 2's complement)
        if (rawBuffer_[i] & 0x800000) {
            rawBuffer_[i] |= 0xFF000000;
        } else {
            rawBuffer_[i] &= 0x00FFFFFF;
        }
    }

   for (int i = 0; i < kNumHX711; i++) {
    outputBuffer_[i] = raw_to_grams(rawBuffer_[i], i);
   }
}

float MultiHX711::get_weight(int channel) {
    return outputBuffer_[channel];
}

void MultiHX711::shiftIn(uint8_t byte_index) {
    for (int i = 0; i < kNumHX711; i++) {
        rawBuffer_[i] &= ~(0xFF << (8 * byte_index));
    }
    for (int i = 0; i < 8; ++i) {
        digitalWrite(config_.clock_pin, HIGH);
        delayMicroseconds(1);
        for (int j = 0; j < kNumHX711; j++) {
            rawBuffer_[j] |= digitalRead(config_.channels[j].data_pin) << (8 * byte_index + 7 - i);
        }
        digitalWrite(config_.clock_pin, LOW);
        delayMicroseconds(1);
    }
}

void MultiHX711::wait_ready() {
    while (!is_ready()) {
        vTaskDelay(pdMS_TO_TICKS(1));
    }
    vTaskDelay(pdMS_TO_TICKS(1));
}

float MultiHX711::raw_to_grams(int32_t raw_value, int channel) {
    return (raw_value - config_.channels[channel].offset) / config_.channels[channel].scale_factor;
}

int32_t MultiHX711::grams_to_raw(float grams, int channel) {
    return (grams * config_.channels[channel].scale_factor) + config_.channels[channel].offset;
}