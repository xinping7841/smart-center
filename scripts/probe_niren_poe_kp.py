import argparse
import socket
import time


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
    return b"".join(chunks).decode("gbk", errors="replace")


def send_at(sock, command, timeout):
    sock.sendall((command.strip() + "\r\n").encode("ascii", errors="ignore"))
    return read_response(sock, timeout)


def main():
    parser = argparse.ArgumentParser(description="Probe Niren POE-KP-I101 AT-over-TCP relay")
    parser.add_argument("--host", default="192.168.50.89")
    parser.add_argument("--port", type=int, default=44489)
    parser.add_argument("--timeout", type=float, default=1.5)
    parser.add_argument("--write-test", action="store_true", help="Toggle DO1 on then off. This physically controls the relay.")
    args = parser.parse_args()

    commands = ["AT", "AT+DEVICEINFO=?", "AT+STACH1=?", "AT+OCCH1=?"]
    if args.write_test:
        commands.extend(["AT+STACH1=1", "AT+STACH1=?", "AT+STACH1=0", "AT+STACH1=?"])

    with socket.create_connection((args.host, args.port), timeout=max(args.timeout, 0.5)) as sock:
        for command in commands:
            response = send_at(sock, command, args.timeout)
            clean = response.replace("\r", "\\r").replace("\n", "\\n")
            print(f"{command} => {clean}")
            if args.write_test and command == "AT+STACH1=1":
                time.sleep(1)


if __name__ == "__main__":
    main()
