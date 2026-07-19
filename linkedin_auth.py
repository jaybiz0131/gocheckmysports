#!/usr/bin/env python3
"""
Run-once LinkedIn OAuth helper (and re-run every ~60 days when the token expires).

Prereqs (one time, at linkedin.com/developers):
  - An app with the products "Share on LinkedIn" and "Sign In with LinkedIn using OpenID
    Connect", and redirect URL http://localhost:8914/callback on its Auth tab.

USAGE
  LINKEDIN_CLIENT_ID=... LINKEDIN_CLIENT_SECRET=... python3 linkedin_auth.py
It opens the consent URL, catches the redirect locally, exchanges the code, and prints the
LINKEDIN_ACCESS_TOKEN and LINKEDIN_PERSON_URN to store as repo secrets.
"""

import http.server
import json
import os
import secrets
import sys
import urllib.parse
import urllib.request
import webbrowser

PORT = 8914
REDIRECT = f"http://localhost:{PORT}/callback"
SCOPES = "openid profile w_member_social"


def main():
    cid = os.environ.get("LINKEDIN_CLIENT_ID", "").strip()
    csec = os.environ.get("LINKEDIN_CLIENT_SECRET", "").strip()
    if not (cid and csec):
        print("Set LINKEDIN_CLIENT_ID and LINKEDIN_CLIENT_SECRET first.")
        return 1

    state = secrets.token_urlsafe(16)
    auth_url = ("https://www.linkedin.com/oauth/v2/authorization?" + urllib.parse.urlencode({
        "response_type": "code", "client_id": cid, "redirect_uri": REDIRECT,
        "state": state, "scope": SCOPES}))
    print("Opening LinkedIn consent page (approve as Jack):\n" + auth_url)
    webbrowser.open(auth_url)

    code_holder = {}

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if q.get("code"):
                code_holder["code"] = q["code"][0]
            elif q.get("error"):
                code_holder["error"] = f'{q["error"][0]}: {(q.get("error_description") or [""])[0]}'
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<h2>Done. You can close this tab and return to the terminal.</h2>")

        def log_message(self, *a):
            pass

    with http.server.HTTPServer(("localhost", PORT), H) as srv:
        srv.timeout = 300
        print(f"Waiting for the redirect on {REDIRECT} (up to 5 minutes) ...")
        # browsers fire favicon/preflight requests too; keep serving until the real
        # callback (code or error) arrives or we time out
        import time
        deadline = time.time() + 300
        while time.time() < deadline and not code_holder:
            srv.handle_request()

    if code_holder.get("error"):
        print("LinkedIn returned an error:", code_holder["error"])
        return 1
    code = code_holder.get("code")
    if not code:
        print("No code received within 5 minutes; run again.")
        return 1

    data = urllib.parse.urlencode({
        "grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT,
        "client_id": cid, "client_secret": csec}).encode()
    with urllib.request.urlopen(urllib.request.Request(
            "https://www.linkedin.com/oauth/v2/accessToken", data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"}), timeout=30) as r:
        tok = json.loads(r.read())
    access = tok["access_token"]
    days = tok.get("expires_in", 0) // 86400

    with urllib.request.urlopen(urllib.request.Request(
            "https://api.linkedin.com/v2/userinfo",
            headers={"Authorization": f"Bearer {access}"}), timeout=30) as r:
        me = json.loads(r.read())
    urn = f"urn:li:person:{me['sub']}"

    print("\n=== store these as gocheckmycrypto repo secrets ===")
    print("LINKEDIN_ACCESS_TOKEN =", access)
    print("LINKEDIN_PERSON_URN   =", urn)
    print(f"(token lives ~{days} days; re-run this script to renew)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
