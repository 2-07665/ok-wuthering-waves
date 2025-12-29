import json
import random
from datetime import datetime
from typing import Any

import requests

from custom.env_vars import env

WAVES_GAME_ID = 3
WAVES_CODE_999 = -999

ENV_ROLE_ID = "WAVES_ROLE_ID"
ENV_TOKEN = "WAVES_TOKEN"
ENV_DID = "WAVES_DID"
MAIN_URL = "https://api.kurobbs.com"
GAME_DATA_URL = f"{MAIN_URL}/gamer/widget/game3/getData"
SIGNIN_URL = f"{MAIN_URL}/encourage/signIn/v2"
SIGNIN_TASK_LIST_URL = f"{MAIN_URL}/encourage/signIn/initSignInV2"

SERVER_ID = "76402e5b20be2c39f095a152090afddc"
SERVER_ID_NET = "919752ae5ea09c1ced910dd668a63ffb"
NET_SERVER_ID_MAP = {
    5: "591d6af3a3090d8ea00d8f86cf6d7501",
    6: "6eb2a235b30d05efd77bedb5cf60999e",
    7: "86d52186155b148b5c138ceb41be9650",
    8: "919752ae5ea09c1ced910dd668a63ffb",
    9: "10cd7254d57e58ae560b15d51e34b4c",
}

CONTENT_TYPE = "application/x-www-form-urlencoded; charset=utf-8"
IOS_USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_6 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko)  KuroGameBox/2.9.0"
)
ANDROID_USER_AGENT = (
    "Mozilla/5.0 (Linux; Android 16; 25098PN5AC Build/BP2A.250605.031.A3; wv) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/143.0.7499.34 "
    "Mobile Safari/537.36 Kuro/2.9.0 KuroGameBox/2.9.0"
)


def _build_base_headers(dev_code: str | None = None) -> dict[str, str]:
    platform_source = random.choice(["ios", "android"])
    user_agent = IOS_USER_AGENT if platform_source == "ios" else ANDROID_USER_AGENT
    if dev_code is None:
        dev_code = f"127.0.0.1, {user_agent}"
    return {
        "source": platform_source,
        "Content-Type": CONTENT_TYPE,
        "User-Agent": user_agent,
        "devCode": dev_code,
    }


def _is_net(role_id: str) -> bool:
    try:
        return int(role_id) >= 200000000
    except (TypeError, ValueError):
        return False


