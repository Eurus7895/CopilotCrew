# ticket-refinement (Level 1)

Turn a rough ticket into a sprint-ready one: imperative title, 2–4 sentences
of context, testable acceptance criteria, out-of-scope list, risk note, and
a T-shirt estimate. Graded by an isolated evaluator against the bar in
`schemas/refined-ticket.json`; up to 3 correction attempts before escalation.

## Usage

```bash
crew "refine PROJ-123"
crew "refine this: <paste of a rough issue body>"
```

Outputs land at `~/.crew/outputs/ticket-refinement/<timestamp>-<uid>-attemptN.md`
— each attempt is preserved. The plan manifest at
`~/.crew/plans/<session>.json` contains the full attempts array with
evaluator verdicts.
