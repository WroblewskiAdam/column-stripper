#ifndef CONNECTION_H
#define CONNECTION_H

#include <CRC32.h>
#include "device.h"
#include "program.h"
#include "command_parse.h"


constexpr int kReceiveBufferSize = 2000;
const uint8_t kStartSeq[] = {0x21, 0x37};

class SerialConnection {
  public:
    void init() {
        Serial.begin(115200);
    }

    void send_data(uint8_t* data, uint8_t data_length) {
        uint8_t data_len[1] = {data_length+(uint8_t)4};
        Serial.write(kStartSeq, 2);
        Serial.write(data_len, 1);
        Serial.write(data, data_length);
        uint32_t crc = compute_crc(data, data_length);
        uint8_t crc_bytes[4] = {0};
        crc_bytes[0] = crc >> 24;
        crc_bytes[1] = crc >> 16;
        crc_bytes[2] = crc >> 8;
        crc_bytes[3] = crc;
        Serial.write(crc_bytes, 4);
    }

    void send_ack(int code) {
        uint8_t data[1] = {0};
        data[0] = code;
        send_data(data, 1);
    }

    bool receive_packet(int timeout_ms, uint8_t** data_ptr, int* data_length) {
        int timeout_start_ms = millis();

        datalen = -1;
        int data_idx = 0;
        state = State::STATE_WAIT_FOR_START1;
        while (true) {
            if (state == State::STATE_WAIT_FOR_START1 && millis() - timeout_start_ms > timeout_ms) {
                return false;
            }
            while (Serial.available() > 0) {
                uint8_t b = Serial.read();
                if (handle_receive_byte(b)) {
                    *data_ptr = receive_buffer;
                    *data_length = datalen;
                    return true;
                }
            }
        }
        return false;
    }

  private:
    enum State {
      STATE_WAIT_FOR_START1,
      STATE_WAIT_FOR_START2,
      STATE_RECEIVE_DATALEN,
      STATE_RECEIVE_DATA,
    };
    enum ChecksumResult {
        CHECKSUM_ERROR,
        CHECKSUM_OK,
    };

    uint8_t receive_buffer[kReceiveBufferSize] = {0};
    int state = STATE_WAIT_FOR_START1;
    int datalen = 0;
    int data_idx = 0;


    bool handle_receive_byte(uint8_t b) {
        switch (state) {
            case State::STATE_WAIT_FOR_START1:
                if (b == kStartSeq[0]) { // First byte of start sequence received
                    state = State::STATE_WAIT_FOR_START2;
                }
                return false;
            case State::STATE_WAIT_FOR_START2:
                if (b == kStartSeq[1]) { // Second byte of start sequence received
                    state = State::STATE_RECEIVE_DATALEN;
                } else { // Start sequence not received, reset to start
                    state = State::STATE_WAIT_FOR_START1;
                }
                return false;
            case State::STATE_RECEIVE_DATALEN:
                datalen = b;
                if (datalen > kReceiveBufferSize || datalen <= 0) {
                    state = State::STATE_WAIT_FOR_START1;
                    return false;
                }
                data_idx = 0;
                state = State::STATE_RECEIVE_DATA;
                return false;
            case State::STATE_RECEIVE_DATA:
                if (data_idx < datalen) { // Receive consecutive byte of payload
                    receive_buffer[data_idx++] = b;
                } 
                if (data_idx >= datalen) { // Full payload received. Verify checksum
                    state = State::STATE_WAIT_FOR_START1;
                    if (verify_checksum(receive_buffer, datalen) == ChecksumResult::CHECKSUM_OK) {
                        return true;
                    }
                    return false;
                }

            }
        return false;
    }

    uint32_t compute_crc(uint8_t* data, int datalen) {
        CRC32 crc;
        crc.update(data, datalen);
        return crc.finalize();
    }


