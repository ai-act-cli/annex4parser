import asyncio
import aiohttp
import feedparser

from annex4parser.rss_listener import UA, REGULATORY_RSS_FEEDS

URLS = [
    REGULATORY_RSS_FEEDS["eurlex_latest_legislation"],
    REGULATORY_RSS_FEEDS["ep_plenary"],
    # "https://ec.europa.eu/newsroom/clima/items/itemType/1041?format=rss",
]

async def main():
    async with aiohttp.ClientSession(headers={"User-Agent": UA}) as s:
        for u in URLS:
            async with s.get(u, timeout=30) as r:
                r.raise_for_status()
                raw = await r.text()
                f = feedparser.parse(raw)
                print(u, "→", len(f.entries), "items")
                if getattr(f, "bozo", False):
                    print("  Parsing error:", f.bozo_exception)

if __name__ == "__main__":
    asyncio.run(main())
