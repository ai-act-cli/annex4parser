import asyncio
import aiohttp
import feedparser

URLS = [
    "https://eur-lex.europa.eu/EN/display-feed.rss?rssId=162",
    "https://www.europarl.europa.eu/rss/doc/debates-plenary/en.xml",
    # "https://ec.europa.eu/newsroom/clima/items/itemType/1041?format=rss",
]

async def main():
    async with aiohttp.ClientSession() as s:
        for u in URLS:
            async with s.get(u, timeout=30) as r:
                r.raise_for_status()
                raw = await r.text()
                f = feedparser.parse(raw)
                print(u, "→", len(f.entries), "items")

if __name__ == "__main__":
    asyncio.run(main())
