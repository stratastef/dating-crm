"""Tinder connector: reads the account owner's own matches, messages and candidates, sends messages, likes and
passes, and spends a Super Like or Boost the account holds, with their web session token.

The API is unofficial. The request and response shapes here follow public write-ups of the web client and are
not confirmed against a real account: see docs/modules/tinder-connector.md for the list of assumptions.
"""

from collections.abc import Iterator

import httpx

from app.connectors import Connector

PAGE_SIZE = 60


class TinderConnector(Connector):
    app = "tinder"
    capabilities = frozenset(
        {"read_matches", "read_messages", "send", "read_candidates", "like", "pass", "super_like", "boost"}
    )

    transport: httpx.BaseTransport | None = None  # tests put a stub here; None is the real network

    def __init__(self) -> None:
        self._person_of: dict[str, str] = {}  # match id -> the other person's user id

    def read_matches(self, token: str) -> list[dict]:
        """Every match: `id`, `name`, `has_messages`, and `last_message_id` (None if unknown or no messages)."""
        matches = []
        with self._client(token) as client:
            # The web client lists matches without and with messages separately.
            for has_messages in (False, True):
                for match in self._pages(client, "/v2/matches", "matches", {"message": int(has_messages)}):
                    self._person_of[match["_id"]] = match["person"]["_id"]
                    preview = match.get("messages") or []
                    # Newest by date, so the order of the preview list does not matter.
                    newest = max(preview, key=lambda message: message["sent_date"], default=None)
                    matches.append(
                        {
                            "id": match["_id"],
                            "name": match["person"]["name"],
                            "has_messages": has_messages,
                            "last_message_id": newest["_id"] if has_messages and newest else None,
                        }
                    )
        return matches

    def read_messages(self, token: str, match_id: str) -> list[dict]:
        """Every message of a match: `id`, `sender` (`me` or `them`), `body`, `sent_at` (ISO 8601)."""
        if match_id not in self._person_of:
            self.read_matches(token)
        them = self._person_of[match_id]
        with self._client(token) as client:
            return [
                {
                    "id": message["_id"],
                    "sender": "them" if message["from"] == them else "me",
                    "body": message["message"],
                    "sent_at": message["sent_date"],
                }
                for message in self._pages(client, f"/v2/matches/{match_id}/messages", "messages", {})
            ]

    def send(self, token: str, match_id: str, text: str) -> dict:
        """Send one message to a match. Returns the sent message's `id` and `sent_at` (ISO 8601)."""
        with self._client(token) as client:
            response = client.post(f"/user/matches/{match_id}", json={"message": text})
            response.raise_for_status()
            message = response.json()
        return {"id": message["_id"], "sent_at": message["sent_date"]}

    def read_candidates(self, token: str) -> list[dict]:
        """The next profiles Tinder offers to swipe on: `id`, `name`, `bio` (may be empty), `photos` (URLs)."""
        with self._client(token) as client:
            response = client.get("/v2/recs/core")
            response.raise_for_status()
            return [
                {
                    "id": result["user"]["_id"],
                    "name": result["user"]["name"],
                    "bio": result["user"].get("bio", ""),
                    "photos": [photo["url"] for photo in result["user"].get("photos", [])],
                }
                # Tinder answers without `results` when it has nobody left to show.
                for result in response.json()["data"].get("results") or []
            ]

    def like(self, token: str, profile_id: str) -> None:
        """A free like. Paid items (Super Like, Boost) have their own endpoints and methods, below."""
        self._swipe(token, "like", profile_id)

    def super_like(self, token: str, profile_id: str) -> bool:
        """Spend one Super Like the account holds on a profile. False when it holds none; nothing is bought."""
        return self._spend(token, f"/like/{profile_id}/super")

    def boost(self, token: str) -> bool:
        """Start one Boost the account holds. False when it holds none; nothing is bought."""
        return self._spend(token, "/boost")

    def _spend(self, token: str, path: str) -> bool:
        with self._client(token) as client:
            response = client.post(path)
            response.raise_for_status()
            return not response.json().get("limit_exceeded")

    def pass_(self, token: str, profile_id: str) -> None:
        self._swipe(token, "pass", profile_id)

    def _swipe(self, token: str, direction: str, profile_id: str) -> None:
        with self._client(token) as client:
            client.get(f"/{direction}/{profile_id}").raise_for_status()

    def _client(self, token: str) -> httpx.Client:
        return httpx.Client(
            base_url="https://api.gotinder.com",
            headers={"X-Auth-Token": token},
            transport=self.transport,
            timeout=30,
        )

    @staticmethod
    def _pages(client: httpx.Client, path: str, key: str, params: dict) -> Iterator[dict]:
        page_token = None
        while True:
            page = {"page_token": page_token} if page_token else {}
            response = client.get(path, params={"count": PAGE_SIZE, **params, **page})
            # The error names the status and URL only. The token is in a header and is never part of it.
            response.raise_for_status()
            data = response.json()["data"]
            yield from data[key]
            page_token = data.get("next_page_token")
            if not page_token:
                return
