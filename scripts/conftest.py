"""The scripts' tests never reach the network (AGENTS.md rule 4): opening a connection or resolving a name fails the
test. The guard is set when this file is imported, before any test module, so a module-level client is caught too."""
import socket


def _refuse(*args, **kwargs):
    raise AssertionError("a test tried to reach the network")


for _name in ("connect", "connect_ex"):
    setattr(socket.socket, _name, _refuse)
socket.create_connection = _refuse
socket.getaddrinfo = _refuse
