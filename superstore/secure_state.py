#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

ROOT = Path(__file__).resolve().parent
PLAIN = ROOT / ".state" / "pcid_token_state.json"
ENCRYPTED = ROOT / "data" / "pcid_state.enc"


def cipher() -> Fernet:
    key = os.getenv("PCEXPRESS_STATE_KEY")
    if not key:
        raise SystemExit("PCEXPRESS_STATE_KEY is not set.")
    try:
        return Fernet(key.encode("ascii"))
    except Exception as exc:
        raise SystemExit(
            "PCEXPRESS_STATE_KEY is invalid. Generate one with: "
            "python -c \"import os,base64; print(base64.urlsafe_b64encode(os.urandom(32)).decode())\""
        ) from exc


def decrypt() -> None:
    PLAIN.parent.mkdir(parents=True, exist_ok=True)
    if not ENCRYPTED.exists():
        # First run is seeded from the GitHub refresh-token secret by auth.py.
        print("No encrypted state yet; first run will use PCEXPRESS_REFRESH_TOKEN.")
        return

    try:
        plaintext = cipher().decrypt(ENCRYPTED.read_bytes())
    except InvalidToken as exc:
        raise SystemExit(
            "Could not decrypt pcid_state.enc. The PCEXPRESS_STATE_KEY does not match."
        ) from exc

    PLAIN.write_bytes(plaintext)
    print("Decrypted PC ID state.")


def encrypt() -> None:
    if not PLAIN.exists():
        raise SystemExit("No plaintext token state exists to encrypt.")
    ENCRYPTED.parent.mkdir(parents=True, exist_ok=True)
    ENCRYPTED.write_bytes(cipher().encrypt(PLAIN.read_bytes()))
    print("Encrypted latest PC ID state.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["encrypt", "decrypt"])
    args = parser.parse_args()
    {"encrypt": encrypt, "decrypt": decrypt}[args.action]()
