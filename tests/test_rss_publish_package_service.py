import unittest
from unittest.mock import patch

from app.models.podcast import RssPodcastEpisode, RssPodcastScript
from app.models.signal import BriefingCategory, BriefingSection, BriefingTopChange, RssBriefing
from app.services import rss_publish_package_service


def make_briefing() -> RssBriefing:
    return RssBriefing(
        briefing_id="brief_1",
        briefing_date="2026-05-09",
        generated_at="2026-05-09T00:00:00Z",
        score_threshold=60,
        top_changes=[
            BriefingTopChange(
                rank=1,
                title="title",
                summary="summary",
                referenced_urls=["https://example.com/a", "https://example.com/a"],
            )
        ],
        categories=[
            BriefingCategory(
                category_id="tech",
                title="科技發展",
                sections=[
                    BriefingSection(
                        section_id="sec_1",
                        title="section",
                        summary="summary",
                        referenced_urls=["https://example.com/b"],
                    )
                ],
            )
        ],
    )


def make_script() -> RssPodcastScript:
    return RssPodcastScript(
        script_id="script_1",
        briefing_id="brief_1",
        briefing_date="2026-05-09",
        generated_at="2026-05-09T00:00:00Z",
        episode_title="2026/05/09-測試標題",
        script="script",
        show_notes="來源：https://example.com/c\n重複：https://example.com/a",
        google_doc_url="https://docs.google.com/document/d/doc-id/edit",
    )


def make_episode() -> RssPodcastEpisode:
    return RssPodcastEpisode(
        episode_id="episode_script_1",
        script_id="script_1",
        briefing_date="2026-05-09",
        generated_at="2026-05-09T00:00:00Z",
        audio_url="gs://bucket/podcasts/2026-05-09/script_1.mp3",
        audio_gcs_uri="gs://bucket/podcasts/2026-05-09/script_1.mp3",
    )


class FakeFirestore:
    def __init__(self, existing=None):
        self.existing = existing
        self.package = None

    def get_publish_package_by_script_id(self, script_id):
        return self.existing

    def get_briefing_by_id(self, briefing_id):
        return make_briefing()

    def upsert_publish_package(self, package):
        self.package = package


class PublishPackageServiceTest(unittest.TestCase):
    def test_create_publish_package_dedupes_sources_and_uses_deterministic_id(self):
        fake_firestore = FakeFirestore()
        with patch.object(rss_publish_package_service, "firestore_client", fake_firestore):
            result = rss_publish_package_service.create_publish_package(make_script(), make_episode())

        self.assertEqual(result["package_id"], "package_script_1")
        self.assertEqual(result["episode_title"], "2026/05/09-測試標題")
        self.assertEqual(
            result["source_urls"],
            ["https://example.com/a", "https://example.com/b", "https://example.com/c"],
        )
        self.assertEqual(fake_firestore.package.audio_gcs_uri, "gs://bucket/podcasts/2026-05-09/script_1.mp3")

    def test_create_publish_package_returns_existing_unless_forced(self):
        existing = rss_publish_package_service.RssPublishPackage(
            package_id="package_script_1",
            script_id="script_1",
            briefing_id="brief_1",
            briefing_date="2026-05-09",
            generated_at="2026-05-09T00:00:00Z",
        )
        fake_firestore = FakeFirestore(existing=existing)
        with patch.object(rss_publish_package_service, "firestore_client", fake_firestore):
            result = rss_publish_package_service.create_publish_package(make_script(), make_episode())

        self.assertEqual(result["package_id"], "package_script_1")
        self.assertIsNone(fake_firestore.package)


if __name__ == "__main__":
    unittest.main()
