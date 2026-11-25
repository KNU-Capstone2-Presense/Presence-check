"""Generate a private demo CA once and a LAN server certificate. Never publish keys."""
import argparse
import ipaddress
from datetime import datetime,timedelta,timezone
from pathlib import Path
from cryptography import x509
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID,ExtendedKeyUsageOID

p=argparse.ArgumentParser();p.add_argument('ip');args=p.parse_args()
address=ipaddress.ip_address(args.ip)
root=Path(__file__).resolve().parents[1]/'certs';root.mkdir(exist_ok=True)
now=datetime.now(timezone.utc)
def save_key(path,key):path.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
if (root/'ca-key.pem').exists() and (root/'ca.pem').exists():
    ca_key=serialization.load_pem_private_key((root/'ca-key.pem').read_bytes(),None)
    ca=x509.load_pem_x509_certificate((root/'ca.pem').read_bytes())
    if ca.not_valid_after_utc<now+timedelta(days=91):raise SystemExit('CA expires soon; create a new demo CA and reinstall it on the phone.')
    try:ca.extensions.get_extension_for_class(x509.SubjectKeyIdentifier)
    except x509.ExtensionNotFound:
        builder=x509.CertificateBuilder().subject_name(ca.subject).issuer_name(ca.issuer).public_key(ca.public_key()).serial_number(ca.serial_number).not_valid_before(ca.not_valid_before_utc).not_valid_after(ca.not_valid_after_utc)
        for extension in ca.extensions:builder=builder.add_extension(extension.value,extension.critical)
        ca=builder.add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()),False).sign(ca_key,hashes.SHA256())
        (root/'ca.pem').write_bytes(ca.public_bytes(serialization.Encoding.PEM))
elif (root/'ca-key.pem').exists() or (root/'ca.pem').exists():raise SystemExit('Incomplete CA files: restore the matching pair before proceeding.')
else:
    ca_key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'Attendance Demo CA')])
    ca=(x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(ca_key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now-timedelta(minutes=5)).not_valid_after(now+timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=True,path_length=0),True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()),False)
        .add_extension(x509.KeyUsage(False,False,False,False,False,True,True,False,False),True).sign(ca_key,hashes.SHA256()))
    save_key(root/'ca-key.pem',ca_key);(root/'ca.pem').write_bytes(ca.public_bytes(serialization.Encoding.PEM))
key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
cert=(x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'Attendance Demo Server')]))
      .issuer_name(ca.subject).public_key(key.public_key()).serial_number(x509.random_serial_number())
      .not_valid_before(now-timedelta(minutes=5)).not_valid_after(now+timedelta(days=90))
      .add_extension(x509.SubjectAlternativeName([x509.DNSName('localhost'),x509.IPAddress(ipaddress.ip_address('127.0.0.1')),x509.IPAddress(address)]),False)
      .add_extension(x509.BasicConstraints(ca=False,path_length=None),True)
      .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),False)
      .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()),False)
      .add_extension(x509.KeyUsage(True,False,True,False,False,False,False,False,False),True)
      .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),False).sign(ca_key,hashes.SHA256()))
save_key(root/'server-key.pem',key);(root/'server.pem').write_bytes(cert.public_bytes(serialization.Encoding.PEM))
public=root/'public';public.mkdir(exist_ok=True)
(public/'attendance-ca.cer').write_bytes(ca.public_bytes(serialization.Encoding.DER))
print(f'Student: https://{address}:8443/student/')
print('Admin: https://localhost:8443/')
print('CA SHA256: '+ca.fingerprint(hashes.SHA256()).hex())
