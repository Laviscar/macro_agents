from sources.rss_feed import RssFeedAdapter


SAMPLE_RSS = """\
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Macro Feed</title>
    <item>
      <guid>cpi-1</guid>
      <title>US CPI cools in March</title>
      <link>https://example.com/cpi-cools</link>
      <description>Inflation data came in softer than expected.</description>
      <pubDate>Mon, 30 Mar 2026 08:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""


def test_rss_feed_adapter_normalizes_feed_entries() -> None:
    adapter = RssFeedAdapter(
        feed_url="https://example.com/feed.xml",
        source_name="example_rss",
        fetcher=lambda _url: SAMPLE_RSS,
    )

    items = adapter.fetch_latest()

    assert len(items) == 1
    item = items[0]
    assert item.source_type == "rss"
    assert item.source_name == "example_rss"
    assert item.external_id == "cpi-1"
    assert item.title == "US CPI cools in March"
    assert item.summary == "Inflation data came in softer than expected."
    assert item.url == "https://example.com/cpi-cools"
    assert item.raw_payload["title"] == "US CPI cools in March"
    assert item.raw_payload["theme"] == ["inflation"]
    assert item.raw_payload["importance_score"] >= 0.7


SAMPLE_RDF = """\
<?xml version="1.0" encoding="utf-8"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:dc="http://purl.org/dc/elements/1.1/"
         xmlns="http://purl.org/rss/1.0/">
  <channel rdf:about="https://www.bis.org/"><title>BIS</title></channel>
  <item rdf:about="https://www.bis.org/press/p260527.htm">
    <title>BIS report on tokenisation</title>
    <link>https://www.bis.org/press/p260527.htm</link>
    <description>Project Agora results.</description>
    <dc:date>2026-05-27T13:42:00+00:00</dc:date>
  </item>
</rdf:RDF>
"""


def test_rss_feed_adapter_parses_rss1_rdf() -> None:
    adapter = RssFeedAdapter(feed_url="https://x/bis.rss", source_name="bis", fetcher=lambda _u: SAMPLE_RDF)
    items = adapter.fetch_latest()
    assert len(items) == 1
    it = items[0]
    assert it.title == "BIS report on tokenisation"
    assert it.url == "https://www.bis.org/press/p260527.htm"
    assert it.published_at == "2026-05-27T13:42:00+00:00"
