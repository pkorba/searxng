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
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:140.0) Gecko/20100101 Firefox/140.0",
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
            engine = result.get("engine", "")
            if engine:
                engine = engine.replace(".", " ")
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
            if length and type(length) is not str:
                length = str(strftime("%H:%M:%S", gmtime(length)))

            parsed_url = result.get("parsed_url", [])
            torrentfile = result.get("torrentfile", "")
            if torrentfile and len(parsed_url) >= 2:
                torrentfile = urlunsplit(parsed_url[:2] + [torrentfile] + [""] * 2)
            seed = result.get("seed", "")
            if seed is not None:
                seed = str(seed)
            leech = result.get("leech", "")
            if leech is not None:
                leech = str(leech)
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
                seed=seed,
                leech=leech,
                magnetlink=result.get("magnetlink", ""),
                torrentfile=torrentfile,
                filesize=result.get("filesize", ""),
                address=address,
                pdf_url=result.get("pdf_url", ""),
                doi=result.get("doi", ""),
                journal=result.get("journal", ""),
                issn=result.get("issn", []),
                comment=result.get("comment", ""),
                maintainer=result.get("maintainer", ""),
                license_name=result.get("license_name", ""),
                license_url=result.get("license_url", ""),
                homepage=result.get("homepage", ""),
                source_code_url=result.get("source_code_url", ""),
                package_name=result.get("package_name", "")
            )
        return None

    async def translate_engine(self, name: str) -> str:
        if not name:
            return ""
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
        url_trimmed = data.url
        if data.url and len(data.url) >= 70:
            url_trimmed = f"{data.url[:70]}..."
        body = (
            f"> `{url_trimmed}`  \n"
            f"> [**{data.title}**]({data.url})  \n>  \n"
        )
        html = (
            f"<blockquote><table><tr><td>"
            f"<sub><code>{url_trimmed}</code></sub><br>"
            f"<b><a href=\"{data.url}\">{data.title}</a></b>"
        )
        # Videos, news etc.
        if pub_date:
            body += f"> {pub_date}  \n>  \n"
            html += f"<p><sub>{pub_date}</sub></p>"
        if data.length:
            body += f"> > **Length:** {data.length}  \n>  \n"
            html += f"<blockquote><b>Length:</b> {data.length}</blockquote>"
        if data.views:
            body += f"> > **Views:** {data.views}  \n>  \n"
            html += f"<blockquote><b>Views:</b> {data.views}</blockquote>"
        if data.author:
            body += f"> > **Author:** {data.author}  \n>  \n"
            html += f"<blockquote><b>Author:</b> {data.author}</blockquote>"
        if data.authors:
            body += f"> > **Authors:** {", ".join(data.authors)}  \n>  \n"
            html += f"<blockquote><b>Authors:</b> {", ".join(data.authors)}</blockquote>"
        if data.publisher:
            body += f"> > **Publisher:** {data.publisher}  \n>  \n"
            html += f"<blockquote><b>Publisher:</b> {data.publisher}</blockquote>"
        # Publications
        if data.journal:
            body += f"> > **Journal:** {data.journal}  \n>  \n"
            html += f"<blockquote><b>Journal:</b> {data.journal}</blockquote>"
        if data.doi:
            body += f"> > **Digital Identifier:** [{data.doi}](https://oadoi.org/{data.doi})  \n>  \n"
            html += f"<blockquote><b>Digital Identifier:</b> <a href=\"https://oadoi.org/{data.doi}\">{data.doi}</a></blockquote>"
        if data.issn:
            body += f"> > **ISSN:** {", ".join(data.issn)}  \n>  \n"
            html += f"<blockquote><b>ISSN:</b> {", ".join(data.issn)}</blockquote>"
        # File content
        if data.seed or data.leech:
            seeders_leechers = f"{data.seed if data.seed else 'N/A'}/{data.leech if data.leech else 'N/A'}"
            body += f"> > **Seeders/Leechers:** {seeders_leechers}  \n>  \n"
            html += f"<blockquote><b>Seeders/Leechers:</b> {seeders_leechers}</blockquote>"
        if data.filesize:
            body += f"> > **Size:** {data.filesize}  \n>  \n"
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
            body += "  \n>  \n"
            html += f"</blockquote>"
        # Repository content
        if data.package_name:
            body += f"> > **Name:** {data.package_name}  \n>  \n"
            html += f"<blockquote><b>Name:</b> {data.package_name}</blockquote>"
        if data.maintainer:
            body += f"> > **Maintainer:** {data.maintainer}  \n>  \n"
            html += f"<blockquote><b>Maintainer:</b> {data.maintainer}</blockquote>"
        if data.homepage or data.source_code_url:
            project_body = ""
            project_html = ""
            if data.homepage:
                project_body += f"[Homepage]({data.homepage})"
                project_html += f"<a href=\"{data.homepage}\">Homepage</a>"
            if data.source_code_url:
                if project_body:
                    project_body += " | "
                    project_html += " | "
                project_body += f"[Source code]({data.source_code_url})"
                project_html += f"<a href=\"{data.source_code_url}\">Source code</a>"
            body += f"> > **Project:** {project_body}  \n>  \n"
            html += f"<blockquote><b>Project:</b> {project_html}</blockquote>"
        if data.license_name:
            if data.license_url:
                license_body = f"[{data.license_name}]({data.license_url})"
                license_html = f"<a href=\"{data.license_url}\">{data.license_name}</a>"
            else:
                license_body = data.license_name
                license_html = data.license_name
            body += f"> > **License:** {license_body}  \n>  \n"
            html += f"<blockquote><b>License:</b> {license_html}</blockquote>"
        # Universal description
        if data.metadata:
            body += f"> > **{data.metadata}**  \n>  \n"
            html += f"<blockquote><b>{data.metadata}</b></blockquote>"
        if data.content:
            content = f"{data.content}{"..." if not data.content.endswith((".", "!", "?")) else ""}"
            body += f"> {content}  \n>  \n"
            html += f"<p>{content}</p>"
        if data.comment:
            body += f"> *{data.comment}*  \n>  \n"
            html += f"<p><i>{data.comment}</i></p>"
        # Map content
        if data.links:
            links = "  \n".join([f"> > {link.label}: [{link.url_label}]({link.url})" for link in data.links])
            body += f"> > **Links:**  \n{links}  \n>  \n"
            links = "<br>".join([f"{link.label}: <a href=\"{link.url}\">{link.url_label}</a>" for link in data.links])
            html += f"<blockquote><b>Links:</b><br>{links}</blockquote>"
        if data.address:
            body += f"> > **Address:**  \n> > {data.address.name if data.address.name else ''}  \n"
            html += (
                f"<blockquote><b>Address:</b><br>"
                f"{data.address.name if data.address.name else ''}<br>"
            )
            if data.address.road:
                body += f"> > {data.address.road} {data.address.house_number if data.address.house_number else ''}  \n"
                html += f"{data.address.road} {data.address.house_number if data.address.house_number else ''}<br>"
            if data.address.locality:
                body += f"> > {data.address.locality} {data.address.postcode if data.address.postcode else ''}  \n"
                html += f"{data.address.locality} {data.address.postcode if data.address.postcode else ''}<br>"
            if data.address.country:
                body += f"> > {data.address.country}  \n"
                html += f"{data.address.country}"
            body += ">  \n"
            html += f"</blockquote>"
        if data.pdf_url:
            body += f"> [**PDF**]({data.pdf_url})  \n>  \n"
            html += f"<br><b><a href=\"{data.pdf_url}\">PDF</a></b>"
        html += f"</td>"
        # Picture
        if data.thumbnail:
            html += (
                f"<td>"
                f"<img src=\"{data.thumbnail}\" height=\"150\" />"
                f"</td>"
            )
        body += f"> **Results from {data.engine}**"
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
