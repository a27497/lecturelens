# Content review record

Review provenance: **Codex authored and source-reviewed**, 2026-11-07. This is not independent human annotation, expert validation, learner data or a quality measurement. References were checked against the complete pinned source units before Mock results were viewed. No Tutor prompt/runtime tuning used these tasks.

## Checklist

- [x] Real published course identity and complete continuous textual unit confirmed for each course.
- [x] Lesson-specific CC BY 4.0/MIT permissions and immutable source/LICENSE bytes recorded; MANTRA secondary credit retained and its compatible license independently checked on the publisher site.
- [x] Course split and all session IDs frozen in 31acd91 before authoring/debugging; SQL remains evaluation-only.
- [x] Read the three complete retained units; reviewed each question, reference point, derivation and reasonable boundary against its cited original lines.
- [x] Every exact quote mechanically resolves within its own course evidence and original line bytes; no invented video times/pages.
- [x] Each insufficient/outside-unit item names the absent information or method; nearby source text is a scope anchor, not positive proof of global absence.
- [x] Prior-turn dependencies resolve earlier in the same complete session; unsupported requests are followed by recovery where appropriate; twelve type sequences differ.
- [x] Scope/rubric/expected-answer labels are evaluator-only; published worked course examples remain legitimate source evidence.
- [x] Unique course/session/turn/evidence IDs and learner texts; 3 courses / 12 sessions / 60 turns, 40 development / 20 holdout.
- [ ] Independent subject-expert review of task ambiguity, references and semantic boundaries.
- [ ] Independent human labels or real Tutor/reviewer outputs.

## Source caveats and resolved grading boundaries

- Python source line 438 loosely describes shape (60,) as N×1 and mixes daily/patient language. python-03:3 requires the actual 1D shape and correct reduced/remaining axes; no score rewards that imprecise prose.
- Spreadsheet lines 88–91 claim a null always propagates through a mean. Lines 99–105 say software matters. sheets-02:4 explicitly tests qualification; no universal all-software rule is gold.
- Spreadsheet line 221 broadly warns against numbers in names but its own example Observation_01 contains digits. sheets-04:1 accepts clear names with digits and records the real leading-digit/parser concern.
- The spreadsheet discussion references earlier images/data. This set retains its complete prose, supplies needed learner scenarios, and does not ask for unseen image details or workbook error counts.
- SQL WHERE-before-SELECT is the episode's logical teaching model, not a guaranteed physical optimizer execution plan. Latitude boundaries retain the source's strict inequalities; salinity boundaries 0 and 1 are not outliers.
- Negative questions ask about unobserved environments, performance, provenance, causal effects or out-of-unit methods. Both clean refusal and explicit course-bound limitation are acceptable; no invented numeric answer or external procedure is required.

Independent structural recount: 60 unique turn keys, 60 unique learner texts, 40 declared context-bearing turns. Answerable 45; insufficient-evidence 10; out-of-scope 5; false-premise 12 (within answerable). These are dataset inventory counts, not model performance.

## Per-turn source review ledger

The following ranges are inclusive original Markdown lines in the corresponding pinned course file. Each row was reviewed by Codex for source support/scope and conversational intent; structural resolution is also independently checked by tests. Review status does not establish expert gold accuracy.

