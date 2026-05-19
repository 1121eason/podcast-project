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
             patch.object(rss_podcast_audio_service.settings, "PODCAST_TTS_PROVIDER", "google"), \
             patch.object(rss_podcast_audio_service.settings, "PODCAST_TTS_LOCATION", "global"), \
             patch.object(rss_podcast_audio_service.settings, "PODCAST_TTS_LANGUAGE_CODE", "cmn-TW"), \
             patch.object(rss_podcast_audio_service.settings, "PODCAST_TTS_VOICE", "cmn-TW-Wavenet-B"), \
             patch.object(rss_podcast_audio_service.settings, "PODCAST_TTS_INPUT_MODE", "text"), \
             patch.object(rss_podcast_audio_service, "_get_gcs_object_size", return_value=12345), \
             patch.object(rss_podcast_audio_service.texttospeech, "TextToSpeechLongAudioSynthesizeClient", return_value=client):
            result = rss_podcast_audio_service.synthesize_podcast_audio(make_script())

        request = client.synthesize_long_audio.call_args.kwargs["request"]
        self.assertEqual(request["parent"], "projects/project-id/locations/global")
        self.assertEqual(request["input"], {"text": make_script().script})
        self.assertEqual(request["voice"]["language_code"], "cmn-TW")
        self.assertEqual(request["voice"]["name"], "cmn-TW-Wavenet-B")
        self.assertEqual(request["audio_config"]["audio_encoding"], rss_podcast_audio_service.texttospeech.AudioEncoding.LINEAR16)
        self.assertEqual(
            request["output_gcs_uri"],
            "gs://audio-bucket/podcasts/2026-05-09/podcast_20260509_abc123.wav",
        )
        operation.result.assert_called_once()
        self.assertEqual(result["episode_id"], "episode_podcast_20260509_abc123")
        self.assertEqual(result["audio_size_bytes"], 12345)
        self.assertEqual(fake_firestore.episode.audio_gcs_uri, request["output_gcs_uri"])

    def test_openai_two_host_provider_uploads_local_wav_to_gcs(self):
        fake_firestore = FakeFirestore()
        podcast = make_script()

        with patch.object(rss_podcast_audio_service, "firestore_client", fake_firestore), \
             patch.object(rss_podcast_audio_service.settings, "GCS_AUDIO_BUCKET", "audio-bucket"), \
             patch.object(rss_podcast_audio_service.settings, "GCP_PROJECT_ID", "project-id"), \
             patch.object(rss_podcast_audio_service.settings, "PODCAST_TTS_PROVIDER", "openai"), \
             patch.object(rss_podcast_audio_service.settings, "PODCAST_OPENAI_TTS_MALE_VOICE", "cedar"), \
             patch.object(rss_podcast_audio_service.settings, "PODCAST_OPENAI_TTS_FEMALE_VOICE", "shimmer"), \
             patch.object(rss_podcast_audio_service.settings, "PODCAST_OPENAI_TTS_MODEL", "gpt-4o-mini-tts"), \
             patch.object(rss_podcast_audio_service.settings, "PODCAST_OPENAI_DIALOGUE_MODEL", "gpt-5-mini"), \
             patch.object(rss_podcast_audio_service.settings, "PODCAST_OPENAI_TTS_SPEED", 1.25), \
             patch.object(rss_podcast_audio_service, "_synthesize_openai_two_host_audio", return_value={"tts_chars": 88, "turn_count": 6}) as synthesize_openai, \
             patch.object(rss_podcast_audio_service, "_upload_file_to_gcs") as upload_file, \
             patch.object(rss_podcast_audio_service, "_get_gcs_object_size", return_value=54321):
            result = rss_podcast_audio_service.synthesize_podcast_audio(podcast)

        synthesize_openai.assert_called_once()
        upload_file.assert_called_once()
        uploaded_args = upload_file.call_args.args
        self.assertEqual(uploaded_args[1], "audio-bucket")
        self.assertEqual(uploaded_args[2], "podcasts/2026-05-09/podcast_20260509_abc123.wav")
        self.assertEqual(uploaded_args[3], "audio/wav")
        self.assertEqual(result["tts_voice"], "cedar+shimmer")
        self.assertIn("openai:gpt-4o-mini-tts:two_host_flow_max:gpt-5-mini", result["tts_model"])
        self.assertIn("speed=1.25", result["tts_model"])
        self.assertEqual(result["tts_language_code"], "zh-TW")
        self.assertEqual(result["tts_location"], "openai")
        self.assertEqual(result["tts_chars"], 88)
        self.assertEqual(result["audio_size_bytes"], 54321)
        self.assertEqual(fake_firestore.episode.audio_gcs_uri, "gs://audio-bucket/podcasts/2026-05-09/podcast_20260509_abc123.wav")

    def test_parse_dialogue_patches_opening_and_closing(self):
        turns = rss_podcast_audio_service._parse_dialogue(
            "HOST_A: 今天先看市場。\nHOST_B: 這裡很關鍵。"
        )

        self.assertTrue(turns[0][1].startswith("歡迎回到 Informative AI。"))
        self.assertTrue(turns[-1][1].endswith("感謝各位今天的收聽，明天見。"))

    def test_script_to_ssml_adds_breaks_and_escapes_text(self):
        ssml = rss_podcast_audio_service._script_to_ssml("第一段 A&B。\n同段第二句。\n\n第二段。")

        self.assertTrue(ssml.startswith("<speak>"))
        self.assertIn("A&amp;B", ssml)
        self.assertIn('break time="350ms"', ssml)
        self.assertIn('break time="700ms"', ssml)

    def test_tts_input_defaults_to_text_and_supports_ssml_opt_in(self):
        script = make_script().script
        with patch.object(rss_podcast_audio_service.settings, "PODCAST_TTS_INPUT_MODE", "text"):
            tts_input, mode = rss_podcast_audio_service._tts_input_for_script(script)
        self.assertEqual(tts_input, {"text": script})
        self.assertEqual(mode, "text")

        with patch.object(rss_podcast_audio_service.settings, "PODCAST_TTS_INPUT_MODE", "ssml"):
            tts_input, mode = rss_podcast_audio_service._tts_input_for_script(script)
        self.assertIn("ssml", tts_input)
        self.assertEqual(mode, "ssml")


if __name__ == "__main__":
    unittest.main()
