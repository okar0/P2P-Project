
import struct

HANDSHAKE_HEADER = b'P2PFILESHARINGPROJ'
ZERO_BITS = b'\x00' * 10

def create_handshake(peerID):
    return HANDSHAKE_HEADER + ZERO_BITS + struct.pack("!I", peerID)

def read_handshake(data):
    if len(data) != 32:
        raise ValueError("Invalid Handshake Length")

    header = data[:18]
    zeros = data[18:28]

    if header != HANDSHAKE_HEADER:
        raise ValueError("Invalid handshake header")
    if zeros != ZERO_BITS:
        raise ValueError("Invalid zero bits section")

    peerID = struct.unpack("!I", data[28:])[0]

    return peerID

