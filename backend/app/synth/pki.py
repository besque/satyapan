"""Local *test* PKI standing in for CCA-licensed DSC issuers, so digital-signature validation runs for real."""
from __future__ import annotations

import datetime as dt
import io
from functools import lru_cache
from pathlib import Path

from asn1crypto import keys as a_keys, x509 as a_x509
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from ..config import DATA

PKI_DIR = DATA / "test_pki"


def _name(cn: str, org: str = "Synthetic Test PKI") -> x509.Name:
    return x509.Name([x509.NameAttribute(NameOID.COUNTRY_NAME, "IN"),
                      x509.NameAttribute(NameOID.ORGANIZATION_NAME, org[:64]),
                      x509.NameAttribute(NameOID.COMMON_NAME, cn[:64])])


def _key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _cert(subject, issuer, pub, issuer_key, ca: bool, days=3650, start=None):
    start = start or dt.datetime(2023, 1, 1, tzinfo=dt.timezone.utc)
    b = (x509.CertificateBuilder().subject_name(subject).issuer_name(issuer).public_key(pub)
         .serial_number(x509.random_serial_number()).not_valid_before(start)
         .not_valid_after(start + dt.timedelta(days=days))
         .add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True))
    if ca:
        b = b.add_extension(x509.KeyUsage(digital_signature=True, content_commitment=False, key_encipherment=False,
                                          data_encipherment=False, key_agreement=False, key_cert_sign=True,
                                          crl_sign=True, encipher_only=False, decipher_only=False), critical=True)
    else:
        b = b.add_extension(x509.KeyUsage(digital_signature=True, content_commitment=True, key_encipherment=False,
                                          data_encipherment=False, key_agreement=False, key_cert_sign=False,
                                          crl_sign=False, encipher_only=False, decipher_only=False), critical=True)
    return b.sign(issuer_key, hashes.SHA256())


def _save(path: Path, obj, key=False):
    if key:
        path.write_bytes(obj.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                           serialization.NoEncryption()))
    else:
        path.write_bytes(obj.public_bytes(serialization.Encoding.PEM))


@lru_cache(maxsize=1)
def root_and_ca():
    PKI_DIR.mkdir(parents=True, exist_ok=True)
    rp, rk, cp, ck = (PKI_DIR / n for n in ("root.pem", "root.key", "ca.pem", "ca.key"))
    if not rp.exists():
        root_key = _key()
        root = _cert(_name("Synthetic Root CA for DSC (TEST ONLY)"), _name("Synthetic Root CA for DSC (TEST ONLY)"),
                     root_key.public_key(), root_key, ca=True, days=7300)
        ca_key = _key()
        ca = _cert(_name("Synthetic DSC Sub-CA Class 3 (TEST ONLY)"), root.subject, ca_key.public_key(), root_key, ca=True)
        _save(rp, root); _save(rk, root_key, key=True); _save(cp, ca); _save(ck, ca_key, key=True)
    load_c = lambda p: x509.load_pem_x509_certificate(p.read_bytes())  # noqa: E731
    load_k = lambda p: serialization.load_pem_private_key(p.read_bytes(), None)  # noqa: E731
    return load_c(rp), load_k(rk), load_c(cp), load_k(ck)


@lru_cache(maxsize=256)
def signer_for(common_name: str, org: str = "Synthetic Test PKI"):
    root, _, ca, ca_key = root_and_ca()
    k = _key()
    c = _cert(_name(common_name, org), ca.subject, k.public_key(), ca_key, ca=False, days=1100,
              start=dt.datetime(2024, 6, 1, tzinfo=dt.timezone.utc))
    return c, k


def _to_asn1_cert(c):
    return a_x509.Certificate.load(c.public_bytes(serialization.Encoding.DER))


def trust_roots():
    root, _, _, _ = root_and_ca()
    return [_to_asn1_cert(root)]


def sign_pdf(pdf_bytes: bytes, common_name: str, org: str = "Synthetic Test PKI", reason: str = "Authenticated") -> bytes:
    from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
    from pyhanko.sign import signers
    from pyhanko_certvalidator.registry import SimpleCertificateStore

    _, _, ca, _ = root_and_ca()
    cert, key = signer_for(common_name, org)
    signer = signers.SimpleSigner(
        signing_cert=_to_asn1_cert(cert),
        signing_key=a_keys.PrivateKeyInfo.load(key.private_bytes(serialization.Encoding.DER,
                                                                 serialization.PrivateFormat.PKCS8,
                                                                 serialization.NoEncryption())),
        cert_registry=SimpleCertificateStore.from_certs([_to_asn1_cert(ca)]),
    )
    w = IncrementalPdfFileWriter(io.BytesIO(pdf_bytes), strict=False)
    out = io.BytesIO()
    signers.sign_pdf(w, signers.PdfSignatureMetadata(field_name="DSC_Signature", reason=reason, name=common_name),
                     signer=signer, output=out)
    return out.getvalue()
