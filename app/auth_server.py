import argparse
import hashlib
import logging
import secrets
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

from app.config import (
    TIKTOK_CLIENT_KEY,
    TIKTOK_CLIENT_SECRET,
    TIKTOK_OAUTH_SCOPES,
    TIKTOK_REDIRECT_URI,
)
from app.tiktok_oauth import exchange_authorization_code
from app.token_store import save_token_store


AUTHORIZE_URL = "https://www.tiktok.com/v2/auth/authorize/"
logger = logging.getLogger(__name__)


class OAuthLoginError(RuntimeError):
    pass


def build_authorization_url(
    client_key: str,
    redirect_uri: str,
    scopes: str,
    state: str,
    code_challenge: str,
) -> str:
    query = urlencode(
        {
            "client_key": client_key,
            "response_type": "code",
            "scope": scopes,
            "redirect_uri": redirect_uri,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
    )
    return f"{AUTHORIZE_URL}?{query}"


def create_code_verifier() -> str:
    return secrets.token_urlsafe(64)


def create_code_challenge(code_verifier: str) -> str:
    return hashlib.sha256(code_verifier.encode("ascii")).hexdigest()


def run_login_server(open_browser: bool = True) -> None:
    missing = [
        name
        for name, value in {
            "TIKTOK_CLIENT_KEY": TIKTOK_CLIENT_KEY,
            "TIKTOK_CLIENT_SECRET": TIKTOK_CLIENT_SECRET,
            "TIKTOK_REDIRECT_URI": TIKTOK_REDIRECT_URI,
        }.items()
        if not value
    ]
    if missing:
        raise OAuthLoginError(f"Missing required .env setting(s): {', '.join(missing)}")

    redirect = urlparse(TIKTOK_REDIRECT_URI)
    if not redirect.hostname or not redirect.port:
        raise OAuthLoginError(
            "TIKTOK_REDIRECT_URI must include a hostname and port for the local "
            "callback server, for example http://127.0.0.1:8080/callback"
        )

    state = secrets.token_urlsafe(32)
    code_verifier = create_code_verifier()
    code_challenge = create_code_challenge(code_verifier)
    done = threading.Event()
    result: dict[str, str] = {}

    class CallbackHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            logger.info(format, *args)

        def do_GET(self) -> None:
            callback = urlparse(self.path)
            expected_path = redirect.path or "/"

            if callback.path != expected_path:
                self.send_response(404)
                self.end_headers()
                return

            params = parse_qs(callback.query)

            if params.get("state", [""])[0] != state:
                self._send_text(400, "Invalid OAuth state. Login rejected.")
                done.set()
                return

            if params.get("error"):
                result["error"] = params.get("error_description", params["error"])[0]
                self._send_text(400, f"TikTok authorization failed: {result['error']}")
                done.set()
                return

            code = params.get("code", [""])[0]
            if not code:
                self._send_text(400, "TikTok did not return an authorization code.")
                done.set()
                return

            try:
                token_data = exchange_authorization_code(
                    client_key=TIKTOK_CLIENT_KEY or "",
                    client_secret=TIKTOK_CLIENT_SECRET or "",
                    code=code,
                    redirect_uri=TIKTOK_REDIRECT_URI or "",
                    code_verifier=code_verifier,
                )
                save_token_store(token_data)
            except Exception as exc:
                result["error"] = str(exc)
                self._send_text(500, f"Token exchange failed: {exc}")
            else:
                result["ok"] = "true"
                self._send_text(
                    200,
                    "TikTok login complete. You can close this browser tab and run the uploader.",
                )
            finally:
                done.set()

        def _send_text(self, status: int, message: str) -> None:
            body = message.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer((redirect.hostname, redirect.port), CallbackHandler)
    auth_url = build_authorization_url(
        client_key=TIKTOK_CLIENT_KEY or "",
        redirect_uri=TIKTOK_REDIRECT_URI or "",
        scopes=TIKTOK_OAUTH_SCOPES,
        state=state,
        code_challenge=code_challenge,
    )

    logger.info("OAuth callback server listening on %s", TIKTOK_REDIRECT_URI)
    print("Open this URL to log in with TikTok:")
    print(auth_url)

    if open_browser:
        webbrowser.open(auth_url)

    try:
        while not done.is_set():
            server.handle_request()
    finally:
        server.server_close()

    if result.get("error"):
        raise OAuthLoginError(result["error"])


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

    parser = argparse.ArgumentParser(description="Start TikTok OAuth login")
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Print the authorization URL without opening a browser",
    )
    args = parser.parse_args()

    run_login_server(open_browser=not args.no_browser)


if __name__ == "__main__":
    main()
