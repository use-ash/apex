#!/usr/bin/env python3
"""Generate mTLS certificates for Apex on Windows."""
import sys, os, datetime
from pathlib import Path
from cryptography import x509
from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.hazmat.primitives.asymmetric import rsa
import ipaddress

EXT_IP = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
ssl = Path(os.environ.get("APEX_SSL_DIR", "C:/apex/state/ssl"))
ssl.mkdir(parents=True, exist_ok=True)

def gk():
    return rsa.generate_private_key(65537, 2048)

def wk(p, k):
    p.write_bytes(k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption()))

def wc(p, c):
    p.write_bytes(c.public_bytes(serialization.Encoding.PEM))

now = datetime.datetime.now(datetime.timezone.utc)

# CA
ca_key = gk()
ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Apex CA")])
ca_cert = (x509.CertificateBuilder()
    .subject_name(ca_name).issuer_name(ca_name)
    .public_key(ca_key.public_key())
    .serial_number(x509.random_serial_number())
    .not_valid_before(now)
    .not_valid_after(now + datetime.timedelta(days=3650))
    .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
    .sign(ca_key, hashes.SHA256()))
wk(ssl / "ca.key", ca_key)
wc(ssl / "ca.crt", ca_cert)
print("CA ok")

# Server
sk = gk()
san = x509.SubjectAlternativeName([
    x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
    x509.IPAddress(ipaddress.ip_address("10.142.0.2")),
    x509.IPAddress(ipaddress.ip_address(EXT_IP)),
    x509.DNSName("localhost"),
    x509.DNSName("apex-windows-test"),
])
sc = (x509.CertificateBuilder()
    .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Apex Server")]))
    .issuer_name(ca_name)
    .public_key(sk.public_key())
    .serial_number(x509.random_serial_number())
    .not_valid_before(now)
    .not_valid_after(now + datetime.timedelta(days=825))
    .add_extension(san, critical=False)
    .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
    .sign(ca_key, hashes.SHA256()))
wk(ssl / "apex.key", sk)
wc(ssl / "apex.crt", sc)
print("Server ok")

# Client
ck = gk()
cc = (x509.CertificateBuilder()
    .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Apex Client")]))
    .issuer_name(ca_name)
    .public_key(ck.public_key())
    .serial_number(x509.random_serial_number())
    .not_valid_before(now)
    .not_valid_after(now + datetime.timedelta(days=825))
    .sign(ca_key, hashes.SHA256()))
wk(ssl / "client.key", ck)
wc(ssl / "client.crt", cc)
try:
    p12_data = pkcs12.serialize_key_and_certificates(
        b"Apex Client", ck, cc, [ca_cert],
        serialization.BestAvailableEncryption(b"apex"))
except Exception:
    p12_data = pkcs12.serialize_key_and_certificates(
        b"Apex Client", ck, cc, [ca_cert],
        serialization.NoEncryption())
(ssl / "client.p12").write_bytes(p12_data)
print("Client + p12 ok")
print("=== ALL CERTS OK ===")
