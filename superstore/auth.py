#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

import requests

CLIENT_ID = "ef9659ede6d44c7ab417f3485c11286c"
CLIENT_SECRET = "f470c525-c422-4070-832b-ae0a2490ea64"
TOKEN_ENDPOINT = "https://accounts.pcid.ca/oauth2/v1/token"
PCID_HEADERS = {
    "source": "ANDROID",
    "relying-party": "pcexpress-android",
}


class PcidAuthError(RuntimeError):
    pass


class TokenManager:
    def __init__(self, state_path: str | Path):
        self.state_path = Path(state_path)
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._session = requests.Session()
        self._state = self._load()

    def _load(self) -> dict:
        if self.state_path.exists():
            try:
                state = json.loads(self.state_path.read_text(encoding="utf-8"))
            except Exception as exc:
                raise PcidAuthError(f"Could not read token state: {exc}") from exc
        else:
            seed = os.getenv("PCEXPRESS_REFRESH_TOKEN")
            if not seed:
                raise PcidAuthError(
                    "No encrypted token state and PCEXPRESS_REFRESH_TOKEN is not set. "
                    "Run login_pcid.py again and update the GitHub secret."
                )
            state = {
                "refresh_token": seed,
                "access_token": None,
                "expires_at": 0,
            }

        if not state.get("refresh_token"):
            raise PcidAuthError("Token state contains no refresh token.")
        return state

    def _save(self) -> None:
        tmp = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        tmp.write_text(json.dumps(self._state), encoding="utf-8")
        os.replace(tmp, self.state_path)

    def get_access_token(self, force: bool = False) -> str:
        with self._lock:
            if (
                not force
                and self._state.get("access_token")
                and time.time() < float(self._state.get("expires_at", 0)) - 120
            ):
                return str(self._state["access_token"])
            return self._refresh()

    def _refresh(self) -> str:
        body = {
            "grant_type": "refresh_token",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "refresh_token": self._state["refresh_token"],
        }
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "okhttp/4.12.0",
            **PCID_HEADERS,
        }
        response = self._session.post(
            TOKEN_ENDPOINT,
            data=body,
            headers=headers,
            timeout=30,
        )
        if response.status_code != 200:
            raise PcidAuthError(
                "PC ID token refresh failed. The refresh-token chain may have expired "
                "or the latest encrypted state may be missing. Re-run login_pcid.py "
                f"and replace the PCEXPRESS_REFRESH_TOKEN secret. HTTP {response.status_code}."
            )

        data = response.json()
        self._state["access_token"] = data["access_token"]
        self._state["expires_at"] = time.time() + int(data.get("expires_in", 3600))
        if data.get("refresh_token"):
            self._state["refresh_token"] = data["refresh_token"]
        self._save()
        return str(self._state["access_token"])
