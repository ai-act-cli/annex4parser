# eli_client.py
"""СПARQL клиент для работы с EUR-Lex CELLAR (CDM).

На публичном SPARQL endpoint Publications Office данные публикуются в **CDM**
(CELLAR) онтологии, а не в ELI. Этот модуль предоставляет асинхронный клиент,
который выполняет запросы в CDM и возвращает базовые метаданные документа.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional, Tuple
import aiohttp
from tenacity import retry, wait_exponential_jitter, stop_after_attempt

logger = logging.getLogger(__name__)

# SPARQL endpoint CELLAR
ELI_ENDPOINT = "https://publications.europa.eu/webapi/rdf/sparql"

# User-Agent для этичного скрапинга
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "Annex4ComplianceBot/1.2 (+https://your-domain.example/contact)"
)

# Базовый SPARQL запрос в CDM для получения цепочки WEMI и item-ресурсов
BASE_QUERY = """
PREFIX cdm:  <http://publications.europa.eu/ontology/cdm#>
PREFIX purl: <http://purl.org/dc/elements/1.1/>
PREFIX owl:  <http://www.w3.org/2002/07/owl#>
SELECT DISTINCT ?title ?date ?version ?item (STR(?format) AS ?format_str) WHERE {{
  ?work owl:sameAs <http://publications.europa.eu/resource/celex/{celex_id}> .
  ?expr cdm:expression_belongs_to_work ?work ;
        cdm:expression_uses_language ?lang .
  ?lang purl:identifier ?lc .
  VALUES ?lc {{"ENG" "EN"}}
  OPTIONAL {{ ?expr cdm:expression_title ?title }}
  OPTIONAL {{ ?work cdm:work_date_document ?date }}
  OPTIONAL {{ ?expr cdm:expression_version ?version }}
  ?manif cdm:manifestation_manifests_expression ?expr ;
         cdm:manifestation_type ?format .
  OPTIONAL {{ ?item1 cdm:item_belongs_to_manifestation ?manif . }}
  OPTIONAL {{ ?manif cdm:manifestation_has_item ?item2 . }}
  BIND(COALESCE(?item1, ?item2) AS ?item)
}}
ORDER BY DESC(?date)
"""


@retry(
    wait=wait_exponential_jitter(initial=5, max=300),
    stop=stop_after_attempt(5)
)
async def fetch_latest_eli(
    session: aiohttp.ClientSession,
    celex_id: str,
    endpoint: str = ELI_ENDPOINT
) -> Optional[Dict[str, Any]]:
    """Получить последнюю версию документа через SPARQL (CDM).
    
    Parameters
    ----------
    session : aiohttp.ClientSession
        HTTP сессия для запросов
    celex_id : str
        CELEX идентификатор документа (например, "32024R1689")
        
    Returns
    -------
    Optional[Dict[str, str]]
        Словарь с данными документа или None если не найден
    """
    query = BASE_QUERY.format(celex_id=celex_id)
    
    params = {"query": query, "format": "application/sparql-results+json"}

    try:
        async with session.get(
            endpoint,
            params=params,
            headers={
                "User-Agent": UA,
                "Accept": "application/sparql-results+json",
                "Accept-Language": "en",
            },
            timeout=aiohttp.ClientTimeout(total=30)
        ) as resp:
            resp.raise_for_status()
            data = await resp.json()
            
            rows = data.get("results", {}).get("bindings", [])
            if not rows:
                logger.warning(f"No results found for CELEX ID: {celex_id}")
                return None

            # Метаданные берём из первой строки
            first = rows[0]
            title = first.get("title", {}).get("value")
            date = first.get("date", {}).get("value")
            version = first.get("version", {}).get("value")

            items = []
            for r in rows:
                item_url = r.get("item", {}).get("value")
                fmt = r.get("format_str", {}).get("value")
                if item_url:
                    items.append({"url": item_url, "format": fmt})

            return {"title": title, "date": date, "version": version, "items": items}
            
    except aiohttp.ClientResponseError as e:
        logger.error(
            "ELI fetch failed: HTTP %s %s; url=%s; headers=%s",
            e.status,
            e.message,
            e.request_info.real_url,
            e.headers,
        )
        raise
    except aiohttp.ClientError as e:
        logger.error("HTTP error fetching ELI data for %s: %s", celex_id, e)
        raise
    except Exception as e:
        logger.exception("Unexpected error fetching ELI data for %s", celex_id)
        raise


async def fetch_regulation_by_celex(celex_id: str) -> Optional[Dict[str, str]]:
    """Удобная функция для получения регуляторного документа по CELEX ID."""
    async with aiohttp.ClientSession() as session:
        return await fetch_latest_eli(session, celex_id)


# Примеры использования
if __name__ == "__main__":
    async def test_eli():
        # EU AI Act CELEX ID
        result = await fetch_regulation_by_celex("32023R0988")
        if result:
            print(f"Title: {result['title']}")
            print(f"Version: {result['version']}")
            print(f"Date: {result['date']}")
            print(f"Items: {len(result['items'])}")
        else:
            print("Document not found")
    
    asyncio.run(test_eli())
