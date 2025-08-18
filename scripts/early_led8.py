# /home/volumio/Quadify/scripts/early_led8.py
import smbus2, yaml
from pathlib import Path

CONFIG_PATH = Path("/home/volumio/Quadify/config.yaml")

def parse_i2c_addr(raw):
    if isinstance(raw, int):
        addr = raw
    elif isinstance(raw, str):
        s = raw.strip().lower()
        if s.startswith("0x"):
            addr = int(s, 16)
        elif len(s) <= 2 and all(c in "0123456789abcdef" for c in s):
            # Treat 1–2 hex chars like "20" or "27" as hex
            addr = int(s, 16)
        else:
            # Otherwise treat as decimal string, e.g. "32" -> 0x20
            addr = int(s, 10)
    else:
        raise KeyError("mcp23017_address missing")

    if not (0x03 <= addr <= 0x77):
        raise ValueError(f"out of range: {addr:#04x}")
    return addr

def load_mcp_address(path: Path):
    cfg = yaml.safe_load(path.read_text()) or {}
    if "mcp23017_address" not in cfg:
        raise KeyError("mcp23017_address missing")
    return parse_i2c_addr(cfg["mcp23017_address"])

try:
    MCP_ADDR = load_mcp_address(CONFIG_PATH)
except Exception as e:
    print(f"early_led8: {e}; skipping early LED init.")
    raise SystemExit(0)

# MCP23017 registers
MCP23017_IODIRA = 0x00
MCP23017_GPIOA  = 0x12

try:
    bus = smbus2.SMBus(1)
    bus.write_byte_data(MCP_ADDR, MCP23017_IODIRA, 0x00)       # Port A as output
    bus.write_byte_data(MCP_ADDR, MCP23017_GPIOA,  0b00000001) # LED8 on
finally:
    try:
        bus.close()
    except Exception:
        pass
