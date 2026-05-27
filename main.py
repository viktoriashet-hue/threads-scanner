from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import httpx
import asyncio
from datetime import datetime
from typing import Optional

app = FastAPI(title="Threads Scanner")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

APIFY_TOKEN = "apify_api_XLGUhUI0AKBH0iMkpArUdDoFHI013R05LASg"
ACTOR_ID = "watcher.data~search-threads-by-keywords"


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
    async with httpx.AsyncClient(timeout=60) as client:

        # Запускаем актор
        run_resp = await client.post(
            f"https://api.apify.com/v2/acts/{ACTOR_ID}/runs",
            params={"token": APIFY_TOKEN},
            json={
                "searchKeywords": [q],
                "maxItemsPerKeyword": limit,
                "sortByRecent": sort == "recent",
            }
        )

        if run_resp.status_code != 201:
            return JSONResponse({"error": "Не удалось запустить скрапер", "posts": [], "total": 0})

        run_id = run_resp.json()["data"]["id"]

        # Ждём завершения
        for _ in range(30):
            await asyncio.sleep(3)
            status_resp = await client.get(
                f"https://api.apify.com/v2/actor-runs/{run_id}",
                params={"token": APIFY_TOKEN}
            )
            status = status_resp.json()["data"]["status"]
            if status == "SUCCEEDED":
                break
            if status in ["FAILED", "ABORTED", "TIMED-OUT"]:
                return JSONResponse({"error": f"Скрапер завершился с ошибкой: {status}", "posts": [], "total": 0})

        # Получаем результаты
        dataset_id = status_resp.json()["data"]["defaultDatasetId"]
        results_resp = await client.get(
            f"https://api.apify.com/v2/datasets/{dataset_id}/items",
            params={"token": APIFY_TOKEN, "format": "json"}
        )

        items = results_resp.json()

        posts = []
        for item in items:
            ts = item.get("timestamp") or item.get("taken_at") or item.get("createdAt", "")
            try:
                if isinstance(ts, (int, float)):
                    ts = datetime.fromtimestamp(ts).strftime("%d.%m.%Y %H:%M")
                elif ts:
                    ts = str(ts)[:16].replace("T", " ")
            except:
                ts = ""

            posts.append({
                "text": str(item.get("text") or item.get("content") or item.get("caption") or "")[:600],
                "like_count": int(item.get("likesCount") or item.get("like_count") or 0),
                "reply_count": int(item.get("repliesCount") or item.get("reply_count") or 0),
                "repost_count": int(item.get("repostsCount") or item.get("repost_count") or 0),
                "timestamp": ts,
                "username": str(item.get("username") or item.get("ownerUsername") or ""),
            })

        # Фильтр по дате
        if date_from or date_to:
            filtered = []
            for p in posts:
                ts = p.get("timestamp", "")
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
            posts = filtered

        if sort == "top":
            posts.sort(key=lambda x: x.get("like_count", 0), reverse=True)

        return {
            "query": q,
            "sort": sort,
            "total": len(posts),
            "posts": posts[:limit],
            "errors": [],
        }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
