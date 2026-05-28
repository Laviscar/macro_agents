from __future__ import annotations

from typing import Callable
from urllib.request import urlopen
from xml.etree import ElementTree as ET

from dateutil.parser import parse as parse_datetime

from sources.config import NewsSourceConfig
from sources.normalization import build_raw_news_item


FetchText = Callable[[str], str]


class RssFeedAdapter:
    source_type = "rss"

    def __init__(
        self,
        feed_url: str,
        source_name: str,
        fetcher: FetchText | None = None,
    ) -> None:
        self.feed_url = feed_url
        self.source_name = source_name
        self.fetcher = fetcher or self._default_fetcher

    @classmethod
    def from_config(
        cls,
        config: NewsSourceConfig,
        fetcher: FetchText | None = None,
    ) -> "RssFeedAdapter":
        feed_url = config.url or config.endpoint
        if not feed_url:
            raise ValueError(f"RSS source '{config.name}' is missing url.")
        return cls(
            feed_url=feed_url,
            source_name=config.name,
            fetcher=fetcher,
        )

    def fetch_latest(self) -> list:
        xml_text = self.fetcher(self.feed_url)
        return self._parse_feed(xml_text)

    def _parse_feed(self, xml_text: str) -> list:
        root = ET.fromstring(xml_text)

        if self._local_name(root.tag) == "rss":
            return self._parse_rss(root)
        if self._local_name(root.tag) == "feed":
            return self._parse_atom(root)
        raise ValueError("Unsupported feed format.")

    def _parse_rss(self, root: ET.Element) -> list:
        items: list = []
        for entry in root.findall("./channel/item"):
            title = self._child_text(entry, "title")
            url = self._child_text(entry, "link")
            summary = self._child_text(entry, "description")
            external_id = self._child_text(entry, "guid") or url or title
            published_at = self._normalize_published_at(self._child_text(entry, "pubDate"))
            items.append(
                build_raw_news_item(
                    source_type="rss",
                    source_name=self.source_name,
                    external_id=external_id,
                    url=url,
                    title=title,
                    summary=summary,
                    published_at=published_at,
                )
            )
        return items

    def _parse_atom(self, root: ET.Element) -> list:
        items: list = []
        for entry in root.findall("{http://www.w3.org/2005/Atom}entry"):
            title = self._child_text(entry, "title")
            url = self._atom_link(entry)
            summary = self._child_text(entry, "summary") or self._child_text(entry, "content")
            external_id = self._child_text(entry, "id") or url or title
            published_at = self._normalize_published_at(
                self._child_text(entry, "published") or self._child_text(entry, "updated")
            )
            items.append(
                build_raw_news_item(
                    source_type="atom",
                    source_name=self.source_name,
                    external_id=external_id,
                    url=url,
                    title=title,
                    summary=summary,
                    published_at=published_at,
                )
            )
        return items

    def _child_text(self, parent: ET.Element, name: str) -> str:
        for child in parent:
            if self._local_name(child.tag) == name and child.text:
                return child.text.strip()
        return ""

    def _atom_link(self, entry: ET.Element) -> str:
        for child in entry:
            if self._local_name(child.tag) != "link":
                continue
            href = child.attrib.get("href", "").strip()
            if href:
                return href
            if child.text:
                return child.text.strip()
        return ""

    def _normalize_published_at(self, raw_value: str) -> str | None:
        if not raw_value:
            return None
        return parse_datetime(raw_value).isoformat()

    def _local_name(self, tag: str) -> str:
        if "}" not in tag:
            return tag
        return tag.rsplit("}", 1)[-1]

    def _default_fetcher(self, feed_url: str) -> str:
        with urlopen(feed_url, timeout=15) as response:
            return response.read().decode("utf-8")
