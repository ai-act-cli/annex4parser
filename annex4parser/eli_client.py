# eli_client.py
"""СПARQL клиент для работы с EUR-Lex CELLAR (CDM).

На публичном SPARQL endpoint Publications Office данные публикуются в **CDM**
(CELLAR) онтологии, а не в ELI. Этот модуль предоставляет асинхронный клиент,
который выполняет запросы в CDM и возвращает базовые метаданные документа.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Tuple
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

# Базовый SPARQL запрос в CDM для получения последней версии документа
BASE_QUERY = """
PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
SELECT ?date ?version ?text ?title WHERE {{
  ?w cdm:resource_legal_id_celex "{celex_id}" .
  ?expr cdm:expression_belongs_to_work ?w .
  ?expr cdm:expression_uses_language <http://publications.europa.eu/resource/authority/language/ENG> .
  OPTIONAL {{ ?expr cdm:expression_title ?title }}
  OPTIONAL {{ ?w cdm:work_date_document ?date }}
  OPTIONAL {{ ?expr cdm:expression_version ?version }}
  OPTIONAL {{
    ?expr cdm:expression_legal_resource ?res .
    ?res cdm:legal_resource_legal_text ?text
  }}
}}
ORDER BY DESC(?date)
LIMIT 1
"""


@retry(
    wait=wait_exponential_jitter(initial=5, max=300),
    stop=stop_after_attempt(5)
)
async def fetch_latest_eli(
    session: aiohttp.ClientSession,
    celex_id: str
) -> Optional[Dict[str, str]]:
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
    
    params = {
        "query": query,
        "format": "application/sparql-results+json"
    }
    
    try:
        async with session.get(
            ELI_ENDPOINT,
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
