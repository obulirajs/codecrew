from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
import uvicorn
from fastapi import FastAPI

app = FastAPI()

@app.get("/health")
async def health_check():
    return {"status": "healthy"}


@app.get("/hello")
async def hello(name: str = ""):
    return {"message": f"Hello, {name}!"}


@app.get("/current")
async def current_place_and_time():
    place = None
    error = None
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get("http://ip-api.com/json/")
            resp.raise_for_status()
            data = resp.json()
        if data.get("status") == "fail":
            error = data.get("message", "geolocation lookup failed")
        else:
            place = {
                "city": data.get("city"),
                "region": data.get("regionName"),
                "country": data.get("country"),
                "lat": data.get("lat"),
                "lon": data.get("lon"),
                "timezone": data.get("timezone"),
            }
    except httpx.HTTPError as exc:
        error = str(exc)

    tz_name = place["timezone"] if place else "UTC"
    now_utc = datetime.now(ZoneInfo("UTC"))
    now_local = now_utc.astimezone(ZoneInfo(tz_name))

    return {
        "place": place,
        "error": error,
        "datetime_utc": now_utc.isoformat(),
        "datetime_local": now_local.isoformat(),
    }

if __name__ == "__main__":
    uvicorn.run("server:app",host="127.0.0.1", port=5000, reload=True)