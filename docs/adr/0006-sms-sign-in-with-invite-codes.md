# Sign-in by SMS code, accounts by invite code

v1 signs in with a server URL and an API token the owner creates on the command line, which no TestFlight tester can do alone. The redesign signs in with the user's phone number and a six-digit sign-in code sent by SMS; the phone number is the account's identity. Creating an account also needs a one-time invite code, which the owner issues to people on a waitlist that lives on a web page outside the app. The server URL and token stay as a hidden developer option.

## Consequences

- The server needs an SMS provider (a cost per message) and rate limits per number and per IP against SMS fraud.
- Every SMS and screen names the sender ("your Dating CRM code"), so it is never confused with a dating app's own login code, such as Hinge's if the Hinge spike picks SMS login.

## Considered options

Email codes, magic links and Sign in with Apple were offered. The owner chose SMS.
