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
    QGroupBox, QGridLayout, QComboBox, QSpinBox, QCheckBox, QDoubleSpinBox,
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
        self.setWindowTitle("Chromapump Control")
        self.setGeometry(100, 100, 1000, 600)
        self.device = None
        self.program = None
        self.program_uploaded = False
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self.update_status)
        self.connection_timer = QTimer()
        self.connection_timer.timeout.connect(self.check_connection)
        
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
        
        # Create splitter for resizable panels
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Left panel - Control widget
        self.create_control_widget()
        splitter.addWidget(self.control_widget)
        
        # Right panel - Monitor widget
        self.create_monitor_widget()
        splitter.addWidget(self.monitor_widget)
        
        # Set initial splitter sizes (60% program, 40% execution)
        splitter.setSizes([600, 400])
        
        layout.addWidget(splitter)
        central.setLayout(layout)
        self.setCentralWidget(central)

    def auto_connect_device(self):
        """Automatically try to connect to all available ports"""
        self.connection_worker.try_connect()

    def on_device_connected(self, port):
        """Called when device connection is successful"""
        try:
            self.device = DeviceConnection(port)
            self.device.open()
            self.connection_label.setText(f"Connected to {port}")
            self.program_uploaded = False
            self.status_timer.start(30)
            self.connection_timer.start(1000)  # Check connection every 1 second
            
        except Exception as e:
            self.connection_label.setText(f"Connection failed: {e}")

    def on_connection_failed(self):
        """Called when connection attempt fails"""
        self.connection_label.setText("Connection failed")
        # Start connection timer to retry periodically
        if not self.connection_timer.isActive():
            self.connection_timer.start(500)  # Retry every 0.5 seconds

    def on_no_device_found(self):
        """Called when no device is found"""
        self.connection_label.setText("No device detected")
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
                    self.status_timer.stop()
                    self.auto_connect_device()
            except Exception:
                # Connection error, try to reconnect
                self.connection_label.setText("Connection error, reconnecting...")
                self.device = None
                self.status_timer.stop()
                self.auto_connect_device()
        else:
            # No device connected, try to find one
            self.auto_connect_device()

    def create_control_widget(self):
        """Create the left panel for program management"""
        self.control_widget = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(5)
        
        # Program loading section
        load_layout = QVBoxLayout()
        load_layout.setSpacing(5)

        # Replace the 16 checkboxes with two dropdown menus for valve control
        valve_group = QGroupBox("Valve control")
        valve_layout = QVBoxLayout()
        
        # Reagent bank selection
        reagent_layout = QHBoxLayout()
        reagent_layout.addWidget(QLabel("Reagent Bank:"))
        self.reagent_valve_combo = QComboBox()
        self.reagent_valve_combo.addItems([str(i) for i in range(1, 7)])  # Options 1-6
        self.reagent_valve_combo.setCurrentIndex(0)  # Default to valve 1
        self.reagent_valve_combo.currentIndexChanged.connect(self.send_valve_command)
        reagent_layout.addWidget(self.reagent_valve_combo)
        valve_layout.addLayout(reagent_layout)
        
        # Column bank selection
        column_layout = QHBoxLayout()
        column_layout.addWidget(QLabel("Column Bank:"))
        self.column_valve_combo = QComboBox()
        self.column_valve_combo.addItems([str(i) for i in range(1, 7)])  # Options 1-6
        self.column_valve_combo.setCurrentIndex(0)  # Default to valve 1
        self.column_valve_combo.currentIndexChanged.connect(self.send_valve_command)
        column_layout.addWidget(self.column_valve_combo)
        valve_layout.addLayout(column_layout)
        
        valve_group.setLayout(valve_layout)
        load_layout.addWidget(valve_group)

        # Add uint16_t input field for pump command, forward/reverse option, and uint16_t acceleration input and a button to send the command
        pump_group = QGroupBox("Pump control")
        pump_layout = QHBoxLayout()
        command_layout = QVBoxLayout()
        command_layout.setSpacing(0.5)
        command_layout.addWidget(QLabel("Command:"))
        self.pump_command_input = QDoubleSpinBox(minimum=-1, maximum=1, singleStep=0.01, value=0.0)
        command_layout.addWidget(self.pump_command_input)
        pump_layout.addLayout(command_layout)

        # direction_layout = QVBoxLayout()
        # direction_layout.setSpacing(0.5)
        # direction_layout.addWidget(QLabel("Direction:"))
        # self.pump_forward_reverse_input = QComboBox()
        # self.pump_forward_reverse_input.addItems(["Forward", "Reverse"])
        # direction_layout.addWidget(self.pump_forward_reverse_input)
        # pump_layout.addLayout(direction_layout)

        acceleration_layout = QVBoxLayout()
        acceleration_layout.setSpacing(0.5)
        acceleration_layout.addWidget(QLabel("Acceleration:"))
        self.pump_acceleration_input = QDoubleSpinBox(minimum=-100, maximum=100, singleStep=0.01, value=1.0)
        acceleration_layout.addWidget(self.pump_acceleration_input)
        pump_layout.addLayout(acceleration_layout)

        # Add a horizontal layout to the pump group
        pump_send_layout = QHBoxLayout()
        pump_send_layout.setSpacing(0.5)
        pump_send_layout.addStretch()
        self.pump_send_button = QPushButton("Send")
        self.pump_send_button.clicked.connect(self.send_pump_command)
        pump_send_layout.addWidget(self.pump_send_button)
        
        self.pump_stop_button = QPushButton("Stop Pump")
        self.pump_stop_button.clicked.connect(self.stop_pump)
        pump_send_layout.addWidget(self.pump_stop_button)
        pump_layout.addLayout(pump_send_layout)

        pump_group.setLayout(pump_layout)
        load_layout.addWidget(pump_group)


        # Add scale measurement display widget
        scale_group = QGroupBox("Weight measurements")
        scale_layout = QVBoxLayout()
        
        # Weight display labels
        weight_display_layout = QHBoxLayout()
        self.scale_labels = []
        for i in range(8):
            label = QLabel(f"{i+1}: ???")
            weight_display_layout.addWidget(label)
            self.scale_labels.append(label)
        
        scale_layout.addLayout(weight_display_layout)
        
        # Tare All button
        tare_layout = QHBoxLayout()
        tare_layout.addStretch()
        self.tare_all_button = QPushButton("Tare All")
        self.tare_all_button.clicked.connect(self.tare_all_weight_sensors)
        tare_layout.addWidget(self.tare_all_button)
        
        scale_layout.addLayout(tare_layout)
        scale_group.setLayout(scale_layout)
        load_layout.addWidget(scale_group)



        layout.addLayout(load_layout)
        layout.addStretch()

        self.control_widget.setLayout(layout)

    def create_monitor_widget(self):
        """Create the right panel for execution control"""
        self.monitor_widget = QWidget()
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
        
        # Here add a text field that will display the serial monitor output
        self.monitor_text = QTextEdit()
        layout.addWidget(self.monitor_text)

        self.monitor_widget.setLayout(layout)
    
    def update_status(self):
        if self.device:
            state = self.device.get_device_state()
            for i in range(8):
                self.scale_labels[i].setText(f"{i+1}: {state.weight[i]:>4.1f}")
            
            if self.device.ser.in_waiting > 0:
                line = self.device.ser.readline().decode('utf-8')
                print(line, end='')

    def send_valve_command(self):
        """Send valve command using the new protocol with reagent and column bank selection"""
        if self.device:
            reagent_valve_id = self.reagent_valve_combo.currentIndex()  # 0-5 for valves 1-6
            column_valve_id = self.column_valve_combo.currentIndex()    # 0-5 for valves 1-6
            # Convert from 1-based display to 0-based firmware
            self.device.valve_command(reagent_valve_id, column_valve_id)

    def send_pump_command(self):
        pump_cmd = self.pump_command_input.value()
        # direction = self.pump_forward_reverse_input.currentIndex() == 0
        acceleration = self.pump_acceleration_input.value()
        # self.device.pump_command(pump_cmd, direction, acceleration)
        self.device.pump_command(pump_cmd, acceleration)

    def stop_pump(self):
        """Stop the pump by sending speed 0 and acceleration 10"""
        self.device.pump_command(0, 10)

    def tare_all_weight_sensors(self):
        """Tare all weight sensors by sending individual tare commands for each channel"""
        if self.device:
            for channel in range(8):
                try:
                    self.device.tare_weight_sensor(channel)
                except Exception as e:
                    print(f"Failed to tare channel {channel}: {e}")


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