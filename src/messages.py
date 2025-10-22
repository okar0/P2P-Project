
import struct


class Message:

    # Constants for message types
    CHOKE = 0
    UNCHOKE = 1
    INTERESTED = 2
    NOT_INTERESTED = 3
    HAVE = 4
    BITFIELD = 5
    REQUEST = 6
    PIECE = 7

    def __init__(self, message_type, payload=b""):
        self.message_type = message_type
        self.payload = payload or b""

    # Encode and decode functions
    def encode(self):
        length = len(self.payload) + 1
        return struct.pack("!IB", length, self.message_type) + self.payload

    @staticmethod
    def decode(data):
        if len(data) < 5:
            raise ValueError("Incomplete Message Header")

        length = struct.unpack("!I", data[:4])[0]
        message_type = struct.unpack("!B", data[4:5])[0]
        payload = data[5:4+length]
        return Message(message_type, payload)

    def __repr__(self):
        return f"<Message type={self.message_type} len={len(self.payload)}>"

# Helper Functions to make message based on message type
def make_choke():
    return Message(Message.CHOKE).encode()

def make_unchoke():
    return Message(Message.UNCHOKE).encode()

def make_interested():
    return Message(Message.INTERESTED).encode()

def make_not_interested():
    return Message(Message.NOT_INTERESTED).encode()

def make_have(piece_index):
    payload = struct.pack("!I", piece_index)
    return Message(Message.HAVE, payload).encode()

def make_bitfield(bitfield_bytes):
    return Message(Message.BITFIELD, bitfield_bytes).encode()

def make_request(piece_index):
    payload = struct.pack("!I", piece_index)
    return Message(Message.REQUEST, payload).encode()

def make_piece(piece_index, data):
    payload = struct.pack("!I", piece_index) + data
    return Message(Message.PIECE, payload).encode()
