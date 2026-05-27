from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import httpx
import asyncio
from datetime import datetime, timezone
from typing import Optional

app = FastAPI(title="Threads Scanner")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 11; iPhone) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "X-IG-App-ID": "238260118697367",
    "X-FB-LSD": "AVqbxe3J_YA",
    "X-ASBD-ID": "129477",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-Mode": "cors",
    "Referer": "https://www.threads.net/",
}

def parse_ts(ts):
    if not ts:
        return None
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%d.%m.%Y %H:%M")
    except:
        return None

def extract_posts(data, found=None, depth=0):
    if found is None:
        found = []
    if depth > 15:
        return found
    if isinstance(data, dict):
        text = data.get("text", "")
        if isinstance(text, dict):
            text = text.get("text", "")
        like_count = data.get("like_count")
        taken_at = data.get("taken_at")
        if text and isinstance(like_count, (int, float)) and len(str(text)) > 3:
            user = data.get("user", {})
            username = user.get("username", "") if isinstance(user, dict) else ""
            found.append({
                "text": str(text)[:600],
                "like_count": int(like_count),
                "reply_count": int(data.get("direct_reply_count", 0)),
                "repost_count": int(data.get("repost_count", 0)),
                "timestamp": parse_ts(taken_at),
                "username": username,
            })
        for v in data.values():
            extract_posts(v, found, depth + 1)
    elif isinstance(data, list):
        for item in data:
            extract_posts(item, found, depth + 1)
    return found

@app.get("/", response_class=HTMLResponse)
async def root():
    with open("templates/index.html", "r", encoding="utf-8") as f:
        return f.read()

@app.get("/api/search")
async def search(
    q: str = Query(...),
    sort: str = Query("top"),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    limit: int = Query(20),
):
    posts = []
    errors = []

    endpoints = [
        {
            "url": "https://www.threads.net/api/v1/search/",
            "params": {"q": q, "count": 30, "search_surface": "top" if sort == "top" else "recent"},
        },
        {
            "url": "https://www.threads.net/api/v1/fbsearch/topsearch/",
            "params": {"context": "blended", "query": q, "include_reel": "false"},
        },
    ]

    async with httpx.AsyncClient(timeout=15, headers=HEADERS, follow_redirects=True) as client:
        for ep in endpoints:
            try:
                r = await client.get(ep["url"], params=ep["params"])
                if r.status_code == 200:
                    data = r.json()
                    found = extract_posts(data)
                    posts.extend(found)
                    if found:
                        break
                else:
                    errors.append(f"Status {r.status_code} from {ep['url']}")
            except Exception as e:
                errors.append(str(e))

    # Deduplicate
    seen, unique = set(), []
    for p in posts:
        key = p.get("text", "")[:50]
        if key not in seen:
            seen.add(key)
            unique.append(p)

    # Date filter
    if date_from or date_to:
        filtered = []
        for p in unique:
            ts = p.get("timestamp")
            if not ts:
                filtered.append(p)
                continue
            try:
                pd = datetime.strptime(ts, "%d.%m.%Y %H:%M").date()
                if date_from and pd < datetime.strptime(date_from, "%Y-%m-%d").date():
                    continue
                if date_to and pd > datetime.strptime(date_to, "%Y-%m-%d").date():
                    continue
                filtered.append(p)
            except:
                filtered.append(p)
        unique = filtered

    if sort == "top":
        unique.sort(key=lambda x: x.get("like_count", 0), reverse=True)

    return {
        "query": q,
        "sort": sort,
        "total": len(unique),
        "posts": unique[:limit],
        "errors": errors,
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
