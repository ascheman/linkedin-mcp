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
    mentions: str = "",
) -> str:
    """Create a new LinkedIn post (text + optional image, max 3000 chars).

    Uses the legacy /v2/ugcPosts endpoint because the modern /rest/posts
    endpoint does not parse inline mention markup for member-authored
    posts (only for organization-authored posts).

    Args:
        text: The post text (max 3000 chars).
        image_path: Optional absolute path to an image file to attach.
        image_alt: Alt text for the image (accessibility).
        mentions: Optional JSON list of mentions to embed in the post
            text, e.g.
              '[{"text": "The Apache Software Foundation",
                 "urn": "urn:li:organization:215982"}]'
            Each entry's `text` must already appear verbatim in the
            post body (case-sensitive). The first occurrence is wrapped
            as a LinkedIn `CompanyAttributedEntity` annotation, so it
            renders as a styled link in the feed. Entity URNs are
            typically `urn:li:organization:NNN` for companies or
            `urn:li:person:XYZ` for people.
    """
    try:
        author = _get_person_urn()

        # Build the attributes array from `mentions` JSON.
        attributes = []
        if mentions.strip():
            try:
                mention_list = json.loads(mentions)
            except json.JSONDecodeError as e:
                return json.dumps({
                    "error": f"mentions parameter is not valid JSON: {e}",
                    "got": mentions,
                })
            if not isinstance(mention_list, list):
                return json.dumps({
                    "error": "mentions parameter must be a JSON list",
                    "got": mentions,
                })
            for m in mention_list:
                if not isinstance(m, dict):
                    continue
                mtext = m.get("text", "")
                murn = m.get("urn", "")
                if not mtext or not murn:
                    continue
                idx = text.find(mtext)
                if idx < 0:
                    return json.dumps({
                        "error": (
                            f"mention text {mtext!r} not found in post body"
                        ),
                    })
                # Pick the wrapping value based on the URN type.
                if ":person:" in murn:
                    value = {
                        "com.linkedin.common.MemberAttributedEntity": {
                            "member": murn,
                        },
                    }
                else:
                    value = {
                        "com.linkedin.common.CompanyAttributedEntity": {
                            "company": murn,
                        },
                    }
                attributes.append({
                    "length": len(mtext),
                    "start": idx,
                    "value": value,
                })

        # Optional image upload — uses the legacy /v2/assets API to fit
        # the ugcPosts schema (assets/uploadUrl + DigitalMediaAsset URN).
        asset_urn = None
        if image_path.strip():
            asset_urn = _upload_image_legacy(image_path, author)

        share_content = {
            "shareCommentary": {
                "text": text,
                "attributes": attributes,
            },
            "shareMediaCategory": "IMAGE" if asset_urn else "NONE",
        }
        if asset_urn:
            share_content["media"] = [{
                "status": "READY",
                "media": asset_urn,
                "title": {"text": image_alt or "Image"},
                "description": {"text": image_alt or ""},
            }]

        post_body = {
            "author": author,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": share_content,
            },
            "visibility": {
                "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC",
            },
        }

        resp = _client.post("/v2/ugcPosts", json=post_body)
        if resp.status_code >= 400:
            return json.dumps({
                "error": f"{resp.status_code} {resp.reason_phrase}",
                "body": resp.text,
                "request_body": post_body,
            }, indent=2)

        # /v2/ugcPosts returns the URN in the x-restli-id header.
        post_urn = resp.headers.get("x-restli-id", "")
        return json.dumps({
            "urn": post_urn,
            "url": f"https://www.linkedin.com/feed/update/{post_urn}/",
            "status": "published",
        }, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


def _upload_image_legacy(file_path: str, author: str) -> str:
    """Upload an image via /v2/assets and return its DigitalMediaAsset URN.

    Legacy two-step flow used by /v2/ugcPosts:
    1. POST /v2/assets?action=registerUpload to get an uploadUrl + asset URN
    2. PUT the binary to the uploadUrl
    """
    register_body = {
        "registerUploadRequest": {
            "recipes": ["urn:li:digitalmediaRecipe:feedshare-image"],
            "owner": author,
            "serviceRelationships": [{
                "relationshipType": "OWNER",
                "identifier": "urn:li:userGeneratedContent",
            }],
        }
    }
    resp = _client.post("/v2/assets?action=registerUpload", json=register_body)
    resp.raise_for_status()
    value = resp.json()["value"]
    upload_url = value["uploadMechanism"][
        "com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest"
    ]["uploadUrl"]
    asset_urn = value["asset"]

    with open(file_path, "rb") as f:
        img_data = f.read()

    upload_resp = httpx.post(
        upload_url,
        content=img_data,
        headers={
            "Authorization": f"Bearer {_access_token}",
            "Content-Type": "application/octet-stream",
        },
        timeout=60.0,
    )
    upload_resp.raise_for_status()

    return asset_urn


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
