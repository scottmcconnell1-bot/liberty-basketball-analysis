"""Encrypt or decrypt the Liberty detections archive (AES-256-GCM, scrypt key).

    python encrypted-archive/archive_crypto.py encrypt <folder> <out.enc>
    python encrypted-archive/archive_crypto.py decrypt <in.enc> <out folder>

The passphrase is read from the LIBERTY_ARCHIVE_PASSPHRASE environment variable,
or typed at a prompt. It is never stored in this repository. Without it the file
cannot be opened, so keep it somewhere that is not only on this computer.

File layout: b"LBAENC1\\0" + salt(16) + nonce(12) + AES-GCM ciphertext+tag.
The header is authenticated, so any change to the file makes decrypt fail.
"""

from __future__ import annotations

import getpass
import io
import os
import secrets
import sys
import tarfile
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

MAGIC = b"LBAENC1\0"
SCRYPT_N = 2**17
SCRYPT_R = 8
SCRYPT_P = 1


def _key(passphrase: str, salt: bytes) -> bytes:
    return Scrypt(salt=salt, length=32, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P).derive(
        passphrase.encode("utf-8")
    )


def _passphrase() -> str:
    value = os.environ.get("LIBERTY_ARCHIVE_PASSPHRASE") or getpass.getpass("Passphrase: ")
    if len(value) < 20:
        raise SystemExit("Passphrase is too short (use at least 20 characters).")
    return value


def encrypt(folder: Path, out: Path) -> None:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as tar:  # contents are already compressed
        for path in sorted(folder.iterdir()):
            if path.is_file():
                tar.add(path, arcname=path.name)
    salt, nonce = secrets.token_bytes(16), secrets.token_bytes(12)
    header = MAGIC + salt + nonce
    sealed = AESGCM(_key(_passphrase(), salt)).encrypt(nonce, buffer.getvalue(), header)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(header + sealed)


def decrypt(source: Path, folder: Path) -> None:
    blob = source.read_bytes()
    if blob[: len(MAGIC)] != MAGIC:
        raise SystemExit("Not a Liberty archive file.")
    header = blob[: len(MAGIC) + 28]
    salt = header[len(MAGIC) : len(MAGIC) + 16]
    nonce = header[len(MAGIC) + 16 :]
    try:
        plain = AESGCM(_key(_passphrase(), salt)).decrypt(nonce, blob[len(header) :], header)
    except InvalidTag:
        raise SystemExit("Wrong passphrase, or the file was changed.")
    folder.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(plain), mode="r") as tar:
        for member in tar.getmembers():
            if not member.isfile() or Path(member.name).name != member.name:
                raise SystemExit(f"Unexpected item in archive: {member.name}")
            (folder / member.name).write_bytes(tar.extractfile(member).read())


def main(argv: list[str]) -> int:
    if len(argv) != 4 or argv[1] not in ("encrypt", "decrypt"):
        print(__doc__)
        return 2
    (encrypt if argv[1] == "encrypt" else decrypt)(Path(argv[2]), Path(argv[3]))
    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
