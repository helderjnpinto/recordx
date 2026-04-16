.PHONY: help install setup run run-fallback-bt run-fallback-cam clean check-deps list-devices

# Default target
help:
	@echo "Available commands:"
	@echo "  make setup      - Set up virtual environment and install dependencies"
	@echo "  make install    - Install dependencies in existing venv"
	@echo "  make run        - Run with primary devices (HD Pro Webcam + Bluetooth)"
	@echo "  make run-fallback-bt - Run with laptop speakers (fallback for Bluetooth)"
	@echo "  make run-fallback-cam - Run with laptop mic (fallback for HD Pro Webcam)"
	@echo "  make list-devices - List available audio devices"
	@echo "  make check-deps - Check if dependencies are installed"
	@echo "  make clean      - Clean virtual environment"
	@echo "  make help       - Show this help message"

# Setup virtual environment and install dependencies
setup:
	@echo "Setting up virtual environment..."
	python3 -m venv .venv
	@echo "Activating virtual environment..."
	. .venv/bin/activate && \
	pip install --upgrade pip && \
	pip install -r requirements.txt
	@echo "Setup complete! Use 'source .venv/bin/activate' to activate the environment."

# Install dependencies in existing virtual environment
install:
	@echo "Installing dependencies..."
	. .venv/bin/activate && \
	pip install --upgrade pip && \
	pip install -r requirements.txt
	@echo "Dependencies installed!"

# Run with primary devices (HD Pro Webcam + Bluetooth headphones)
run:
	@echo "Running with primary devices: HD Pro Webcam + Bluetooth headphones"
	. .venv/bin/activate && \
	python standup_recorder.py \
	  --monitor-source bluez_output.44_E1_61_91_CC_47.1.monitor \
	  --mic-source alsa_input.usb-046d_HD_Pro_Webcam_C920_7ACBEC1F-02.3.analog-stereo \
	  --model large-v3 \
	  --language pt \
	  --device cuda \
	  --compute-type float16

# Run with fallback for Bluetooth (use laptop speakers)
run-fallback-bt:
	@echo "Running with fallback: HD Pro Webcam + Laptop speakers"
	. .venv/bin/activate && \
	python standup_recorder.py \
	  --monitor-source alsa_output.pci-0000_05_00.6.3.analog-stereo.monitor \
	  --mic-source alsa_input.usb-046d_HD_Pro_Webcam_C920_7ACBEC1F-02.3.analog-stereo \
	  --model large-v3 \
	  --language pt \
	  --device cuda \
	  --compute-type float16

# Run with fallback for HD Pro Webcam (use laptop mic)
run-fallback-cam:
	@echo "Running with fallback: Laptop mic + Bluetooth headphones"
	. .venv/bin/activate && \
	python standup_recorder.py \
	  --monitor-source bluez_output.44_E1_61_91_CC_47.1.monitor \
	  --mic-source alsa_input.pci-0000_05_00.6.3.analog-stereo \
	  --model large-v3 \
	  --language pt \
	  --device cuda \
	  --compute-type float16

# List available audio devices
list-devices:
	@echo "Available audio sources:"
	pactl list short sources

# Check if dependencies are installed
check-deps:
	@echo "Checking dependencies..."
	. .venv/bin/activate && \
	python -c "import faster_whisper; print('faster-whisper: OK')" || echo "faster-whisper: MISSING"

# Clean virtual environment
clean:
	@echo "Removing virtual environment..."
	rm -rf .venv
	@echo "Virtual environment removed!"
