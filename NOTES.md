# Build log: what we did, tried, and decided (ContextCon 04, 5 to 6 Nov 2026)

Running notes, newest facts last. The README is the polished version; this is the honest trail behind it.

## Where things are recorded
| What | Where |
|---|---|
| Polished write-up for judges | `README.md` |
| Test list and live results with numbers | `tests/RESULTS.md` |
| Live checklist and phase timing | `../orgchart-xray-live-tracker.html` (one folder up) |
| Full submission checklist | `../OrgChart-XRay-CHECKLIST.md` (one folder up) |
| This trail | `NOTES.md` |

## Idea and choices
- Shortlisted ideas: vendor check (Shell Hunter), background check (Backchannel), churn warning, stale job roles, **org chart X-Ray** (chosen).
- Picked X-Ray because Crustdata's person records carry dated roles, seniority, department tags and previous employers, so a rival's org can be rebuilt from public data.
- Buyer: a strategy team at a fintech. Demo company: Groww. Unseen checks: CRED and Cashfree.

## First look at the data (Groww, before any code)
- Company resolved for free (id 5894). 2,119 current people; 437 had a current role starting in the last 12 months.
- Every role has title, start/end date, seniority and department tags. The weekly headcount series exists back to 2019.
- **Trap found:** 221 of the 437 "joiners" already worked at Groww. They are re-recorded roles (promotions, restructures), not hires. A naive count shows a fake April 2026 spike (181 raw, about 37 real).
- Also found: size range says 501-1000 but the series says 3,155; Company Enrich says 1 open job but Job Search lists 296; 14% of joiners have no department.

## What we built (in order)
1. Client with retries, cache and credit budget; SQLite store; offline fixtures.
2. Analysis (dedupe, teams, pace, previous employers) and the pipeline with saved steps and resume.
3. Brief made of facts with ids and sources; a model rewrite is rejected if it invents a number.
4. Web UI: live steps, brief, naive-vs-real chart, org tree with time slider, headcount, evidence panel.
5. Live runs on CRED and Cashfree; live crash-and-resume test.
6. Fixes driven by what the live runs showed (below).
7. Features: senior hires radar, exits and net change, rival comparison with talent flow, export (markdown, printable page, email draft).
8. README with architecture diagram; five git commits.

## Problems found and how we fixed them
| Problem | Fix |
|---|---|
| Re-recorded roles counted as hires | Gap rule: earlier same-company role ended within 120 days means re-recorded; longer gap counts as a returning hire |
| Capped pull is newest-first, so it faked "growing 56 vs 5" | Growth labels switch off when the pull is capped |
| 10 "Assistant Managers" tagged Retail Store Management at Cashfree | Teams that are mostly one vague title are flagged and left out of conclusions |
| "Groww Inc" silently matched a 2-10 person company | Resolver asks when a shorter name matches a far bigger company |
| "Cashfree Payments Pvt Ltd" matched unrelated firms | Legal suffixes are stripped and tried; assumed matches are labelled |
| Department of a leaver describes their new job | Exits are grouped by keywords in the title of the role they left, marked approximate |
| Hires minus exits disagreed in sign with the headcount series (Groww, CRED) | Warning shown instead of hiding it |

## Checks that came out well
- Talent moving between rivals counted two independent ways (hiring side, exit side): Cashfree to Groww 3 and 3, Cashfree to CRED 2 and 2.
- Hand check of 20 classified people: 10 of 10 "re-recorded" were promotions or conversions; 10 of 10 "new" had a different previous employer.
- Live crash after the people step, then resume: finished steps skipped, no repeated paid pull.
- Different wording of the same request gives identical numbers.

## Numbers
- Tests: 31 passing (`python -m unittest discover -s tests`).
- Real hires in the window: Groww 217 of 419 raw, CRED 180 of 257, Cashfree 198 of 283.
- Exits: Groww 261 left (net -44), CRED 326 (net -146), Cashfree 191 (net +7).
- Credits: started with 15,200 and 14,127.78 remain (about 1,070 used, including runs on other companies made from the UI).

## Not done yet
- Backtest against a known past event; previous-year baseline per team.
- Tests for 429 and 5xx handling (code exists, exercised by hand only).
- Model-written brief end to end (no model key set).
- Demo video, diagram link check, form fields.
- Team items: name, roles, teammates' signups, public GitHub repo and push (not pushed; GitHub is not signed in here).
- Git: five commits made locally on `main`; this file and the tracker are not committed.

## Notes for the demo
- Open with the request in customer words; show the naive-vs-real chart first (it is the clearest "facts and verification" moment).
- Show the clash between net and the headcount series as a feature: the product says when it is unsure.
- If anything breaks, tick "offline fixtures" or use "Load last saved run".
