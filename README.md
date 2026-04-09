# LinkedIn MCP Server

A lightweight [MCP](https://modelcontextprotocol.io/) server that lets Claude Code
create, read, and delete LinkedIn posts via LinkedIn's REST API.

## Tools

| Tool | Description |
|---|---|
| `create_post` | Publish a post (text + optional image, max 3000 chars) |
| `delete_post` | Delete a post by URN |
| `get_post` | Fetch a single post by URN |
| `get_my_posts` | Fetch own recent posts |
| `get_profile` | Get authenticated user's profile info |

**Note:** LinkedIn posts cannot be edited via API.
To correct a post, delete and re-post.

### Mentions

LinkedIn's REST Posts API does **not** support @mentions of organizations
or people via the API. Neither top-level `annotations` nor inline
`@[Name](urn)` markup work with the versioned `/rest/posts` endpoint.

To add @mentions, edit the post manually in the LinkedIn web UI after
creating it via the API. LinkedIn's editor will suggest organizations
and people as you type `@`.

## Setup

LinkedIn's API uses OAuth2 — the setup is more involved than Mastodon/Bluesky.

### 1. Create a LinkedIn Developer App

1. Go to https://developer.linkedin.com/ → **Create App**
2. Fill in: app name, LinkedIn Page (can create a minimal one), logo
3. Under **Auth** tab, add the redirect URL: `http://localhost:8080/callback`
4. Under **Products** tab, request access to **Share on LinkedIn** and
   **Sign In with LinkedIn using OpenID Connect**
5. Note your **Client ID** and **Client Secret**

### 2. Obtain an access token

LinkedIn uses a browser-based OAuth2 flow. A helper script is included:

```bash
cd linkedin-mcp
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python3 get-token.py <client_id> <client_secret>
```

This opens your browser for authorization, runs a temporary local server
to capture the callback, exchanges the code for a token, and prints it.
The token is valid for **60 days**.

### 3. Export the access token

Add to your shell profile (`.zshrc`, `.bashrc`, or `.envrc`):

```bash
export LINKEDIN_ACCESS_TOKEN="<your-access-token>"
```

The token is **not** stored in Claude Code's settings — it is inherited
from the shell environment at runtime.

**Important:** LinkedIn tokens expire after 60 days. You'll need to
re-run `get-token.py` when they expire. The server will error with
`401 Unauthorized` when the token is stale.

### 4. Configure in Claude Code

```bash
claude mcp add linkedin \
  --transport stdio \
  -- ${PWD}/.venv/bin/python3 \
     ${PWD}/server.py
```

Run this from the `linkedin-mcp` directory after activating the venv.

### 5. Verify

```
claude mcp list          # should show "linkedin"
```

Then in a Claude Code session, try: "Show me my LinkedIn profile" or
"Show me my recent LinkedIn posts".

## License

MIT
