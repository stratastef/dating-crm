# Twilio sends sign-in codes

ADR 0006 needs an SMS provider for sign-in codes. We send them with Twilio Programmable Messaging, called over plain HTTPS from `app/sms.py`, with no Twilio SDK. Germany uses the sender name "DatingCRM", which needs no registration there. US testers can be added later with a verified toll-free number, by changing one setting. We assume the owner is in Germany and the TestFlight testers are in the EU and the US; correct this in review if the countries differ.

## Options compared

Prices are from the providers' public pages on 2026-11-25, before VAT, for one SMS of up to 160 characters.

| | Twilio Programmable Messaging | seven.io (Berlin) | Plivo | Vonage SMS API | AWS End User Messaging SMS |
| --- | --- | --- | --- | --- | --- |
| Germany | $0.112, plus $0.025 for the optional SMS Pumping Protection | €0.075 | $0.095 to $0.20, by network | Not public: only in the dashboard's price sheet | Not on the page: only in a per-country CSV |
| US | $0.0083 plus a carrier fee of $0.0035 to $0.005; toll-free number $2.15 a month | €0.075 (same flat list price) | Long code or toll-free, after registration | Long code or toll-free, after registration | 10DLC: $4.50 + $41.50 vetting once, $10 a month per campaign, $1 a month per number. Toll-free: $2 a month |
| Sender name | "DatingCRM" in Germany, free, no registration. Not possible in the US or Canada | Own sender up to 11 characters | Not stated | Supported in Germany; generic names such as INFO are banned | Only in some countries |
| US registration | Toll-free verification in the Console (business or sole proprietor, address, website, use case, opt-in); needs a paid account | No documented toll-free or 10DLC path | 10DLC or toll-free verification | 10DLC or toll-free verification | 10DLC or toll-free registration |
| Sign-up | Instant, no card. The trial sends only Twilio's templates to 5 verified numbers, so our text needs an upgrade: legal name, phone number, a payment method, sometimes a government ID | €0.50 test credit, top-up by card, SEPA or PayPal, no monthly fee | Account and top-up | Account and top-up | AWS account; a sandbox texts only verified numbers until a support case grants production access |
| Client | HTTPS form POST with Basic auth (`httpx`, already installed) | HTTPS form POST with `X-Api-Key` | HTTPS | HTTPS | Requests signed with AWS SigV4: `boto3` or our own signing |
| Test mode | Test credentials with magic numbers, nothing sent or charged (not with a Messaging Service) | None documented | Not checked | Not checked | The sandbox |
| Fraud controls | Geo Permissions (which countries can be texted); SMS Pumping Protection | None documented | Not checked | Not checked | Monthly spending limit |

Twilio Verify was rejected. It creates and checks its own codes, so it would replace our sign-in codes, tries and rate limits instead of sitting behind `sms.send()`.

## Why Twilio

- Germany works as soon as the account is upgraded: the sender name needs no registration, and no number is rented.
- US testers need no code change. The owner verifies a toll-free number, puts it and "DatingCRM" in a Messaging Service, and sets `TWILIO_SENDER` to the service's SID. The service then picks the sender name or the number for each country.
- Geo Permissions limit texts to the countries testers live in. This is a cheap guard against SMS pumping.
- It needs only a plain HTTPS call and no new dependency. Its test credentials let the owner try the settings without sending a text.
- It costs the most per text in Germany: $0.112 against seven.io's €0.075, both before VAT. For a small beta of a few hundred codes a month, that is under €10 more each month.

## Consequences

- The main guard against SMS pumping is ours. A number gets a text only if it has an account or comes with an unused invite code. Code requests are also limited per number and per IP (`docs/modules/sign-in.md`). Twilio's SMS Pumping Protection is optional outside the US and Canada.
- Fail closed. If `SMS_PROVIDER` is set and a Twilio setting is missing, or Twilio refuses the text or cannot be reached, the code request answers `503 sms_not_sent` and no code for that number works. When `SMS_PROVIDER` is not set, the code is written to the server log, for local development only. Never leave it unset on a server testers use.
- If Twilio accepts a text that the carrier later fails to deliver, we never hear about it. The user taps "Send a new code". Undelivered texts show in the Twilio Console under Monitor, Logs, Messages.
- Twilio, a US company, receives each tester's phone number and the text with its code. The code is useless after 10 minutes. Twilio's data processing addendum is part of its terms.

## What the owner does

1. Create a Twilio account at twilio.com, then upgrade it: add your legal name, a payment method and a starting balance.
2. In the Console, open Messaging, Settings, Geo permissions. Allow only the countries your testers live in, such as Germany, and turn off the rest.
3. Choose the sender:
   - **Germany and other countries that allow sender names:** use `DatingCRM` as the sender. It has at most 11 characters and at least one letter. Nothing to buy or register.
   - **To add US testers:** buy a toll-free number and submit its toll-free verification. Use case: one-time sign-in codes. Opt-in: the user types their own number into the app and asks for a code. Then create a Messaging Service, add the toll-free number and the sender name `DatingCRM` to its sender pool, and use the service SID (`MG…`) as the sender.
4. Set these on the server, where `compose.yaml` passes them to the API:

   | Variable | Value |
   | --- | --- |
   | `SMS_PROVIDER` | `twilio` |
   | `TWILIO_ACCOUNT_SID` | Account SID (`AC…`), Console home page |
   | `TWILIO_AUTH_TOKEN` | Auth token, Console home page |
   | `TWILIO_SENDER` | `DatingCRM`, or the Messaging Service SID (`MG…`) |

5. Restart the API. Request a code in the app with your own phone number, and check that a text "123456 is your Dating CRM code. It expires in 10 minutes." arrives from DatingCRM. Then close #50.

If no text arrives, the API log has a line such as `Sign-in code for +49… not sent: Twilio refused the text: 400 21408 …`. Look up the number at `https://www.twilio.com/docs/api/errors/<number>`.

## Sources

- Twilio prices: <https://www.twilio.com/en-us/sms/pricing/de>, <https://www.twilio.com/en-us/sms/pricing/us>
- Twilio, Germany sender rules: <https://www.twilio.com/en-us/guidelines/de/sms>
- Twilio trial limits: <https://www.twilio.com/docs/usage/trials>
- Twilio toll-free verification: <https://www.twilio.com/docs/messaging/compliance/toll-free/console-onboarding>
- Twilio SMS Pumping Protection: <https://www.twilio.com/docs/messaging/features/sms-pumping-protection-programmable-messaging>
- Twilio test credentials: <https://www.twilio.com/docs/iam/test-credentials>
- Twilio Message API: <https://www.twilio.com/docs/messaging/api/message-resource>
- seven.io: <https://www.seven.io/en/full-sms-pricelist/>, <https://docs.seven.io/en/rest-api/endpoints/sms>, <https://help.seven.io/en/billing/test-credit>
- Plivo: <https://www.plivo.com/sms/pricing/de/>
- Vonage, Germany: <https://api.support.vonage.com/hc/en-us/articles/212871228-Germany-SMS-Features-and-Restrictions>
- AWS: <https://aws.amazon.com/end-user-messaging/pricing/>, <https://docs.aws.amazon.com/sms-voice/latest/userguide/sandbox.html>
