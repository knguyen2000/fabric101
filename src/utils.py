import socket
import struct
import json

# Constants
SCHEDULER_HOST = '0.0.0.0'
SCHEDULER_CONTROL_PORT = 5000
WORKER_DATA_PORT = 6000

# Message Types
MSG_ALLOW = b"ALLOW_SEND\n"
MSG_WAIT = b"WAIT\n"

def send_json(sock, data):
    """Helper to send JSON data over a socket."""
    msg = json.dumps(data) + "\n"
    sock.sendall(msg.encode('utf-8'))

def recv_json(sock):
    """Helper to receive a JSON line from a socket."""
    try:
        data = b""
        while True:
            chunk = sock.recv(1)
            if not chunk:
                return None
            data += chunk
            if chunk == b"\n":
                break
        return json.loads(data.decode('utf-8'))
    except Exception:
        return None

def send_bulk(sock, data):
    """Helper to send bulk bytes prefixed with length."""
    length = len(data)
    sock.sendall(struct.pack('!Q', length))
    sock.sendall(data)

def recv_bulk(sock):
    """Helper to receive bulk bytes prefixed with length."""
    len_data = sock.recv(8)
    if not len_data:
        return None
    length = struct.unpack('!Q', len_data)[0]
    
    data = b""
    while len(data) < length:
        chunk = sock.recv(min(4096, length - len(data)))
        if not chunk:
            break
        data += chunk
    return data
