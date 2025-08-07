import pytest
import asyncio
import json
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime
from aioresponses import aioresponses
from tenacity import RetryError, stop_after_attempt, wait_exponential_jitter
from annex4parser.eli_client import fetch_latest_eli
from annex4parser.rss_listener import fetch_rss
from tests.helpers import (
    create_test_source, mock_eli_response, mock_rss_feed,
    setup_aiohttp_mocks, create_retry_test_data, mock_html_content
)


class TestRetryMechanisms:
    """Тесты для retry механизмов"""

    @pytest.mark.skip(reason="skip by user request")
    @pytest.mark.asyncio
    async def test_eli_fetch_success_first_attempt(self):
        """Тест успешного ELI fetch с первой попытки"""
        from aiohttp import ClientSession
        with aioresponses() as m:
            setup_aiohttp_mocks(
                m, "https://publications.europa.eu/webapi/rdf/sparql?format=application%2Fsparql-results%2Bjson&query=%0APREFIX+eli%3A+%3Chttp%3A%2F%2Fdata.europa.eu%2Feli%2Fontology%23%3E%0APREFIX+dcterms%3A+%3Chttp%3A%2F%2Fpurl.org%2Fdc%2Fterms%2F%3E%0ASELECT+%3Fdate+%3Fversion+%3Ftext+%3Ftitle+WHERE+%7B%0A++%3Fwork+eli%3Ais_realised_by%2Feli%3Adate_publication+%3Fdate+%3B%0A++++++++eli%3Ais_member_of+%2Feli%3Aid_local+%3Fcelex_id+.%0A++%3Fexpr+eli%3Ais_embodiment_of+%3Fwork+%3B%0A++++++++eli%3Alanguage+%3Chttp%3A%2F%2Fpublications.europa.eu%2Fresource%2Fauthority%2Flanguage%2FENG%3E+%3B%0A++++++++eli%3Aversion+%3Fversion+%3B%0A++++++++eli%3Acontent+%3Ftext+.%0A++OPTIONAL+%7B+%3Fwork+dcterms%3Atitle+%3Ftitle+%7D%0A++FILTER%28%3Fcelex_id+%3D+%2232024R1689%22%29%0A%7D%0AORDER+BY+DESC%28%3Fdate%29+LIMIT+1%0A",
                content=json.dumps(mock_eli_response())
            )
            async with ClientSession() as session:
                result = await fetch_latest_eli(session, "32024R1689")
            assert result is not None
            assert "title" in result
            assert "text" in result

    @pytest.mark.skip(reason="skip by user request")
    @pytest.mark.asyncio
    async def test_eli_fetch_retry_on_failure(self):
        """Тест retry для ELI fetch при неудаче"""
        from aiohttp import ClientSession
        with aioresponses() as m:
            # Первые 2 попытки неудачные, третья успешная
            m.add(
                url="https://publications.europa.eu/webapi/rdf/sparql?format=application%2Fsparql-results%2Bjson&query=%0APREFIX+eli%3A+%3Chttp%3A%2F%2Fdata.europa.eu%2Feli%2Fontology%23%3E%0APREFIX+dcterms%3A+%3Chttp%3A%2F%2Fpurl.org%2Fdc%2Fterms%2F%3E%0ASELECT+%3Fdate+%3Fversion+%3Ftext+%3Ftitle+WHERE+%7B%0A++%3Fwork+eli%3Ais_realised_by%2Feli%3Adate_publication+%3Fdate+%3B%0A++++++++eli%3Ais_member_of+%2Feli%3Aid_local+%3Fcelex_id+.%0A++%3Fexpr+eli%3Ais_embodiment_of+%3Fwork+%3B%0A++++++++eli%3Alanguage+%3Chttp%3A%2F%2Fpublications.europa.eu%2Fresource%2Fauthority%2Flanguage%2FENG%3E+%3B%0A++++++++eli%3Aversion+%3Fversion+%3B%0A++++++++eli%3Acontent+%3Ftext+.%0A++OPTIONAL+%7B+%3Fwork+dcterms%3Atitle+%3Ftitle+%7D%0A++FILTER%28%3Fcelex_id+%3D+%2232024R1689%22%29%0A%7D%0AORDER+BY+DESC%28%3Fdate%29+LIMIT+1%0A",
                method="GET",
                status=500,
                body="Server Error"
            )
            m.add(
                url="https://publications.europa.eu/webapi/rdf/sparql?format=application%2Fsparql-results%2Bjson&query=%0APREFIX+eli%3A+%3Chttp%3A%2F%2Fdata.europa.eu%2Feli%2Fontology%23%3E%0APREFIX+dcterms%3A+%3Chttp%3A%2F%2Fpurl.org%2Fdc%2Fterms%2F%3E%0ASELECT+%3Fdate+%3Fversion+%3Ftext+%3Ftitle+WHERE+%7B%0A++%3Fwork+eli%3Ais_realised_by%2Feli%3Adate_publication+%3Fdate+%3B%0A++++++++eli%3Ais_member_of+%2Feli%3Aid_local+%3Fcelex_id+.%0A++%3Fexpr+eli%3Ais_embodiment_of+%3Fwork+%3B%0A++++++++eli%3Alanguage+%3Chttp%3A%2F%2Fpublications.europa.eu%2Fresource%2Fauthority%2Flanguage%2FENG%3E+%3B%0A++++++++eli%3Aversion+%3Fversion+%3B%0A++++++++eli%3Acontent+%3Ftext+.%0A++OPTIONAL+%7B+%3Fwork+dcterms%3Atitle+%3Ftitle+%7D%0A++FILTER%28%3Fcelex_id+%3D+%2232024R1689%22%29%0A%7D%0AORDER+BY+DESC%28%3Fdate%29+LIMIT+1%0A",
                method="GET",
                status=503,
                body="Service Unavailable"
            )
            m.add(
                url="https://publications.europa.eu/webapi/rdf/sparql?format=application%2Fsparql-results%2Bjson&query=%0APREFIX+eli%3A+%3Chttp%3A%2F%2Fdata.europa.eu%2Feli%2Fontology%23%3E%0APREFIX+dcterms%3A+%3Chttp%3A%2F%2Fpurl.org%2Fdc%2Fterms%2F%3E%0ASELECT+%3Fdate+%3Fversion+%3Ftext+%3Ftitle+WHERE+%7B%0A++%3Fwork+eli%3Ais_realised_by%2Feli%3Adate_publication+%3Fdate+%3B%0A++++++++eli%3Ais_member_of+%2Feli%3Aid_local+%3Fcelex_id+.%0A++%3Fexpr+eli%3Ais_embodiment_of+%3Fwork+%3B%0A++++++++eli%3Alanguage+%3Chttp%3A%2F%2Fpublications.europa.eu%2Fresource%2Fauthority%2Flanguage%2FENG%3E+%3B%0A++++++++eli%3Aversion+%3Fversion+%3B%0A++++++++eli%3Acontent+%3Ftext+.%0A++OPTIONAL+%7B+%3Fwork+dcterms%3Atitle+%3Ftitle+%7D%0A++FILTER%28%3Fcelex_id+%3D+%2232024R1689%22%29%0A%7D%0AORDER+BY+DESC%28%3Fdate%29+LIMIT+1%0A",
                method="GET",
                status=200,
                body=json.dumps(mock_eli_response())
            )
            async with ClientSession() as session:
                result = await fetch_latest_eli(session, "32024R1689")
            assert result is not None
            assert "title" in result

    @pytest.mark.skip(reason="skip by user request")
    @pytest.mark.asyncio
    async def test_eli_fetch_max_retries_exceeded(self):
        """Тест превышения максимального количества retry для ELI"""
        from aiohttp import ClientSession
        with aioresponses() as m:
            # Все попытки неудачные
            for _ in range(6):  # Больше чем max_attempts (5)
                m.add(
                    url="https://publications.europa.eu/webapi/rdf/sparql?format=application%2Fsparql-results%2Bjson&query=%0APREFIX+eli%3A+%3Chttp%3A%2F%2Fdata.europa.eu%2Feli%2Fontology%23%3E%0APREFIX+dcterms%3A+%3Chttp%3A%2F%2Fpurl.org%2Fdc%2Fterms%2F%3E%0ASELECT+%3Fdate+%3Fversion+%3Ftext+%3Ftitle+WHERE+%7B%0A++%3Fwork+eli%3Ais_realised_by%2Feli%3Adate_publication+%3Fdate+%3B%0A++++++++eli%3Ais_member_of+%2Feli%3Aid_local+%3Fcelex_id+.%0A++%3Fexpr+eli%3Ais_embodiment_of+%3Fwork+%3B%0A++++++++eli%3Alanguage+%3Chttp%3A%2F%2Fpublications.europa.eu%2Fresource%2Fauthority%2Flanguage%2FENG%3E+%3B%0A++++++++eli%3Aversion+%3Fversion+%3B%0A++++++++eli%3Acontent+%3Ftext+.%0A++OPTIONAL+%7B+%3Fwork+dcterms%3Atitle+%3Ftitle+%7D%0A++FILTER%28%3Fcelex_id+%3D+%2232024R1689%22%29%0A%7D%0AORDER+BY+DESC%28%3Fdate%29+LIMIT+1%0A",
                    method="GET",
                    status=500,
                    body="Server Error"
                )
            async with ClientSession() as session:
                try:
                    result = await fetch_latest_eli(session, "32024R1689")
                except Exception:
                    result = None
                assert result is None

    @pytest.mark.skip(reason="skip by user request")
    @pytest.mark.asyncio
    async def test_rss_fetch_success_first_attempt(self):
        """Тест успешного RSS fetch с первой попытки"""
        import aiohttp
        with aioresponses() as m:
            setup_aiohttp_mocks(
                m, "https://ec.europa.eu/info/feed/ai-act",
                content=mock_rss_feed()
            )
            async with aiohttp.ClientSession() as session:
                result = await fetch_rss(session, "https://ec.europa.eu/info/feed/ai-act")
            assert result is not None
            assert len(result) > 0
            assert isinstance(result[0], tuple)
            assert len(result[0]) == 3  # title, link, description

    @pytest.mark.skip(reason="skip by user request")
    @pytest.mark.asyncio
    async def test_rss_fetch_retry_on_failure(self):
        """Тест retry для RSS fetch при неудаче"""
        import aiohttp
        with aioresponses() as m:
            # Первые 2 попытки неудачные, третья успешная
            m.add(
                url="https://ec.europa.eu/info/feed/ai-act",
                method="GET",
                status=500,
                body="Server Error"
            )
            m.add(
                url="https://ec.europa.eu/info/feed/ai-act",
                method="GET",
                status=503,
                body="Service Unavailable"
            )
            m.add(
                url="https://ec.europa.eu/info/feed/ai-act",
                method="GET",
                status=200,
                body=mock_rss_feed()
            )
            async with aiohttp.ClientSession() as session:
                result = await fetch_rss(session, "https://ec.europa.eu/info/feed/ai-act")
            assert result is not None
            assert len(result) > 0

    @pytest.mark.skip(reason="skip by user request")
    @pytest.mark.asyncio
    async def test_rss_fetch_max_retries_exceeded(self):
        """Тест превышения максимального количества retry для RSS"""
        import aiohttp
        with aioresponses() as m:
            # Все попытки неудачные
            for _ in range(6):  # Больше чем max_attempts (5)
                m.add(
                    url="https://ec.europa.eu/info/feed/ai-act",
                    method="GET",
                    status=500,
                    body="Server Error"
                )
            async with aiohttp.ClientSession() as session:
                try:
                    result = await fetch_rss(session, "https://ec.europa.eu/info/feed/ai-act")
                except Exception:
                    result = None
                assert result is None

    @pytest.mark.skip(reason="skip by user request")
    @pytest.mark.asyncio
    async def test_retry_with_different_status_codes(self):
        """Тест retry с разными кодами статуса"""
        test_data = create_retry_test_data()
        
        for test_case in test_data:
            with aioresponses() as m:
                # Настраиваем ответы в зависимости от тестового случая
                if test_case["should_retry"]:
                    # Добавляем несколько неудачных попыток
                    for _ in range(test_case["attempt"]):
                        m.add(
                            url="https://publications.europa.eu/webapi/rdf/sparql?format=application%2Fsparql-results%2Bjson&query=%0APREFIX+eli%3A+%3Chttp%3A%2F%2Fdata.europa.eu%2Feli%2Fontology%23%3E%0APREFIX+dcterms%3A+%3Chttp%3A%2F%2Fpurl.org%2Fdc%2Fterms%2F%3E%0ASELECT+%3Fdate+%3Fversion+%3Ftext+%3Ftitle+WHERE+%7B%0A++%3Fwork+eli%3Ais_realised_by%2Feli%3Adate_publication+%3Fdate+%3B%0A++++++++eli%3Ais_member_of+%2Feli%3Aid_local+%3Fcelex_id+.%0A++%3Fexpr+eli%3Ais_embodiment_of+%3Fwork+%3B%0A++++++++eli%3Alanguage+%3Chttp%3A%2F%2Fpublications.europa.eu%2Fresource%2Fauthority%2Flanguage%2FENG%3E+%3B%0A++++++++eli%3Aversion+%3Fversion+%3B%0A++++++++eli%3Acontent+%3Ftext+.%0A++OPTIONAL+%7B+%3Fwork+dcterms%3Atitle+%3Ftitle+%7D%0A++FILTER%28%3Fcelex_id+%3D+%2232024R1689%22%29%0A%7D%0AORDER+BY+DESC%28%3Fdate%29+LIMIT+1%0A",
                            method="GET",
                            status=test_case["status"],
                            body="Error"
                        )
                    
                    # Добавляем успешный ответ в конце
                    m.add(
                        url="https://publications.europa.eu/webapi/rdf/sparql?format=application%2Fsparql-results%2Bjson&query=%0APREFIX+eli%3A+%3Chttp%3A%2F%2Fdata.europa.eu%2Feli%2Fontology%23%3E%0APREFIX+dcterms%3A+%3Chttp%3A%2F%2Fpurl.org%2Fdc%2Fterms%2F%3E%0ASELECT+%3Fdate+%3Fversion+%3Ftext+%3Ftitle+WHERE+%7B%0A++%3Fwork+eli%3Ais_realised_by%2Feli%3Adate_publication+%3Fdate+%3B%0A++++++++eli%3Ais_member_of+%2Feli%3Aid_local+%3Fcelex_id+.%0A++%3Fexpr+eli%3Ais_embodiment_of+%3Fwork+%3B%0A++++++++eli%3Alanguage+%3Chttp%3A%2F%2Fpublications.europa.eu%2Fresource%2Fauthority%2Flanguage%2FENG%3E+%3B%0A++++++++eli%3Aversion+%3Fversion+%3B%0A++++++++eli%3Acontent+%3Ftext+.%0A++OPTIONAL+%7B+%3Fwork+dcterms%3Atitle+%3Ftitle+%7D%0A++FILTER%28%3Fcelex_id+%3D+%2232024R1689%22%29%0A%7D%0AORDER+BY+DESC%28%3Fdate%29+LIMIT+1%0A",
                        method="GET",
                        status=200,
                        body=json.dumps(mock_eli_response())
                    )
                else:
                    # Добавляем только неудачный ответ
                    m.add(
                        url="https://publications.europa.eu/webapi/rdf/sparql?format=application%2Fsparql-results%2Bjson&query=%0APREFIX+eli%3A+%3Chttp%3A%2F%2Fdata.europa.eu%2Feli%2Fontology%23%3E%0APREFIX+dcterms%3A+%3Chttp%3A%2F%2Fpurl.org%2Fdc%2Fterms%2F%3E%0ASELECT+%3Fdate+%3Fversion+%3Ftext+%3Ftitle+WHERE+%7B%0A++%3Fwork+eli%3Ais_realised_by%2Feli%3Adate_publication+%3Fdate+%3B%0A++++++++eli%3Ais_member_of+%2Feli%3Aid_local+%3Fcelex_id+.%0A++%3Fexpr+eli%3Ais_embodiment_of+%3Fwork+%3B%0A++++++++eli%3Alanguage+%3Chttp%3A%2F%2Fpublications.europa.eu%2Fresource%2Fauthority%2Flanguage%2FENG%3E+%3B%0A++++++++eli%3Aversion+%3Fversion+%3B%0A++++++++eli%3Acontent+%3Ftext+.%0A++OPTIONAL+%7B+%3Fwork+dcterms%3Atitle+%3Ftitle+%7D%0A++FILTER%28%3Fcelex_id+%3D+%2232024R1689%22%29%0A%7D%0AORDER+BY+DESC%28%3Fdate%29+LIMIT+1%0A",
                        method="GET",
                        status=test_case["status"],
                        body="Error"
                    )
                
                import aiohttp
                async with aiohttp.ClientSession() as session:
                    try:
                        result = await fetch_latest_eli(session, "32024R1689")
                    except Exception:
                        result = None
                
                if test_case["should_retry"] and test_case["status"] in [500, 503]:
                    assert result is not None
                elif test_case["status"] == 404:
                    assert result is None
                elif test_case["attempt"] >= 5:
                    assert result is None

    @pytest.mark.skip(reason="skip by user request")
    @pytest.mark.asyncio
    async def test_retry_with_network_errors(self):
        """Тест retry с сетевыми ошибками"""
        import aiohttp
        with aioresponses() as m:
            # Сетевые ошибки
            m.add(
                url="https://publications.europa.eu/webapi/rdf/sparql?format=application%2Fsparql-results%2Bjson&query=%0APREFIX+eli%3A+%3Chttp%3A%2F%2Fdata.europa.eu%2Feli%2Fontology%23%3E%0APREFIX+dcterms%3A+%3Chttp%3A%2F%2Fpurl.org%2Fdc%2Fterms%2F%3E%0ASELECT+%3Fdate+%3Fversion+%3Ftext+%3Ftitle+WHERE+%7B%0A++%3Fwork+eli%3Ais_realised_by%2Feli%3Adate_publication+%3Fdate+%3B%0A++++++++eli%3Ais_member_of+%2Feli%3Aid_local+%3Fcelex_id+.%0A++%3Fexpr+eli%3Ais_embodiment_of+%3Fwork+%3B%0A++++++++eli%3Alanguage+%3Chttp%3A%2F%2Fpublications.europa.eu%2Fresource%2Fauthority%2Flanguage%2FENG%3E+%3B%0A++++++++eli%3Aversion+%3Fversion+%3B%0A++++++++eli%3Acontent+%3Ftext+.%0A++OPTIONAL+%7B+%3Fwork+dcterms%3Atitle+%3Ftitle+%7D%0A++FILTER%28%3Fcelex_id+%3D+%2232024R1689%22%29%0A%7D%0AORDER+BY+DESC%28%3Fdate%29+LIMIT+1%0A",
                method="GET",
                exception=asyncio.TimeoutError("Request timeout")
            )
            m.add(
                url="https://publications.europa.eu/webapi/rdf/sparql?format=application%2Fsparql-results%2Bjson&query=%0APREFIX+eli%3A+%3Chttp%3A%2F%2Fdata.europa.eu%2Feli%2Fontology%23%3E%0APREFIX+dcterms%3A+%3Chttp%3A%2F%2Fpurl.org%2Fdc%2Fterms%2F%3E%0ASELECT+%3Fdate+%3Fversion+%3Ftext+%3Ftitle+WHERE+%7B%0A++%3Fwork+eli%3Ais_realised_by%2Feli%3Adate_publication+%3Fdate+%3B%0A++++++++eli%3Ais_member_of+%2Feli%3Aid_local+%3Fcelex_id+.%0A++%3Fexpr+eli%3Ais_embodiment_of+%3Fwork+%3B%0A++++++++eli%3Alanguage+%3Chttp%3A%2F%2Fpublications.europa.eu%2Fresource%2Fauthority%2Flanguage%2FENG%3E+%3B%0A++++++++eli%3Aversion+%3Fversion+%3B%0A++++++++eli%3Acontent+%3Ftext+.%0A++OPTIONAL+%7B+%3Fwork+dcterms%3Atitle+%3Ftitle+%7D%0A++FILTER%28%3Fcelex_id+%3D+%2232024R1689%22%29%0A%7D%0AORDER+BY+DESC%28%3Fdate%29+LIMIT+1%0A",
                method="GET",
                exception=ConnectionError("Connection failed")
            )
            m.add(
                url="https://publications.europa.eu/webapi/rdf/sparql?format=application%2Fsparql-results%2Bjson&query=%0APREFIX+eli%3A+%3Chttp%3A%2F%2Fdata.europa.eu%2Feli%2Fontology%23%3E%0APREFIX+dcterms%3A+%3Chttp%3A%2F%2Fpurl.org%2Fdc%2Fterms%2F%3E%0ASELECT+%3Fdate+%3Fversion+%3Ftext+%3Ftitle+WHERE+%7B%0A++%3Fwork+eli%3Ais_realised_by%2Feli%3Adate_publication+%3Fdate+%3B%0A++++++++eli%3Ais_member_of+%2Feli%3Aid_local+%3Fcelex_id+.%0A++%3Fexpr+eli%3Ais_embodiment_of+%3Fwork+%3B%0A++++++++eli%3Alanguage+%3Chttp%3A%2F%2Fpublications.europa.eu%2Fresource%2Fauthority%2Flanguage%2FENG%3E+%3B%0A++++++++eli%3Aversion+%3Fversion+%3B%0A++++++++eli%3Acontent+%3Ftext+.%0A++OPTIONAL+%7B+%3Fwork+dcterms%3Atitle+%3Ftitle+%7D%0A++FILTER%28%3Fcelex_id+%3D+%2232024R1689%22%29%0A%7D%0AORDER+BY+DESC%28%3Fdate%29+LIMIT+1%0A",
                method="GET",
                status=200,
                body=json.dumps(mock_eli_response())
            )
            
            import aiohttp
            async with aiohttp.ClientSession() as session:
                result = await fetch_latest_eli(session, "32024R1689")
            
            assert result is not None

    @pytest.mark.skip(reason="skip by user request")
    @pytest.mark.asyncio
    async def test_retry_with_exponential_backoff(self):
        """Тест exponential backoff в retry"""
        import aiohttp
        url = "https://publications.europa.eu/webapi/rdf/sparql?format=application%2Fsparql-results%2Bjson&query=%0APREFIX+eli%3A+%3Chttp%3A%2F%2Fdata.europa.eu%2Feli%2Fontology%23%3E%0APREFIX+dcterms%3A+%3Chttp%3A%2F%2Fpurl.org%2Fdc%2Fterms%2F%3E%0ASELECT+%3Fdate+%3Fversion+%3Ftext+%3Ftitle+WHERE+%7B%0A++%3Fwork+eli%3Ais_realised_by%2Feli%3Adate_publication+%3Fdate+%3B%0A++++++++eli%3Ais_member_of+%2Feli%3Aid_local+%3Fcelex_id+.%0A++%3Fexpr+eli%3Ais_embodiment_of+%3Fwork+%3B%0A++++++++eli%3Alanguage+%3Chttp%3A%2F%2Fpublications.europa.eu%2Fresource%2Fauthority%2Flanguage%2FENG%3E+%3B%0A++++++++eli%3Aversion+%3Fversion+%3B%0A++++++++eli%3Acontent+%3Ftext+.%0A++OPTIONAL+%7B+%3Fwork+dcterms%3Atitle+%3Ftitle+%7D%0A++FILTER%28%3Fcelex_id+%3D+%2232024R1689%22%29%0A%7D%0AORDER+BY+DESC%28%3Fdate%29+LIMIT+1%0A"
        with aioresponses() as m:
            # Добавляем несколько неудачных попыток
            for _ in range(3):
                m.add(
                    url=url,
                    method="GET",
                    status=500,
                    body="Server Error"
                )
            # Добавляем успешный ответ
            m.add(
                url=url,
                method="GET",
                status=200,
                body=json.dumps(mock_eli_response())
            )
            start_time = datetime.now()
            async with aiohttp.ClientSession() as session:
                try:
                    result = await fetch_latest_eli(session, "32024R1689")
                except Exception:
                    result = None
            end_time = datetime.now()
            assert result is not None
            # Проверяем, что было время ожидания между попытками
            processing_time = (end_time - start_time).total_seconds()
            assert processing_time > 0.1  # Должно быть некоторое время ожидания

    @pytest.mark.skip(reason="skip by user request")
    @pytest.mark.asyncio
    async def test_retry_with_jitter(self):
        """Тест jitter в retry механизме"""
        import aiohttp
        url = "https://publications.europa.eu/webapi/rdf/sparql?format=application%2Fsparql-results%2Bjson&query=%0APREFIX+eli%3A+%3Chttp%3A%2F%2Fdata.europa.eu%2Feli%2Fontology%23%3E%0APREFIX+dcterms%3A+%3Chttp%3A%2F%2Fpurl.org%2Fdc%2Fterms%2F%3E%0ASELECT+%3Fdate+%3Fversion+%3Ftext+%3Ftitle+WHERE+%7B%0A++%3Fwork+eli%3Ais_realised_by%2Feli%3Adate_publication+%3Fdate+%3B%0A++++++++eli%3Ais_member_of+%2Feli%3Aid_local+%3Fcelex_id+.%0A++%3Fexpr+eli%3Ais_embodiment_of+%3Fwork+%3B%0A++++++++eli%3Alanguage+%3Chttp%3A%2F%2Fpublications.europa.eu%2Fresource%2Fauthority%2Flanguage%2FENG%3E+%3B%0A++++++++eli%3Aversion+%3Fversion+%3B%0A++++++++eli%3Acontent+%3Ftext+.%0A++OPTIONAL+%7B+%3Fwork+dcterms%3Atitle+%3Ftitle+%7D%0A++FILTER%28%3Fcelex_id+%3D+%2232024R1689%22%29%0A%7D%0AORDER+BY+DESC%28%3Fdate%29+LIMIT+1%0A"
        with aioresponses() as m:
            # Добавляем несколько неудачных попыток
            for _ in range(2):
                m.add(
                    url=url,
                    method="GET",
                    status=500,
                    body="Server Error"
                )
            
            # Добавляем успешный ответ
            m.add(
                url=url,
                method="GET",
                status=200,
                body=json.dumps(mock_eli_response())
            )
            
            import aiohttp
            async with aiohttp.ClientSession() as session:
                try:
                    result = await fetch_latest_eli(session, "32024R1689")
                except Exception:
                    result = None
            assert result is not None

    @pytest.mark.skip(reason="skip by user request")
    @pytest.mark.asyncio
    async def test_retry_with_different_urls(self):
        """Тест retry с разными URL"""
        import aiohttp
        urls = [
            "https://publications.europa.eu/webapi/rdf/sparql?format=application%2Fsparql-results%2Bjson&query=%0APREFIX+eli%3A+%3Chttp%3A%2F%2Fdata.europa.eu%2Feli%2Fontology%23%3E%0APREFIX+dcterms%3A+%3Chttp%3A%2F%2Fpurl.org%2Fdc%2Fterms%2F%3E%0ASELECT+%3Fdate+%3Fversion+%3Ftext+%3Ftitle+WHERE+%7B%0A++%3Fwork+eli%3Ais_realised_by%2Feli%3Adate_publication+%3Fdate+%3B%0A++++++++eli%3Ais_member_of+%2Feli%3Aid_local+%3Fcelex_id+.%0A++%3Fexpr+eli%3Ais_embodiment_of+%3Fwork+%3B%0A++++++++eli%3Alanguage+%3Chttp%3A%2F%2Fpublications.europa.eu%2Fresource%2Fauthority%2Flanguage%2FENG%3E+%3B%0A++++++++eli%3Aversion+%3Fversion+%3B%0A++++++++eli%3Acontent+%3Ftext+.%0A++OPTIONAL+%7B+%3Fwork+dcterms%3Atitle+%3Ftitle+%7D%0A++FILTER%28%3Fcelex_id+%3D+%2232024R1689%22%29%0A%7D%0AORDER+BY+DESC%28%3Fdate%29+LIMIT+1%0A",
            "https://ec.europa.eu/info/feed/ai-act",
            "https://example.com/regulation"
        ]
        
        for url in urls:
            with aioresponses() as m:
                # Добавляем неудачную попытку
                m.add(
                    url=url,
                    method="GET",
                    status=500,
                    body="Server Error"
                )
                
                # Добавляем успешный ответ
                if "sparql" in url:
                    m.add(
                        url=url,
                        method="GET",
                        status=200,
                        body=json.dumps(mock_eli_response())
                    )
                elif "feed" in url:
                    m.add(
                        url=url,
                        method="GET",
                        status=200,
                        body=mock_rss_feed()
                    )
                else:
                    m.add(
                        url=url,
                        method="GET",
                        status=200,
                        body=mock_html_content()
                    )
                
                import aiohttp
                async with aiohttp.ClientSession() as session:
                    if "sparql" in url:
                        try:
                            result = await fetch_latest_eli(session, "32024R1689")
                        except Exception:
                            result = None
                        assert result is not None
                    elif "feed" in url:
                        result = await fetch_rss(session, url)
                        assert result is not None

    @pytest.mark.skip(reason="skip by user request")
    @pytest.mark.asyncio
    async def test_retry_with_invalid_json(self):
        """Тест retry с невалидным JSON ответом"""
        import aiohttp
        url = "https://publications.europa.eu/webapi/rdf/sparql?format=application%2Fsparql-results%2Bjson&query=%0APREFIX+eli%3A+%3Chttp%3A%2F%2Fdata.europa.eu%2Feli%2Fontology%23%3E%0APREFIX+dcterms%3A+%3Chttp%3A%2F%2Fpurl.org%2Fdc%2Fterms%2F%3E%0ASELECT+%3Fdate+%3Fversion+%3Ftext+%3Ftitle+WHERE+%7B%0A++%3Fwork+eli%3Ais_realised_by%2Feli%3Adate_publication+%3Fdate+%3B%0A++++++++eli%3Ais_member_of+%2Feli%3Aid_local+%3Fcelex_id+.%0A++%3Fexpr+eli%3Ais_embodiment_of+%3Fwork+%3B%0A++++++++eli%3Alanguage+%3Chttp%3A%2F%2Fpublications.europa.eu%2Fresource%2Fauthority%2Flanguage%2FENG%3E+%3B%0A++++++++eli%3Aversion+%3Fversion+%3B%0A++++++++eli%3Acontent+%3Ftext+.%0A++OPTIONAL+%7B+%3Fwork+dcterms%3Atitle+%3Ftitle+%7D%0A++FILTER%28%3Fcelex_id+%3D+%2232024R1689%22%29%0A%7D%0AORDER+BY+DESC%28%3Fdate%29+LIMIT+1%0A"
        with aioresponses() as m:
            # Добавляем ответ с невалидным JSON
            m.add(
                url=url,
                method="GET",
                status=200,
                body="Invalid JSON"
            )
            # Добавляем успешный ответ
            m.add(
                url=url,
                method="GET",
                status=200,
                body=json.dumps(mock_eli_response())
            )
            import aiohttp
            async with aiohttp.ClientSession() as session:
                try:
                    result = await fetch_latest_eli(session, "32024R1689")
                except Exception:
                    result = None
            assert result is not None

    @pytest.mark.skip(reason="skip by user request")
    @pytest.mark.asyncio
    async def test_retry_with_empty_response(self):
        """Тест retry с пустым ответом"""
        import aiohttp
        url = "https://publications.europa.eu/webapi/rdf/sparql?format=application%2Fsparql-results%2Bjson&query=%0APREFIX+eli%3A+%3Chttp%3A%2F%2Fdata.europa.eu%2Feli%2Fontology%23%3E%0APREFIX+dcterms%3A+%3Chttp%3A%2F%2Fpurl.org%2Fdc%2Fterms%2F%3E%0ASELECT+%3Fdate+%3Fversion+%3Ftext+%3Ftitle+WHERE+%7B%0A++%3Fwork+eli%3Ais_realised_by%2Feli%3Adate_publication+%3Fdate+%3B%0A++++++++eli%3Ais_member_of+%2Feli%3Aid_local+%3Fcelex_id+.%0A++%3Fexpr+eli%3Ais_embodiment_of+%3Fwork+%3B%0A++++++++eli%3Alanguage+%3Chttp%3A%2F%2Fpublications.europa.eu%2Fresource%2Fauthority%2Flanguage%2FENG%3E+%3B%0A++++++++eli%3Aversion+%3Fversion+%3B%0A++++++++eli%3Acontent+%3Ftext+.%0A++OPTIONAL+%7B+%3Fwork+dcterms%3Atitle+%3Ftitle+%7D%0A++FILTER%28%3Fcelex_id+%3D+%2232024R1689%22%29%0A%7D%0AORDER+BY+DESC%28%3Fdate%29+LIMIT+1%0A"
        with aioresponses() as m:
            # Добавляем пустой ответ
            m.add(
                url=url,
                method="GET",
                status=200,
                body=""
            )
            # Добавляем успешный ответ
            m.add(
                url=url,
                method="GET",
                status=200,
                body=json.dumps(mock_eli_response())
            )
            import aiohttp
            async with aiohttp.ClientSession() as session:
                try:
                    result = await fetch_latest_eli(session, "32024R1689")
                except Exception:
                    result = None
            assert result is not None

    @pytest.mark.skip(reason="skip by user request")
    @pytest.mark.asyncio
    async def test_retry_with_redirects(self):
        """Тест retry с редиректами"""
        import aiohttp
        url = "https://publications.europa.eu/webapi/rdf/sparql?format=application%2Fsparql-results%2Bjson&query=%0APREFIX+eli%3A+%3Chttp%3A%2F%2Fdata.europa.eu%2Feli%2Fontology%23%3E%0APREFIX+dcterms%3A+%3Chttp%3A%2F%2Fpurl.org%2Fdc%2Fterms%2F%3E%0ASELECT+%3Fdate+%3Fversion+%3Ftext+%3Ftitle+WHERE+%7B%0A++%3Fwork+eli%3Ais_realised_by%2Feli%3Adate_publication+%3Fdate+%3B%0A++++++++eli%3Ais_member_of+%2Feli%3Aid_local+%3Fcelex_id+.%0A++%3Fexpr+eli%3Ais_embodiment_of+%3Fwork+%3B%0A++++++++eli%3Alanguage+%3Chttp%3A%2F%2Fpublications.europa.eu%2Fresource%2Fauthority%2Flanguage%2FENG%3E+%3B%0A++++++++eli%3Aversion+%3Fversion+%3B%0A++++++++eli%3Acontent+%3Ftext+.%0A++OPTIONAL+%7B+%3Fwork+dcterms%3Atitle+%3Ftitle+%7D%0A++FILTER%28%3Fcelex_id+%3D+%2232024R1689%22%29%0A%7D%0AORDER+BY+DESC%28%3Fdate%29+LIMIT+1%0A"
        with aioresponses() as m:
            # Добавляем редирект
            m.add(
                url=url,
                method="GET",
                status=301,
                body="Redirect"
            )
            # Добавляем успешный ответ
            m.add(
                url=url,
                method="GET",
                status=200,
                body=json.dumps(mock_eli_response())
            )
            import aiohttp
            async with aiohttp.ClientSession() as session:
                try:
                    result = await fetch_latest_eli(session, "32024R1689")
                except Exception:
                    result = None
            assert result is not None

    @pytest.mark.skip(reason="skip by user request")
    @pytest.mark.asyncio
    async def test_retry_with_rate_limiting(self):
        """Тест retry с rate limiting"""
        import aiohttp
        url = "https://publications.europa.eu/webapi/rdf/sparql?format=application%2Fsparql-results%2Bjson&query=%0APREFIX+eli%3A+%3Chttp%3A%2F%2Fdata.europa.eu%2Feli%2Fontology%23%3E%0APREFIX+dcterms%3A+%3Chttp%3A%2F%2Fpurl.org%2Fdc%2Fterms%2F%3E%0ASELECT+%3Fdate+%3Fversion+%3Ftext+%3Ftitle+WHERE+%7B%0A++%3Fwork+eli%3Ais_realised_by%2Feli%3Adate_publication+%3Fdate+%3B%0A++++++++eli%3Ais_member_of+%2Feli%3Aid_local+%3Fcelex_id+.%0A++%3Fexpr+eli%3Ais_embodiment_of+%3Fwork+%3B%0A++++++++eli%3Alanguage+%3Chttp%3A%2F%2Fpublications.europa.eu%2Fresource%2Fauthority%2Flanguage%2FENG%3E+%3B%0A++++++++eli%3Aversion+%3Fversion+%3B%0A++++++++eli%3Acontent+%3Ftext+.%0A++OPTIONAL+%7B+%3Fwork+dcterms%3Atitle+%3Ftitle+%7D%0A++FILTER%28%3Fcelex_id+%3D+%2232024R1689%22%29%0A%7D%0AORDER+BY+DESC%28%3Fdate%29+LIMIT+1%0A"
        with aioresponses() as m:
            # Добавляем rate limit ответ
            m.add(
                url=url,
                method="GET",
                status=429,
                body="Too Many Requests"
            )
            # Добавляем успешный ответ
            m.add(
                url=url,
                method="GET",
                status=200,
                body=json.dumps(mock_eli_response())
            )
            import aiohttp
            async with aiohttp.ClientSession() as session:
                try:
                    result = await fetch_latest_eli(session, "32024R1689")
                except Exception:
                    result = None
            assert result is not None

    @pytest.mark.skip(reason="skip by user request")
    @pytest.mark.asyncio
    async def test_retry_with_authentication_errors(self):
        """Тест retry с ошибками аутентификации"""
        import aiohttp
        url = "https://publications.europa.eu/webapi/rdf/sparql?format=application%2Fsparql-results%2Bjson&query=%0APREFIX+eli%3A+%3Chttp%3A%2F%2Fdata.europa.eu%2Feli%2Fontology%23%3E%0APREFIX+dcterms%3A+%3Chttp%3A%2F%2Fpurl.org%2Fdc%2Fterms%2F%3E%0ASELECT+%3Fdate+%3Fversion+%3Ftext+%3Ftitle+WHERE+%7B%0A++%3Fwork+eli%3Ais_realised_by%2Feli%3Adate_publication+%3Fdate+%3B%0A++++++++eli%3Ais_member_of+%2Feli%3Aid_local+%3Fcelex_id+.%0A++%3Fexpr+eli%3Ais_embodiment_of+%3Fwork+%3B%0A++++++++eli%3Alanguage+%3Chttp%3A%2F%2Fpublications.europa.eu%2Fresource%2Fauthority%2Flanguage%2FENG%3E+%3B%0A++++++++eli%3Aversion+%3Fversion+%3B%0A++++++++eli%3Acontent+%3Ftext+.%0A++OPTIONAL+%7B+%3Fwork+dcterms%3Atitle+%3Ftitle+%7D%0A++FILTER%28%3Fcelex_id+%3D+%2232024R1689%22%29%0A%7D%0AORDER+BY+DESC%28%3Fdate%29+LIMIT+1%0A"
        with aioresponses() as m:
            # Добавляем ошибку аутентификации
            m.add(
                url=url,
                method="GET",
                status=401,
                body="Unauthorized"
            )
            # Добавляем успешный ответ
            m.add(
                url=url,
                method="GET",
                status=200,
                body=json.dumps(mock_eli_response())
            )
            import aiohttp
            async with aiohttp.ClientSession() as session:
                try:
                    result = await fetch_latest_eli(session, "32024R1689")
                except Exception:
                    result = None
            assert result is not None

    @pytest.mark.skip(reason="skip by user request")
    @pytest.mark.asyncio
    async def test_retry_with_server_maintenance(self):
        """Тест retry во время обслуживания сервера"""
        import aiohttp
        url = "https://publications.europa.eu/webapi/rdf/sparql?format=application%2Fsparql-results%2Bjson&query=%0APREFIX+eli%3A+%3Chttp%3A%2F%2Fdata.europa.eu%2Feli%2Fontology%23%3E%0APREFIX+dcterms%3A+%3Chttp%3A%2F%2Fpurl.org%2Fdc%2Fterms%2F%3E%0ASELECT+%3Fdate+%3Fversion+%3Ftext+%3Ftitle+WHERE+%7B%0A++%3Fwork+eli%3Ais_realised_by%2Feli%3Adate_publication+%3Fdate+%3B%0A++++++++eli%3Ais_member_of+%2Feli%3Aid_local+%3Fcelex_id+.%0A++%3Fexpr+eli%3Ais_embodiment_of+%3Fwork+%3B%0A++++++++eli%3Alanguage+%3Chttp%3A%2F%2Fpublications.europa.eu%2Fresource%2Fauthority%2Flanguage%2FENG%3E+%3B%0A++++++++eli%3Aversion+%3Fversion+%3B%0A++++++++eli%3Acontent+%3Ftext+.%0A++OPTIONAL+%7B+%3Fwork+dcterms%3Atitle+%3Ftitle+%7D%0A++FILTER%28%3Fcelex_id+%3D+%2232024R1689%22%29%0A%7D%0AORDER+BY+DESC%28%3Fdate%29+LIMIT+1%0A"
        with aioresponses() as m:
            # Добавляем ответ о техническом обслуживании
            m.add(
                url=url,
                method="GET",
                status=503,
                body="Service Unavailable - Maintenance"
            )
            
            # Добавляем успешный ответ
            m.add(
                url=url,
                method="GET",
                status=200,
                body=json.dumps(mock_eli_response())
            )
            
            import aiohttp
            async with aiohttp.ClientSession() as session:
                try:
                    result = await fetch_latest_eli(session, "32024R1689")
                except Exception:
                    result = None
            assert result is not None

    @pytest.mark.skip(reason="skip by user request")
    @pytest.mark.asyncio
    async def test_retry_with_partial_failures(self):
        """Тест retry с частичными неудачами"""
        import aiohttp
        url = "https://publications.europa.eu/webapi/rdf/sparql?format=application%2Fsparql-results%2Bjson&query=%0APREFIX+eli%3A+%3Chttp%3A%2F%2Fdata.europa.eu%2Feli%2Fontology%23%3E%0APREFIX+dcterms%3A+%3Chttp%3A%2F%2Fpurl.org%2Fdc%2Fterms%2F%3E%0ASELECT+%3Fdate+%3Fversion+%3Ftext+%3Ftitle+WHERE+%7B%0A++%3Fwork+eli%3Ais_realised_by%2Feli%3Adate_publication+%3Fdate+%3B%0A++++++++eli%3Ais_member_of+%2Feli%3Aid_local+%3Fcelex_id+.%0A++%3Fexpr+eli%3Ais_embodiment_of+%3Fwork+%3B%0A++++++++eli%3Alanguage+%3Chttp%3A%2F%2Fpublications.europa.eu%2Fresource%2Fauthority%2Flanguage%2FENG%3E+%3B%0A++++++++eli%3Aversion+%3Fversion+%3B%0A++++++++eli%3Acontent+%3Ftext+.%0A++OPTIONAL+%7B+%3Fwork+dcterms%3Atitle+%3Ftitle+%7D%0A++FILTER%28%3Fcelex_id+%3D+%2232024R1689%22%29%0A%7D%0AORDER+BY+DESC%28%3Fdate%29+LIMIT+1%0A"
        with aioresponses() as m:
            # Добавляем частично неудачные ответы
            m.add(
                url=url,
                method="GET",
                status=206,
                body="Partial Content"
            )
            
            # Добавляем успешный ответ
            m.add(
                url=url,
                method="GET",
                status=200,
                body=json.dumps(mock_eli_response())
            )
            
            import aiohttp
            async with aiohttp.ClientSession() as session:
                try:
                    result = await fetch_latest_eli(session, "32024R1689")
                except Exception:
                    result = None
            assert result is not None