    int verify_checksum(uint8_t* data, int datalen) {
    // Ensure the data buffer is at least 4 bytes long (for the checksum itself)
        if (datalen < 4) {
            // Not enough data to even contain a checksum
            return 0;
        }

        int data_payload_len = datalen - 4;

        uint32_t received_checksum = 0;
        received_checksum |= (uint32_t)data[datalen - 4] << 24; // MSB
        received_checksum |= (uint32_t)data[datalen - 3] << 16;
        received_checksum |= (uint32_t)data[datalen - 2] << 8;
        received_checksum |= (uint32_t)data[datalen - 1];      // LSB

        uint32_t calculated_checksum = compute_crc(data, data_payload_len);

        // Compare the calculated checksum with the received checksum
        if (calculated_checksum == received_checksum) {
            return ChecksumResult::CHECKSUM_OK;
        } else {
            return ChecksumResult::CHECKSUM_ERROR;
        }
    }
};



void handle_communication(SerialConnection& connection, Program& program, ProgramLoader& program_loader, ProgramExecutor& program_executor) {
    uint8_t* data_ptr = nullptr;
    int data_length = 0;
    bool result = connection.receive_packet(10, &data_ptr, &data_length);
    if (result) {
        command_t command;
        parse_command(data_ptr, data_length, &command);
        if (command.command_id == 0) {
            // ping
            connection.send_ack(0);
        } else if (command.command_id == 1) {
            // set valves
            uint8_t reagent_valve_id = command.data[0];
            uint8_t column_valve_id = command.data[1];
            device.set_valves(reagent_valve_id, column_valve_id);
            connection.send_ack(0);
        } else if (command.command_id == 2) {
            // set pump
            PumpCommand pump_cmd;
            memcpy(&pump_cmd, command.data, sizeof(PumpCommand));
            device.set_pump(pump_cmd);
            connection.send_ack(0);
        } else if (command.command_id == 3) {
            // get weight
            connection.send_ack(0);
        } else if (command.command_id == 4) {
            // init program write
            program_executor.abort();
            program_loader.reset();
            connection.send_ack(0);
        } else if (command.command_id == 5) {
            // write program block
            program_loader.load_from_buffer(command.data, command.data_length);
            connection.send_ack(0);
        } else if (command.command_id == 6) {
            // execute program
            connection.send_ack(0);
            program_executor.execute();
        } else if (command.command_id == 13) {
            // abort program execution
            program_executor.abort();
            connection.send_ack(0);
        } else if (command.command_id == 7) {
            // read program block
            uint16_t block_idx = (command.data[0] << 8) | command.data[1];
            uint16_t nSteps = (command.data[2] << 8) | command.data[3];
            uint8_t buffer[sizeof(ProgramStep) * nSteps];
            program.read_block(block_idx, nSteps, buffer);
            connection.send_data(buffer, sizeof(buffer));
        } else if (command.command_id == 8) {
            // get program length
            uint16_t length = program.length();
            uint8_t buffer[4] = {0};
            buffer[0] = length >> 8;
            buffer[1] = length & 0xff;
            buffer[2] = Program::kMaxLen >> 8;
            buffer[3] = Program::kMaxLen & 0xff;
            connection.send_data(buffer, sizeof(buffer));
        } else if (command.command_id == 9) {
            // get reagents
            connection.send_data((uint8_t*)program.reagents, sizeof(program.reagents));
        } else if (command.command_id == 10) {
            // get columns
            connection.send_data((uint8_t*)program.columns, sizeof(program.columns));
        } else if (command.command_id == 11) {
            // set reagents
            program.set_reagents(command.data);
            connection.send_ack(0);
        } else if (command.command_id == 12) {
            // set columns
            program.set_columns(command.data);
            connection.send_ack(0);
        } else if (command.command_id == 14) {
            // get device state
            connection.send_data((uint8_t*)&device.device_state, sizeof(DeviceState));
        } else if (command.command_id == 15) {
            // tare weight sensor REMOVED
            // uint8_t channel = command.data[0];
            // device.tare_weight_sensor(channel);
            connection.send_ack(0);
        } else {
            // unknown command
            connection.send_ack(1);
        }
    } else {

    }
}

#endif // CONNECTION_H