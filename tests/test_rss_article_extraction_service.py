import unittest
from unittest.mock import patch

import httpx

from app.models.rss import RssItem
from app.services import rss_article_extraction_service


def make_item(**kwargs) -> RssItem:
    return RssItem(
        item_id=kwargs.get("item_id", "item_1"),
        source_id="source_1",
        publisher="Federal Register",
        title="Notice of filing",
        url=kwargs.get(
            "url",
            "https://www.federalregister.gov/documents/2026/05/18/example",
        ),
        summary=kwargs.get("summary", "Short RSS summary."),
        first_seen_at="2026-05-18T00:00:00Z",
        last_seen_at="2026-05-18T00:00:00Z",
        content_hash="hash_1",
        feed_url="https://example.com/rss",
        article_lead=kwargs.get("article_lead", ""),
        article_text_hash=kwargs.get("article_text_hash"),
    )


class RssArticleExtractionServiceTest(unittest.TestCase):
    def test_unblock_redirect_page_is_failed_not_article_lead(self):
        item = make_item(article_lead="previous useful lead", article_text_hash="old_hash")

        def fake_get(*args, **kwargs):
            return httpx.Response(
                200,
                headers={"content-type": "text/html"},
                text="<html><body><p>Please unblock to continue.</p></body></html>",
                request=httpx.Request("GET", "https://unblock.federalregister.gov/"),
            )

        with patch.object(rss_article_extraction_service.httpx, "get", fake_get):
            result = rss_article_extraction_service.extract_article_lead(item)

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["article_lead"], "previous useful lead")
        self.assertEqual(result["article_text_hash"], "old_hash")
        self.assertIn("blocked article fetch", result["error"])

    def test_regular_article_html_can_succeed(self):
        item = make_item()
        paragraph = " ".join(["This filing describes a proposed market structure change."] * 20)

        def fake_get(*args, **kwargs):
            return httpx.Response(
                200,
                headers={"content-type": "text/html"},
                text=f"<html><body><article><p>{paragraph}</p></article></body></html>",
                request=httpx.Request("GET", item.url),
            )

        with patch.object(rss_article_extraction_service.httpx, "get", fake_get):
            result = rss_article_extraction_service.extract_article_lead(item)

        self.assertEqual(result["status"], "success")
        self.assertIn("market structure change", result["article_lead"])
        self.assertTrue(result["article_text_hash"])


if __name__ == "__main__":
    unittest.main()
