import unittest
from unittest.mock import Mock, patch

from app.clients.docs_client import DocsClient, extract_text_from_document


class DocsClientTest(unittest.TestCase):
    def test_extract_text_from_document_reads_paragraphs_and_tables(self):
        document = {
            "body": {
                "content": [
                    {
                        "paragraph": {
                            "elements": [
                                {"textRun": {"content": "Signal Brief\n"}},
                                {"textRun": {"content": "Reviewed copy\n"}},
                            ]
                        }
                    },
                    {
                        "table": {
                            "tableRows": [
                                {
                                    "tableCells": [
                                        {
                                            "content": [
                                                {
                                                    "paragraph": {
                                                        "elements": [
                                                            {"textRun": {"content": "Source A\n"}}
                                                        ]
                                                    }
                                                }
                                            ]
                                        }
                                    ]
                                }
                            ]
                        }
                    },
                ]
            }
        }

        self.assertEqual(
            extract_text_from_document(document),
            "Signal Brief\nReviewed copy\nSource A",
        )

    def test_create_document_uses_drive_when_output_folder_is_configured(self):
        client = DocsClient.__new__(DocsClient)
        client.service = Mock()
        client.drive_service = Mock()
        create_request = Mock()
        create_request.execute.return_value = {"id": "doc-id"}
        client.drive_service.files.return_value.create.return_value = create_request

        with patch("app.clients.docs_client.settings.DRIVE_OUTPUT_FOLDER_ID", "folder-id"):
            document = client.create_document("Signal Brief")

        client.drive_service.files.return_value.create.assert_called_once_with(
            body={
                "name": "Signal Brief",
                "mimeType": "application/vnd.google-apps.document",
                "parents": ["folder-id"],
            },
            fields="id",
            supportsAllDrives=True,
        )
        self.assertEqual(document, {"documentId": "doc-id"})


if __name__ == "__main__":
    unittest.main()