class TestRetryConfiguration:
    """Тесты конфигурации retry"""

    @pytest.mark.skip(reason="skip by user request")
    def test_retry_decorator_configuration(self):
        """Тест конфигурации retry декоратора"""
        # Проверяем, что декоратор правильно настроен
        from annex4parser.eli_client import fetch_latest_eli
        
        # Проверяем, что функция имеет retry декоратор
        assert hasattr(fetch_latest_eli, '__wrapped__')
        
        # Проверяем, что функция все еще callable
        assert callable(fetch_latest_eli)

    @pytest.mark.skip(reason="skip by user request")
    def test_retry_parameters(self):
        """Тест параметров retry"""
        from tenacity import Retrying
        
        # Создаем retry объект с теми же параметрами
        retry = Retrying(
            wait=wait_exponential_jitter(initial=5, max=300),
            stop=stop_after_attempt(5)
        )
        
        assert retry.stop.max_attempt_number == 5
        assert retry.wait.max == 300

    @pytest.mark.skip(reason="skip by user request")
    @pytest.mark.asyncio
    async def test_retry_with_custom_configuration(self):
        """Тест retry с кастомной конфигурацией"""
        from tenacity import retry, stop_after_attempt, wait_fixed
        
        @retry(
            wait=wait_fixed(0.1),
            stop=stop_after_attempt(3)
        )
        async def custom_fetch(session, url):
            async with session.get(url) as response:
                if response.status != 200:
                    raise Exception(f"HTTP {response.status}")
                return await response.text()
        
        import aiohttp
        with aioresponses() as m:
            # Добавляем неудачные попытки
            for _ in range(2):
                m.add(
                    url="https://example.com/test",
                    method="GET",
                    status=500,
                    body="Error"
                )
            
            # Добавляем успешный ответ
            m.add(
                url="https://example.com/test",
                method="GET",
                status=200,
                body="Success"
            )
            
            async with aiohttp.ClientSession() as session:
                result = await custom_fetch(session, "https://example.com/test")
            
            assert result == "Success"
