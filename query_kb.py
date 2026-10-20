"""Query the ISTAT knowledge base and inspect document-level citations."""

import argparse
import json
from pathlib import Path
import subprocess
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


ENDPOINT = "https://aifoundry-6956-search.search.windows.net"
KNOWLEDGE_BASE = "knowledgebase-istat"
SUBSCRIPTION = "5d476556-6599-4792-a97f-4066de1fa86c"
API_VERSION = "2026-08-01-preview"


def get_access_token() -> str:
    try:
        result = subprocess.run(
            [
                "az", "account", "get-access-token",
                "--subscription", SUBSCRIPTION,
                "--resource", "https://search.azure.com",
                "--query", "accessToken",
                "--output", "tsv",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("Azure CLI is required. Install it and run az login.") from exc
    except subprocess.CalledProcessError as exc:
        details = exc.stderr.strip() or exc.stdout.strip()
        raise RuntimeError(
            f"Azure authentication failed: {details}\n"
            f"Run az login with access to subscription {SUBSCRIPTION}."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Azure CLI authentication timed out after 60 seconds.") from exc
    token = result.stdout.strip()
    if not token:
        raise RuntimeError("Azure CLI returned an empty access token.")
    return token


def request_json(
    path: str,
    token: str,
    api_version: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    url = f"{ENDPOINT}/{path}?{urlencode({'api-version': api_version})}"
    request = Request(
        url,
        data=None if payload is None else json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="GET" if payload is None else "POST",
    )
    try:
        with urlopen(request, timeout=180) as response:
            text = response.read().decode("utf-8")
            if response.status != 200:
                raise RuntimeError(
                    f"Azure AI Search returned HTTP {response.status} "
                    f"(incomplete or unexpected response) for {path}:\n{text}"
                )
    except HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        hint = ""
        if exc.code in (401, 403):
            hint = (
                "\nCheck Azure login, Search data-plane RBAC permissions, "
                "network access, and any SharePoint document-level permissions."
            )
        raise RuntimeError(
            f"Azure AI Search HTTP {exc.code} for {path}:\n{details}{hint}"
        ) from exc
    except URLError as exc:
        raise RuntimeError(f"Cannot reach Azure AI Search: {exc.reason}") from exc
    except TimeoutError as exc:
        raise RuntimeError(f"Azure AI Search request timed out for {path}.") from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Azure AI Search returned invalid JSON for {path}.") from exc
    if not isinstance(data, dict):
        raise RuntimeError(f"Expected a JSON object from Azure AI Search for {path}.")
    return data


def query_knowledge_base(
    question: str, token: str, api_version: str = API_VERSION
) -> dict[str, Any]:
    if not question.strip():
        raise ValueError("The question must not be empty.")
    kb_path = f"knowledgebases/{quote(KNOWLEDGE_BASE, safe='')}"
    definition = request_json(kb_path, token, api_version)
    sources = definition.get("knowledgeSources")
    if not isinstance(sources, list) or not sources:
        raise RuntimeError("The knowledge base has no knowledgeSources.")
    source_params = []
    for source in sources:
        if not isinstance(source, dict) or not isinstance(source.get("name"), str):
            raise RuntimeError("A knowledge source reference has no valid name.")
        name = source["name"]
        source_definition = request_json(
            f"knowledgesources/{quote(name, safe='')}", token, api_version
        )
        kind = source_definition.get("kind")
        if not isinstance(kind, str) or not kind:
            raise RuntimeError(f"Knowledge source {name!r} has no valid kind.")
        source_params.append(
            {
                "knowledgeSourceName": name,
                "kind": kind,
                "includeReferences": True,
                "includeReferenceSourceData": True,
            }
        )
    return request_json(
        f"{kb_path}/retrieve",
        token,
        api_version,
        {
            "messages": [
                {"role": "user", "content": [{"type": "text", "text": question}]}
            ],
            "knowledgeSourceParams": source_params,
            "includeActivity": True,
        },
    )


def print_result(result: dict[str, Any]) -> None:
    print("=== Answer / grounding response ===")
    messages = result.get("response")
    if not isinstance(messages, list):
        raise RuntimeError("The retrieval response has no valid response array.")
    for message in messages:
        for content in message.get("content", []):
            if content.get("type") == "text":
                print(content["text"])

    print("\n=== References (including sourceData and document paths) ===")
    references = result.get("references")
    if not isinstance(references, list):
        raise RuntimeError("The retrieval response has no valid references array.")
    print(json.dumps(references, ensure_ascii=False, indent=2))
    if not references:
        print("Warning: retrieval returned no document references.", file=sys.stderr)
    elif any(not reference.get("sourceData") for reference in references):
        print(
            "Warning: some references have no sourceData despite "
            "includeReferenceSourceData=true. Inspect the full response and "
            "the corresponding indexed documents.",
            file=sys.stderr,
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "question",
        nargs="?",
        default="Quale categoria di prodotti alimentari è stata più acquistata online in Italia nel 2024?",
        help="Question to send to knowledgebase-istat.",
    )
    parser.add_argument(
        "--api-version", default=API_VERSION, help="Azure AI Search REST API version."
    )
    parser.add_argument(
        "--output", type=Path, help="Save the full JSON response, including activity."
    )
    args = parser.parse_args(argv)
    try:
        if not args.question.strip():
            raise ValueError("The question must not be empty.")
        result = query_knowledge_base(
            args.question, get_access_token(), args.api_version
        )
        if args.output is not None:
            args.output.write_text(
                json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            print(f"Full response saved to {args.output}", file=sys.stderr)
        print(f"\n\n===== Citation:{result['references'][0]["sourceData"]["doc_url"].split("/root:", 1)[1]} =====\n\n")
        print_result(result)
    except (RuntimeError, ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
