import unittest
from unittest.mock import Mock, patch

from app.models.podcast import RssPodcastScript
from app.services import rss_podcast_audio_service


def make_script() -> RssPodcastScript:
    return RssPodcastScript(
        script_id="podcast_20260509_abc123",
        briefing_id="brief_1",
        briefing_date="2026-05-09",
        generated_at="2026-05-09T00:00:00Z",
        episode_title="2026/05/09-測試標題",
        script="歡迎回到 Informative AI。今天內容。感謝各位今天的收聽，明天見。",
        word_count=32,
        duration_estimate_minutes=1.5,
    )


class FakeFirestore:
    def __init__(self):
        self.episode = None

    def get_podcast_episode_by_script_id(self, script_id):
        return None

    def upsert_podcast_episode(self, episode):
        self.episode = episode


class PodcastAudioServiceTest(unittest.TestCase):
    def test_missing_bucket_fails_before_tts_call(self):
        client_factory = Mock()
        with patch.object(rss_podcast_audio_service.firestore_client, "get_podcast_episode_by_script_id", return_value=None), \
             patch.object(rss_podcast_audio_service.settings, "GCS_AUDIO_BUCKET", ""), \
             patch.object(rss_podcast_audio_service.texttospeech, "TextToSpeechLongAudioSynthesizeClient", client_factory):
            with self.assertRaisesRegex(ValueError, "GCS_AUDIO_BUCKET"):
                rss_podcast_audio_service.synthesize_podcast_audio(make_script())

        client_factory.assert_not_called()

    def test_synthesize_podcast_audio_writes_long_audio_to_gcs(self):
        fake_firestore = FakeFirestore()
        operation = Mock()
        client = Mock()
        client.synthesize_long_audio.return_value = operation

        with patch.object(rss_podcast_audio_service, "firestore_client", fake_firestore), \
             patch.object(rss_podcast_audio_service.settings, "GCS_AUDIO_BUCKET", "audio-bucket"), \
             patch.object(rss_podcast_audio_service.settings, "GCP_PROJECT_ID", "project-id"), \
             patch.object(rss_podcast_audio_service.settings, "PODCAST_TTS_LOCATION", "global"), \
             patch.object(rss_podcast_audio_service.settings, "PODCAST_TTS_LANGUAGE_CODE", "cmn-TW"), \
             patch.object(rss_podcast_audio_service.settings, "PODCAST_TTS_VOICE", "cmn-TW-Chirp3-HD-Charon"), \
             patch.object(rss_podcast_audio_service, "_get_gcs_object_size", return_value=12345), \
             patch.object(rss_podcast_audio_service.texttospeech, "TextToSpeechLongAudioSynthesizeClient", return_value=client):
            result = rss_podcast_audio_service.synthesize_podcast_audio(make_script())

        request = client.synthesize_long_audio.call_args.kwargs["request"]
        self.assertEqual(request["parent"], "projects/project-id/locations/global")
        self.assertEqual(request["voice"]["language_code"], "cmn-TW")
        self.assertEqual(request["voice"]["name"], "cmn-TW-Chirp3-HD-Charon")
        self.assertEqual(request["audio_config"]["audio_encoding"], rss_podcast_audio_service.texttospeech.AudioEncoding.LINEAR16)
        self.assertEqual(
            request["output_gcs_uri"],
            "gs://audio-bucket/podcasts/2026-05-09/podcast_20260509_abc123.wav",
        )
        operation.result.assert_called_once()
        self.assertEqual(result["episode_id"], "episode_podcast_20260509_abc123")
        self.assertEqual(result["audio_size_bytes"], 12345)
        self.assertEqual(fake_firestore.episode.audio_gcs_uri, request["output_gcs_uri"])


if __name__ == "__main__":
    unittest.main()
