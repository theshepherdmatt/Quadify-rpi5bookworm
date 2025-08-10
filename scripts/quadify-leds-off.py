#!/usr/bin/env python3
import sys, yaml
from smbus2 import SMBus

BUSNUM = 1
IODIRA, IODIRB = 0x00, 0x01
GPIOA,  GPIOB  = 0x12, 0x13
OLATA,  OLATB  = 0x14, 0x15

def addr_from_cfg():
    try:
        with open("/home/volumio/Quadify/config.yaml","r") as f:
            data = yaml.safe_load(f) or {}
        v = data.get("mcp23017_address")
        if v is None: return None
        if isinstance(v, int): return v
        s = str(v).strip().lower()
        return int(s,16) if s.startswith("0x") else int(s)
    except Exception:
        return None

def probe(bus, addr):
    try: bus.write_quick(addr); return True
    except Exception: return False

def off(bus, addr):
    try:
        bus.write_byte_data(addr, IODIRA, 0x00)
        bus.write_byte_data(addr, IODIRB, 0x00)
        for reg in (OLATA, OLATB, GPIOA, GPIOB):
            bus.write_byte_data(addr, reg, 0x00)
        # optionally float as inputs
        bus.write_byte_data(addr, IODIRA, 0xFF)
        bus.write_byte_data(addr, IODIRB, 0xFF)
        print(f"LEDs off via MCP23017 at 0x{addr:02X}")
        return True
    except Exception:
        return False

def main():
    # priority: CLI arg -> config -> scan
    addr = None
    if len(sys.argv) > 1:
        try:
            s=sys.argv[1].lower(); addr=int(s,16) if s.startswith("0x") else int(s)
        except Exception: addr=None
    if addr is None: addr = addr_from_cfg()

    with SMBus(BUSNUM) as bus:
        if addr is not None and probe(bus, addr) and off(bus, addr): return
        for a in range(0x20, 0x28):
            if probe(bus, a) and off(bus, a): return
    print("No responding MCP23017 on i2c-1 (0x20–0x27)."); sys.exit(1)

if __name__ == "__main__":
    main()
