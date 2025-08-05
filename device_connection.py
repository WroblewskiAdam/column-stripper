import zlib
import time
import serial
from program import Program, ProgramConverter
from typing import List, Optional, Callable
import struct

START_SEQUENCE = b'\x21\x37'

class DeviceState:
    def __init__(self):
        self.pump_speed = 0.0
        self.pump_volume = 0.0
        self.program_step_idx = 0
        self.device_state = 0
        self.reagent_valve_position = 0
        self.reagent_valve_state = 0
        self.column_valve_position = 0
        self.column_valve_state = 0
        self.running = 0
        self.program_step_progress = 0
    
    def __repr__(self):
        return f"DeviceState(pump_speed={self.pump_speed:.2f}, pump_volume={self.pump_volume:.2f}, program_step_idx={self.program_step_idx}, device_state={self.device_state}, reagent_valve_pos={self.reagent_valve_position}, reagent_valve_state={self.reagent_valve_state}, column_valve_pos={self.column_valve_position}, column_valve_state={self.column_valve_state}, running={self.running}, program_step_progress={self.program_step_progress})"

class DeviceConnection:
    def __init__(self, port, debug_callback: Optional[Callable[[str], None]] = None):
        self.port = port
        self.debug_callback = debug_callback
        self.ser = None
        self.debug_buffer = ""  # Buffer for accumulating debug output
        self.single_byte_message = ""
    
    def open(self):
        self.ser = serial.Serial(self.port, 115200, timeout=1)
        self._log_debug(f"[CONN] Opened serial connection to {self.port}")
        if not self.ping():
            self._log_debug("[CONN] Ping failed - connection not established")
            raise ConnectionError("Failed to open connection")
        self._log_debug("[CONN] Connection established successfully")
    
    def check(self) -> bool:
        if self.ser is None:
            return False
        return self.ping()

    
    def close(self):
        if self.ser:
            self.ser.close()

    def _log_debug(self, message: str):
        """Log debug message if callback is provided"""
        if self.debug_callback:
            self.debug_callback(message)
    

    def _log_program_steps(self, raw_data: List[bytes], prefix: str = "[PROG]"):
        """Log program steps with both parsed data and raw hex"""
        self._log_debug(f"{prefix} Raw program data ({len(raw_data)} blocks):")
        for i, block in enumerate(raw_data):
            self._log_debug(f"{prefix} Block {i+1}:")
            # Parse and display individual steps in this block
            for j in range(0, len(block), 16):  # Each step is 16 bytes
                step_bytes = block[j:j+16]
                if len(step_bytes) == 16:
                    step_data = struct.unpack('<BBBBfff', step_bytes)
                    step_num = i*5 + j//16 + 1
                    # Format raw bytes with spaces between each byte
                    raw_hex_spaced = ' '.join(f'{b:02x}' for b in step_bytes)
                    self._log_debug(f"{prefix}   Step {step_num}: reagent={step_data[0]}, column={step_data[1]}, flow={step_data[4]:.1f}, volume={step_data[5]:.1f}ml, duration={step_data[6]:.0f}s")
                    self._log_debug(f"{len(prefix) * ' '}   Raw: {raw_hex_spaced}")
                else:
                    # Format incomplete step bytes with spaces
                    raw_hex_spaced = ' '.join(f'{b:02x}' for b in step_bytes)
                    self._log_debug(f"{prefix}   Incomplete step: {raw_hex_spaced}")

    def _read_serial_debug(self, timeout=0.1):
        """Read any available serial data for debugging (non-command responses)"""
        if not self.ser or not self.ser.in_waiting:
            return
            
        try:
            # Read available data
            data = self.ser.read(self.ser.in_waiting)
            if data:
                # Try to decode as text
                try:
                    text = data.decode('utf-8', errors='replace')
                    if text:
                        # Add to buffer
                        self.debug_buffer += text
                        
                        # Process complete lines
                        while '\n' in self.debug_buffer:
                            line, self.debug_buffer = self.debug_buffer.split('\n', 1)
                            line = line.strip()
                            if line:  # Only log non-empty lines
                                self._log_debug(f"[DEVICE] {line}")
                except:
                    # If not text, show as hex
                    self._log_debug(f"[DEVICE] Raw: {data.hex()}")
        except Exception as e:
            self._log_debug(f"[ERROR] Failed to read debug data: {e}")

    def check_debug_output(self):
        """Check for any debug output from the device"""
        if self.ser:
            self._read_serial_debug()

    def clear_debug_buffer(self):
        """Clear the debug buffer"""
        self.debug_buffer = ""

    def receive_response(self, timeout=1):
        state = 0
        datalen = 0
        response = bytes([])
        start_time = time.time()
        
        while True:
            if time.time() - start_time > timeout:
                raise ConnectionError("timeout")
            if state == 0:
                if self.ser.in_waiting > 0:
                    data = self.ser.read(1)
                    if data == b'\x21':
                        state = 1
                    else:
                        self._log_single_byte(data)
                        pass
            elif state == 1:
                if self.ser.in_waiting > 0:
                    data = self.ser.read(1)
                    if data == b'\x37':
                        state = 2
                    else:
                        state = 0
            elif state == 2:
                datalen = int(self.ser.read(1)[0])
                if datalen <= 0:
                    raise ConnectionError("datalen <= 0")
                state = 3
            elif state == 3:
                if self.ser.in_waiting > 0:
                    response += self.ser.read(1)
                    if len(response) == datalen:
                        checksum = zlib.crc32(response[:-4])
                        if checksum == int.from_bytes(response[-4:], 'big'):
                            return response[:-4]
                        else:
                            raise ConnectionError("response checksum error")
            else:
                # Unknown state, should not happen
                raise ConnectionError("unknown state")
    
    def _log_single_byte(self, data):
        self.single_byte_message += data.decode('utf-8', errors='replace')
        if '\n' in self.single_byte_message:
            self._log_debug(f"[DEVICE] {self.single_byte_message.strip()}")
            self.single_byte_message = ""
            

    def _try_send_command(self, command_id, payload=None, timeout=0.5):
        data = bytes([command_id])
        if payload is not None:
            data = data + payload
        checksum = zlib.crc32(data)
        data = data + checksum.to_bytes(4, 'big')
        datalen = bytes([len(data)])
        self.ser.write(START_SEQUENCE + datalen + data)
        
        # Log command being sent (for debugging) - exclude ping commands
        if self.debug_callback and command_id not in [0, 14]:  # Don't log ping commands and device state
            cmd_name = self._get_command_name(command_id)
            self._log_debug(f"[CMD] Sending {cmd_name} (ID: {command_id})")
        
        resp = self.receive_response(timeout)
        return resp

    def _get_command_name(self, command_id):
        """Get human-readable name for command ID"""
        commands = {
            0: "PING",
            1: "VALVE_CMD",
            2: "PUMP_CMD", 
            4: "INIT_PROGRAM_WRITE",
            5: "WRITE_PROGRAM_BLOCK",
            6: "EXECUTE_PROGRAM",
            7: "GET_PROGRAM_BLOCK",
            8: "GET_PROGRAM_LENGTH",
            9: "GET_REAGENTS",
            10: "GET_COLUMNS",
            11: "SET_REAGENTS",
            12: "SET_COLUMNS",
            13: "ABORT_PROGRAM",
            14: "GET_DEVICE_STATE",
            15: "TARE_WEIGHT_SENSOR"
        }
        return commands.get(command_id, f"UNKNOWN_CMD_{command_id}")
    
    def send_command(self, command_id, payload=None, timeout=10):
        start_time = time.time()
        while True:
            try:
                return self._try_send_command(command_id, payload, 0.5)
            except ConnectionError:
                if time.time() - start_time > timeout:
                    raise ConnectionError("timeout")
                continue
    
    def ping(self) -> bool:
        try:
            resp = self.send_command(0)
            if resp[0] != 0:
                return False
            return True
        except ConnectionError:
            return False
    
    def _init_program_write(self):
        self.send_command(4)
    
    def _write_program_block(self, block):
        self.send_command(5, block)
    
    def _get_program_length(self):
        resp = self.send_command(8)
        return int.from_bytes(resp[:2], 'big')

    def get_max_program_length(self):
        resp = self.send_command(8)
        return int.from_bytes(resp[2:], 'big')
    
    def _get_program_block(self, block_index, n_steps):
        resp = self.send_command(7, block_index.to_bytes(2, 'big') + n_steps.to_bytes(2, 'big'))
        return resp
    
    def valve_command(self, reagent_valve_id, column_valve_id):
        """Set valves using the new protocol: reagent_valve_id and column_valve_id (0-5 for valves 1-6)"""
        # Send 0-based indices directly to firmware
        self.send_command(1, bytes([reagent_valve_id, column_valve_id]))
    
    def pump_command(self, command, acceleration):
        self.send_command(2, struct.pack('ff', command, acceleration))
    
    def write_program(self, program: Program):
        """Write program to device"""
        self._log_debug(f"[PROG] Starting program upload with {len(program.steps)} steps")
        self._init_program_write()
        self.set_reagents(program.reagents)
        self.set_columns(program.columns)
        max_len = self.get_max_program_length()
        raw_data = ProgramConverter().convert_to_raw_bytes(program)
        
        # Log raw program data
        self._log_program_steps(raw_data, "[PROG]")
        
        if len(raw_data) > max_len:
            self._log_debug(f"[PROG] Program too long: {len(raw_data)} > {max_len}")
            raise ConnectionError("program too long")
        # ProgramConverter().print_program_stats(program, raw_data, max_len)
        self._log_debug(f"[PROG] Uploading {len(raw_data)} blocks...")
        for i, block in enumerate(raw_data):
            self._write_program_block(block)
            self._log_debug(f"[PROG] Uploaded block {i+1}/{len(raw_data)}")
        uploaded_len = self._get_program_length()
        if uploaded_len != len(program.steps):
            self._log_debug(f"[PROG] Upload verification failed: {uploaded_len} != {len(program.steps)}")
            raise ConnectionError("program upload failed")
        self._log_debug(f"[PROG] Program upload completed successfully")

    def execute_program(self):
        self._log_debug("[PROG] Executing program")
        self.send_command(6)

    def abort_program(self):
        self._log_debug("[PROG] Aborting program")
        self.send_command(13)

    def read_program(self) -> Program:
        """Read program from device"""
        self._log_debug(f"[PROG] Reading program from device")
        reagents = self.get_reagents()
        self._log_debug(f"[PROG] Reagents: {reagents}")
        columns = self.get_columns()
        self._log_debug(f"[PROG] Columns: {columns}")
        raw_data = []
        length = self._get_program_length()
        self._log_debug(f"[PROG] Program length: {length} steps")
        full_blocks = length // ProgramConverter().max_steps_per_block
        last_block_steps = length % ProgramConverter().max_steps_per_block
        self._log_debug(f"[PROG] Full blocks: {full_blocks}, last block steps: {last_block_steps}")
        
        for i in range(full_blocks):
            self._log_debug(f"[PROG] Reading block {i+1}/{full_blocks}")
            block = self._get_program_block(i*ProgramConverter().max_steps_per_block, ProgramConverter().max_steps_per_block)
            raw_data.append(block)
            self._log_debug(f"[PROG] Block {i+1} size: {len(block)} bytes")
            
        if last_block_steps > 0:
            self._log_debug(f"[PROG] Reading final block with {last_block_steps} steps")
            block = self._get_program_block(full_blocks*ProgramConverter().max_steps_per_block, last_block_steps)
            raw_data.append(block)
            self._log_debug(f"[PROG] Final block size: {len(block)} bytes")
        
        # Log raw program data read from device
        self._log_program_steps(raw_data, "[PROG] Read")
        
        program = ProgramConverter().convert_from_raw_bytes(reagents, columns, raw_data)
        self._log_debug(f"[PROG] Converted program has {len(program.steps)} steps")
        return program
    
    def get_reagents(self) -> List[str]:
        resp = self.send_command(9)
        m = ProgramConverter().max_reagent_name_len
        reagents = [resp[i:i+m].strip(b'\0').decode('utf-8') for i in range(0, len(resp), m)]
        # Convert to 1-based indexing for UI
        return {i+1: reagents[i] for i in range(ProgramConverter().max_reagents)}
    
    def get_columns(self) -> List[str]:
        resp = self.send_command(10)
        m = ProgramConverter().max_column_name_len
        columns = [resp[i:i+m].strip(b'\0').decode('utf-8') for i in range(0, len(resp), m)]
        # Convert to 1-based indexing for UI
        return {i+1: columns[i] for i in range(ProgramConverter().max_columns)}

    def set_reagents(self, reagents):
        sorted_pairs = sorted(reagents.items(), key=lambda x: x[0])
        n = ProgramConverter().max_reagents
        m = ProgramConverter().max_reagent_name_len
        reagents_bytes = bytearray(b'\0' * n * m)
        for i, reagent in sorted_pairs:
            # Convert from 1-based UI index to 0-based firmware index
            firmware_index = i - 1
            reagents_bytes[firmware_index*m:(firmware_index*m+len(reagent))] = reagent.encode('utf-8')
        self.send_command(11, reagents_bytes)
    
    def set_columns(self, columns):
        sorted_pairs = sorted(columns.items(), key=lambda x: x[0])
        n = ProgramConverter().max_columns
        m = ProgramConverter().max_column_name_len
        columns_bytes = bytearray(b'\0' * n * m)
        for i, column in sorted_pairs:
            # Convert from 1-based UI index to 0-based firmware index
            firmware_index = i - 1
            columns_bytes[firmware_index*m:(firmware_index*m+len(column))] = column.encode('utf-8')
        self.send_command(12, columns_bytes)
    
    def get_device_state(self):
        """Get current device state"""
        resp = self.send_command(14)
        state = DeviceState()
        
        # Parse the response according to the new DeviceState structure
        # Structure order: pump_speed (4), pump_volume (4), program_step_idx (2), 
        # device_state (1), reagent_valve_position (1), reagent_valve_state (1),
        # column_valve_position (1), column_valve_state (1), running (1), 
        # program_step_progress (1), padding (3)
        
        if len(resp) >= 20:  # Total size should be 20 bytes (17 data + 3 padding)
            state.pump_speed = struct.unpack('<f', resp[0:4])[0]
            state.pump_volume = struct.unpack('<f', resp[4:8])[0]
            state.program_step_idx = struct.unpack('<H', resp[8:10])[0]  # uint16_t
            state.device_state = resp[10]
            state.reagent_valve_position = resp[11]
            state.reagent_valve_state = resp[12]
            state.column_valve_position = resp[13]
            state.column_valve_state = resp[14]
            state.running = resp[15]
            state.program_step_progress = resp[16] / 2.55
            # resp[17:20] contains padding bytes, ignore them
        
        return state
    
    def tare_weight_sensor(self, channel):
        """Tare a specific weight sensor channel (0-7)"""
        if channel < 0 or channel > 7:
            raise ValueError("Channel must be between 0 and 7")
        self.send_command(15, bytes([channel]))
