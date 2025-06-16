import asyncio
import aiohttp
import filetype
from maubot import Plugin, MessageEvent
from maubot.handlers import command
from mautrix.types import TextMessageEventContent, MessageType, Format
from mautrix.util.config import BaseProxyConfig, ConfigUpdateHelper
from .resources import engines
from .resources import languages
from .resources.datastructures import LinkData, AddressData, SearchData
from time import strftime
from time import gmtime
from typing import Type, Any
from urllib.parse import urlunsplit


class Config(BaseProxyConfig):
    def do_update(self, helper: ConfigUpdateHelper) -> None:
        helper.copy("url")
        helper.copy("port")
        helper.copy("language")
        helper.copy("safesearch")


class SearxngBot(Plugin):
    headers = {
        "Sec-GPC": "1",
        "accept-encoding": "gzip, deflate, br, zstd",
        "accept-language": "en,en-US;q=0.5",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:139.0) Gecko/20100101 Firefox/139.0",
    }

    async def start(self) -> None:
        await super().start()
        self.config.load_and_update()

    @command.new(name="sx", aliases=["searxng"], help="Get the most relevant result from SearXNG Web Search")
    @command.argument("query", pass_raw=True, required=True)
    async def search(self, evt: MessageEvent, query: str) -> None:
        await evt.mark_read()
        # Remove "bangs" that could redirect out of the search engine
        query = query.strip().replace("!!", "").replace("\\", "")
        if not query:
            await evt.reply("> **Usage:** !sx <query>")
            return

        response = await self.get_result(query)
        search_data = await self.parse_json(response)
        if not search_data:
            await evt.reply(f"> Failed to find results for *{query}*")
            return
        if search_data.thumbnail:
            search_data.thumbnail = await self.get_thumbnail_url(search_data.thumbnail)
        message = await self.prepare_message(search_data)
        await evt.reply(message)

    async def get_result(self, query: str) -> Any:
        """
        Get results from the SearxNG Web Search API.
        :param query: search query
        :return: JSON API response
        """
        params = {
            "q": query,  # keywords
            "language": self.get_language(),  # language
            "format": "json",  # request json
            "safesearch": self.get_safesearch(),  # safe search
        }
        url = self.get_address()
        timeout = aiohttp.ClientTimeout(total=20)
        try:
            response = await self.http.get(url, timeout=timeout, params=params, raise_for_status=True)
            return await response.json()
        except aiohttp.ClientError as e:
            self.log.error(f"Connection failed: {e}")
            return ""

    async def parse_json(self, data: Any) -> SearchData | None:
        if data and data.get("results", None):
            result = data["results"][0]
            engine = result.get("engine", "").replace(".", " ")
            links: list[LinkData] = []
            if result.get("links", []):
                for li in result["links"]:
                    link = LinkData(
                        label=li.get("label", ""),
                        url=li.get("url", ""),
                        url_label=li.get("url_label", ""),
                    )
                    links.append(link)
            address = None
            if result.get("address", None):
                address = AddressData(
                    name=result["address"].get("name", ""),
                    house_number=result["address"].get("house_number", ""),
                    road=result["address"].get("road", ""),
                    locality=result["address"].get("locality", ""),
                    postcode=result["address"].get("postcode", ""),
                    country=result["address"].get("country", "")
                )
            length = result.get("length", "")
            if type(length) != str:
                length = str(strftime("%H:%M:%S", gmtime(length)))

            parsed_url = result.get("parsed_url", [])
            torrentfile = result.get("torrentfile", "")
            if torrentfile and len(parsed_url) >= 2:
                torrentfile = urlunsplit(parsed_url[:2] + [torrentfile] + [""] * 2)
            return SearchData(
                url=result.get("url", ""),
                links=links,
                content=result.get("content", ""),
                title=result.get("title", ""),
                engine=f"SearXNG ({await self.translate_engine(engine)})",
                published_date=result.get("publishedDate", ""),
                thumbnail=result.get("thumbnail", ""),
                author=result.get("author", ""),
                authors=result.get("authors", []),
                publisher=result.get("publisher", ""),
                views=result.get("views", ""),
                length=length,
                metadata=result.get("metadata", ""),
                seed=str(result.get("seed", "")),
                leech=str(result.get("leech", "")),
                magnetlink=result.get("magnetlink", ""),
                torrentfile=torrentfile,
                filesize=result.get("filesize", ""),
                address=address,
                pdf_url=result.get("pdf_url", "")
            )
        return None

    async def translate_engine(self, name: str) -> str:
        name_parts = name.split()
        for i in range(0, len(name_parts)):
            name_parts[i] = engines.engine_dict.get(name_parts[i], name_parts[i].title())
        return " ".join(name_parts)

    async def get_thumbnail_url(self, url: str) -> str:
        """
        Download thumbnail from external source and upload it to Matrix server
        :param url: external URL to the thumbnail
        :return: Matrix mxc image URL
        """
        try:
            # Download image from external source
            response = await self.http.get(url, headers=self.headers, raise_for_status=True)
            data = await response.read()
            content_type = await asyncio.get_event_loop().run_in_executor(None, filetype.guess, data)
            if not content_type:
                self.log.error("Failed to determine file type")
                return ""
            if content_type not in filetype.image_matchers:
                self.log.error("Downloaded file is not an image")
                return ""
            # Upload image to Matrix server
            return await self.client.upload_media(
                data=data,
                mime_type=content_type.mime,
                filename=f"image.{content_type.extension}",
                size=len(data)
            )
        except aiohttp.ClientError as e:
            self.log.error(f"Downloading image - connection failed: {e}")
        except Exception as e:
            self.log.error(f"Uploading image to Matrix server - unknown error: {e}")
        return ""

    async def prepare_message(self, data: SearchData) -> TextMessageEventContent:
        """
        Prepares HTML and text message based on provided search data.
        :param data: search data object
        :return: final message
        """
        pub_date = data.published_date.split("T")[0] if data.published_date else ""
        body = (
            f"> `{data.url if len(data.url) < 70 else f'{data.url[:70]}...'}`  \n"
            f"> [**{data.title}**]({data.url})  \n"
        )
        html = (
            f"<blockquote><table><tr><td>"
            f"<sub><code>{data.url if len(data.url) < 70 else f'{data.url[:70]}...'}</code></sub><br>"
            f"<b><a href=\"{data.url}\">{data.title}</a></b>"
        )
        # Videos, news etc.
        if pub_date:
            body += f"> {pub_date}  \n"
            html += f"<p><sub>{pub_date}</sub></p>"
        if data.length:
            body += f"> > **Length:** {data.length}  \n"
            html += f"<blockquote><b>Length:</b> {data.length}</blockquote>"
        if data.views:
            body += f"> > **Views:** {data.views}  \n"
            html += f"<blockquote><b>Views:</b> {data.views}</blockquote>"
        if data.publisher:
            body += f"> > **Publisher:** {data.publisher}  \n"
            html += f"<blockquote><b>Publisher:</b> {data.publisher}</blockquote>"
        if data.author:
            body += f"> > **Author:** {data.author}  \n"
            html += f"<blockquote><b>Author:</b> {data.author}</blockquote>"
        if data.authors:
            body += f"> > **Authors:** {", ".join(data.authors)}  \n"
            html += f"<blockquote><b>Authors:</b> {", ".join(data.authors)}</blockquote>"
        # File content
        if data.seed or data.leech:
            body += f"> > **Seeders/Leechers:** {data.seed if data.seed else 'N/A'}/{data.leech if data.leech else 'N/A'}  \n"
            html += f"<blockquote><b>Seeders/Leechers:</b> {data.seed if data.seed else 'N/A'}/{data.leech if data.leech else 'N/A'}</blockquote>"
        if data.filesize:
            body += f"> > **Size:** {data.filesize}  \n"
            html += f"<blockquote><b>Size:</b> {data.filesize}</blockquote>"
        if data.magnetlink or data.torrentfile:
            body += "> > "
            html += f"<blockquote>"
            if data.torrentfile:
                body += f"[**⬇️ Torrent**]({data.torrentfile}) "
                html += f"<b><a href=\"{data.torrentfile}\">⬇️ Torrent</a></b> "
            if data.magnetlink:
                body += f"[**🧲 Magnet**]({data.magnetlink})"
                html += f"<b><a href=\"{data.magnetlink}\">🧲 Magnet</a></b>"
            body += "  \n"
            html += f"</blockquote>"
        # Universal description
        if data.metadata:
            body += f"> > **{data.metadata}**  \n"
            html += f"<blockquote><b>{data.metadata}</b></blockquote>"
        if data.content:
            body += f">  \n> {data.content}  \n"
            html += f"<p>{data.content}</p>"
        # Map content
        if data.links:
            links = "  \n".join([f"> > {link.label}: [{link.url_label}]({link.url})" for link in data.links])
            body += f"> > **Links:**  \n{links}  \n"
            links = "<br>".join([f"{link.label}: <a href=\"{link.url}\">{link.url_label}</a>" for link in data.links])
            html += (f"<blockquote><b>Links:</b><br>{links}</blockquote>")
        if data.address:
            body += f"> > **Address:**  \n> > {data.address.name}  \n"
            html += (
                f"<blockquote><b>Address:</b><br>"
                f"{data.address.name}<br>"
            )
            if data.address.road:
                body += f"> > {data.address.road} {data.address.house_number}  \n"
                html += f"{data.address.road} {data.address.house_number}<br>"
            if data.address.locality:
                body += f"> > {data.address.locality} {data.address.postcode}  \n"
                html += f"{data.address.locality} {data.address.postcode}<br>"
            if data.address.country:
                body += f"> > {data.address.country}  \n"
                html += f"{data.address.country}"
            html += f"</blockquote>"
        if data.pdf_url:
            body += f"> [**PDF**]({data.pdf_url})  \n"
            html += f"<br><b><a href=\"{data.pdf_url}\">PDF</a></b>"
        html += f"</td>"
        # Picture
        if data.thumbnail:
            html += (
                f"<td>"
                f"<img src=\"{data.thumbnail}\" height=\"150\" />"
                f"</td>"
            )
        body += f">  \n> **Results from {data.engine}**"
        html += (
            f"</tr>"
            f"</table>"
            f"<p><b><sub>Results from {data.engine}</sub></b></p>"
            f"</blockquote>"
        )
        return TextMessageEventContent(
            msgtype=MessageType.NOTICE,
            format=Format.HTML,
            body=body,
            formatted_body=html)

    def get_address(self) -> str:
        """
        Get SearXNG backend address
        :return: SearXNG backend address
        """
        url = self.config.get("url", "http://127.0.0.1")
        port = self.config.get("port", 8080)
        return f"{url}:{port}/search"

    def get_safesearch(self) -> str:
        """
        Get safe search filter status from config for SearXNG Image Search
        :return: Value corresponding to safe search status
        """
        safesearch_base = {
            "on": "2",
            "moderate": "1",
            "off": "0"
        }
        return safesearch_base.get(self.config.get("safesearch", "moderate"), safesearch_base["moderate"])

    def get_language(self) -> str:
        """
        Get search region from config for SearXNG Image Search
        :return: Search region
        """
        lang = self.config.get("language", "all")
        if lang in languages.locales:
            return lang
        return "all"

    @classmethod
    def get_config_class(cls) -> Type[BaseProxyConfig]:
        return Config
