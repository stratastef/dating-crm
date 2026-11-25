# Screenshot import

`POST /screenshots` in `app/screenshots.py` is the copilot path for every app, with or without a connector. The iOS share extension calls it.

- **Request:** the body is the image itself, with `Content-Type: image/png` or `image/jpeg`, at most 5 MB. Another type is `415`, a larger body `413`, an empty one `422`.
- **Read:** Claude reads the app, the match's name and the visible messages (`llm.call` with `purpose` `screenshot`). A reply that is not usable is `502`; the client can retry.
- **Card:** the user's card with the same app and name, ignoring case, else a new card in `matched`. An existing card keeps everything but gains messages.
- **Messages:** the screenshot usually repeats the end of the stored chat, so only what comes after that overlap is added, through `upsert_message()`.
- **Answer:** `201` with a draft for the card, as `POST /cards/{id}/drafts` returns it, including its `409` until the style profile is written. On any error no card, message or draft is stored.
- **Limits:** two matches with the same name on one app share a card. A screenshot of an older part of a chat is added again at the end. Message times are not read: new messages are stamped with the time of the import. The image is not kept. Reading a real screenshot with the real Claude API has not been tried; the tests use the stub.