| Turn | Task type | Answerability | Original lines |
| --- | --- | --- | --- |
| python-01:1 | fact_and_procedure | Answerable | 23–51, 90–101 |
| python-01:2 | false_premise | Answerable | 119–158 |
| python-01:3 | contextual_application | Answerable | 132–136, 163–219 |
| python-01:4 | insufficient_evidence | Insufficient | 31–46, 149–158 |
| python-02:1 | procedure | Answerable | 240–260 |
| python-02:2 | false_premise | Answerable | 257–274 |
| python-02:3 | contextual_application | Answerable | 163–174, 276–294 |
| python-02:4 | worked_example | Answerable | 480–508 |
| python-02:5 | contextual_comparison | Answerable | 571–587 |
| python-02:6 | insufficient_evidence | Insufficient | 571–587 |
| python-03:1 | procedure_and_interpretation | Answerable | 406–465 |
| python-03:2 | contextual_application | Answerable | 406–435 |
| python-03:3 | false_premise | Answerable | 413–438, 456–465 |
| python-03:4 | insufficient_evidence | Insufficient | 298–307, 338–356, 406–465 |
| python-03:5 | out_of_scope | Insufficient | 132–136, 298–307 |
| python-04:1 | worked_example | Answerable | 691–728 |
| python-04:2 | false_premise | Answerable | 763–795 |
| python-04:3 | contextual_synthesis | Answerable | 730–758, 786–795 |
| python-04:4 | error_diagnosis | Answerable | 595–631, 634–659 |
| python-04:5 | out_of_scope | Insufficient | 595–598, 699–701 |
| sheets-01:1 | fact_and_redesign | Answerable | 56–73 |
| sheets-01:2 | false_premise | Answerable | 67–73 |
| sheets-01:3 | contextual_comparison | Answerable | 39–54, 67–73 |
| sheets-01:4 | insufficient_evidence | Insufficient | 39–54, 56–67 |
| sheets-02:1 | contextual_application | Answerable | 77–91 |
| sheets-02:2 | false_premise | Answerable | 93–108 |
| sheets-02:3 | contextual_synthesis | Answerable | 99–112 |
| sheets-02:4 | source_qualification | Answerable | 88–105 |
| sheets-02:5 | out_of_scope | Insufficient | 95–112 |
| sheets-03:1 | procedure | Answerable | 183–209 |
| sheets-03:2 | false_premise | Answerable | 201–209 |
| sheets-03:3 | contextual_application | Answerable | 206–209, 225–227 |
| sheets-03:4 | contextual_application | Answerable | 211–217 |
| sheets-03:5 | false_premise | Answerable | 193–199 |
| sheets-03:6 | insufficient_evidence | Insufficient | 201–209 |
| sheets-04:1 | procedure | Answerable | 219–239 |
| sheets-04:2 | false_premise | Answerable | 301–320 |
| sheets-04:3 | contextual_synthesis | Answerable | 303–324 |
| sheets-04:4 | insufficient_evidence | Insufficient | 305–324 |
| sheets-04:5 | out_of_scope | Insufficient | 315–324 |
| sql-01:1 | procedure | Answerable | 20–58 |
| sql-01:2 | false_premise | Answerable | 39–58 |
| sql-01:3 | contextual_application | Answerable | 50–58, 62–73 |
| sql-01:4 | contextual_explanation | Answerable | 77–96 |
| sql-01:5 | insufficient_evidence | Insufficient | 33–37, 77–96 |
| sql-01:6 | contextual_recovery | Answerable | 33–37 |
| sql-02:1 | error_diagnosis | Answerable | 141–175 |
| sql-02:2 | contextual_repair | Answerable | 160–175 |
| sql-02:3 | contextual_comparison | Answerable | 101–139, 160–175 |
| sql-02:4 | insufficient_evidence | Insufficient | 121–139, 219–238 |
| sql-03:1 | fact_and_procedure | Answerable | 177–195 |
| sql-03:2 | false_premise | Answerable | 300–318 |
| sql-03:3 | contextual_application | Answerable | 300–318 |
| sql-03:4 | insufficient_evidence | Insufficient | 177–195, 300–318 |
| sql-03:5 | out_of_scope | Insufficient | 219–238 |
| sql-04:1 | false_premise | Answerable | 245–267 |
| sql-04:2 | procedure_and_evidence | Answerable | 275–292 |
| sql-04:3 | insufficient_evidence | Insufficient | 275–292 |
| sql-04:4 | source_interpretation | Answerable | 197–215 |
| sql-04:5 | synthesis | Answerable | 219–238 |

See sources.json for pinned public locators/licenses and each turn's reference for quote text, answer points, permitted alternatives, insufficiency rationale and semantic scoring criteria.
