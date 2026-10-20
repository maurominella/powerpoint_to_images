from contextlib import redirect_stderr, redirect_stdout
from io import BytesIO, StringIO
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

from query_kb import (
    SUBSCRIPTION,
    get_access_token,
    main,
    print_result,
    query_knowledge_base,
    request_json,
)


class KnowledgeBaseTests(unittest.TestCase):
    @patch("query_kb.subprocess.run")
    def test_token_uses_explicit_subscription_and_search_resource(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, "test-token\n", "")
        self.assertEqual(get_access_token(), "test-token")
        command = run.call_args.args[0]
        self.assertEqual(command[command.index("--subscription") + 1], SUBSCRIPTION)
        self.assertEqual(
            command[command.index("--resource") + 1], "https://search.azure.com"
        )

    @patch("query_kb.subprocess.run", side_effect=FileNotFoundError)
    def test_missing_cli_is_explicit(self, run):
        with self.assertRaisesRegex(RuntimeError, "Azure CLI is required"):
            get_access_token()

    @patch("query_kb.request_json")
    def test_discovers_sources_and_requests_all_reference_data(self, request):
        expected = {"response": [], "references": []}
        request.side_effect = [
            {"knowledgeSources": [{"name": "istat2023"}, {"name": "istat2024"}]},
            {"kind": "indexedSharePoint"},
            {"kind": "indexedSharePoint"},
            expected,
        ]
        self.assertEqual(query_knowledge_base("Confronta 2023 e 2024", "token"), expected)
        path, token, version, body = request.call_args.args
        self.assertEqual(path, "knowledgebases/knowledgebase-istat/retrieve")
        self.assertEqual(body["messages"][0]["content"][0]["text"], "Confronta 2023 e 2024")
        self.assertTrue(body["includeActivity"])
        self.assertEqual(
            body["knowledgeSourceParams"],
            [
                {
                    "knowledgeSourceName": name,
                    "kind": "indexedSharePoint",
                    "includeReferences": True,
                    "includeReferenceSourceData": True,
                }
                for name in ("istat2023", "istat2024")
            ],
        )

    @patch("query_kb.request_json", return_value={"knowledgeSources": []})
    def test_empty_sources_fail(self, request):
        with self.assertRaisesRegex(RuntimeError, "no knowledgeSources"):
            query_knowledge_base("Question", "token")

    @patch("query_kb.urlopen")
    def test_http_payload_and_bearer_auth(self, open_url):
        response = MagicMock()
        response.status = 200
        response.read.return_value = b'{"references": []}'
        open_url.return_value.__enter__.return_value = response
        self.assertEqual(
            request_json("test/retrieve", "secret", "2026-08-01-preview", {"x": 1}),
            {"references": []},
        )
        request = open_url.call_args.args[0]
        self.assertEqual(request.method, "POST")
        self.assertEqual(request.get_header("Authorization"), "Bearer secret")
        self.assertEqual(json.loads(request.data), {"x": 1})
        self.assertIn("api-version=2026-08-01-preview", request.full_url)

    @patch("query_kb.urlopen")
    def test_http_error_preserves_service_details(self, open_url):
        open_url.side_effect = HTTPError(
            "https://example.test", 403, "Forbidden", {}, BytesIO(b"permission denied")
        )
        with self.assertRaisesRegex(RuntimeError, "permission denied"):
            request_json("test", "token", "version")

    @patch("query_kb.urlopen")
    def test_partial_response_is_not_success(self, open_url):
        response = MagicMock()
        response.status = 206
        response.read.return_value = b'{"error": "one source failed"}'
        open_url.return_value.__enter__.return_value = response
        with self.assertRaisesRegex(RuntimeError, "HTTP 206"):
            request_json("test", "token", "version")

    def test_prints_exact_reference_id_and_document_path(self):
        reference = {
            "id": "7",
            "docKey": "chunk-42",
            "sourceData": {
                "doc_url": "https://example.sharepoint.com/ISTAT/2023/slide007.png"
            },
        }
        output = StringIO()
        with redirect_stdout(output):
            print_result(
                {
                    "response": [{"content": [{"type": "text", "text": "Answer [7]"}]}],
                    "references": [reference],
                }
            )
        text = output.getvalue()
        self.assertIn("Answer [7]", text)
        self.assertEqual(json.loads(text[text.index("[\n"):]), [reference])

    def test_warns_when_source_data_is_missing(self):
        errors = StringIO()
        with redirect_stdout(StringIO()), redirect_stderr(errors):
            print_result({"response": [], "references": [{"id": "0", "sourceData": None}]})
        self.assertIn("no sourceData", errors.getvalue())

    @patch("query_kb.get_access_token", return_value="token")
    @patch("query_kb.query_knowledge_base")
    def test_cli_saves_full_json_including_activity(self, query, token):
        result = {"response": [], "references": [], "activity": [{"id": 1}]}
        query.return_value = result
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "response.json"
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                self.assertEqual(main(["Question", "--output", str(output)]), 0)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), result)

    @patch("query_kb.get_access_token")
    def test_blank_question_fails_before_authentication(self, token):
        with redirect_stderr(StringIO()):
            self.assertEqual(main(["  "]), 1)
        token.assert_not_called()


if __name__ == "__main__":
    unittest.main()
