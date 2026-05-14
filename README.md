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

`create_post` supports `@mentions` via the optional `mentions` parameter.
Pass a JSON list of `{text, urn}` pairs — each entry's `text` must
appear verbatim (case-sensitive) in the post body, and the first
occurrence is wrapped as a LinkedIn `CompanyAttributedEntity`
(or `MemberAttributedEntity` if the URN is `urn:li:person:...`).

```python
create_post(
    text="Thanks to The Apache Software Foundation for the Maven project.",
    mentions='[{"text": "The Apache Software Foundation", "urn": "urn:li:organization:215982"}]',
)
```

Entity URNs are typically `urn:li:organization:NNN` for companies or
`urn:li:person:XYZ` for people. To find an organization's URN, open its
LinkedIn page and look for `facetCurrentCompany=NNNNNN` in any embedded
employee-directory link — that number is the org ID.

#### Why we use the legacy `/v2/ugcPosts` endpoint

Posts go through LinkedIn's legacy `/v2/ugcPosts` API (with the
matching `/v2/assets` image-upload flow) rather than the newer
`/rest/posts` endpoint. The newer API documents inline
`@[Name](urn)` mention markup, but only parses it for
organization-authored posts; member-authored posts pass the markup
through as literal text. The legacy endpoint's explicit
`shareCommentary.attributes` array works for member-authored posts,
which is what this MCP serves.

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
