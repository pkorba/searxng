import aiohttp
import asyncio
import unittest
from searxng.searxng import SearxngBot
from .searxng.resources.datastructures import LinkData, AddressData, SearchData
from maubot.matrix import MaubotMatrixClient
from mautrix.api import HTTPAPI
from mautrix.errors.base import MatrixResponseError
from mautrix.types import MessageType, TextMessageEventContent
from mautrix.util.logging import TraceLogger
from unittest.mock import AsyncMock


class TestSearxngBot(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.session = aiohttp.ClientSession()
        api = HTTPAPI(base_url="http://matrix.example.com", client_session=self.session)
        client = MaubotMatrixClient(api=api)
        self.bot = SearxngBot(
            client=client,
            loop=asyncio.get_event_loop(),
            http=self.session,
            instance_id="matrix.example.com",
            log=TraceLogger("testlogger"),
            config=None,
            database=None,
            webapp=None,
            webapp_url=None,
            loader=None
        )

    async def asyncTearDown(self):
        await self.session.close()

    async def create_resp(self, status_code=200, json=None, resp_bytes=None, content_type=None, content_length=0):
        resp = AsyncMock(status_code=status_code, content_type=content_type, content_length=content_length)
        resp.json.return_value = json
        resp.read.return_value = resp_bytes
        return resp

    async def test_get_result_when_request_is_successful_then_return_json(self):
        # Arrange
        json_data = {'test': 1}
        self.bot.config = {
            "language": "all",
            "url": "http://127.0.0.1",
            "port": 8080,
            "safesearch": "moderate",
        }
        self.bot.http.get = AsyncMock(return_value=await self.create_resp(200, json=json_data))

        # Act
        json_response = await self.bot.get_result("query")

        # Assert
        self.assertEqual(json_response, json_data)

    async def test_get_result_when_aiohttp_ClientError_then_return_empty_string(self):
        # Arrange
        self.bot.config = {
            "language": "all",
            "url": "http://127.0.0.1",
            "port": 8080,
            "safesearch": "moderate",
        }
        self.bot.http.get = AsyncMock(side_effect=aiohttp.ClientError)

        # Act
        json_response = await self.bot.get_result("query")

        # Assert
        self.assertEqual(json_response, "")

    async def test_parse_json_when_data_exists_return_SearchData(self):
        # Arrange
        json = {
            "query": "test",
            "number_of_results": 0,
            "results": [
                {
                    "url": "https://www.example.com/",
                    "title": "Example",
                    "content": "content",
                    "author": "John Smith",
                    "authors": [
                        "John Smith",
                        "John Paul II",
                        "Torment Nexus"
                    ],
                    "publisher": "Example Press",
                    "views": "1000",
                    "length": 1050,
                    "pdf_url": "http://example.com/pdf/123abc",
                    "seed": 100,
                    "leech": 15,
                    "filesize": "10.0 GiB",
                    "torrentfile": "/download/1234567.torrent",
                    "magnetlink": "magnet:?xt=urn:btih:123abc",
                    "publishedDate": "1970-01-01T00:00:00",
                    "engine": "search engine",
                    "parsed_url": [
                        "https",
                        "www.example.com",
                        "/view/1234567",
                        "",
                        "",
                        ""
                    ],
                    "address": {
                        "name": "Name",
                        "house_number": "0",
                        "road": "Street",
                        "locality": "City",
                        "postcode": "00-000",
                        "country": "Country",
                        "country_code": "xx"
                    },
                    "links": [
                        {
                            "label": "official website",
                            "url": "http://www.official.example.com/",
                            "url_label": "http://www.official.example.com/"
                        },
                        {
                            "label": "Wikipedia",
                            "url": "https://en.wikipedia.example.org/wiki/Example",
                            "url_label": "Example (en)"
                        },
                        {
                            "label": "Wikidata",
                            "url": "https://wikidata.example.org/wiki/Example",
                            "url_label": "Example"
                        }
                    ],
                    "thumbnail": "https://upload.example.com/image.jpg",
                    "metadata": "metadata",
                }
            ]
        }
        links = [
            LinkData("official website", "http://www.official.example.com/", "http://www.official.example.com/"),
            LinkData("Wikipedia", "https://en.wikipedia.example.org/wiki/Example", "Example (en)"),
            LinkData("Wikidata", "https://wikidata.example.org/wiki/Example", "Example"),
        ]
        address = AddressData(
            name="Name",
            house_number="0",
            road="Street",
            locality="City",
            postcode="00-000",
            country="Country"
        )

        # Act
        result = await self.bot.parse_json(json)

        # Assert
        self.assertIsInstance(result, SearchData)
        self.assertEqual(result.url, "https://www.example.com/")
        self.assertEqual(result.links, links)
        self.assertEqual(result.content, "content")
        self.assertEqual(result.title, "Example")
        self.assertEqual(result.engine, "SearXNG (Search Engine)")
        self.assertEqual(result.published_date, "1970-01-01T00:00:00")
        self.assertEqual(result.thumbnail, "https://upload.example.com/image.jpg")
        self.assertEqual(result.author, "John Smith")
        self.assertEqual(result.authors, ["John Smith", "John Paul II", "Torment Nexus"])
        self.assertEqual(result.publisher, "Example Press")
        self.assertEqual(result.views, "1000")
        self.assertEqual(result.length, "00:17:30")
        self.assertEqual(result.metadata, "metadata")
        self.assertEqual(result.seed, "100")
        self.assertEqual(result.leech, "15")
        self.assertEqual(result.magnetlink, "magnet:?xt=urn:btih:123abc")
        self.assertEqual(result.torrentfile, "https://www.example.com/download/1234567.torrent")
        self.assertEqual(result.filesize, "10.0 GiB")
        self.assertEqual(result.address, address)
        self.assertEqual(result.pdf_url, "http://example.com/pdf/123abc")

    async def test_parse_json_when_data_does_not_exists_return_empty_SearchData(self):
        # Arrange
        json = {
            "query": "test",
            "number_of_results": 0,
            "results": [
                {
                    "url": None,
                    "title": None,
                    "content": None,
                    "author": None,
                    "authors": [],
                    "publisher": None,
                    "views": None,
                    "length": None,
                    "pdf_url": None,
                    "seed": None,
                    "leech": None,
                    "filesize": None,
                    "torrentfile": None,
                    "magnetlink": None,
                    "publishedDate": None,
                    "engine": None,
                    "parsed_url": [],
                    "address": {
                        "name": None,
                        "house_number": None,
                        "road": None,
                        "locality": None,
                        "postcode": None,
                        "country": None,
                        "country_code": None
                    },
                    "links": [],
                    "thumbnail": None,
                    "metadata": None,
                }
            ]
        }
        links = []
        address = AddressData(
            name=None,
            house_number=None,
            road=None,
            locality=None,
            postcode=None,
            country=None
        )

        # Act
        result = await self.bot.parse_json(json)

        # Assert
        self.assertIsInstance(result, SearchData)
        self.assertEqual(result.url, None)
        self.assertEqual(result.links, links)
        self.assertEqual(result.content, None)
        self.assertEqual(result.title, None)
        self.assertEqual(result.engine, "SearXNG ()")
        self.assertEqual(result.published_date, None)
        self.assertEqual(result.thumbnail, None)
        self.assertEqual(result.author, None)
        self.assertEqual(result.authors, [])
        self.assertEqual(result.publisher, None)
        self.assertEqual(result.views, None)
        self.assertEqual(result.length, None)
        self.assertEqual(result.metadata, None)
        self.assertEqual(result.seed, None)
        self.assertEqual(result.leech, None)
        self.assertEqual(result.magnetlink, None)
        self.assertEqual(result.torrentfile, None)
        self.assertEqual(result.filesize, None)
        self.assertEqual(result.address, address)
        self.assertEqual(result.pdf_url, None)

    async def test_parse_json_when_no_results_return_None(self):
        # Arrange
        json = {
            "query": "test",
            "number_of_results": 0,
            "results": []
        }

        # Act
        result = await self.bot.parse_json(json)

        # Assert
        self.assertEqual(result, None)

    async def test_parse_json_when_no_data_return_None(self):
        # Arrange
        json = {}

        # Act
        result = await self.bot.parse_json(json)

        # Assert
        self.assertEqual(result, None)

    async def test_translate_engine(self):
        # Arrange
        config = (
            ("duckduckgo", "DuckDuckGo"),
            ("imdb", "IMDb"),
            ("tineye", "TinEye"),
            ("findthatmeme", "FindThatMeme"),
            ("peertube", "PeerTube"),
            ("youtube", "YouTube"),
            ("openstreetmap", "OpenStreetMap"),
            ("mixcloud", "MixCloud"),
            ("soundcloud", "SoundCloud"),
            ("npm", "npm"),
            ("pypi", "PyPI"),
            ("rubygems", "RubyGems"),
            ("voidlinux", "Void Linux"),
            ("askubuntu", "AskUbuntu"),
            ("stackoverflow", "StackOverflow"),
            ("superuser", "SuperUser"),
            ("github", "GitHub"),
            ("gitlab", "GitLab"),
            ("huggingface", "HuggingFace"),
            ("hackernews", "HackerNews"),
            ("mdn", "MDN"),
            ("arxiv", "arXiv"),
            ("apkmirror", "APK Mirror"),
            ("fdroid", "F-Droid"),
            ("nyaa", "nyaa"),
            ("piratebay", "ThePirateBay"),
            ("rottentomatoes", "RottenTomatoes"),
            ("tmdb", "TMDb"),
            ("openmeteo", "Open-Meteo"),
            ("brave search", "Brave Search")
        )
        for lowercase, expected_result in config:
            with self.subTest(lowercase=lowercase, expected_result=expected_result):
                # Act
                result = await self.bot.translate_engine(lowercase)

                # Assert
                self.assertEqual(result, expected_result)

    async def test_get_thumbnail_url_when_correct_data_return_mxc_url(self):
        # Arrange
        # white 10x10 png rectangle
        image = (b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\n\x00\x00\x00\n\x08\x06\x00\x00\x00\x8d2\xcf\xbd\x00'
                 b'\x00\x00\tpHYs\x00\x00\x0e\xc4\x00\x00\x0e\xc4\x01\x95+\x0e\x1b\x00\x00\x00\x18IDAT\x18\x95c\xfc\xff'
                 b'\xff\xff\x7f\x06"\x00\x131\x8aF\x15RO!\x00i\x9a\x04\x10\x8a\x8d\x0bh\x00\x00\x00\x00IEND\xaeB`\x82')
        self.bot.http.get = AsyncMock(return_value=await self.create_resp(200, resp_bytes=image))
        self.bot.client.upload_media = AsyncMock(return_value="mxc://thumbnail.example.com/image.png")

        # Act
        result = await self.bot.get_thumbnail_url("https://example.com/image.png")

        # Assert
        self.assertEqual(result, "mxc://thumbnail.example.com/image.png")

    async def test_get_thumbnail_url_when_not_image_type_return_empty_string(self):
        # Arrange
        # ZIP archive
        archive = (b'\x50\x4B\x03\x04\x0A\x00\x00\x00\x00\x00\xA7\x6B\x05\x5B\xC6\x35\xB9\x3B\x05'
                   b'\x00\x00\x00\x05\x00\x00\x00\x08\x00\x1C\x00\x74\x65\x73\x74\x2E\x74\x78\x74'
                   b'\x55\x54\x09\x00\x03\x09\xEB\x91\x68\x09\xEB\x91\x68\x75\x78\x0B\x00\x01\x04'
                   b'\xE8\x03\x00\x00\x04\xE8\x03\x00\x00\x74\x65\x73\x74\x0A\x50\x4B\x01\x02\x1E'
                   b'\x03\x0A\x00\x00\x00\x00\x00\xA7\x6B\x05\x5B\xC6\x35\xB9\x3B\x05\x00\x00\x00'
                   b'\x05\x00\x00\x00\x08\x00\x18\x00\x00\x00\x00\x00\x00\x00\x00\x00\xA4\x81\x00'
                   b'\x00\x00\x00\x74\x65\x73\x74\x2E\x74\x78\x74\x55\x54\x05\x00\x03\x09\xEB\x91'
                   b'\x68\x75\x78\x0B\x00\x01\x04\xE8\x03\x00\x00\x04\xE8\x03\x00\x00\x50\x4B\x05'
                   b'\x06\x00\x00\x00\x00\x01\x00\x01\x00\x4E\x00\x00\x00\x47\x00\x00\x00\x00\x00')
        self.bot.http.get = AsyncMock(return_value=await self.create_resp(200, resp_bytes=archive))

        # Act
        result = await self.bot.get_thumbnail_url("https://example.com/test.zip")

        # Assert
        self.assertEqual(result, "")

    async def test_get_thumbnail_url_when_unknown_content_type_return_empty_string(self):
        # Arrange
        # random byte data
        text = (b'test')
        self.bot.http.get = AsyncMock(return_value=await self.create_resp(200, resp_bytes=text))

        # Act
        result = await self.bot.get_thumbnail_url("https://example.com/unknown")

        # Assert
        self.assertEqual(result, "")

    async def test_get_thumbnail_url_when_error_return_empty_string(self):
        # Arrange
        errors = [aiohttp.ClientError, Exception, ValueError, MatrixResponseError("test")]
        for error in errors:
            with self.subTest(error=error):
                self.bot.http.get = AsyncMock(side_effect=error)

                # Act
                result = await self.bot.get_thumbnail_url("https://example.com/image.png")

                # Assert
                self.assertEqual(result, "")

    async def test_prepare_message_return_TextMessageEventContent(self):
        # Arrange
        search_data = SearchData(
            url="http://example.com",
            links=[],
            content="content",
            title="title",
            engine="engine",
            published_date="1970-01-01",
            thumbnail="mxc://thumbnail.example.com",
            publisher="publisher",
            author="author",
            authors=["author1", "author2"],
            views="1000",
            length="3:00",
            metadata="metadata",
            seed="100",
            leech="10",
            magnetlink="magnetlink",
            torrentfile="torrentfile",
            filesize="30000",
            address=None,
            pdf_url="pdfurl",
        )

        # Act
        result = await self.bot.prepare_message(search_data)

        # Assert
        self.assertIsInstance(result, TextMessageEventContent)
        self.assertEqual(result.msgtype, MessageType.NOTICE)
        self.assertIn("http://example.com", result.body)
        self.assertIn("http://example.com", result.formatted_body)

    async def test_get_address(self):
        # Arrange
        config = (
            ({"url": "https://www.example.com", "port": 80}, "https://www.example.com:80/search"),
            ({}, "http://127.0.0.1:8080/search")
        )
        for config_dict, expected_result in config:
            with self.subTest(config_dict=config_dict, expected_result=expected_result):
                self.bot.config = config_dict

                # Act
                result = self.bot.get_address()

                # Assert
                self.assertEqual(result, expected_result)

    async def test_get_safesearch(self):
        # Arrange
        config = (
            ({"safesearch": "on"}, "2"),
            ({"safesearch": "off"}, "0"),
            ({"safesearch": "moderate"}, "1"),
            ({"safesearch": ""}, "1"),
            ({"ssafesearch": "on"}, "1")
        )
        for config_dict, expected_result in config:
            with self.subTest(config_dict=config_dict, expected_result=expected_result):
                self.bot.config = config_dict

                # Act
                result = self.bot.get_safesearch()

                # Assert
                self.assertEqual(result, expected_result)

    async def test_get_language(self):
        # Arrange
        config = (
            ({"language": "all"}, "all"),
            ({"language": "pl"}, "pl"),
            ({"language": "PL"}, "all"),
            ({"language": ""}, "all"),
            ({"llanguage": "pl"}, "all")
        )
        for config_dict, expected_result in config:
            with self.subTest(config_dict=config_dict, expected_result=expected_result):
                self.bot.config = config_dict

                # Act
                result = self.bot.get_language()

                # Assert
                self.assertEqual(result, expected_result)


if __name__ == '__main__':
    unittest.main()
