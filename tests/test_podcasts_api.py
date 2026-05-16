import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.models.podcast import RssPodcastEpisode, RssPodcastScript, RssPublishPackage


def make_script(date="2026-05-09") -> RssPodcastScript:
    return RssPodcastScript(
        script_id="script_1",
        briefing_id="brief_1",
        briefing_date=date,
        generated_at="2026-05-09T00:00:00Z",
        episode_title="2026/05/09-測試標題",
        script="script",
    )


class PodcastsApiTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_generate_script_requires_admin_token(self):
        r = self.client.post("/podcasts/generate-script")
        self.assertEqual(r.status_code, 401)

    def test_run_daily_calls_service(self):
        payload = {"ok": True, "script": {"script_id": "script_1"}}
        from app.api import routes_podcasts

        with patch.object(routes_podcasts.settings, "ADMIN_TOKEN", "token"), \
             patch.object(routes_podcasts, "run_daily_podcast", return_value=payload) as run_daily:
            r = self.client.post(
                "/podcasts/run-daily",
                headers={"X-Admin-Token": "token"},
                json={"briefing_id": "brief_1", "write_google_doc": False},
            )

        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), payload)
        run_daily.assert_called_once_with(
            briefing_id="brief_1",
            write_google_doc=False,
            force_audio=False,
            force_package=False,
            run_bucket=None,
            model_overrides={},
        )

    def test_today_returns_script_episode_and_package(self):
        from app.api import routes_podcasts

        episode = RssPodcastEpisode(
            episode_id="episode_script_1",
            script_id="script_1",
            briefing_date="2026-05-09",
            generated_at="2026-05-09T00:00:00Z",
        )
        package = RssPublishPackage(
            package_id="package_script_1",
            script_id="script_1",
            briefing_id="brief_1",
            briefing_date="2026-05-09",
            generated_at="2026-05-09T00:00:00Z",
        )
        with patch.object(routes_podcasts, "_today_date_str", return_value="2026-05-09"), \
             patch.object(routes_podcasts.firestore_client, "list_recent_podcast_scripts", return_value=[make_script()]), \
             patch.object(routes_podcasts.firestore_client, "get_podcast_episode_by_script_id", return_value=episode), \
             patch.object(routes_podcasts.firestore_client, "get_publish_package_by_script_id", return_value=package):
            r = self.client.get("/podcasts/today")

        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["briefing_date"], "2026-05-09")
        self.assertEqual(body["script"]["script_id"], "script_1")
        self.assertEqual(body["episode"]["episode_id"], "episode_script_1")
        self.assertEqual(body["publish_package"]["package_id"], "package_script_1")

    def test_episode_and_publish_package_not_found(self):
        from app.api import routes_podcasts

        with patch.object(routes_podcasts.firestore_client, "get_podcast_episode_by_script_id", return_value=None):
            episode_response = self.client.get("/podcasts/missing/episode")
        with patch.object(routes_podcasts.firestore_client, "get_publish_package_by_script_id", return_value=None):
            package_response = self.client.get("/podcasts/missing/publish-package")

        self.assertEqual(episode_response.status_code, 404)
        self.assertEqual(package_response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
