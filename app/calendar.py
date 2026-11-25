"""Google Calendar: connect it, find free slots, and hold every slot offered to a match.

Other code calls `free_slots()`, `hold_slot()`, `release_holds()` and `confirm_date()`.
`google` is the only object that talks to Google; tests replace it.
The refresh token lives in the token vault under the app name `google_calendar`. Never log it.
"""

import os
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import httpx
from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy import Connection, text
from sqlalchemy.exc import IntegrityError

from app import vault
from app.audit import record_action
from app.auth import CurrentUser, Db
from app.card_lookup import find_card

router = APIRouter()

VAULT_APP = "google_calendar"
# Events to write the holds, free/busy to read availability. Nothing else is asked for.
SCOPES = "https://www.googleapis.com/auth/calendar.events https://www.googleapis.com/auth/calendar.freebusy"
_API = "https://www.googleapis.com/calendar/v3"
_TOKEN_URL = "https://oauth2.googleapis.com/token"

Slot = tuple[datetime, datetime]


class NotConnected(Exception):
    """The user has not connected Google Calendar."""


class SlotTaken(Exception):
    """The slot is busy in the user's calendar or already held for a match."""


class GoogleCalendar:
    """The one seam to Google. Each calendar method takes the user's refresh token and acts on their primary calendar."""

    def exchange_code(self, code: str) -> str:
        """Trade the authorization code from the OAuth redirect for a refresh token."""
        granted = self._token(grant_type="authorization_code", code=code, redirect_uri=os.environ["GOOGLE_REDIRECT_URI"])
        return granted["refresh_token"]

    def free_busy(self, refresh_token: str, start: datetime, end: datetime) -> list[Slot]:
        """The busy times between `start` and `end`."""
        body = {"timeMin": start.isoformat(), "timeMax": end.isoformat(), "items": [{"id": "primary"}]}
        busy = self._call(refresh_token, "POST", "/freeBusy", body)["calendars"]["primary"]["busy"]
        return [(datetime.fromisoformat(b["start"]), datetime.fromisoformat(b["end"])) for b in busy]

    def create_tentative(self, refresh_token: str, start: datetime, end: datetime, summary: str) -> str:
        """Create a tentative event and return its ID."""
        body = {
            "summary": summary,
            "status": "tentative",
            "start": {"dateTime": start.isoformat()},
            "end": {"dateTime": end.isoformat()},
        }
        return self._call(refresh_token, "POST", "/calendars/primary/events", body)["id"]

    def delete(self, refresh_token: str, event_id: str) -> None:
        # 404 and 410: the user already deleted the event in Google, which is what we want.
        self._call(refresh_token, "DELETE", f"/calendars/primary/events/{event_id}", ok=(404, 410))

    def confirm(self, refresh_token: str, event_id: str, summary: str) -> None:
        """Turn a tentative event into a confirmed one."""
        self._call(
            refresh_token, "PATCH", f"/calendars/primary/events/{event_id}", {"status": "confirmed", "summary": summary}
        )

    def _token(self, **grant: str) -> dict:
        response = httpx.post(
            _TOKEN_URL,
            data={"client_id": os.environ["GOOGLE_CLIENT_ID"], "client_secret": os.environ["GOOGLE_CLIENT_SECRET"], **grant},
            timeout=10,
        )
        response.raise_for_status()
        return response.json()

    def _call(self, refresh_token: str, method: str, path: str, body: dict | None = None, ok: tuple[int, ...] = ()) -> dict:
        # shortcut: one token request per call, cache the access token (valid 1 hour) if Google rate-limits.
        access = self._token(grant_type="refresh_token", refresh_token=refresh_token)["access_token"]
        response = httpx.request(
            method, _API + path, json=body, headers={"Authorization": f"Bearer {access}"}, timeout=10
        )
        if response.status_code not in ok:
            response.raise_for_status()
        return response.json() if response.content else {}


google = GoogleCalendar()


def _refresh_token(db: Connection, user_id: int) -> str:
    token = vault.read_token(db, user_id, VAULT_APP)
    if token is None:
        raise NotConnected(f"user {user_id} has not connected Google Calendar")
    return token


def _check(start: datetime, end: datetime) -> None:
    if start.tzinfo is None or end.tzinfo is None or not start < end:
        raise ValueError("a slot needs timezone-aware datetimes with start before end")


def free_slots(
    db: Connection, user_id: int, start: datetime, end: datetime, duration: timedelta = timedelta(hours=2)
) -> list[Slot]:
    """The slots of `duration` between `start` and `end` that can be offered to a match.

    A slot is left out if it touches a busy time in the user's Google Calendar or a slot already held for a match.
    """
    # shortcut: slots sit on a fixed grid from `start`, slide in smaller steps if that offers too few.
    _check(start, end)
    busy = google.free_busy(_refresh_token(db, user_id), start, end)
    busy += db.execute(
        text(
            "SELECT lower(slot), upper(slot) FROM calendar_holds"
            " WHERE user_id = :user_id AND slot && tstzrange(:start, :end)"
        ),
        {"user_id": user_id, "start": start, "end": end},
    ).all()
    slots = []
    while start + duration <= end:
        if not any(busy_start < start + duration and start < busy_end for busy_start, busy_end in busy):
            slots.append((start, start + duration))
        start += duration
    return slots


