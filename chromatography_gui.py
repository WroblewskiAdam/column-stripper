#!/usr/bin/env python3
"""
Chromatography Device Control GUI
A desktop application for controlling chromatography hardware devices.
"""

import sys
import os
import time
import threading
from typing import Optional, Dict, List
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QTextEdit, QProgressBar, QFileDialog,
    QGroupBox, QGridLayout, QComboBox, QSpinBox, QCheckBox,
    QTabWidget, QSplitter, QFrame, QMessageBox, QStatusBar,
    QTableWidget, QTableWidgetItem, QHeaderView, QStackedWidget,
    QScrollArea, QTextBrowser
)
from PySide6.QtCore import QTimer, Qt, QThread, Signal
from PySide6.QtGui import QFont, QPalette, QColor

# Import our device communication modules
from device_connection import DeviceConnection, DeviceState
from program import Program, ProgramConverter


class ConnectionWorker(QThread):
    """Worker thread for device connection operations"""
    connected = Signal(str)  # Emits port name when connected
    connection_failed = Signal()
    no_device_found = Signal()
    
    def __init__(self):
        super().__init__()
        self.port_to_try = None
    
    def try_connect(self, port=None):
        """Try to connect to a specific port or scan all ports"""
        self.port_to_try = port
        self.start()
    
    def run(self):
        try:
            import serial.tools.list_ports
            ports = [port.device for port in serial.tools.list_ports.comports()]
            
            if self.port_to_try:
                # Try specific port
                try:
                    device = DeviceConnection(self.port_to_try)
                    device.open()
                    device.close()  # Just test the connection
                    self.connected.emit(self.port_to_try)
                    return
                except:
                    self.connection_failed.emit()
                    return
            
            # Try all ports
            for port in ports:
                try:
                    device = DeviceConnection(port)
                    device.open()
                    device.close()  # Just test the connection
                    self.connected.emit(port)
                    return
                except:
                    continue
                    
            self.no_device_found.emit()
        except:
            self.connection_failed.emit()


