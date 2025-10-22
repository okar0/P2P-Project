class Bitfield:
    def __init__(self, num_pieces):
        self.num_pieces = num_pieces
        self.field = bytearray((num_pieces + 7) // 8)

    def has_piece(self, index):
        byte_index = index // 8
        bit_index = index % 8
        return bool(self.field[byte_index] & (1 << (7 - bit_index)))

    def set_piece(self, index):
        byte_index = index // 8
        bit_index = index % 8
        self.field[byte_index] |= (1 << (7 - bit_index))

    def missing_pieces(self):
        """Return indexes of missing pieces."""
        missing = []
        for i in range(self.num_pieces):
            if not self.has_piece(i):
                missing.append(i)
        return missing

    def to_bytes(self):
        return bytes(self.field)

    @classmethod
    def from_bytes(cls, data, num_pieces):
        bf = cls(num_pieces)
        bf.field = bytearray(data)
        return bf

    def __repr__(self):
        bits = "".join(f"{byte:08b}" for byte in self.field)
        return f"<Bitfield {bits[:self.num_pieces]}>"


# test
if __name__ == "__main__":
    # expect a file split in 10 pieces
    bf = Bitfield(10)

    print("Initial bitfield:", bf)
    print("Has piece 1?", bf.has_piece(1))
    print("Has piece 3?", bf.has_piece(3))
    print("Has piece 5?", bf.has_piece(5))
    print("Has piece 7?", bf.has_piece(7))

    # set some pieces
    bf.set_piece(3)
    bf.set_piece(7)

    print("After setting pieces 3 and 7:", bf)
    print("Has piece 1?", bf.has_piece(1))
    print("Has piece 3?", bf.has_piece(3))
    print("Has piece 5?", bf.has_piece(5))
    print("Has piece 7?", bf.has_piece(7))

    # get bytes
    raw_bytes = bf.to_bytes()
    print("Bitfield bytes:", raw_bytes)

    # decode + verify
    bf2 = Bitfield.from_bytes(raw_bytes, 10)
    print("Decoded bitfield:", bf2)
    print("Bitfields equal?", bf.field == bf2.field)
