import argparse
import logging

import requests

from app.token_store import save_token_store


TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"

logger = logging.getLogger(__name__)


class TikTokOAuthError(RuntimeError):
    pass


def exchange_authorization_code(
    client_key: str,
    client_secret: str,
    code: str,
    redirect_uri: str,
    code_verifier: str | None = None,
) -> dict:
    payload = {
        "client_key": client_key,
        "client_secret": client_secret,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
    }

    if code_verifier:
        payload["code_verifier"] = code_verifier

    return _post_token_request(payload)


def refresh_access_token(
    client_key: str,
    client_secret: str,
    refresh_token: str,
) -> dict:
    return _post_token_request(
        {
            "client_key": client_key,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }
    )


def _post_token_request(payload: dict[str, str]) -> dict:
    missing = [key for key, value in payload.items() if not value]
    if missing:
        raise TikTokOAuthError(f"Missing OAuth value(s): {', '.join(missing)}")

    response = requests.post(
        TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data=payload,
        timeout=30,
    )

    data = _json_response(response)
    if response.status_code >= 400 or "error" in data:
        raise TikTokOAuthError(f"TikTok OAuth request failed: {data}")

    access_token = data.get("access_token")
    refresh_token = data.get("refresh_token")
    if not access_token:
        raise TikTokOAuthError(f"TikTok OAuth response missing access_token: {data}")

    logger.info("Received TikTok access token; expires_in=%s", data.get("expires_in"))
    if refresh_token:
        logger.info(
            "Received TikTok refresh token; refresh_expires_in=%s",
            data.get("refresh_expires_in"),
        )

    return data


def _json_response(response: requests.Response) -> dict:
    try:
        return response.json()
    except ValueError as exc:
        raise TikTokOAuthError(
            f"TikTok returned non-JSON response: status={response.status_code}; "
            f"body={response.text}"
        ) from exc


def main() -> None:
    parser = argparse.ArgumentParser(description="TikTok OAuth helper")
    subparsers = parser.add_subparsers(dest="command", required=True)

    exchange_parser = subparsers.add_parser("exchange-code")
    exchange_parser.add_argument("--client-key", required=True)
    exchange_parser.add_argument("--client-secret", required=True)
    exchange_parser.add_argument("--code", required=True)
    exchange_parser.add_argument("--redirect-uri", required=True)
    exchange_parser.add_argument("--code-verifier")

    refresh_parser = subparsers.add_parser("refresh-token")
    refresh_parser.add_argument("--client-key", required=True)
    refresh_parser.add_argument("--client-secret", required=True)
    refresh_parser.add_argument("--refresh-token", required=True)

    args = parser.parse_args()

    if args.command == "exchange-code":
        token_data = exchange_authorization_code(
            client_key=args.client_key,
            client_secret=args.client_secret,
            code=args.code,
            redirect_uri=args.redirect_uri,
            code_verifier=args.code_verifier,
        )
    else:
        token_data = refresh_access_token(
            client_key=args.client_key,
            client_secret=args.client_secret,
            refresh_token=args.refresh_token,
        )

    if args.command == "exchange-code":
        save_token_store(token_data)
        print("Saved TikTok OAuth tokens to token_store.json")
    else:
        print_token_values(token_data)


def print_token_values(token_data: dict) -> None:
    redacted = dict(token_data)
    for key in ("access_token", "refresh_token"):
        if redacted.get(key):
            redacted[key] = f"{redacted[key][:8]}...{redacted[key][-4:]}"

    for key, value in redacted.items():
        print(f"{key}={value}")


if __name__ == "__main__":
    main()