def _get_server_id(role_id: str, server_id: str | None = None) -> str:
    if server_id:
        return server_id
    if _is_net(role_id):
        return NET_SERVER_ID_MAP.get(int(role_id) // 100000000, SERVER_ID_NET)
    return SERVER_ID


def _parse_response(resp: requests.Response) -> dict[str, Any]:
    try:
        raw_data = resp.json()
    except ValueError:
        return {"code": WAVES_CODE_999, "msg": "non-json response", "data": resp.text}

    if isinstance(raw_data, dict):
        data = raw_data.get("data")
        if isinstance(data, str):
            try:
                raw_data["data"] = json.loads(data)
            except Exception:
                pass

    return raw_data


class WavesDailyClient:
    def __init__(self, base_url: str | None = None, session: requests.Session | None = None) -> None:
        self.base_url = base_url or MAIN_URL
        self.session = session or requests.Session()

    def close(self) -> None:
        self.session.close()

    def get_daily_info(
        self,
        role_id: str | None = None,
        token: str | None = None,
        *,
        game_id: int = WAVES_GAME_ID,
        server_id: str | None = None,
        did: str | None = None,
        bat: str | None = None,
        dev_code: str | None = None,
        timeout: float = 10.0,
    ) -> dict[str, Any]:
        if role_id is None:
            role_id = env(ENV_ROLE_ID, required=True)
        if token is None:
            token = env(ENV_TOKEN, required=True)
        if did is None:
            did = env(ENV_DID, default="")

        headers = _build_base_headers(dev_code=dev_code)
        headers.update(
            {
                "token": token,
                "did": did or "",
                "b-at": bat or "",
            }
        )
        data = {
            "type": "2",
            "sizeType": "1",
            "gameId": game_id,
            "serverId": _get_server_id(role_id, server_id),
            "roleId": role_id,
        }

        try:
            resp = self.session.post(GAME_DATA_URL, headers=headers, data=data, timeout=timeout)
        except requests.RequestException as exc:
            return {"code": WAVES_CODE_999, "msg": str(exc), "data": None}

        return _parse_response(resp)

    def sign_in(
        self,
        role_id: str | None = None,
        token: str | None = None,
        *,
        server_id: str | None = None,
        timeout: float = 10.0,
    ) -> dict[str, Any]:
        if role_id is None:
            role_id = env(ENV_ROLE_ID, required=True)
        if token is None:
            token = env(ENV_TOKEN, required=True)

        headers = _build_base_headers(dev_code="")
        headers.update({"token": token})

        data = {
            "gameId": WAVES_GAME_ID,
            "serverId": _get_server_id(role_id, server_id),
            "roleId": role_id,
            "reqMonth": f"{datetime.now().month:02}",
        }

        try:
            resp = self.session.post(SIGNIN_URL, headers=headers, data=data, timeout=timeout)
        except requests.RequestException as exc:
            return {"code": WAVES_CODE_999, "msg": str(exc), "data": None}

        return _parse_response(resp)

    def sign_in_task_list(
        self,
        role_id: str | None = None,
        token: str | None = None,
        *,
        server_id: str | None = None,
        timeout: float = 10.0,
    ) -> dict[str, Any]:
        if role_id is None:
            role_id = env(ENV_ROLE_ID, required=True)
        if token is None:
            token = env(ENV_TOKEN, required=True)

        headers = _build_base_headers(dev_code="")
        headers.update({"token": token})
        data = {
            "gameId": WAVES_GAME_ID,
            "serverId": _get_server_id(role_id, server_id),
            "roleId": role_id,
        }

        try:
            resp = self.session.post(SIGNIN_TASK_LIST_URL, headers=headers, data=data, timeout=timeout)
        except requests.RequestException as exc:
            return {"code": WAVES_CODE_999, "msg": str(exc), "data": None}

        return _parse_response(resp)


def extract_daily_metrics(resp: dict[str, Any]) -> dict[str, int] | None:
    if not isinstance(resp, dict):
        return None
    if resp.get("success") is True:
        data = resp.get("data")
    elif resp.get("code") in (0, 200):
        data = resp.get("data")
    else:
        return None

    if not isinstance(data, dict):
        return None

    energy = data.get("energyData") or {}
    store_energy = data.get("storeEnergyData") or {}
    liveness = data.get("livenessData") or {}

    stamina = energy.get("cur")
    backup_stamina = store_energy.get("cur")
    daily_points = liveness.get("cur")

    if stamina is None or backup_stamina is None or daily_points is None:
        return None

    try:
        return {
            "stamina": int(stamina),
            "backup_stamina": int(backup_stamina),
            "daily_points": int(daily_points),
        }
    except (TypeError, ValueError):
        return None


def read_api_daily_info(
    client: WavesDailyClient | None = None,
) -> tuple[int | None, int | None, int | None]:
    """Return stamina, backup stamina, and daily points via Kuro API (no OCR)."""
    should_close = client is None
    client = client or WavesDailyClient()
    try:
        resp = client.get_daily_info()
        metrics = extract_daily_metrics(resp)
        if not metrics:
            return None, None, None
        stamina = metrics.get("stamina")
        backup_stamina = metrics.get("backup_stamina")
        daily_points = metrics.get("daily_points")
        return stamina, backup_stamina, daily_points
    except Exception:
        return None, None, None
    finally:
        if should_close:
            client.close()
