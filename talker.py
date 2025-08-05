import time
from device_connection import DeviceConnection
from program import ProgramConverter


connection = DeviceConnection('/dev/ttyACM0')

connection.open()
print("connection check:", connection.check())

program = ProgramConverter().load_from_yaml("example_program.yaml")
connection.write_program(program)

connection.execute_program()

print("executing program...")
try:
    while True:
        state = connection.get_device_state()
        if state.running:
            print(f"running step {state.program_step_idx+1} / {len(program.steps)}: {round(state.program_step_progress)}%"+20*" ", end="\r")
        else:
            print(f"program finished"+20*" ")
            break
        time.sleep(0.1)
except KeyboardInterrupt:
    pass
finally:
    connection.close()