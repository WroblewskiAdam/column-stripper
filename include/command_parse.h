#ifndef COMMAND_PARSE_H
#define COMMAND_PARSE_H

#include <cstdint>


struct Command {
    uint8_t command_id;
    uint8_t* data;
    int data_length;
};

typedef struct Command command_t;


void parse_command(uint8_t* data, int data_length, Command* command) {
    command->command_id = data[0];
    command->data = data + 1;
    command->data_length = data_length - 5; // 4 bytes for checksum, 1 byte for command id
}



#endif // COMMAND_PARSE_H