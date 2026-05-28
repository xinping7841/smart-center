import argparse
import socket
import time


def crc16_modbus(data):
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc.to_bytes(2, "little")


def read_response(sock, timeout):
    sock.settimeout(timeout)
    chunks = []
    end_at = time.monotonic() + timeout
    while time.monotonic() < end_at:
        try:
            data = sock.recv(4096)
        except socket.timeout:
            break
        if not data:
            break
        chunks.append(data)
        sock.settimeout(0.15)
    return b"".join(chunks)


def at_exchange(host, port, command, timeout):
    with socket.create_connection((host, port), timeout=max(timeout, 0.5)) as sock:
        sock.sendall((command.strip() + "\r\n").encode("ascii", errors="ignore"))
        raw = read_response(sock, timeout)
    return raw.decode("gbk", errors="replace")


def modbus_rtu_exchange(host, port, body_hex, timeout):
    body = bytes.fromhex("".join(body_hex.split()))
    frame = body + crc16_modbus(body)
    with socket.create_connection((host, port), timeout=max(timeout, 0.5)) as sock:
        sock.sendall(frame)
        return read_response(sock, timeout)


def modbus_tcp_exchange(host, port, pdu_hex, timeout):
    pdu = bytes.fromhex("".join(pdu_hex.split()))
    frame = b"\x12\x34\x00\x00" + len(pdu).to_bytes(2, "big") + pdu
    with socket.create_connection((host, port), timeout=max(timeout, 0.5)) as sock:
        sock.sendall(frame)
        return read_response(sock, timeout)


def print_at(host, port, command, timeout):
    text = at_exchange(host, port, command, timeout)
    print(f"{command} => {text.replace(chr(13), '<CR>').replace(chr(10), '<LF>')}")
    return text


def main():
    parser = argparse.ArgumentParser(description="Controlled Niren POE-KP-I101 mode test")
    parser.add_argument("--host", default="192.168.50.89")
    parser.add_argument("--port", type=int, default=44489)
    parser.add_argument("--timeout", type=float, default=1.5)
    parser.add_argument(
        "--switch-modbus",
        action="store_true",
        help="Set AT+PROTOCOL=4 and test Modbus. Warning: the data port may stop accepting AT restore commands after switching.",
    )
    parser.add_argument("--restore-at", action="store_true", help="Send AT+PROTOCOL=0 and verify AT mode.")
    args = parser.parse_args()

    print_at(args.host, args.port, "AT+MODEL=?", args.timeout)
    print_at(args.host, args.port, "AT+PORT=?", args.timeout)
    print_at(args.host, args.port, "AT+MBTCPADDR=?", args.timeout)
    print_at(args.host, args.port, "AT+PROTOCOL=?", args.timeout)

    if args.restore_at:
        print_at(args.host, args.port, "AT+PROTOCOL=0", args.timeout)
        print_at(args.host, args.port, "AT+PROTOCOL=?", args.timeout)
        return

    if not args.switch_modbus:
        print("No mode change requested. Use --switch-modbus to run the reversible Modbus test.")
        return

    try:
        print_at(args.host, args.port, "AT+PROTOCOL=4", args.timeout)
        time.sleep(0.5)
        rtu = modbus_rtu_exchange(args.host, args.port, "01 01 00 00 00 01", args.timeout)
        print("RTU read DO1 =>", rtu.hex(" ") or "<empty>")
        tcp = modbus_tcp_exchange(args.host, args.port, "01 01 00 00 00 01", args.timeout)
        print("Modbus TCP read DO1 =>", tcp.hex(" ") or "<empty>")
    finally:
        try:
            print_at(args.host, args.port, "AT+PROTOCOL=0", args.timeout)
            print_at(args.host, args.port, "AT+PROTOCOL=?", args.timeout)
        except Exception as exc:
            print(f"Restore via AT failed: {exc}")


if __name__ == "__main__":
    main()
