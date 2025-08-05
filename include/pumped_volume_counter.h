#ifndef PUMPED_VOLUME_COUNTER_H
#define PUMPED_VOLUME_COUNTER_H

#include <Arduino.h>

class PumpedVolumeCounter {

    public:
        PumpedVolumeCounter(float volume_per_step) : volume_per_step_(volume_per_step) {}

        void increment() {
            volume_ += volume_per_step_;
        }

        void reset() {
            volume_ = 0;
        }

        float get_volume() const {
            return volume_;
        }

    private:
        float volume_ = 0;
        const float volume_per_step_;
};

#endif // PUMPED_VOLUME_COUNTER_H