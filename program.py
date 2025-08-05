import yaml
import struct
from dataclasses import dataclass
from typing import Dict, List, Union, Optional
from enum import Enum

class CommandType(Enum):
    FLUSH = "flush"
    SLEEP = "sleep"

@dataclass
class ProgramStep:
    """Represents a single program step compatible with the device"""
    reagent_valve_id: int
    column_valve_id: int
    flow_rate: float
    volume: float # mL, use float infinity for unlimited volume
    duration: float # seconds, use float infinity for unlimited time

@dataclass
class FlushStep:
    """Represents a flush operation from YAML"""
    reagent: str
    column: str
    flow_rate: float
    volume: Optional[str] = None  # e.g., "20ml"
    duration: Optional[str] = None    # e.g., "20m"

@dataclass
class SleepStep:
    """Represents a sleep operation from YAML"""
    duration: str  # e.g., "20m"

@dataclass
class Program:
    """Represents a complete chromatography program"""
    reagents: Dict[int, str]
    columns: Dict[int, str]
    steps: List[Union[FlushStep, SleepStep]]

class ProgramConverter:
    """Converts YAML programs to device-compatible format"""
    max_steps_per_block = 5
    max_reagents = 6
    max_columns = 6
    max_reagent_name_len = 40
    max_column_name_len = 40
    
    def __init__(self):
        self.reagent_map = {}
        self.column_map = {}
    
    def load_from_yaml(self, yaml_file: str) -> Program:
        """Load program from YAML file"""
        with open(yaml_file, 'r') as file:
            data = yaml.safe_load(file)
        
        # Load reagent and column mappings
        reagents = {int(k): v[:self.max_reagent_name_len] for k, v in data.get('reagents', {}).items()}
        columns = {int(k): v[:self.max_column_name_len] for k, v in data.get('columns', {}).items()}
        
        # Parse program steps
        steps = []
        for step_data in data.get('program', []):
            if 'flush' in step_data:
                flush_data = step_data['flush']
                step = FlushStep(
                    reagent=flush_data['reagent'],
                    column=flush_data['column'],
                    flow_rate=flush_data['flow_rate'],
                    volume=flush_data.get('volume'),
                    duration=flush_data.get('duration')
                )
                steps.append(step)
            elif 'sleep' in step_data:
                sleep_data = step_data['sleep']
                step = SleepStep(duration=sleep_data['duration'])
                steps.append(step)

        steps = ProgramConverter.convert_to_device_format(steps, reagents, columns)
        
        return Program(reagents=reagents, columns=columns, steps=steps)
    
    def _parse_flow_rate(flow_rate_str: str) -> float:
        """Convert flow rate string to float (mL/min)"""
        if flow_rate_str.endswith('ml/min'):
            return float(flow_rate_str[:-6])
        return float(flow_rate_str)
    
    def _parse_volume(volume_str: Optional[str]) -> float:
        """Convert volume string to 1/10 ml units"""
        if volume_str is None:
            return float('inf')
        if volume_str.endswith('ml'):
            return float(volume_str[:-2])
        return float(volume_str)
    
    def _parse_time(time_str: Optional[str]) -> float:
        """Convert time string to seconds"""
        if time_str is None:
            return float('inf')
        
        if isinstance(time_str, (int, float)):
            return float('inf')
        
        time_str = time_str.lower().strip()
        total_seconds = 0
        
        # Handle decimal hours like "1.2h"
        if 'h' in time_str and '.' in time_str:
            # Extract hours part
            hours_part = time_str.split('h')[0]
            try:
                hours = float(hours_part)
                total_seconds += int(hours * 3600)
                time_str = time_str.split('h')[1]  # Remove hours part
            except ValueError:
                pass
        
        # Handle combined formats like "2h30m" or "1h30m5s"
        # Extract hours
        if 'h' in time_str:
            parts = time_str.split('h')
            if parts[0]:
                try:
                    hours = int(parts[0])
                    total_seconds += hours * 3600
                except ValueError:
                    pass
            time_str = parts[1] if len(parts) > 1 else ""
        
        # Extract minutes
        if 'm' in time_str:
            parts = time_str.split('m')
            if parts[0]:
                try:
                    minutes = int(parts[0])
                    total_seconds += minutes * 60
                except ValueError:
                    pass
            time_str = parts[1] if len(parts) > 1 else ""
        
        # Extract seconds
        if 's' in time_str:
            parts = time_str.split('s')
            if parts[0]:
                try:
                    seconds = int(parts[0])
                    total_seconds += seconds
                except ValueError:
                    pass
        
        # If no units specified, try to parse as seconds
        if total_seconds == 0 and time_str:
            try:
                total_seconds = int(float(time_str))
            except ValueError:
                pass
        
        return float(total_seconds) if total_seconds > 0 else float('inf')
    
    def _get_reagent_valve(reagent_name: str, reagents: Dict[int, str]) -> int:
        """Get valve number for reagent"""
        for valve_id, name in reagents.items():
            if name == reagent_name:
                return valve_id - 1  # Convert 1-based to 0-based for firmware
        raise ValueError(f"Reagent '{reagent_name}' not found")
    
    def _get_column_valve(column_name: str, columns: Dict[int, str]) -> int:
        """Get valve number for column"""
        for valve_id, name in columns.items():
            if name == column_name:
                return valve_id - 1  # Convert 1-based to 0-based for firmware
        raise ValueError(f"Column '{column_name}' not found")
    
    def convert_to_device_format(steps, reagents, columns) -> List[ProgramStep]:
        """Convert YAML program to device-compatible ProgramStep list"""
        device_steps = []
        
        for step in steps:
            if isinstance(step, FlushStep):
                # Get valve numbers
                reagent_valve = ProgramConverter._get_reagent_valve(step.reagent, reagents)
                column_valve = ProgramConverter._get_column_valve(step.column, columns)
                
                # Convert pump percentage to device format
                pump_cmd = ProgramConverter._parse_flow_rate(step.flow_rate)
                
                # Parse duration and volume
                duration = ProgramConverter._parse_time(step.duration) if step.duration else float('inf')
                volume = ProgramConverter._parse_volume(step.volume) if step.volume else float('inf')
                
                device_step = ProgramStep(
                    reagent_valve_id=reagent_valve,
                    column_valve_id=column_valve,
                    flow_rate=pump_cmd,
                    duration=duration,
                    volume=volume
                )
                device_steps.append(device_step)
                
            elif isinstance(step, SleepStep):
                # Sleep step - all valves closed, pump off
                duration = ProgramConverter._parse_time(step.duration)
                
                device_step = ProgramStep(
                    reagent_valve_id=0xff,  # No valve change
                    column_valve_id=0xff,   # No valve change
                    flow_rate=0,    # Pump off
                    duration=duration,
                    volume=float('inf')  # Not applicable for sleep
                )
                device_steps.append(device_step)
        
        return device_steps
    
    def convert_to_raw_bytes(self, program: Program) -> List[bytes]:
        """Convert program to raw bytes for device transmission. The data is split into blocks."""
        device_steps = program.steps
        # Pack all steps into bytes
        raw_data_blocks = []
        raw_data = b''
        block_idx = 0
        for step in device_steps:
            # Pack as little-endian: reagent_valve_id(1), column_valve_id(1), flow_rate(4), duration(4), volume(4)
            step_bytes = struct.pack('<BBBBfff',
                                   step.reagent_valve_id,
                                   step.column_valve_id,
                                   0,
                                   0,
                                   step.flow_rate,
                                   step.volume,
                                   step.duration)
            raw_data += step_bytes
            block_idx += 1
            if block_idx == self.max_steps_per_block:
                raw_data_blocks.append(raw_data)
                raw_data = b''
                block_idx = 0
        if raw_data:
            raw_data_blocks.append(raw_data)
        return raw_data_blocks
    
    def convert_from_raw_bytes(self, reagents: Dict[int, str], columns: Dict[int, str], raw_data: List[bytes]) -> Program:
        """Convert raw bytes to program"""
        steps = []
        for block in raw_data:
            for i in range(0, len(block), 16):  # Each step is 16 bytes
                step_bytes = block[i:i+16]
                if len(step_bytes) == 16:
                    step = struct.unpack('<BBBBfff', step_bytes)
                    steps.append(ProgramStep(
                        reagent_valve_id=step[0],
                        column_valve_id=step[1],
                        flow_rate=step[4],
                        volume=step[5],
                        duration=step[6]
                    ))
        return Program(reagents=reagents, columns=columns, steps=steps)
    
    def print_program_details(self, program: Program):
        """Print human-readable program information"""
        print(f"Program loaded:")
        print(f"  Reagents: {program.reagents}")
        print(f"  Columns: {program.columns}")
        print(f"  Steps: {len(program.steps)}")
        
        device_steps = program.steps
        print(f"\nDevice steps:")
        print(device_steps)
        for i, step in enumerate(device_steps):
            print(f"  Step {i}:")
            print(f"    Reagent valve: {step.reagent_valve_id}")
            print(f"    Column valve:  {step.column_valve_id}")
            print(f"    Flow rate:     {step.flow_rate} mL/min")
            print(f"    Duration:      {step.duration}s")
            print(f"    Volume:        {step.volume} mL")
    
    def print_program_stats(self, program: Program, raw_data: List[bytes], max_len: int):
        """Print program statistics"""
        print(f"program length: {len(program.steps)} steps ({max_len} max)")
        print(f"divided into {len(raw_data)} blocks")
        print(f"raw size {len(program.steps) * 16} bytes")
        


def main():
    """Example usage"""
    converter = ProgramConverter()
    
    # Load program from YAML
    try:
        program = converter.load_from_yaml('example_program.yaml')
        converter.print_program_details(program)
        
        # Convert to raw bytes
        raw_data = converter.convert_to_raw_bytes(program)
        converter.print_program_stats(program, raw_data, converter.max_steps_per_block)
        print(f"\nRaw data size: {sum(len(block) for block in raw_data)} bytes")
        print(f"Raw data (hex): {b''.join(raw_data).hex()}")
        
    except FileNotFoundError:
        print("Error: example_program.yaml not found")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
