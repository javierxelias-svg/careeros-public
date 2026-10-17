# CareerOS build log

CareerOS is a job-search engine I designed and direct. Every morning it reads a few hundred company job boards, throws out the roles that break my written terms, ranks the rest, and sends me a short digest on Telegram. The digest is the daily message listing the roles.

**How it was built:** I directed Claude Code (Anthropic's AI coding agent) for every line of Python in this project. I did not hand-write the code. My part was the design, the rules, reading the output every morning, catching what was wrong, and refusing to call anything done without proof. Every commit listed below has a `Co-Authored-By: Claude` line, and that line is accurate.

**The rule the project runs on:** the sentence "this should work" is banned. A change is done when it has run and left a receipt: test output, a dry run, or a live check saved in the repo.

This log comes from the private repository's commit history, its `LEARNINGS.md` file, and its GitHub Actions run history. The hashes are short commit IDs from that private repo. Names of companies I applied to have been removed on purpose.

---

## By the numbers (measured 2026-10-17)

| | |
|---|---|
| Commits | 182 total; 125 are real work I directed, the other 57 are the robot's automated daily bookkeeping |
| Active days | 27 distinct days with commits, July 6 to October 17, 2026 |
| Job boards in config | 341 (298 active, 43 paused) across 8 applicant-tracking platforms; 295 actually read in the Oct 17 run |
| Python | 13,765 lines in 51 files, standard library only, zero third-party packages |
| Tests | 25 test files, 886 printed checks plus two summary-style files, all passing |
| Cloud runs | 109 GitHub Actions runs since 2026-09-28: 108 succeeded. The one failure was a test I caused on purpose to prove the failure alert works |
| Receipts | 38 verification files in the repo (raw output, never summaries) |


---

## Words used below

- **ATS (applicant-tracking system):** the software companies use to post jobs. Many of them have a public feed, which is what CareerOS reads.
- **Dry run:** the full pipeline run on live data, except that nothing gets sent.
- **Frozen pool / replay:** I save one day's listings to disk, then run the old code and the new code on the same file. Job boards change every hour, so this is the only way a before-and-after number measures the code and not the market.
- **Regex:** a text-matching pattern. Most of the filters are regexes.
- **Gate vs. rank:** a gate removes a role. A rank only moves it up or down the list.
- **Ledger:** the file recording which roles were already sent, so nothing repeats.
- **OTE (on-target earnings):** base pay plus commission or bonus that you only get if you hit targets. It is not guaranteed salary.
- **Deadman alert:** an alarm that fires when something *doesn't* happen, like a missing morning digest.

---

## Timeline

### July 2026: the rules come before the product

- **2026-07-06** `03cc766`: Set up the workspace every project is built in. It has a fixed pipeline (spec, plan, implement, verify, ship), a verification gate that requires raw-output receipts, and a secret scan before every commit. CareerOS was later built inside these rules.

### August 2026: build it, then catch it lying

- **2026-08-14** `a795be2`: First working pipeline: fetch, filter, remove duplicates, rank, send. Built in from day one: a preflight check of every dependency, a crash wrapper that alerts me, and a ledger that is written only *after* Telegram confirms delivery. The salary parser refuses to guess. Receipt: 27/27 parser tests, 356 listings scanned in 11 seconds on a dry run, and the missing-credential, invalid-token and mid-run-crash paths all tested.
- **2026-08-14** `83f25d5`: Proved it on the real thing, not in theory. First real send delivered 10 roles. An immediate rerun sent zero repeats (12 duplicates dropped). A third run under the macOS scheduler confirmed the credentials could still be read there.
- **2026-08-15** `19e7748`: The ranking put a $240k lawyer job at the top tier, because it scored pay and culture words and never looked at the job title. The code did exactly what it was told, so the mistake was in my definition of a "good" job. I added role-fit scoring against my target roles. Roles outside my lanes are now counted in the footer, not silently dropped.
- **2026-08-17** `7122500`: Six defects found in one morning's digest, each now covered by a test built from that morning's real data. One feed labels nearly everything "Anywhere in the World" because that is the *category* it publishes, not a fact about each job. The job's own title now wins.
- **2026-08-17** `ca61d20`: I declined to apply because the output wasn't trustworthy. Measuring showed the salary estimator ran high (one guessed ~$109k–$151k where the real page said $48k–$65k), while real published pay was being hidden. The premise "85% of listings never state pay" described the feed, not the market. The estimator became a fallback, and the engine now opens the job page.
- **2026-08-17** `13d8c58`: Stopped inventing salaries. Invented "published" salaries went from 9 to 0, and real published pay found went from 206 to 842, on a frozen pool of 3,190 listings. I also stopped padding: the digest had a fixed 14 slots, while only 10 roles in the whole pool truly fit. A fixed slot count turns scarcity into noise.
- **2026-08-17** `498e25d`: The remote filter treated a posting that said nothing about location as remote. That was safe for remote-only job feeds and wrong for company boards, which list every job the company has. Two candidate rules were measured and *rejected* before shipping. One would have let 494 non-remote listings through on phrases like "distributed systems."
- **2026-08-18** `4efde91`: The digest silently didn't arrive. Root cause: the Mac's scheduler can't open log files on the Desktop, so the job never started and no alarm could fire. Fixed and proved under the real scheduler. Also made the job idempotent, meaning it is safe to run any number of times: it delivers once per day at the first chance and skips every run after that.
- **2026-08-18** `07bea2b`: Separated guaranteed base pay from OTE. One role was overstated by about $20k. I changed the one property every ranking step reads, so the rule holds everywhere at once. Replaying cached job pages found the opposite bug too: a real job's base pay understated by $35k. The test suite had missed it.
- **2026-08-18** `a310d8f`: A filter meant to drop people-manager roles also deleted "Customer Success Manager" roles, including one I was actively applying to. The test only checked that the pattern matched. It never checked that the right roles survived. The test was rewritten to check the decision itself.
- **2026-08-18** `3daaf0d`: Widened the search to more boards, and found two data problems that only show up at scale. One employer posted the same role once per city (14 near-identical rows). Another published a pay band with the floor above the ceiling.
- **2026-08-19** `df6afd0`, `b944989`: Hand-checking the digest found a hybrid, commission-paid role ranked 3rd. I fixed both causes, then made a separate commit **correcting my own earlier note** about the root cause (story 3 below).

### September 2026: survive without me watching

- **2026-09-28** `cc0b65d`: A power outage took the Mac mini down for 27 days, and nothing alerted, because every alarm lived on the dead machine. I moved the daily run to GitHub Actions, GitHub's cloud servers that run scheduled jobs. The move was small because earlier choices had already paid for it: no third-party packages, file paths that don't depend on the working folder, and a secrets loader that already fell back to environment variables.
- **2026-09-28** `231eb1b`: A script to copy secrets from the Mac's Keychain into GitHub. Values go straight from one to the other: never printed, never written to disk, never shown as command arguments. It reports success per key, because an earlier paste had silently set one secret and skipped the other.
- **2026-09-28** `7096e6a`: Two bugs I introduced that same day, caught by a dry run. A new "Latin America" pattern ran before the sales exclusions, so it let quota-sales jobs through. And a seniority penalty went into the fifth sort key, where it changed the score and never changed the order.
- **2026-09-28** `fec7fda`: A page-reading limit of 30 was right when written and later became a hidden quality ceiling: 2,062 listings a day were never opened. I raised it to 200, sized to the cloud time budget, and the footer now reports anything beyond the limit.
- **2026-09-29** `4c4a857`, `c71aa1f`: GitHub's scheduler dropped three runs in a row on the first real morning. A failure alert can't fire for a run that never started, so the digest now opens with its own absence ("No digest for 3 days, last was Sep 26"). This is computed from delivery receipts. Ten test cases cover it.
- **2026-09-29** `9feaa48`: Two roles asked for languages I don't speak. Whether I *can* do the job is now checked before any other filter, at the top of the classifier, because in three days the order of the rules had been the bug three times.
- **2026-09-30** `814f000`: Measured GitHub's scheduler at 4 of 22 time slots fired. So a scheduled Claude routine now holds the clock and pushes a trigger, and GitHub only does the work. The routine decides nothing: the "already sent today?" check stays in Python, against the ledger.
- **2026-09-30** `f4506a2`: Tested the failure alert for the first time by breaking a run on purpose. It fired, but it threw away Telegram's reply, so an alert that had stopped working would have looked like one that worked. It now checks the reply. That deliberate break is the only failed run in the Actions history.
- **2026-09-30** `5e318eb`: Checked the "is this job livable" filters against real postings for the first time. All three were broken (story 5 below). A new test file is built from exact posting text, not invented examples.
- **2026-09-30** `283284e`: The experience filter passed all 20 test files twice while it still let five-year roles through (story 4 below).
- **2026-09-30** `7e15759`: My first-ranked term, "fully remote, no hybrid", had been written down for six weeks and never enforced in code. It is now a hard reject. Negations like "no office, ever" are removed before matching, so they don't count against a posting.

### October 2026: terms, not filters

- **2026-10-01** `7f90451`: Senior titles on pages the engine couldn't read were slipping through, because the "unreadable" check ran before the title check. The title check now runs first.
- **2026-10-08** `e0932f4`: Added readers for two large enterprise job platforms, plus new role lanes and culture flags. Every hand-added board is pinned, because the discovery script rebuilds the board list and would otherwise silently delete them.
- **2026-10-13** `e070a64`: Replayed 11,424 frozen listings and found the engine hiding roles that fit (a "lunch in the office" perk was read as an office requirement). It was also passing roles locked to foreign countries. The new rule: only a *written* hard no removes a role.
- **2026-10-13** `7d455e1`: Six defects from a wider dry run, including a 220-character text window that cut "$184,000" to "$184" and flipped the band. The commit says plainly that one new board reader was **not** verified live, because the platform was rate-limiting me.
- **2026-10-13** `a177db6`: Every role now prints my terms in three states: written in the posting, silent, or written opposite. Silence never counts as a fail. I had been doing this check by hand for every role.
- **2026-10-16** `f060218`: Ten fixes from a week of applying. One of them: phrases like "paid month off after 4 years" or "the company is 4 years old" no longer read as experience requirements. Before a soft penalty became a hard block again, I read every newly blocked line, not just the test results.

---

## Times it was confidently wrong, and how I caught it

### 1. The engine was inventing salaries

- **Symptom:** Several postings showed a $260,000 salary, including sales roles that stated no pay at all.
- **Root cause:** The text was "With $125M raised at Series B." The parser matched "$125", dropped the "M", decided a number under 500 must be an hourly rate, and multiplied by 2,080 work hours. The same branch turned 148 into $307,840, and turned a digit from a web page's styling code into $8,320. Separately, the parser read only the first 3,000 characters of each posting, which is the company pitch. The real pay usually sits at the bottom.
- **Fix (`13d8c58`):** Funding and growth figures are refused. Plain text can no longer be guessed into an hourly wage. The parser now looks for the pay section instead of reading a fixed window. Measured on a frozen pool of 3,190 listings, invented salaries went from 9 to 0 and real published pay found went from 206 to 842.
- **How it's tested now:** `test_lean.py` pins the exact sentence ("$125M raised" must not parse as pay), alongside the other cases from that day.

### 2. Twenty-seven days of silence, and nothing alerted

- **Symptom:** No digests for four weeks. I noticed because my phone was quiet.
- **Root cause:** A power outage, and a Mac set not to restart after power loss. The scheduling code was correct. It just had no machine to run on. The crash alerts lived on the same dead machine.
- **Fix:** Moved to the cloud (`cc0b65d`), then found GitHub's scheduler drops runs (`4c4a857`). The digest now reports its own absence (`c71aa1f`), a routine owns the clock (`814f000`), and I broke a run on purpose to prove the failure alert delivers (`f4506a2`).
- **How it's tested now:** `test_gap.py` (ten cases, including "given only an Aug 31 delivery, the Sep 29 digest opens with *No digest for 28 days*"). The workflow's failure alert was proven by a deliberate failure, the one red run in 109.

### 3. I blamed the wrong module, then corrected the record

- **Symptom:** A hybrid, commission-paid role ranked 3rd in a digest that is supposed to show only remote roles with base pay.
- **What I first believed:** The salary parser was misreading OTE as base.
- **Actual root cause:** Two upstream problems. The board's data said both "remote: true" and "workplace: hybrid", and the reader only looked at the first. And the board's combined pay summary dropped the "On Target Earnings" label, so the parser received a plain "$175K – $225K" and parsed it *correctly*. A correct parser fed bad input looks exactly like a broken parser.
- **Fix:** `df6afd0` fixed both causes. `b944989` is a separate commit that does one thing: correct my earlier written note so the history doesn't keep a wrong explanation.
- **How it's tested now:** the pay-tier tests and `test_salary_ote.py` (38 base-vs-OTE checks in the live engine), with cases copied from live postings.

### 4. Twenty test files passed while the filter had a hole in it

- **Symptom:** After I asked to stop receiving roles that require years I don't have, the next digest showed 11 of 18 roles as "experience unknown". After the first fix, 6 roles came through as "not checked", two of them asking 4–5 years.
- **Root cause:** Some job pages are blank shells until JavaScript runs. The engine read them as "no requirement stated" and let them through, as if they were entry-level. I then designed a whole workaround for missing text that was never actually missing: the board's own feed already carried the full description for 951 of 952 of those listings. The second hole: roles past the page-reading limit were never checked, and the filter let "never checked" through.
- **Fix (`283284e`):** The experience bar is now read from the description the feed already sends, for every listing, at no extra network cost. A single function owns the rule "absent is not the same as clean".
- **How it's tested now:** `test_experience.py` and `test_enrich.py`. The lesson changed how I write tests: a filter's tests must list the reasons it *lets things through*, not only what it blocks. Both holes were found by running the pipeline and reading all 18 output lines.

### 5. The "is this job livable" filters had never seen a real posting

- **Symptom:** A role requiring 50% travel reached the top of my list.
- **Root causes, three in one day:**
  - The travel pattern ended in `%` wrapped in a word boundary (`\b`). A word boundary can't follow a `%`, so that part of the filter had **never matched anything** since the day it was written.
  - "No on-call, ever. We protect your evenings." was rejected *for* on-call, because the pattern matched the words inside their own negation. A guard against this already existed on the curated page and had never been added to the daily digest.
  - The shift-work pattern needed "rotating" before "weekends", so "weekend rotation required" passed.
- **Fix (`5e318eb`):** Each pattern part is anchored on its own, and negations are removed before matching.
- **How it's tested now:** `test_fit_terms.py`, built from exact posting text. It checks both what must be blocked and what must pass ("travel up to 5%", "100% remote").

### 6. The order of the rules was the bug

- **Symptom:** A quota-sales "Account Executive, LATAM" role showed up in the main digest. Separately, a seniority penalty I'd just added changed the scores and not the list.
- **Root cause:** A new Latin America pattern ran *before* the sales exclusions, so it let excluded roles through. The penalty went into the fifth sort key, behind four keys that already decided the order. I had checked that the score changed. I never checked that the digest reordered.
- **Fix (`7096e6a`, then `9feaa48`):** Only three named exceptions may run before the exclusions. A "can I do this job at all" check now runs first in the classifier. Level is sorted second, right after lane.
- **How it's tested now:** `test_fit.py` has five regression cases (sales, HR and marketing titles carrying a region). `test_experience.py` checks that the penalty moves the order in step with the years asked, because a penalty that doesn't change the order does nothing.

### 7. The job didn't start, so nothing could report it

- **Symptom:** No digest one morning: no log, no alert, no crash message.
- **Root cause:** The macOS scheduler opens log files *before* starting the program, and it isn't allowed to write to the Desktop. The open failed and the program never started. The only trace was an exit code of 78 in the scheduler's own records. I isolated it with a test job using the same Python and working folder before changing anything. A second problem turned up on the way: the standard plist checker approved a scheduler config file that the scheduler itself rejects.
- **Fix (`4efde91`):** Logs moved out of protected folders. The installer now also parses the config file with Python's own parser. The commit says plainly that the mechanism is proven but *why it started on that date* is not.
- **How it's handled now:** This failure class no longer applies, because the run moved to the cloud. The lesson moved with it: anything that can fail before the program starts needs an alarm that lives somewhere else.

---

## What I'd point an engineer to

- **Measure before and after on frozen data.** Most of the commits above quote a before/after number from a replay of saved listings, not from live data that changes every hour.
- **Correct the record in public.** `b944989` exists only to fix my own wrong explanation.
- **Say what isn't verified.** `7d455e1` ships with "still not verified live" in the commit message instead of hiding it.
- **Keep decisions in code, not in the model.** The AI routine only pushes a trigger. Whether to send is decided in Python, against a ledger.

---

Portfolio: [javierxelias-svg.github.io](https://javierxelias-svg.github.io) · How I debug it: [javierxelias-svg.github.io/how-i-found-this](https://javierxelias-svg.github.io/how-i-found-this/)
