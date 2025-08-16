# /home/volumio/Quadify/scripts/early_led8.py

import smbus2
import yaml
from pathlib import Path

CONFIG_PATH = Path("/home/volumio/Quadify/config.yaml")

def load_mcp_address(config_path):
    try:
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
        # Pull out `mcp23017_address` (default 0x20 if missing)
        return int(config.get("mcp23017_address", "0x20"), 16)
    except Exception as e:
        print(f"Error reading config.yaml, falling back to 0x20: {e}")
        return 0x20

MCP23017_ADDRESS = load_mcp_address(CONFIG_PATH)

# MCP23017 register definitions
MCP23017_IODIRA = 0x00
MCP23017_GPIOA  = 0x12

# Open I2C bus
bus = smbus2.SMBus(1)

# Set port A as output and turn LED 8 on
bus.write_byte_data(MCP23017_ADDRESS, MCP23017_IODIRA, 0x00)      # All A pins as output
bus.write_byte_data(MCP23017_ADDRESS, MCP23017_GPIOA, 0b00000001) # Set bit 0 = LED 8 ON

bus.close()
