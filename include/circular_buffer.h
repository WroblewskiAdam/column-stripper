#ifndef CIRCULAR_BUFFER_H
#define CIRCULAR_BUFFER_H

#include <stdint.h>
#include <Arduino.h>

constexpr int kMaxCircularBufferSize = 256;

class CircularBuffer {
  public:
    CircularBuffer(int size) : size_(size) {
        if (size > kMaxCircularBufferSize) {
            throw std::invalid_argument("size is too large");
        }
    }
    void push_back(float value) {
        average_ -= buffer_[index_]/size_;
        average_ += value/size_;
        buffer_[index_] = value;
        index_ = (index_ + 1) % size_;
    }
    float get_average() {
        return average_;
    }
  private:
    float buffer_[kMaxCircularBufferSize];
    float average_ = 0;
    int index_;
    int size_;
};

#endif // CIRCULAR_BUFFER_H