class ChromatographyGUI(QMainWindow):
    """Main GUI application for chromatography device control"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Chromatography Control")
        self.setGeometry(100, 100, 1600, 800)
        self.device = None
        self.program = None
        self.program_uploaded = False
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self.update_status)
        self.connection_timer = QTimer()
        self.connection_timer.timeout.connect(self.check_connection)
        self.debug_timer = QTimer()
        self.debug_timer.timeout.connect(self.check_debug_output)
        
        # Create connection worker
        self.connection_worker = ConnectionWorker()
        self.connection_worker.connected.connect(self.on_device_connected)
        self.connection_worker.connection_failed.connect(self.on_connection_failed)
        self.connection_worker.no_device_found.connect(self.on_no_device_found)
        
        self.init_ui()
        
        # Auto-connect device on startup
        self.auto_connect_device()

    def init_ui(self):
        central = QWidget()
        layout = QHBoxLayout()
        layout.setSpacing(10)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Create main splitter for left panels
        left_splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Left panel - Program widget
        self.create_program_widget()
        left_splitter.addWidget(self.program_widget)
        
        # Middle panel - Execution widget
        self.create_execution_widget()
        left_splitter.addWidget(self.execution_widget)
        
        # Set initial splitter sizes (50% program, 50% execution)
        left_splitter.setSizes([600, 600])
        
        # Create main horizontal splitter
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_splitter.addWidget(left_splitter)
        
        # Add serial monitor on the right side
        self.create_serial_monitor_widget()
        main_splitter.addWidget(self.serial_monitor_widget)
        
        # Set initial splitter sizes (60% left panels, 40% serial monitor)
        main_splitter.setSizes([960, 640])
        
        layout.addWidget(main_splitter)
        central.setLayout(layout)
        self.setCentralWidget(central)

    def auto_connect_device(self):
        """Automatically try to connect to all available ports"""
        self.connection_worker.try_connect()

    def on_device_connected(self, port):
        """Called when device connection is successful"""
        try:
            self.device = DeviceConnection(port, debug_callback=self.log_debug_message)
            self.device.open()
            self.connection_label.setText(f"Connected to {port}")
            self.program_uploaded = False
            self.status_timer.start(300)
            self.connection_timer.start(1000)  # Check connection every 1 second
            self.debug_timer.start(50)  # Check debug output every 50ms
            
            # Try to read program from device on startup
            self.read_program_from_device()
            
            # Enable download button now that device is connected
            self.download_btn.setEnabled(True)
            
            # Show device state display when device is connected
            self.state_group.show()
            
        except Exception as e:
            self.connection_label.setText(f"Connection failed: {e}")

    def log_debug_message(self, message: str):
        """Log debug message to the serial monitor"""
        if hasattr(self, 'serial_monitor'):
            self.serial_monitor.append(f"{time.strftime('%H:%M:%S')} {message}")

    def check_debug_output(self):
        """Check for debug output from the device"""
        if self.device:
            self.device.check_debug_output()

    def read_program_from_device(self):
        """Read program from device if available"""
        try:
            self.log_debug_message(f"[GUI] Attempting to read program from device...")
            program_length = self.device._get_program_length()
            self.log_debug_message(f"[GUI] Program length from device: {program_length}")
            
            if program_length > 0:
                # Device has a program, read it
                self.log_debug_message(f"[GUI] Reading program with {program_length} steps...")
                self.program = self.device.read_program()
                self.log_debug_message(f"[GUI] Program read successfully, {len(self.program.steps)} steps")
                self.update_program_display()
                self.program_status_label.setText("Program loaded from device")
                self.run_btn.setEnabled(True)
            else:
                # No program on device
                self.log_debug_message(f"[GUI] No program found on device")
                self.clear_program_display()
                self.program_status_label.setText("Ready")
                self.run_btn.setEnabled(False)
        except Exception as e:
            self.log_debug_message(f"[GUI] Error reading program from device: {e}")
            self.clear_program_display()
            self.program_status_label.setText("Ready")

    def update_program_display(self):
        """Update the program display with current program"""
        if not self.program:
            self.clear_program_display()
            return
            
        # Update program info
        self.program_info.setText(f"Program: {len(self.program.steps)} steps")
        
        # Update reagents display
        reagents_text = ""
        for idx, name in self.program.reagents.items():
            if name.strip():  # Only show non-empty names
                reagents_text += f"{idx}: {name}\n"
        self.reagents_display.setText(reagents_text if reagents_text else "(No reagents)")
        
        # Update columns display
        columns_text = ""
        for idx, name in self.program.columns.items():
            if name.strip():  # Only show non-empty names
                columns_text += f"{idx}: {name}\n"
        self.columns_display.setText(columns_text if columns_text else "(No columns)")
        
        # Update steps display
        self.update_steps_display()

    def clear_program_display(self):
        """Clear all program displays"""
        self.program_info.setText("No program loaded")
        self.reagents_display.setText("(No program)")
        self.columns_display.setText("(No program)")
        self.clear_steps_display()

    def update_steps_display(self):
        """Update the steps display"""
        if not self.program or not self.program.steps:
            self.clear_steps_display()
            return
            
        # Clear existing steps
        self.clear_steps_display()
        
        # Add each step
        for i, step in enumerate(self.program.steps):
            step_widget = self.create_step_widget(i, step)
            self.steps_layout.addWidget(step_widget)
        
        # Add stretch at the end
        self.steps_layout.addStretch()

    def clear_steps_display(self):
        """Clear the steps display"""
        # Remove all widgets except the stretch
        while self.steps_layout.count() > 1:
            child = self.steps_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def create_step_widget(self, step_index, step):
        """Create a widget for displaying a single step"""
        step_frame = QFrame()
        step_frame.setFrameStyle(QFrame.Shape.StyledPanel)
        step_frame.setStyleSheet("background-color: #404040;")
        
        layout = QHBoxLayout()
        layout.setSpacing(5)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # Step number on the left
        step_label = QLabel(f"{step_index + 1}")
        step_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(step_label)
        
        # Step details on the right
        details = []
        
        # Check if this is a sleep step (no valve or pump commands)
        if step.reagent_valve_id == 0xff and step.column_valve_id == 0xff and step.flow_rate == 0:
            details.append("Sleep")
        else:
            # Valve information - show reagent -> column
            if step.reagent_valve_id != 0xff and step.column_valve_id != 0xff:
                reagent_name, column_name = self.get_valve_names(step.reagent_valve_id, step.column_valve_id)
                if reagent_name and column_name:
                    details.append(f"{reagent_name} → {column_name}")
            
            # Pump information
            if step.flow_rate > 0:
                details.append(f"| pump: {step.flow_rate:.1f} ml/min")
        
        # Duration
        if step.duration != float('inf'):
            details.append(f"| duration: {step.duration:.0f}s")
        
        # Volume
        if step.volume != float('inf'):
            details.append(f"| volume: {step.volume:.1f}ml")
        
        # Add details to layout
        for detail in details:
            detail_label = QLabel(detail)
            layout.addWidget(detail_label)
        
        # Add stretch to push details to the right
        layout.addStretch()
        
        step_frame.setLayout(layout)
        return step_frame

    def get_valve_names(self, reagent_valve_id, column_valve_id):
        """Get reagent and column names from valve IDs"""
        if not self.program:
            return None, None
            
        # Get reagent name - convert 0-based to 1-based for lookup
        reagent_name = self.program.reagents.get(reagent_valve_id + 1, None)
        
        # Get column name - convert 0-based to 1-based for lookup
        column_name = self.program.columns.get(column_valve_id + 1, None)
        
        return reagent_name, column_name

    def on_connection_failed(self):
        """Called when connection attempt fails"""
        self.connection_label.setText("Connection failed")
        self.download_btn.setEnabled(False)  # Disable download button
        self.state_group.hide()  # Hide device state when disconnected
        # Start connection timer to retry periodically
        if not self.connection_timer.isActive():
            self.connection_timer.start(500)  # Retry every 0.5 seconds

    def on_no_device_found(self):
        """Called when no device is found"""
        self.connection_label.setText("No device detected")
        self.download_btn.setEnabled(False)  # Disable download button
        self.state_group.hide()  # Hide device state when no device found
        # Start connection timer to retry periodically
        if not self.connection_timer.isActive():
            self.connection_timer.start(500)  # Retry every 0.5 seconds

    def check_connection(self):
        """Periodically check device connection and attempt reconnection if lost"""
        if self.device:
            try:
                if not self.device.check():
                    # Connection lost, try to reconnect
                    self.connection_label.setText("Connection lost, reconnecting...")
                    self.device.close()
                    self.device = None
                    self.download_btn.setEnabled(False)  # Disable download button
                    self.state_group.hide()  # Hide device state when disconnected
                    self.status_timer.stop()
                    self.debug_timer.stop()
                    self.auto_connect_device()
            except Exception:
                # Connection error, try to reconnect
                self.connection_label.setText("Connection error, reconnecting...")
                self.device = None
                self.download_btn.setEnabled(False)  # Disable download button
                self.state_group.hide()  # Hide device state when disconnected
                self.status_timer.stop()
                self.debug_timer.stop()
                self.auto_connect_device()
        else:
            # No device connected, try to find one
            self.auto_connect_device()

    def create_program_widget(self):
        """Create the left panel for program management"""
        self.program_widget = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(5)
        
        # Program loading section
        load_group = QGroupBox("Program")
        load_layout = QVBoxLayout()
        load_layout.setSpacing(5)
        
        # Button layout for Load and Download buttons
        button_layout = QHBoxLayout()
        
        self.load_btn = QPushButton("Load")
        self.load_btn.clicked.connect(self.load_program)
        button_layout.addWidget(self.load_btn)
        
        self.download_btn = QPushButton("Download from Device")
        self.download_btn.clicked.connect(self.download_program_from_device)
        self.download_btn.setEnabled(False)  # Disabled until device is connected
        button_layout.addWidget(self.download_btn)
        
        load_layout.addLayout(button_layout)
        
        self.program_info = QLabel("No program loaded")
        load_layout.addWidget(self.program_info)
        
        load_group.setLayout(load_layout)
        layout.addWidget(load_group)
        
        # Combined configuration and steps section
        program_group = QGroupBox("Program Details")
        program_layout = QVBoxLayout()
        program_layout.setSpacing(10)
        
        # Reagents and Columns
        config_layout = QHBoxLayout()
        config_layout.setSpacing(10)
        
        # Reagents
        reagents_layout = QVBoxLayout()
        reagents_layout.addWidget(QLabel("Reagents:"))
        self.reagents_display = QLabel("(No program)")
        self.reagents_display.setWordWrap(True)
        reagents_layout.addWidget(self.reagents_display)
        config_layout.addLayout(reagents_layout)
        
        # Columns
        columns_layout = QVBoxLayout()
        columns_layout.addWidget(QLabel("Columns:"))
        self.columns_display = QLabel("(No program)")
        self.columns_display.setWordWrap(True)
        columns_layout.addWidget(self.columns_display)
        config_layout.addLayout(columns_layout)
        
        program_layout.addLayout(config_layout)
        
        # Program steps
        program_layout.addWidget(QLabel("Steps:"))
        
        # Create scrollable area for steps
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        # scroll_area.setMaximumHeight(250)
        
        # Container widget for steps
        steps_container = QWidget()
        self.steps_layout = QVBoxLayout()
        self.steps_layout.setSpacing(2)
        self.steps_layout.addStretch()  # Add stretch at the end
        steps_container.setLayout(self.steps_layout)
        
        scroll_area.setWidget(steps_container)
        program_layout.addWidget(scroll_area)
        
        program_group.setLayout(program_layout)
        layout.addWidget(program_group)
        
        # layout.addStretch()
        self.program_widget.setLayout(layout)

    def create_execution_widget(self):
        """Create the right panel for execution control"""
        self.execution_widget = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(10)
        
        # Connection status
        status_group = QGroupBox("Connection")
        status_layout = QVBoxLayout()
        
        self.connection_label = QLabel("Scanning for devices...")
        self.connection_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status_layout.addWidget(self.connection_label)
        
        status_group.setLayout(status_layout)
        layout.addWidget(status_group)
        
        # Control buttons
        control_group = QGroupBox("Control")
        control_layout = QVBoxLayout()
        
        # Program status
        self.program_status_label = QLabel("Ready")
        self.program_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        control_layout.addWidget(self.program_status_label)
        
        self.run_btn = QPushButton("Run Program")
        self.run_btn.clicked.connect(self.run_program)
        self.run_btn.setEnabled(False)
        control_layout.addWidget(self.run_btn)
        
        self.stop_btn = QPushButton("Stop Program")
        self.stop_btn.clicked.connect(self.stop_program)
        self.stop_btn.setEnabled(False)
        control_layout.addWidget(self.stop_btn)
        
        control_group.setLayout(control_layout)
        layout.addWidget(control_group)
        
        # Progress (hidden by default)
        self.progress_group = QGroupBox("Progress")
        progress_layout = QVBoxLayout()
        
        overall_layout = QHBoxLayout()
        overall_layout.addWidget(QLabel("Overall:"))
        self.overall_progress = QProgressBar()
        overall_layout.addWidget(self.overall_progress)
        progress_layout.addLayout(overall_layout)
        
        step_layout = QHBoxLayout()
        step_layout.addWidget(QLabel("Step:"))
        self.progress = QProgressBar()
        step_layout.addWidget(self.progress)
        progress_layout.addLayout(step_layout)
        
        self.step_label = QLabel("Step 0")
        self.step_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        progress_layout.addWidget(self.step_label)
        
        self.progress_group.setLayout(progress_layout)
        self.progress_group.hide()  # Hidden by default
        layout.addWidget(self.progress_group)
        
        # Device state (hidden by default)
        self.state_group = QGroupBox("Device State")
        state_layout = QGridLayout()
        
        # Device state
        state_layout.addWidget(QLabel("State:"), 0, 0)
        self.device_state_display = QLabel("Idle")
        state_layout.addWidget(self.device_state_display, 0, 1)
        
        # Reagent valve
        state_layout.addWidget(QLabel("Reagent Valve:"), 1, 0)
        self.reagent_valve_display = QLabel("Pos: 0, State: Idle")
        state_layout.addWidget(self.reagent_valve_display, 1, 1)
        
        # Column valve
        state_layout.addWidget(QLabel("Column Valve:"), 2, 0)
        self.column_valve_display = QLabel("Pos: 0, State: Idle")
        state_layout.addWidget(self.column_valve_display, 2, 1)
        
        # Pump
        state_layout.addWidget(QLabel("Pump:"), 3, 0)
        self.pump_display = QLabel("Speed: 0.0 ml/min, Volume: 0.0 ml")
        state_layout.addWidget(self.pump_display, 3, 1)
        
        self.state_group.setLayout(state_layout)
        self.state_group.hide()  # Hidden by default
        layout.addWidget(self.state_group)
        
        layout.addStretch()
        self.execution_widget.setLayout(layout)

    def create_serial_monitor_widget(self):
        """Create the serial monitor widget"""
        self.serial_monitor_widget = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(5)
        
        # Serial monitor header
        monitor_group = QGroupBox("Device Monitor")
        monitor_layout = QVBoxLayout()
        
        # Add clear button
        button_layout = QHBoxLayout()
        self.clear_monitor_btn = QPushButton("Clear")
        self.clear_monitor_btn.clicked.connect(self.clear_serial_monitor)
        button_layout.addWidget(self.clear_monitor_btn)
        button_layout.addStretch()
        monitor_layout.addLayout(button_layout)
        
        # Serial monitor text area
        self.serial_monitor = QTextBrowser()
        self.serial_monitor.setStyleSheet("""
            QTextBrowser {
                background-color: #1e1e1e;
                color: #00ff00;
                font-family: 'Courier New', monospace;
                font-size: 10px;
                border: 1px solid #404040;
            }
        """)
        monitor_layout.addWidget(self.serial_monitor)
        
        monitor_group.setLayout(monitor_layout)
        layout.addWidget(monitor_group)
        
        self.serial_monitor_widget.setLayout(layout)

    def clear_serial_monitor(self):
        """Clear the serial monitor"""
        if hasattr(self, 'serial_monitor'):
            self.serial_monitor.clear()
        if self.device:
            self.device.clear_debug_buffer()

    def load_program(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Load Program", "", "YAML Files (*.yaml *.yml)")
        if file_path:
            try:
                converter = ProgramConverter()
                self.program = converter.load_from_yaml(file_path)
                self.program_uploaded = False  # Reset upload flag for new program
                self.update_program_display()
                self.run_btn.setEnabled(self.device is not None)
                self.program_status_label.setText("Program loaded")
            except Exception as e:
                self.program_info.setText(f"Failed: {e}")
                self.program = None
                self.run_btn.setEnabled(False)
                self.program_status_label.setText("Load failed")

    def download_program_from_device(self):
        """Manually download program from device"""
        if not self.device:
            self.program_status_label.setText("No device connected")
            return
            
        try:
            self.program_status_label.setText("Downloading...")
            self.log_debug_message(f"[GUI] Manual download requested")
            
            # Read program from device
            self.read_program_from_device()
            
            if self.program:
                self.program_status_label.setText("Download completed")
                self.run_btn.setEnabled(True)
            else:
                self.program_status_label.setText("No program on device")
                
        except Exception as e:
            self.log_debug_message(f"[GUI] Download failed: {e}")
            self.program_status_label.setText(f"Download failed: {e}")
            self.program = None
            self.run_btn.setEnabled(False)

    def run_program(self):
        if not self.device:
            self.program_status_label.setText("No device connected")
            return
        
        if not self.program:
            self.program_status_label.setText("No program loaded")
            return
            
        try:
            if not self.program_uploaded:
                self.program_status_label.setText("Uploading...")
                self.device.write_program(self.program)
                self.program_uploaded = True
            
            self.device.execute_program()
            self.program_status_label.setText("Running")
            self.run_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
            self.progress_group.show()
            self.state_group.show()
        except Exception as e:
            self.program_status_label.setText(f"Run failed: {e}")
            self.program_uploaded = False

    def stop_program(self):
        if self.device:
            try:
                self.device.abort_program()
                self.program_status_label.setText("Stopped")
                self.run_btn.setEnabled(True)
                self.stop_btn.setEnabled(False)
                self.progress_group.hide()
                self.state_group.hide()
                self.program_uploaded = False
            except Exception as e:
                self.program_status_label.setText(f"Stop failed: {e}")

    def update_status(self):
        if not self.device:
            return
            
        try:
            state = self.device.get_device_state()
            
            # Always show device state when device is connected
            self.state_group.show()
            
            # Update progress information only if program is running
            if self.program_uploaded:
                step_progress = int(state.program_step_progress)
                self.progress.setValue(step_progress)
                self.step_label.setText(f"Step {state.program_step_idx+1}")
                
                if self.program and len(self.program.steps) > 0:
                    completed_steps = state.program_step_idx
                    current_step_contribution = step_progress / 100.0
                    total_progress = (completed_steps + current_step_contribution) / len(self.program.steps)
                    overall_percentage = min(100, int(total_progress * 100))
                    self.overall_progress.setValue(overall_percentage)
                else:
                    self.overall_progress.setValue(0)
            else:
                # Clear progress when no program is running
                self.progress.setValue(0)
                self.overall_progress.setValue(0)
                self.step_label.setText("No program running")
            
            # Update device state display
            device_state_names = {
                0: "Idle",
                1: "Pumping", 
                2: "Stopping",
                3: "Setting Valves"
            }
            device_state_name = device_state_names.get(state.device_state, f"Unknown ({state.device_state})")
            if state.device_state == 1 and abs(state.pump_speed) < 0.001:
                device_state_name = "Stopped"
            self.device_state_display.setText(device_state_name)
            
            # Update valve displays
            valve_state_names = {
                0: "Idle",
                1: "Homing",
                2: "Stopped",
                3: "Moving"
            }
            
            reagent_valve_state = valve_state_names.get(state.reagent_valve_state, f"Unknown ({state.reagent_valve_state})")
            if state.reagent_valve_state == 2:  # STOP state
                self.reagent_valve_display.setText(f"Pos: {state.reagent_valve_position + 1}, State: {reagent_valve_state}")
            else:
                self.reagent_valve_display.setText(f"State: {reagent_valve_state}")
            
            column_valve_state = valve_state_names.get(state.column_valve_state, f"Unknown ({state.column_valve_state})")
            if state.column_valve_state == 2:  # STOP state
                self.column_valve_display.setText(f"Pos: {state.column_valve_position + 1}, State: {column_valve_state}")
            else:
                self.column_valve_display.setText(f"State: {column_valve_state}")
            
            # Update pump display
            self.pump_display.setText(f"Speed: {state.pump_speed:.2f} ml/min, Volume: {state.pump_volume/1000:.2f} ml")
            
            if state.running:
                self.program_status_label.setText("Running")
                self.run_btn.setEnabled(False)
                self.stop_btn.setEnabled(True)
                self.progress_group.show()
            else:
                # Program finished or not running
                if self.program_uploaded:
                    self.program_status_label.setText("Program completed")
                    self.program_uploaded = False
                else:
                    self.program_status_label.setText("Ready")
                self.progress_group.hide()
                self.run_btn.setEnabled(True)
                self.stop_btn.setEnabled(False)
        except Exception:
            # Connection error will be handled by check_connection timer
            pass


def main():
    """Main application entry point"""
    app = QApplication(sys.argv)
    
    # Set application style
    app.setStyle('Fusion')
    
    # Create and show the main window
    window = ChromatographyGUI()
    window.show()
    
    # Start the application
    sys.exit(app.exec())


if __name__ == "__main__":
    main() 