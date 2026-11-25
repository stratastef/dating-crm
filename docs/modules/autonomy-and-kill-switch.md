# Autonomy and kill switch

All in `app/autopilot.py`. Each job (`chat`, `profile`, `swipe`) has a level: `off`, `copilot`, `guardrails` or `full`. Chat and profile default to `copilot`, swipe to `off`. A pause stops autopilot for one app or for all apps.

| Route | Does |
| --- | --- |
| `GET /autonomy` | Level per job |
| `PUT /autonomy/{job}` with `{"level": "full"}` | Sets one level |
| `GET /autopilot/pause` | `{"all": false, "apps": ["tinder"]}` |
| `POST /autopilot/pause?app=tinder`, `POST /autopilot/resume?app=tinder` | Pauses or resumes one app. Without `app`: all apps. |

From code, with `app=None` meaning all apps:

```python
pause(db, user_id, "tinder", reason="ban signal")  # the reason is recorded on skipped jobs
resume(db, user_id, "tinder")
autopilot_allowed(db, user_id, "tinder", "chat")   # False if paused, or if chat autonomy is off or copilot
```

A pause stops only what the app would do alone. What the user does by hand still goes out while paused: a tapped or approved draft, a swipe, an approved paid item.

Resuming all apps lifts only the pause on all apps. An app paused on its own stays paused until it is resumed by name.

Mark a job handler as autopilot with the job it acts for, and put the app in the payload as `"app"`:

```python
@handler("send_reply", autopilot="chat")
def send_reply(db: Connection, user_id: int, payload: dict) -> None: ...
```

The worker runs such a job only if `autopilot_allowed()` is true at that moment. Otherwise it sets the job's status to `skipped` and writes the reason to `last_error`. Skipped jobs are not retried. Handlers that draft for copilot are not autopilot jobs: leave `autopilot` unset.