def _card(db: Connection, user_id: int, card_id: int):
    card = find_card(db, user_id, card_id)
    if not card:
        raise LookupError(f"card {card_id} not found")  # not a 404: these functions also run in jobs
    return card


def _audit(db: Connection, user_id: int, app: str, card_id: int, action: str, start: datetime, trigger: str) -> None:
    target = f"card:{card_id} {action} {start.astimezone(UTC).isoformat()}"
    record_action(db, user_id, type="calendar_hold", app=app, target=target, trigger=trigger)


def hold_slot(
    db: Connection,
    user_id: int,
    card_id: int,
    start: datetime,
    end: datetime,
    *,
    trigger: str,
    draft_id: int | None = None,
) -> int:
    """Hold a slot offered to a card's match: a tentative event in the user's calendar. Returns the hold's ID.

    Call it for every slot a message offers, in the transaction that stores or sends the message. `draft_id`
    is the draft whose text offers the slot: the hold is released when that draft is dismissed or fails.
    Raises `SlotTaken` if the slot is busy in Google or overlaps any slot held or confirmed for a match.
    """
    _check(start, end)
    token = _refresh_token(db, user_id)
    card = _card(db, user_id, card_id)
    if google.free_busy(token, start, end):
        raise SlotTaken(f"{start.isoformat()} is busy in the calendar")
    try:
        # The exclusion constraint on `calendar_holds` decides, so two concurrent offers cannot both win.
        with db.begin_nested():
            hold_id = db.execute(
                text(
                    "INSERT INTO calendar_holds (user_id, card_id, slot, draft_id)"
                    " VALUES (:user_id, :card_id, tstzrange(:start, :end), :draft_id) RETURNING id"
                ),
                {"user_id": user_id, "card_id": card_id, "start": start, "end": end, "draft_id": draft_id},
            ).scalar_one()
    except IntegrityError:
        raise SlotTaken(f"{start.isoformat()} is already held for a match")
    # shortcut: if the transaction fails after this call, the tentative event stays in Google with no row;
    # add a sweep that deletes such events if that ever happens.
    event_id = google.create_tentative(token, start, end, f"Hold: date with {card.name}")
    db.execute(
        text("UPDATE calendar_holds SET event_id = :event_id WHERE id = :id AND user_id = :user_id"),
        {"event_id": event_id, "id": hold_id, "user_id": user_id},
    )
    _audit(db, user_id, card.app, card_id, "hold", start, trigger)
    return hold_id


# shortcut: the slots offered are 19:00 to 21:00 in the server's `USER_TIMEZONE` on the next 7 days, and the
# sentence that names them is English. Make the window a user setting when a second user or another
# language needs it.
OFFER_HOUR = 19
OFFER_DURATION = timedelta(hours=2)
OFFER_DAYS = 7
MAX_OFFERED = 2


def _zone() -> ZoneInfo:
    return ZoneInfo(os.environ.get("USER_TIMEZONE") or "UTC")


def say(start: datetime) -> str:
    """A slot's start as a message names it, in the user's timezone."""
    return start.astimezone(_zone()).strftime("%a %d %b %H:%M")


def offer_slots(db: Connection, user_id: int, card_id: int, draft_id: int, *, trigger: str) -> str | None:
    """Pick up to `MAX_OFFERED` free evenings, hold each for the draft, and return the sentence that offers
    them, for the caller to add to the draft's text. None, with nothing held, when no evening is free.

    This is the one way a draft offers a time, so that every slot offered is held. Raises `NotConnected`.
    """
    first = (datetime.now(_zone()) + timedelta(days=1)).replace(hour=OFFER_HOUR, minute=0, second=0, microsecond=0)
    slots = free_slots(db, user_id, first, first + timedelta(days=OFFER_DAYS), OFFER_DURATION)
    offered = [slot for slot in slots if slot[0].astimezone(_zone()).hour == OFFER_HOUR][:MAX_OFFERED]
    for start, end in offered:
        hold_slot(db, user_id, card_id, start, end, trigger=trigger, draft_id=draft_id)
    return f"I'm free {' or '.join(say(start) for start, _ in offered)}." if offered else None


def _release(db: Connection, user_id: int, app: str, card_id: int, holds, trigger: str) -> None:
    for hold in holds:
        google.delete(_refresh_token(db, user_id), hold.event_id)
        db.execute(
            text("DELETE FROM calendar_holds WHERE id = :id AND user_id = :user_id"),
            {"id": hold.id, "user_id": user_id},
        )
        _audit(db, user_id, app, card_id, "release", hold.start, trigger)


