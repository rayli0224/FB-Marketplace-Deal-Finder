"""
TCP proxy for Chrome DevTools remote debugging.

Forwards connections from all network interfaces (0.0.0.0) to Chrome's
debugging port on localhost. This is needed because Chrome ignores
--remote-debugging-address=0.0.0.0 in some builds and only listens on
loopback. Docker port forwarding enters through the container's network
interface (not loopback), so without this proxy the host machine cannot
reach Chrome's DevTools endpoint.

Started once as a daemon thread when the scraper runs in headed (debug) mode.
"""

import logging
import socket
import threading

from src.utils.colored_logger import log_warning

logger = logging.getLogger("fb_scraper")

# Default ports for FB Marketplace scraper.
LISTEN_PORT = 9222
CHROME_PORT = 9223

_proxy_lock = threading.Lock()
_proxy_started: set[tuple[int, int]] = set()


def _forward(src: socket.socket, dst: socket.socket):
    """Forward data between two sockets until either side closes."""
    try:
        while True:
            data = src.recv(65536)
            if not data:
                break
            dst.sendall(data)
    except Exception:
        pass
    finally:
        try:
            src.close()
        except Exception:
            pass
        try:
            dst.close()
        except Exception:
            pass


def _run_proxy(listen_port: int, chrome_port: int):
    """Accept connections on 0.0.0.0:listen_port and forward each to localhost:chrome_port."""
    try:
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("0.0.0.0", listen_port))
        server.listen(5)
    except OSError as e:
        log_warning(logger, f"Could not start debug proxy on port {listen_port} — {e}")
        return

    while True:
        try:
            client, _ = server.accept()
        except OSError:
            break
        try:
            remote = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            remote.connect(("127.0.0.1", chrome_port))
            threading.Thread(target=_forward, args=(client, remote), daemon=True).start()
            threading.Thread(target=_forward, args=(remote, client), daemon=True).start()
        except Exception:
            client.close()


def start_debug_proxy(proxy_port: int = LISTEN_PORT, chrome_port: int = CHROME_PORT):
    """Start the TCP proxy in a background daemon thread (idempotent per port pair)."""
    with _proxy_lock:
        key = (proxy_port, chrome_port)
        if key in _proxy_started:
            return
        _proxy_started.add(key)
    threading.Thread(target=_run_proxy, args=(proxy_port, chrome_port), daemon=True).start()
