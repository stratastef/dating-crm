# Paid items

All in `app/paid_items.py`; the table is `paid_item_proposals`. A paid item is a Super Like, a Rose or a Boost. The app proposes one, the proposal waits in the review queue, and the item is spent only when the user approves it. The app spends items the account already holds. It never buys one and never touches a payment method.

| Route | Does |
| --- | --- |
| `POST /paid-items/{id}/approve` | Approve the proposal and spend the item now. The answer's `status` is `spent`, or `failed` when the app was not reached or the account holds no such item. `409` if it no longer waits, `404` if it is not the caller's. |
| `POST /paid-items/{id}/decline` | Decline the proposal. Nothing is spent. Same errors. |

- A proposal is `{"id", "app", "item", "name", "reason", "status"}`. `item` is `super_like`, `rose` or `boost`. `name` is the profile the item is for, or the app's name for a Boost. `status` goes `pending` to `declined`, or through `approved` to `spent` or `failed`.
- **Who proposes:** `propose(db, user_id, app, item, reason, candidate_id=None)` stores a proposal and spends nothing. Today one caller: when the swipe pre-screen model answers `super like`, `screen()` stores the candidate as a like and proposes a Super Like for it. Nothing proposes a Boost yet. `propose()` returns `None` and stores nothing when the app's connector does not declare the item or it is switched off (`CONNECTOR_DISABLED_CAPABILITIES=tinder:super_like`). There is at most one proposal per candidate, and one pending Boost per app.
- **Swipe autopilot waits:** it skips a candidate while a proposal for it is pending. After a decline or a failed spend it likes the profile for free on its next run. A proposal leaves the queue when the user swipes on the profile themselves.
- **The approval is structural.** `call()` refuses a paid capability with `PaidItemNeedsApproval`. `spend(db, user_id, proposal)` is the only function that reaches one. It first claims the row in the database (`id`, this `user_id`, status `approved`), so a proposal of another user, one that is not approved, and a second use all raise `NotApproved` before the app is touched. Do not call `connectors._run()` or a connector's `super_like`, `rose` or `boost` from anywhere else: `tests/test_paid_items.py` reads the source and fails.
- **Audit:** a spent item writes one entry: type `super_like`, `rose` or `boost`, target `candidate:<swipe_candidates.id>` (`account` for a Boost), trigger `paid item: user approved proposal <id>`. A failed or declined proposal writes none.
- A spent Super Like also sets the candidate's `decision` to `like`. Purging a candidate deletes its proposal.
- Hinge has no connector, so no Rose is ever proposed. A Hinge connector turns it on by declaring `rose` and implementing `rose()`.
- Not built: reading how many items the account holds. An approval when it holds none ends as `failed`.
