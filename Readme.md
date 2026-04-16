# Setup and Installation

## Quick Start with Makefile

```bash
# Setup environment and install dependencies
make setup

# Run with primary devices (HD Pro Webcam + Bluetooth headphones)
make run

# Run with fallback devices
make run-fallback-bt    # Use laptop speakers instead of Bluetooth
make run-fallback-cam   # Use laptop mic instead of HD Pro Webcam

# List available audio devices
make list-devices

# Check dependencies
make check-deps

# Clean environment
make clean
```

## Manual Setup

```bash
source .venv/bin/activate

python standup_recorder.py \
  --monitor-source bluez_output.44_E1_61_91_CC_47.1.monitor \
  --mic-source alsa_input.usb-046d_HD_Pro_Webcam_C920_7ACBEC1F-02.3.analog-stereo \
  --model large-v3 \
  --language pt \
  --device cuda \
  --compute-type float16

# Fallback if Bluetooth headphones not connected (use laptop speakers):

```sh
python standup_recorder.py \
  --monitor-source alsa_output.pci-0000_05_00.6.3.analog-stereo.monitor \
  --mic-source alsa_input.usb-046d_HD_Pro_Webcam_C920_7ACBEC1F-02.3.analog-stereo \
  --model large-v3 \
  --language pt \
  --device cuda \
  --compute-type float16
```

# Fallback if HD Pro Webcam not available (use laptop mic):

```sh
 python standup_recorder.py \
   --monitor-source bluez_output.44_E1_61_91_CC_47.1.monitor \
   --mic-source alsa_input.pci-0000_05_00.6.3.analog-stereo \
   --model large-v3 \
   --language pt \
   --device cuda \
   --compute-type float16
```
