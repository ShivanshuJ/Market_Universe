# Test results (written 6 Nov 2026, during the build)

Run: `python -m unittest discover -s tests -v` (no network, no credits). **26 tests, all passing.**

## What the unit tests cover
- Re-recorded vs returning vs new joiner (gap rule), open-ended and overlapping earlier roles.
- Window edges (people before the window are ignored), unplaced department kept as its own group.
- Growth labels (growing, fading, too few to judge) and switched off when the people pull is capped.
- Company size conflict and an old headcount series both produce warnings.
- A team made of one vague title ("Assistant Manager") is flagged and left out of the brief.
- Model-written briefs: an invented number, or a fact id that does not exist, is rejected.
- Resume skips finished steps; cached responses are reused (no second spend); credit budget stops before any call.
- Company names: a shorter name matching a much bigger company asks a human; legal suffixes are tried and the assumption is reported; near-matches are flagged; two equal-size companies with one name ask a human; no company asks a human.
- Different wording of the same request gives identical counts.

## Added later: exits, senior hires, comparison, export (31 tests passing)
Live runs with exits (extra credits): Groww 261 left vs 217 hires (net -44, 108 credits), CRED 326 left vs 180 (net -146, 94 credits), Cashfree 191 left vs 198 (net +7, 65 credits).
Cross-check that came out right: Cashfree to Groww shows 3 on the hiring side and 3 on the exit side, Cashfree to CRED 2 and 2. Two independent counts of the same movement agree.
Groww and CRED nets are negative while the headcount series says they grew, so the app flags the disagreement instead of hiding it.

## Live runs (real Crustdata data, 5 to 6 Nov 2026)
| Company | Raw "joiners" | Re-recorded (excluded) | Real hires | Credits |
|---|---|---|---|---|
| Groww | 419 | 202 | 217 | 101 |
| CRED | 257 | 77 | 180 | 64 |
| Cashfree | 283 | 85 | 198 | 70 |

Re-running any of them costs 0 credits (responses cached). A live crash after the people step followed by `resume` skipped all four finished steps and did not repeat the 25-credit pull.

## Messy input (live, free calls)
| Input | Result |
|---|---|
| "GROWW" (any case) | resolved to Groww (groww.in) |
| "groww.in" | resolved by website |
| "Gorww" (typo) | resolved to Groww and **flagged as assumed** |
| "Groww Inc" | **asks a human**: matches a 2-10 person company (groww.ca) but "Groww" is a 501-1000 company |
| "Cashfree Payments Pvt Ltd" | resolved to Cashfree, flagged as assumed (before the fix it matched unrelated payment firms) |
| "Acme" | **asks a human**: two companies of the same size |
| "teams?" (no company) | **asks a human** |

## Hand check of the re-recorded rule (Groww, 20 random people from saved data)
- 10 of 10 "re-recorded" cases were level changes or conversions at the same company (e.g. SDE 2 to SDE 3, Analyst to Senior Analyst, Engineering Manager to Senior Engineering Manager, SDE Intern to SDE 1).
- 10 of 10 "new" cases had a different previous employer. One had a company name in the title field ("Building W by Groww"), which is a data oddity.
- Limit of this check: it compares our classification with the same Crustdata records, not with live profile pages.

## Known gaps
- No test for 429 / 5xx / timeout handling (the code exists; only exercised by hand).
- Departures (people who left) are not computed.
- The model-written brief path is untested end to end (no model key set).
- No backtest yet.
- Profile `updated_at` is not requested, so per-person freshness is not shown (headcount series date is).
