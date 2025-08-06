from dataclasses import dataclass


@dataclass
class LinkData:
    label: str
    url: str
    url_label: str


@dataclass
class AddressData:
    name: str
    house_number: str
    road: str
    locality: str
    postcode: str
    country: str


@dataclass
class SearchData:
    url: str
    links: list[LinkData]
    content: str
    title: str
    engine: str
    published_date: str
    thumbnail: str
    publisher: str
    author: str
    authors: list[str]
    views: str
    length: str
    metadata: str
    seed: str
    leech: str
    magnetlink: str
    torrentfile: str
    filesize: str
    address: AddressData
    pdf_url: str
    doi: str
    journal: str
    issn: list[str]
    comment: str
    maintainer: str
    license_name: str
    license_url: str
    homepage: str
    source_code_url: str
    package_name: str
