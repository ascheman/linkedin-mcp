#!/usr/bin/env python3
"""
LinkedIn MCP Server — create, read, and delete LinkedIn posts via Claude Code.

LinkedIn's API uses OAuth2. You need a Developer App + an access token.
See README.md for the one-time setup.

Environment variables:
    LINKEDIN_ACCESS_TOKEN  OAuth2 access token (obtain via browser flow)
"""

import json
import os
import sys
from urllib.parse import quote

import httpx
from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# LinkedIn API client
# ---------------------------------------------------------------------------

_access_token = os.environ.get("LINKEDIN_ACCESS_TOKEN", "")

if not _access_token:
    print("LINKEDIN_ACCESS_TOKEN environment variable is required", file=sys.stderr)
    sys.exit(1)

_API_BASE = "https://api.linkedin.com"
_HEADERS = {
    "Authorization": f"Bearer {_access_token}",
    "LinkedIn-Version": "202604",
    "X-Restli-Protocol-Version": "2.0.0",
    "Content-Type": "application/json",
}

_client = httpx.Client(base_url=_API_BASE, headers=_HEADERS, timeout=30.0)

# Cache the user's profile URN (needed for creating posts)
_person_urn = None


def _get_person_urn() -> str:
    """Get the current user's person URN (cached after first call)."""
    global _person_urn
    if _person_urn is None:
        resp = _client.get("/v2/userinfo")
        resp.raise_for_status()
        data = resp.json()
        _person_urn = f"urn:li:person:{data['sub']}"
    return _person_urn


# ---------------------------------------------------------------------------
# MCP server
# ---------------------------------------------------------------------------

mcp = FastMCP("linkedin")


@mcp.tool()
def get_profile() -> str:
    """Get the current authenticated user's LinkedIn profile info."""
    try:
        resp = _client.get("/v2/userinfo")
        resp.raise_for_status()
        data = resp.json()
        return json.dumps({
            "sub": data.get("sub"),
            "name": data.get("name"),
            "email": data.get("email"),
            "picture": data.get("picture"),
            "person_urn": f"urn:li:person:{data.get('sub')}",
        }, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def create_post(
    text: str,
    image_path: str = "",
    image_alt: str = "",
) -> str:
    """Create a new LinkedIn post (text + optional image, max 3000 chars).

    Args:
        text: The post text (max 3000 chars).
        image_path: Optional absolute path to an image file to attach.
        image_alt: Alt text for the image (accessibility).
    """
    try:
        author = _get_person_urn()

        # Handle image upload if provided
        image_urn = None
        if image_path.strip():
            image_urn = _upload_image(image_path, author)

        # Build post body
        post_body = {
            "author": author,
            "lifecycleState": "PUBLISHED",
            "visibility": "PUBLIC",
            "commentary": text,
            "distribution": {
                "feedDistribution": "MAIN_FEED",
                "targetEntities": [],
                "thirdPartyDistributionChannels": [],
            },
        }

        if image_urn:
            post_body["content"] = {
                "media": {
                    "title": image_alt or "Image",
                    "id": image_urn,
                    "altText": image_alt or "",
                }
            }

        resp = _client.post("/rest/posts", json=post_body)
        if resp.status_code >= 400:
            return json.dumps({
                "error": f"{resp.status_code} {resp.reason_phrase}",
                "body": resp.text,
                "request_body": post_body,
            }, indent=2)

        # LinkedIn returns the post URN in the x-restli-id header
        post_urn = resp.headers.get("x-restli-id", "")

        return json.dumps({
            "urn": post_urn,
            "url": f"https://www.linkedin.com/feed/update/{post_urn}/",
            "status": "published",
        }, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


def _upload_image(file_path: str, author: str) -> str:
    """Upload an image to LinkedIn and return its media URN.

    LinkedIn image upload is a two-step process:
    1. Register the upload (get an upload URL + image URN)
    2. Upload the binary to that URL
    """
    # Step 1: Register upload
    register_body = {
        "initializeUploadRequest": {
            "owner": author,
        }
    }
    resp = _client.post("/rest/images?action=initializeUpload", json=register_body)
    resp.raise_for_status()
    upload_data = resp.json()["value"]
    upload_url = upload_data["uploadUrl"]
    image_urn = upload_data["image"]

    # Step 2: Upload binary
    with open(file_path, "rb") as f:
        img_data = f.read()

    upload_resp = httpx.put(
        upload_url,
        content=img_data,
        headers={
            "Authorization": f"Bearer {_access_token}",
            "Content-Type": "application/octet-stream",
        },
        timeout=60.0,
    )
    upload_resp.raise_for_status()

    return image_urn


@mcp.tool()
def delete_post(post_urn: str) -> str:
    """Delete a LinkedIn post by its URN.

    Args:
        post_urn: The post URN (e.g. urn:li:share:7654321 or urn:li:ugcPost:7654321).
    """
    try:
        encoded_urn = quote(post_urn, safe="")
        resp = _client.delete(f"/rest/posts/{encoded_urn}")
        resp.raise_for_status()
        return json.dumps({"deleted": post_urn})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def get_post(post_urn: str) -> str:
    """Fetch a single LinkedIn post by its URN.

    Args:
        post_urn: The post URN.
    """
    try:
        encoded_urn = quote(post_urn, safe="")
        resp = _client.get(f"/rest/posts/{encoded_urn}")
        resp.raise_for_status()
        data = resp.json()
        return json.dumps({
            "urn": data.get("id", post_urn),
            "author": data.get("author"),
            "commentary": data.get("commentary"),
            "created_at": data.get("createdAt"),
            "lifecycle_state": data.get("lifecycleState"),
            "visibility": data.get("visibility"),
        }, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def get_my_posts(count: int = 10) -> str:
    """Fetch my own recent LinkedIn posts.

    Args:
        count: Number of posts to fetch (max 50).
    """
    try:
        author = _get_person_urn()
        resp = _client.get(
            "/rest/posts",
            params={
                "author": author,
                "q": "author",
                "count": min(count, 50),
                "sortBy": "LAST_MODIFIED",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        posts = []
        for p in data.get("elements", []):
            posts.append({
                "urn": p.get("id"),
                "commentary": p.get("commentary", "")[:200],
                "created_at": p.get("createdAt"),
                "lifecycle_state": p.get("lifecycleState"),
                "url": f"https://www.linkedin.com/feed/update/{p.get('id', '')}/",
            })
        return json.dumps(posts, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


if __name__ == "__main__":
    mcp.run(transport="stdio")
