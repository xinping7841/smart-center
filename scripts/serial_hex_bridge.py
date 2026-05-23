import json
import sys

import serial


def build_result(success: bool, **kwargs):
    data = {"success": success}
    data.update(kwargs)
    return data


def normalize_hex(text: str) -> str:
    return "".join(str(text or "").replace("0x", "").split()).upper()


def main():
    if len(sys.argv) < 3:
        print(json.dumps(build_result(False, error="usage", message="Usage: python serial_hex_bridge.py <COMx> <HEX> [baudrate]"), ensure_ascii=False))
        return 1

    port = str(sys.argv[1]).strip()
    hex_text = normalize_hex(sys.argv[2])
    baudrate = int(sys.argv[3]) if len(sys.argv) > 3 else 9600

    if not port:
        print(json.dumps(build_result(False, error="missing_port", message="Serial port is required"), ensure_ascii=False))
        return 2

    if not hex_text or len(hex_text) % 2 != 0:
        print(json.dumps(build_result(False, error="invalid_hex", message="HEX string must contain an even number of characters"), ensure_ascii=False))
        return 3

    try:
        payload = bytes.fromhex(hex_text)
    except ValueError as exc:
        print(json.dumps(build_result(False, error="invalid_hex", message=str(exc), hex=hex_text), ensure_ascii=False))
        return 4

    try:
        with serial.Serial(
            port=port,
            baudrate=baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=1
        ) as ser:
            ser.reset_input_buffer()
            ser.reset_output_buffer()
            written = ser.write(payload)
            ser.flush()
        print(json.dumps(build_result(True, port=port, baudrate=baudrate, hex=hex_text, bytes_written=written), ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps(build_result(False, error="serial_write_failed", message=str(exc), port=port, baudrate=baudrate, hex=hex_text), ensure_ascii=False))
        return 5


if __name__ == "__main__":
    raise SystemExit(main())
