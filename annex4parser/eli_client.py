# eli_client.py
"""ELI SPARQL клиент для работы с EUR-Lex API.

Этот модуль предоставляет асинхронный клиент для работы с ELI (European Legislation Identifier)
SPARQL endpoint'ом. ELI даёт стабильные URI и метаданные для регуляторных документов.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Tuple
import aiohttp
from tenacity import retry, wait_exponential_jitter, stop_after_attempt

logger = logging.getLogger(__name__)

# ELI SPARQL endpoint
ELI_ENDPOINT = "https://publications.europa.eu/webapi/rdf/sparql"

# User-Agent для этичного скрапинга
UA = "Annex4ComplianceBot/1.2 (+https://your-domain.example/contact)"

# Базовый SPARQL запрос для получения последней версии регуляторного документа
BASE_QUERY = """
PREFIX eli: <http://data.europa.eu/eli/ontology#>
PREFIX dcterms: <http://purl.org/dc/terms/>
SELECT ?date ?version ?text ?title WHERE {{
  ?work eli:is_realised_by/eli:date_publication ?date ;
        eli:is_member_of /eli:id_local ?celex_id .
  ?expr eli:is_embodiment_of ?work ;
        eli:language <http://publications.europa.eu/resource/authority/language/ENG> ;
        eli:version ?version ;
        eli:content ?text .
  OPTIONAL {{ ?work dcterms:title ?title }}
  FILTER(?celex_id = "{celex_id}")
}}
ORDER BY DESC(?date) LIMIT 1
"""


@retry(
    wait=wait_exponential_jitter(initial=5, max=300),
    stop=stop_after_attempt(5)
)
async def fetch_latest_eli(
    session: aiohttp.ClientSession, 
    celex_id: str
) -> Optional[Dict[str, str]]:
    """Получить последнюю версию документа через ELI SPARQL.
    
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
    
    params = {
        "query": query,
        "format": "application/sparql-results+json"
    }
    
    try:
        async with session.get(
            ELI_ENDPOINT, 
            params=params,
            headers={"User-Agent": UA},
            timeout=aiohttp.ClientTimeout(total=30)
        ) as resp:
            resp.raise_for_status()
            data = await resp.json()
            
            if not data.get("results", {}).get("bindings"):
                logger.warning(f"No results found for CELEX ID: {celex_id}")
                return None
                
            result = data["results"]["bindings"][0]
            return {
                "date": result.get("date", {}).get("value"),
                "version": result.get("version", {}).get("value"),
                "text": result.get("text", {}).get("value"),
                "title": result.get("title", {}).get("value", "Unknown Title")
            }
            
    except aiohttp.ClientError as e:
        logger.error(f"HTTP error fetching ELI data for {celex_id}: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error fetching ELI data for {celex_id}: {e}")
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
            print(f"Text length: {len(result['text'])} chars")
        else:
            print("Document not found")
    
    asyncio.run(test_eli())
