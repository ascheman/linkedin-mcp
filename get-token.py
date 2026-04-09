#!/usr/bin/env python3
"""
OAuth2 helper to obtain a LinkedIn access token.

Usage:
    python3 get-token.py <client_id> <client_secret>

Opens a browser for authorization, captures the callback on localhost:8080,
exchanges the code for an access token, and prints it.

The token is valid for 60 days. Export it as:
    export LINKEDIN_ACCESS_TOKEN="<printed-token>"
"""

import http.server
import sys
import urllib.parse
import webbrowser

import httpx

PORT = 8080
REDIRECT_URI = f"http://localhost:{PORT}/callback"
SCOPES = "openid profile email w_member_social"
AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)

    client_id = sys.argv[1]
    client_secret = sys.argv[2]

    # Step 1: Open browser for user authorization
    auth_params = urllib.parse.urlencode({
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPES,
        "state": "claude-code-mcp",
    })
    auth_url = f"{AUTH_URL}?{auth_params}"
    print(f"Opening browser for LinkedIn authorization...")
    print(f"URL: {auth_url}\n")
    webbrowser.open(auth_url)

    # Step 2: Start local server to capture the callback
    auth_code = None

    class CallbackHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            nonlocal auth_code
            query = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(query)

            if "code" in params:
                auth_code = params["code"][0]
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(
                    b"<h1>Authorization successful!</h1>"
                    b"<p>You can close this tab and return to the terminal.</p>"
                )
            elif "error" in params:
                self.send_response(400)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                error = params.get("error_description", params["error"])
                self.wfile.write(f"<h1>Error: {error}</h1>".encode())
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, format, *args):
            pass  # Suppress request logging

    server = http.server.HTTPServer(("localhost", PORT), CallbackHandler)
    print(f"Waiting for callback on http://localhost:{PORT}/callback ...")
    server.handle_request()
    server.server_close()

    if not auth_code:
        print("ERROR: No authorization code received.", file=sys.stderr)
        sys.exit(1)

    print(f"Authorization code received. Exchanging for access token...\n")

    # Step 3: Exchange code for access token
    resp = httpx.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": auth_code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": REDIRECT_URI,
        },
    )
    resp.raise_for_status()
    token_data = resp.json()

    access_token = token_data["access_token"]
    expires_in = token_data.get("expires_in", "unknown")

    print("=" * 60)
    print(f"Access token (expires in {expires_in} seconds):\n")
    print(access_token)
    print()
    print("Export it:")
    print(f'export LINKEDIN_ACCESS_TOKEN="{access_token}"')
    print("=" * 60)


if __name__ == "__main__":
    main()
