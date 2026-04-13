"""
Canonical printer auto-discovery and print dispatch.
All printer discovery logic lives here — never in routes.
"""
from __future__ import annotations
import io
import ipaddress
import socket
import time
from typing import Optional

from PIL import Image

from app import config

# ── Discovery cache ───────────────────────────────────────────────────────────
_cached_printer_ip: Optional[str] = None
_cache_expires_at: float = 0.0
_CACHE_TTL = 300  # seconds


def discover_printer(force: bool = False) -> Optional[str]:
    """
    Return printer IP (host:port format) or None if not found.
    Results are cached for 5 minutes.

    Strategy:
      1. mDNS/Bonjour — browse _pdl-datastream._tcp.local. and _printer._tcp.local.
      2. TCP port-9100 subnet sweep as fallback
    """
    global _cached_printer_ip, _cache_expires_at

    if not force and _cached_printer_ip and time.time() < _cache_expires_at:
        return _cached_printer_ip

    ip = _discover_mdns() or _discover_tcp_sweep()

    if ip:
        _cached_printer_ip = ip
        _cache_expires_at = time.time() + _CACHE_TTL

    return ip


def discover_all_printers() -> list[str]:
    """
    Return ALL printer addresses (IP:port) found via TCP port-9100 sweep.
    Scans the host machine's /24 (via host.docker.internal) and the configured
    subnet. Returns every device with port 9100 open.
    """
    return _discover_tcp_sweep_all()


def _discover_mdns() -> Optional[str]:
    """Browse mDNS for label printers; return IP:port or None."""
    try:
        from zeroconf import ServiceBrowser, Zeroconf
        import threading

        found: list[str] = []
        event = threading.Event()

        class Handler:
            def add_service(self, zc: Zeroconf, svc_type: str, name: str) -> None:
                info = zc.get_service_info(svc_type, name)
                if info and info.addresses:
                    ip = socket.inet_ntoa(info.addresses[0])
                    port = info.port or 9100
                    found.append(f"{ip}:{port}")
                    event.set()

            def remove_service(self, *_): pass
            def update_service(self, *_): pass

        zc = Zeroconf()
        browsers = [
            ServiceBrowser(zc, "_pdl-datastream._tcp.local.", Handler()),
            ServiceBrowser(zc, "_printer._tcp.local.", Handler()),
        ]
        event.wait(timeout=5)
        zc.close()

        return found[0] if found else None
    except Exception:
        return None


def _host_prefix() -> Optional[str]:
    """
    On Docker Desktop (macOS/Windows), host.docker.internal resolves to the
    Mac host's LAN IP — gives us the correct /24 to scan even though the
    container's own IP is on the Docker internal network.
    Returns the /24 prefix (e.g. "10.100.5") or None if not resolvable.
    """
    try:
        ip = socket.gethostbyname("host.docker.internal")
        return ".".join(ip.split(".")[:3])
    except OSError:
        return None


def _sorted_prefixes() -> list[str]:
    """Build ordered list of /24 prefixes to scan, host /24 first."""
    our_ip = _get_own_ip()
    prefixes = _resolve_scan_prefixes(config.PRINTER_SUBNET, our_ip)
    host = _host_prefix()
    if host:
        if host in prefixes:
            prefixes.remove(host)
        prefixes.insert(0, host)
    return prefixes


def _discover_tcp_sweep() -> Optional[str]:
    """Sweep /24 subnets for port 9100. Returns first match."""
    try:
        import concurrent.futures

        def check(host: str) -> Optional[str]:
            try:
                with socket.create_connection((host, 9100), timeout=0.4):
                    return f"{host}:9100"
            except OSError:
                return None

        for prefix in _sorted_prefixes():
            hosts = [f"{prefix}.{i}" for i in range(1, 255)]
            with concurrent.futures.ThreadPoolExecutor(max_workers=128) as ex:
                for result in ex.map(check, hosts):
                    if result:
                        return result
    except Exception:
        pass
    return None


