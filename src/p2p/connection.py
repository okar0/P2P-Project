import socket
from p2p.messages import Message

class Connection:
    def __init__(self, host, port, peer_id, sock=None):
        self.host = host
        self.port = port
        self.peer_id = peer_id
        self.socket = sock

    def connect(self):
        self.socket = socket.create_connection((self.host, self.port))
        print(f"Connected to peer {self.peer_id} at {self.host}:{self.port}")

    def send(self, message_bytes):
        self.socket.sendall(message_bytes)

    def receive(self):
        header = self.socket.recv(5)
        if not header:
            return None
        length = int.from_bytes(header[:4], "big")
        rest = b""
        while len(rest) < length - 1:
            part = self.socket.recv(length - 1 - len(rest))
            if not part:
                break
            rest += part
        msg_type = header[4]
        return Message(msg_type, rest)

    def close(self):
        if self.socket:
            self.socket.close()
            print(f"Connection closed with peer {self.peer_id}")


if __name__ == "__main__":
    import threading
    import time
    from messages import make_choke, make_have

    def server():
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(("localhost", 5000))
        s.listen()
        conn, addr = s.accept()
        connection = Connection("localhost", peer_id=2, port=5000, sock=conn)
        msg = connection.receive()
        print("Server received:", msg)
        connection.send(make_choke())
        connection.close()
        s.close()

    def client():
        time.sleep(0.5) # wait for server to start
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect(("localhost", 5000))
        connection = Connection("localhost", peer_id=1, port=5000, sock=s)
        connection.send(make_have(3))
        msg = connection.receive()
        print("Client received:", msg)
        connection.close()

    # Run threads
    t_server = threading.Thread(target=server)
    t_client = threading.Thread(target=client)
    t_server.start()
    t_client.start()
    t_server.join()
    t_client.join()
