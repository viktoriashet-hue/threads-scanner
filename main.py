from fastapi import FastAPI, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from playwright.async_api import async_playwright
import asyncio
import json
import re
from datetime import datetime, timezone
from typing import Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Threads Scanner")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")


def parse_timestamp(ts):
    if not ts:
        return None
    try:
        if isinstance(ts, (int, float)):
            return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
        return str(ts)
    except:
        return None


def extract_posts_from_json(data, found=None, depth=0):
    if found is None:
        found = []
    if depth > 15:
        return found
    if isinstance(data, dict):
        text_val = data.get("text", "")
        if isinstance(text_val, dict):
            text_val = text_val.get("text", "")
        like_count = data.get("like_count")
        taken_at = data.get("taken_at") or data.get("device_timestamp")
        if text_val and isinstance(like_count, (int, float)):
            found.append({
                "text": str(text_val)[:500],
                "like_count": int(like_count),
                "reply_count": int(data.get("text_post_app_info", {}).get("direct_reply_count", 0) if isinstance(data.get("text_post_app_info"), dict) else data.get("direct_reply_count", 0)),
                "repost_count": int(data.get("repost_count", 0)),
                "timestamp": parse_timestamp(taken_at),
                "username": data.get("user", {}).get("username", "") if isinstance(data.get("user"), dict) else "",
                "post_id": str(data.get("pk", data.get("id", ""))),
            })
        for v in data.values():
            extract_posts_from_json(v, found, depth + 1)
    elif isinstance(data, list):
        for item in data:
            extract_posts_from_json(item, found, depth + 1)
    return found


@app.get("/", response_class=HTMLResponse)
async def root():
    with open("templates/index.html", "r", encoding="utf-8") as f:
        return f.read()


@app.get("/api/search")
async def search_threads(
    q: str = Query(..., description="Search query"),
    sort: str = Query("top", description="top or recent"),
    date_from: Optional[str] = Query(None, description="Filter from date YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="Filter to date YYYY-MM-DD"),
    limit: int = Query(20, description="Max results"),
):
    if not q.strip():
        return JSONResponse({"error": "Query is empty"}, status_code=400)

    posts = []
    errors = []

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled",
                ]
            )
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 800},
                locale="en-US",
            )

            page = await context.new_page()
            captured = []

            async def handle_response(response):
                url = response.url
                if response.status == 200 and ("graphql" in url or "api/v1" in url or "search" in url.lower()):
                    try:
                        ct = response.headers.get("content-type", "")
                        if "json" in ct:
                            data = await response.json()
                            found = extract_posts_from_json(data)
                            if found:
                                captured.extend(found)
                                logger.info(f"Captured {len(found)} posts from {url[:80]}")
                    except Exception as e:
                        pass

            page.on("response", handle_response)

            serp_type = "default" if sort == "top" else "recent"
            url = f"https://www.threads.net/search?q={q}&serp_type={serp_type}"
            logger.info(f"Navigating to: {url}")

            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(4000)

                # Scroll to load more
                for _ in range(4):
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await page.wait_for_timeout(1500)

            except Exception as e:
                errors.append(str(e))
                logger.warning(f"Navigation error: {e}")

            await browser.close()

            posts = captured

    except Exception as e:
        logger.error(f"Playwright error: {e}")
        errors.append(str(e))

    # Deduplicate
    seen = set()
    unique = []
    for p in posts:
        key = p.get("post_id") or p.get("text", "")[:50]
        if key and key not in seen:
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
                post_date = datetime.fromisoformat(ts.replace("Z", "+00:00")).date()
                if date_from and post_date < datetime.strptime(date_from, "%Y-%m-%d").date():
                    continue
                if date_to and post_date > datetime.strptime(date_to, "%Y-%m-%d").date():
                    continue
                filtered.append(p)
            except:
                filtered.append(p)
        unique = filtered

    # Sort
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