def _discover_tcp_sweep_all() -> list[str]:
    """Sweep /24 subnets for port 9100. Returns ALL matches (up to 5 /24 blocks)."""
    try:
        import concurrent.futures

        results: list[str] = []

        def check(host: str) -> Optional[str]:
            try:
                with socket.create_connection((host, 9100), timeout=0.4):
                    return f"{host}:9100"
            except OSError:
                return None

        for prefix in _sorted_prefixes()[:5]:
            hosts = [f"{prefix}.{i}" for i in range(1, 255)]
            with concurrent.futures.ThreadPoolExecutor(max_workers=128) as ex:
                for result in ex.map(check, hosts):
                    if result:
                        results.append(result)

        return results
    except Exception:
        return []


def _get_own_ip() -> str:
    """Return this machine's primary LAN IP."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    finally:
        s.close()


def _resolve_scan_prefixes(subnet_cfg: str, our_ip: str) -> list[str]:
    """
    Convert PRINTER_SUBNET config value into a list of /24 prefixes to scan.
    Our own /24 is always first so the printer is found quickly if it's nearby.
    """
    our_prefix = ".".join(our_ip.split(".")[:3])

    if not subnet_cfg:
        return [our_prefix]

    subnet_cfg = subnet_cfg.strip()

    # Bare prefix like "192.168.1" or "10.100.0"
    if "/" not in subnet_cfg:
        return [subnet_cfg]

    # CIDR notation
    try:
        network = ipaddress.ip_network(subnet_cfg, strict=False)
    except ValueError:
        return [our_prefix]

    if network.prefixlen >= 24:
        # It's already a /24 or smaller — one prefix
        parts = str(network.network_address).split(".")
        return [".".join(parts[:3])]

    # Wider network (e.g. /16): collect all /24 blocks within it,
    # but put our own /24 first so we find the printer quickly.
    subnets_24 = list(network.subnets(new_prefix=24))
    prefixes = [".".join(str(s.network_address).split(".")[:3]) for s in subnets_24]

    # Bubble our own /24 to front
    if our_prefix in prefixes:
        prefixes.remove(our_prefix)
        prefixes.insert(0, our_prefix)

    return prefixes


def print_badge(printer_addr: str, img: Image.Image) -> None:
    """
    Send a PIL Image to a printer at 'host:port' via the appropriate method.

    For Brother QL printers (detected by PRINTER_MODEL env):
      Uses brother_ql to generate raster and sends over TCP.
    For all others:
      Sends the PNG as raw data over TCP port 9100 (works for many
      PCL/PostScript printers in passthrough mode).
    """
    host, _, port_str = printer_addr.partition(":")
    port = int(port_str) if port_str else 9100

    model = config.PRINTER_MODEL.upper()

    if model.startswith("QL-") or model.startswith("QL"):
        _print_brother_ql(host, port, img, model)
    else:
        _print_raw_png(host, port, img)


def _print_brother_ql(host: str, port: int, img: Image.Image, model: str) -> None:
    """Print via brother_ql library (Brother QL series)."""
    # brother_ql 0.9.4 uses Image.ANTIALIAS which was removed in Pillow 10
    if not hasattr(Image, "ANTIALIAS"):
        Image.ANTIALIAS = Image.LANCZOS  # type: ignore[attr-defined]

    from brother_ql.conversion import convert
    from brother_ql.backends.helpers import send
    from brother_ql.raster import BrotherQLRaster

    # 62mm continuous tape label = "62"
    label = "62"

    qlr = BrotherQLRaster(model)
    qlr.exception_on_warning = True

    instructions = convert(
        qlr=qlr,
        images=[img],
        label=label,
        rotate="0",
        threshold=70.0,
        dither=False,
        compress=False,
        red=False,
        dpi_600=False,
        hq=True,
        cut=True,
    )

    send(
        instructions=instructions,
        printer_identifier=f"tcp://{host}:{port}",
        backend_identifier="network",
        blocking=True,
    )


def _print_raw_png(host: str, port: int, img: Image.Image) -> None:
    """Send PNG bytes raw over TCP port 9100 (generic passthrough)."""
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    data = buf.getvalue()

    with socket.create_connection((host, port), timeout=10) as s:
        s.sendall(data)
