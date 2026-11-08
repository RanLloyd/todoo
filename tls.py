"""Local HTTPS helpers.

Browsers only allow camera access on https:// pages (or http://localhost). A phone that opens
http://192.168.x.x:5000 therefore gets "Camera streaming not supported by the browser".
This module creates a self-signed certificate that is valid for localhost, this computer's name
and every LAN IP address, so the app can also be served over HTTPS on the school network.
"""
import datetime
import ipaddress
import json
import socket
from pathlib import Path


def lan_ips():
    """IPv4 addresses of this computer on the local network (best effort, no traffic is sent)."""
    found = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('10.255.255.255', 1))  # UDP connect only selects the outgoing interface
        found.append(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            found.append(info[4][0])
    except OSError:
        pass
    out = []
    for ip in found:
        if ip and not ip.startswith('127.') and ip not in out:
            out.append(ip)
    return out


def _names():
    names = {'localhost'}
    try:
        host = socket.gethostname()
        if host:
            names.add(host)
    except OSError:
        pass
    return sorted(names)


def ensure_cert(cert_dir):
    """Return (cert_path, key_path); (re)create them when missing, expiring or when the IPs changed."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    cert_dir = Path(cert_dir)
    cert_dir.mkdir(parents=True, exist_ok=True)
    cert_path, key_path, meta_path = cert_dir / 'local.crt', cert_dir / 'local.key', cert_dir / 'local.json'
    names, ips = _names(), ['127.0.0.1'] + lan_ips()
    wanted = {'names': names, 'ips': ips}

    if cert_path.exists() and key_path.exists() and meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text())
            fresh = datetime.datetime.fromisoformat(meta['expires']) - datetime.datetime.utcnow() > datetime.timedelta(days=30)
            covers = set(ips) <= set(meta.get('ips', [])) and set(names) <= set(meta.get('names', []))
            if fresh and covers:
                return str(cert_path), str(key_path)
        except (ValueError, KeyError, OSError):
            pass

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Pila SHS Attendance (local network)')])
    alt = [x509.DNSName(n) for n in names] + [x509.IPAddress(ipaddress.ip_address(i)) for i in ips]
    alt.append(x509.IPAddress(ipaddress.ip_address('::1')))
    not_before = datetime.datetime.utcnow() - datetime.timedelta(days=1)
    not_after = not_before + datetime.timedelta(days=800)
    cert = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(not_before).not_valid_after(not_after)
            .add_extension(x509.SubjectAlternativeName(alt), critical=False)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .sign(key, hashes.SHA256()))
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
                                           serialization.NoEncryption()))
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    wanted['expires'] = not_after.isoformat()
    meta_path.write_text(json.dumps(wanted))
    return str(cert_path), str(key_path)
