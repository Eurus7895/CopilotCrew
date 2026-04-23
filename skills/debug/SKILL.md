---
name: debug
description: Systematic debugging methodology. Invoke when the user needs
  to diagnose a test failure, crash, unexpected behaviour, or flaky
  outcome. Injects a disciplined reproduce-isolate-fix loop into the
  active session.
version: 0.1.0
allowed-tools:
  - read
  - shell
---

## Purpose

You are now assisting with debugging. Follow this methodology instead of
guessing, even if the user seems to want a quick answer.

## Methodology

1. **Reproduce first.** Before proposing a fix, confirm you can make the
   problem happen reliably. Ask for the exact command or steps. If the
   bug is flaky, run the reproducer a few times to measure the failure
   rate.
2. **Isolate the minimal case.** Strip away code/data/config until the
   failure still fires but with less surface. Each thing you remove is a
   suspect eliminated.
3. **State your hypothesis.** Write one sentence: "I think X is happening
   because Y." If you can't, you haven't isolated enough.
4. **Test the hypothesis cheaply.** A log, a print, a single-line change,
   a `git bisect` — pick the cheapest experiment that would disprove it.
5. **Fix, then verify.** Apply the smallest change that addresses the
   root cause. Re-run the reproducer from step 1 to confirm. If the flake
   rate was <100%, run enough times to be statistically sure.

## Common mistakes to avoid

- Fixing the symptom, not the cause. ("Add a retry" without asking why.)
- Assuming the stack trace is the bug. The trace often points at the
  victim, not the culprit.
- Skipping reproduction because the bug "seems obvious".
- Changing multiple things at once, so you can't tell which one worked.

## Output

When you report back, include:

1. What the reproduction steps were.
2. What you isolated.
3. Your hypothesis.
4. The fix (as a diff or specific lines).
5. Verification results.