def _held(db: Connection, user_id: int, card_id: int, draft_id: int | None = None) -> list:
    """The card's holds that are not confirmed, earliest first. With `draft_id`, only those that draft offered."""
    return list(db.execute(
        text(
            "SELECT id, event_id, lower(slot) AS start FROM calendar_holds"
            " WHERE user_id = :user_id AND card_id = :card_id AND status = 'held'"
            " AND (CAST(:draft_id AS bigint) IS NULL OR draft_id = :draft_id) ORDER BY lower(slot)"
        ),
        {"user_id": user_id, "card_id": card_id, "draft_id": draft_id},
    ).all())


def release_holds(db: Connection, user_id: int, card_id: int, *, trigger: str, draft_id: int | None = None) -> None:
    """Delete the card's tentative holds, in Google too. Call it when the match declines.

    With `draft_id`, only the holds that draft offered: call it when the draft is dismissed or its send fails.
    The confirmed event of a date that is set is kept. Does nothing if there are no such holds.
    """
    holds = _held(db, user_id, card_id, draft_id)
    if holds:
        _release(db, user_id, _card(db, user_id, card_id).app, card_id, holds, trigger)


def delete_events(db: Connection, user_id: int, card_ids: list[int]) -> None:
    """Delete from Google every event of the cards, held or confirmed. For the purge: the rows go with the cards."""
    event_ids = db.execute(
        text(
            "SELECT event_id FROM calendar_holds"
            " WHERE user_id = :user_id AND card_id = ANY(:card_ids) AND event_id IS NOT NULL"
        ),
        {"user_id": user_id, "card_ids": card_ids},
    ).scalars().all()
    if event_ids:
        token = _refresh_token(db, user_id)
        for event_id in event_ids:
            google.delete(token, event_id)


def confirm_date(db: Connection, user_id: int, card_id: int, *, trigger: str, start: datetime | None = None) -> bool:
    """Turn the card's hold that starts at `start` into a confirmed event and release its other holds.

    Without `start`, the card must have exactly one hold. Returns False, changing nothing, if no hold matches.
    """
    holds = _held(db, user_id, card_id)
    agreed = [hold for hold in holds if start is None or hold.start == start]
    if len(agreed) != 1:
        return False
    card = _card(db, user_id, card_id)
    google.confirm(_refresh_token(db, user_id), agreed[0].event_id, f"Date with {card.name}")
    db.execute(
        text("UPDATE calendar_holds SET status = 'confirmed' WHERE id = :id AND user_id = :user_id"),
        {"id": agreed[0].id, "user_id": user_id},
    )
    _audit(db, user_id, card.app, card_id, "confirm", agreed[0].start, trigger)
    _release(db, user_id, card.app, card_id, [hold for hold in holds if hold.id != agreed[0].id], trigger)
    return True


def stage_changed(db: Connection, user_id: int, card_id: int, stage: str) -> None:
    """Keep the card's holds in step with its stage. Every code path that sets a card's stage must call it."""
    if stage == "date_set":
        confirm_date(db, user_id, card_id, trigger="card reached date_set")
    elif stage == "archived":
        release_holds(db, user_id, card_id, trigger="card archived")


def _state_key() -> Fernet:
    return Fernet(os.environ["TOKEN_VAULT_MASTER_KEY"])


@router.get("/calendar")
def status(user: CurrentUser, db: Db) -> dict[str, bool]:
    return {"connected": vault.read_token(db, user.id, VAULT_APP) is not None}


@router.get("/calendar/connect")
def connect(user: CurrentUser) -> dict[str, str]:
    """The Google consent page to open in a browser. Google then sends the browser to `/calendar/callback`."""
    names = ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REDIRECT_URI")
    # Compose passes an unset variable as an empty string.
    if not all(os.environ.get(name) for name in names):
        raise HTTPException(status_code=503, detail=f"Google Calendar is not set up: set {', '.join(names)}")
    query = {
        "client_id": os.environ["GOOGLE_CLIENT_ID"],
        "redirect_uri": os.environ["GOOGLE_REDIRECT_URI"],
        "response_type": "code",
        "scope": SCOPES,
        # Both are needed for Google to return a refresh token, also on a second connect.
        "access_type": "offline",
        "prompt": "consent",
        # The callback carries no API token: the encrypted state says which user it is for.
        "state": _state_key().encrypt(str(user.id).encode()).decode(),
    }
    return {"url": "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(query)}


@router.get("/calendar/callback", response_class=PlainTextResponse)
def callback(code: str, state: str, db: Db) -> str:
    try:
        user_id = int(_state_key().decrypt(state.encode(), ttl=600))
    except InvalidToken:
        raise HTTPException(status_code=400, detail="invalid or expired state: start again from /calendar/connect")
    vault.store_token(db, user_id, VAULT_APP, google.exchange_code(code))
    return "Google Calendar is connected. You can close this page."
