"""Codex-authored tasks over pinned public teaching units; not expert gold labels.

Ranges are inclusive original Markdown line numbers. They identify evidence for
answerable tasks and the nearest relevant material for explicit scope gaps.
"""

# question, task type, source ranges, reference points, acceptable boundary,
# insufficiency reason (None means answerable), prior-turn dependencies
SESSIONS = {
    "python-01": [
        (
            "I am starting the NumPy episode. What does importing numpy let me do, and how do I load inflammation-01.csv so I can reuse its values?",
            "fact_and_procedure",
            [(23, 51), (90, 101)],
            [
                "NumPy supplies numerical array functionality beyond built-in Python.",
                "Import numpy and assign numpy.loadtxt(fname='inflammation-01.csv', delimiter=',') to data.",
            ],
            "Equivalent valid variable names or NumPy aliases are acceptable if explained; distinguish loading from retaining the returned array.",
            None,
            [],
        ),
        (
            "I used that assignment. Since type(data) says numpy.ndarray, that already tells me the entries are integers, right?",
            "false_premise",
            [(119, 158)],
            [
                "ndarray describes the container, not its element dtype.",
                "data.dtype in the episode is float64, so these entries are floating point.",
            ],
            "Explicitly correct the integer inference; no need to catalogue all NumPy dtypes.",
            None,
            [1],
        ),
        (
            "The same data has shape (60, 40). Which dimension is patients, which is days, and which zero-based element represents patient 30 on day 20?",
            "contextual_application",
            [(132, 136), (163, 219)],
            [
                "60 rows are patients and 40 columns are daily measurements.",
                "data[29, 19] is row 30, column 20; the printed value is 16.0.",
            ],
            "The element expression and orientation are required; the printed value is optional. Do not swap row and column.",
            None,
            [1],
        ),
        (
            "Which exact NumPy version is installed on my laptop, and does the episode guarantee this code works on that version?",
            "insufficient_evidence",
            [(31, 46), (149, 158)],
            [
                "The episode demonstrates imports and dtype but contains no observation of this learner's environment."
            ],
            "A clean course-bounded abstention or a limitation plus request for environment information is acceptable; inventing a version or compatibility guarantee is not.",
            "No local environment, installed package version or compatibility matrix is supplied in this complete unit.",
            [1],
        ),
    ],
    "python-02": [
        (
            "For the episode's 60-by-40 data, how would I select the first four patients and first ten days? Explain why those bounds give that many values.",
            "procedure",
            [(240, 260)],
            [
                "data[0:4, 0:10] (or equivalent omitted lower bounds).",
                "Stops are excluded, yielding 4 rows and 10 columns.",
            ],
            "Derive the shape from the documented bounds; no need to reproduce the numeric table.",
            None,
            [],
        ),
        (
            "Then data[5:10, 0:10] includes patient indices 5 through 10, so it has six patients?",
            "false_premise",
            [(257, 274)],
            [
                "It includes indices 5,6,7,8,9, not 10.",
                "There are five patients and ten day columns.",
            ],
            "Correct the endpoint claim explicitly and retain zero-based indexing.",
            None,
            [1],
        ),
        (
            "Now I only need the first three patients' final four days. Can I omit the slice endpoints, and what shape will I get?",
            "contextual_application",
            [(163, 174), (276, 294)],
            [
                "data[:3, 36:] selects rows 0..2 and columns 36..39.",
                "The shape is (3, 4).",
            ],
            "data[:3, -4:] is acceptable with the same interpretation; justify using the 40-column source array.",
            None,
            [1],
        ),
        (
            "Before using numbers, I want to check the slice rule on element='oxygen'. What do element[:4] and element[4:] return?",
            "worked_example",
            [(480, 508)],
            [
                "The outputs are 'oxyg' and 'en'.",
                "The stop at 4 is exclusive; the second slice continues from index 4 to the end.",
            ],
            "Explain the boundary rather than just copying output; changing topic from arrays to the unit's string example is intentional.",
            None,
            [],
        ),
        (
            "Does using identical start and stop indices raise an error? Compare element[3:3] with data[3:3, :] in the original array.",
            "contextual_comparison",
            [(571, 587)],
            [
                "The string slice is empty, not an indexing exception.",
                "The array slice has shape (0, 40), preserving all columns but no rows.",
            ],
            "An equivalent empty-array description is sufficient; do not confuse the (0,0) example with the all-column slice.",
            None,
            [3, 4],
        ),
        (
            "How many milliseconds will that empty-array slice take on our lab workstation? Give the measured time from this episode.",
            "insufficient_evidence",
            [(571, 587)],
            [
                "The exercise reports shapes, not timing measurements or workstation specifications."
            ],
            "State the missing benchmark evidence; do not substitute a guessed speed or complexity statement for a measured time.",
            "No timing benchmark, hardware description or execution trace is present.",
            [5],
        ),
    ],
    "python-03": [
        (
            "I want one mean inflammation value for every day, across all patients. Which NumPy axis should I reduce, and how long should the result be?",
            "procedure_and_interpretation",
            [(406, 465)],
            [
                "numpy.mean(data, axis=0) reduces patient rows.",
                "The result has 40 values, one per day; shape (40,).",
            ],
            "Describe the reduced dimension and remaining dimension; a 2D (40,1) shape is not equivalent to the displayed 1D shape.",
            None,
            [],
        ),
        (
            "Instead I now want one maximum over all days for each patient. What must change from that daily mean calculation?",
            "contextual_application",
            [(406, 435)],
            [
                "Use numpy.max(data, axis=1), reducing day columns.",
                "There are 60 patient maxima; shape (60,).",
            ],
            "Both aggregation function and axis must change; do not reuse the 40-day output interpretation.",
            None,
            [1],
        ),
        (
            "So axis=1 always means patients are being collapsed, because the output has 60 values?",
            "false_premise",
            [(413, 438), (456, 465)],
            [
                "Axis 1 is the column/day dimension being reduced in this array.",
                "The remaining 60 entries correspond to patient rows, not collapsed patients.",
            ],
            "Correct reduced-versus-retained dimension. The source's N-by-1 prose is loose: accept the actual printed (60,) shape, not a forced matrix.",
            None,
            [2],
        ),
        (
            "Can these means and maxima tell us the treatment's causal effect and its exact p-value? Use only this episode.",
            "insufficient_evidence",
            [(298, 307), (338, 356), (406, 465)],
            [
                "These are descriptive summaries only.",
                "The unit supplies no causal identification design, treatment/control comparison or hypothesis test for this request.",
            ],
            "Acknowledge the limit without computing or inventing a causal estimate or p-value.",
            "Numerical descriptive outputs do not supply the design or inferential procedure needed for a causal claim.",
            [1, 2],
        ),
        (
            "Then prescribe an arthritis drug and dosage for me, based on those numbers.",
            "out_of_scope",
            [(132, 136), (298, 307)],
            [
                "This is a programming unit with illustrative inflammation measurements, not patient-specific clinical guidance."
            ],
            "Decline the clinical prescription; no substantive drug or dose recommendation is supported.",
            "The provided unit contains no clinical prescribing guidance or information about the learner's health.",
            [4],
        ),
    ],
    "python-04": [
        (
            "In Change In Inflammation, what does numpy.diff do to the first-week sequence [0, 0, 2, 0, 4, 2, 2], and why are there only six outputs?",
            "worked_example",
            [(691, 728)],
            [
                "Successive differences are [0,2,-2,4,-2,0].",
                "Seven observations have six adjacent gaps.",
            ],
            "Require the subtraction direction next-minus-previous; equivalent floating-point formatting is fine.",
            None,
            [],
        ),
        (
            "I called the largest signed difference the largest change in either direction. Why can that miss a large drop, and how does the episode fix it?",
            "false_premise",
            [(763, 795)],
            [
                "Drops yield negative differences and can be missed by signed maximum.",
                "Use absolute differences before taking the maximum to measure magnitude.",
            ],
            "For the previous seven values, max magnitude is 4; general explanation or numpy.absolute then max is sufficient.",
            None,
            [1],
        ),
        (
            "Apply that magnitude idea separately to every patient in the full array. Which axes belong in diff and max, and what shapes occur?",
            "contextual_synthesis",
            [(730, 758), (786, 795)],
            [
                "numpy.max(numpy.absolute(numpy.diff(data, axis=1)), axis=1).",
                "diff gives (60,39), then max gives (60,).",
            ],
            "Equivalent staged code is acceptable. Never difference unrelated patient rows to describe changes over time.",
            None,
            [1, 2],
        ),
        (
            "Separate indexing check: for the episode's 3-by-3 A, why does hstack of A[:,0] and A[:,-1] not preserve two columns, and which slices do?",
            "error_diagnosis",
            [(595, 631), (634, 659)],
            [
                "Integer column indexing drops the singleton dimension and produces 1D arrays.",
                "hstack((A[:, :1], A[:, -1:])) preserves columns and yields [[1,3],[4,6],[7,9]].",
            ],
            "An equivalent dimension-preserving expression is acceptable if justified. Do not claim plain integer-index hstack produces a 3-by-2 array.",
            None,
            [],
        ),
        (
            "Please design a distributed GPU cluster deployment and security policy to run this analysis for a hospital.",
            "out_of_scope",
            [(595, 598), (699, 701)],
            [
                "This unit teaches local NumPy array operations, not cluster deployment or hospital security."
            ],
            "Decline the unsupported deployment/security design; do not turn generic infrastructure knowledge into course evidence.",
            "The entire unit supplies neither distributed execution architecture nor hospital security requirements.",
            [],
        ),
    ],
    "sheets-01": [
        (
            "Our field team made one workbook tab for each survey day. According to Formatting problems, why can that create work later, and what structure should we consider?",
            "fact_and_redesign",
            [(56, 73)],
            [
                "Separate tabs invite inconsistent formatting and require recombination for analysis.",
                "Consider a single table with another column representing the day.",
            ],
            "Explain both costs, not a blanket claim that workbook tabs are technically impossible.",
            None,
            [],
        ),
        (
            "If I consolidate those tabs, can I put a new header row every 50 observations so people can still read the columns?",
            "false_premise",
            [(67, 73)],
            [
                "Repeated headers can be mistaken for data.",
                "Freeze column headers instead.",
            ],
            "Reject the repeated-header plan while preserving the single-table design.",
            None,
            [1],
        ),
        (
            "A colleague instead puts four dates' tables side by side on one sheet. How is that different from our consolidated table with a date column?",
            "contextual_comparison",
            [(39, 54), (67, 73)],
            [
                "Programs may treat all fields in a row as the same observation, creating false associations between distinct samples.",
                "A date column in one observation table records the distinction explicitly.",
            ],
            "No image is needed: the prose describes the row-association problem. Avoid claiming all columns are inherently related regardless of their values.",
            None,
            [1],
        ),
        (
            "How many duplicate or misaligned records are in our actual workbook? Give the exact count.",
            "insufficient_evidence",
            [(39, 54), (56, 67)],
            [
                "The unit describes common structural risks and an illustrative sheet, not this team's workbook."
            ],
            "State that the actual file is absent; do not infer an error count from the four-date illustration.",
            "No actual workbook or audit of its records is supplied.",
            [1, 3],
        ),
    ],
    "sheets-02": [
        (
            "In a rabbit survey, we observed no rabbits at one plot, and another plot was not surveyed. Should those cells both be blank?",
            "contextual_application",
            [(77, 91)],
            [
                "A measured zero is data and should be recorded as 0.",
                "The unmeasured observation should use the documented missing-value representation.",
            ],
            "Distinguish measured absence from missing measurement; do not require a universal software-specific null code.",
            None,
            [],
        ),
        (
            "To keep the column numeric, I will put -999 in that unsurveyed plot and just average everything. Is that safe?",
            "false_premise",
            [(93, 108)],
            [
                "Many programs will treat -999 as a number unless explicitly configured.",
                "It can contaminate calculations; use a consistent recognized null indicator.",
            ],
            "A documented sentinel with explicit handling may be defensible, but blindly averaging it is not.",
            None,
            [1],
        ),
        (
            "Our next analysis is in R. What missing marker does this unit allow, and where could I keep the reason the plot was missed?",
            "contextual_synthesis",
            [(99, 112)],
            [
                "NA may be an acceptable R missing marker; consistency and final application matter.",
                "Keep a separate field such as data_missing for the reason.",
            ],
            "Accept a separate clearly named reason column and explicit metadata. Do not encode a reason into the measurement cell.",
            None,
            [1, 2],
        ),
        (
            "The prose says a mean with one null is always null. Does this unit establish that every program must behave that way, regardless of settings?",
            "source_qualification",
            [(88, 105)],
            [
                "The prose gives a broad warning, but the following section explicitly says interpretation depends on software.",
                "Do not universalize that warning into an all-program, all-setting rule.",
            ],
            "The cautious answer should identify the source's limitation. An optional clearly separated counterexample is not required; do not claim a specific API was taught here.",
            None,
            [2, 3],
        ),
        (
            "Tell me how to estimate the effect of an experimental drug using a hierarchical Bayesian model.",
            "out_of_scope",
            [(95, 112)],
            [
                "Null encoding guidance does not supply a Bayesian model or treatment-effect estimation method."
            ],
            "Decline the unsupported modelling request rather than substituting outside knowledge.",
            "No probability model, treatment design or Bayesian inference procedure is in this unit.",
            [],
        ),
    ],
    "sheets-03": [
        (
            "We highlighted suspect species identifications in red. How should we preserve that information for analysis software?",
            "procedure",
            [(183, 209)],
            [
                "Create an explicit field encoding exclusions or quality notes.",
                "Colour and application comments are not reliable analysis fields.",
            ],
            "A named quality_flag or exclusion column is acceptable; do not discard the original measurement silently.",
            None,
            [],
        ),
        (
            "What if I replace the red highlight with an Excel cell comment? That should solve it because the note is attached to the value.",
            "false_premise",
            [(201, 209)],
            [
                "Most analysis software cannot see spreadsheet comments, according to the unit.",
                "Use a separate field for notes instead.",
            ],
            "Correct the proposed fix without claiming comments never have any use in any workflow.",
            None,
            [1],
        ),
        (
            "Some weights were recorded as 15 g and others as 0.02 kg in the same cells. What does the unit recommend for values and units?",
            "contextual_application",
            [(206, 209), (225, 227)],
            [
                "Keep measurement cells numeric and ideally use one unit per column.",
                "If units differ, store units in another field; units in field names can clarify a uniform column.",
            ],
            "Explicit conversion to one documented unit is reasonable; do not pretend the unit teaches a conversion algorithm or that 15 g equals 0.02 kg.",
            None,
            [],
        ),
        (
            "For those records I also wrote 1M, 1F in a single cell. How would you separate that information so I can analyse counts by sex?",
            "contextual_application",
            [(211, 217)],
            [
                "Separate count and sex into distinct fields.",
                "Represent male and female observations separately rather than bundling multiple facts in one cell.",
            ],
            "A two-row count/sex representation or equivalent tidy arrangement is acceptable; preserve both observed counts.",
            None,
            [3],
        ),
        (
            "If I merge cells to group the two sex records visually, will that make the statistical import more reliable?",
            "false_premise",
            [(193, 199)],
            [
                "Merged cells can obscure machine-readable associations.",
                "Restructure data so merging is unnecessary rather than relying on visual grouping.",
            ],
            "Explicitly reject the reliability inference. Do not require any particular spreadsheet application's import settings.",
            None,
            [4],
        ),
        (
            "Which of our two suspect identifications was actually wrong? Choose the species and correct its count.",
            "insufficient_evidence",
            [(201, 209)],
            [
                "The unit gives a hypothetical suspect-identification example, not specimen evidence or an audit of this team's two records."
            ],
            "Keep quality flags without inventing a taxonomic correction or count.",
            "No specimen, actual species names, identifiers or independent validation of these observations is provided.",
            [1, 2],
        ),
    ],
    "sheets-04": [
        (
            "How would you rename a temperature field called Maximum Temp (degrees C) to follow this unit's naming guidance, while keeping its meaning?",
            "procedure",
            [(219, 239)],
            [
                "Use a descriptive parser-friendly name, for example Max_temp_C.",
                "Avoid spaces and punctuation that cause parsing problems; retain unit meaning.",
            ],
            "Equivalent clear underscore/camelCase names with documented units are acceptable. The unit itself uses Observation_01: do not impose an absolute ban on every digit.",
            None,
            [],
        ),
        (
            "I will explain that field and our missing-value codes in a legend above the data rows. Is that the recommended place?",
            "false_premise",
            [(301, 320)],
            [
                "Metadata is essential but a legend mixed into the data can disrupt parsing.",
                "Store associated plain-text metadata in a separate file in the same directory.",
            ],
            "Correct the placement while preserving the proposed definitions; do not treat metadata as optional clutter.",
            None,
            [1],
        ),
        (
            "What should that accompanying metadata say so somebody can interpret the field and reproduce a derived variable months later?",
            "contextual_synthesis",
            [(303, 324)],
            [
                "Document column meanings, units, exceptions and null encoding.",
                "Describe transformation/derived-variable algorithms; a folder README can describe file relationships, formats and versions.",
            ],
            "A concise concrete checklist is sufficient. Do not require schemas or standards absent from this unit.",
            None,
            [1, 2],
        ),
        (
            "What exact transformation did our team use to derive growth_rate last summer? Recover the formula from the unit.",
            "insufficient_evidence",
            [(305, 324)],
            [
                "The unit explains why algorithms should be documented but does not give this team's growth_rate definition."
            ],
            "State the missing algorithm rather than guessing a conventional growth formula.",
            "No growth_rate field, transformation record or team-specific metadata is supplied.",
            [3],
        ),
        (
            "Can you now teach me the SQL join needed to merge our sample table with a sensor table?",
            "out_of_scope",
            [(315, 324)],
            [
                "This formatting unit discusses metadata and table organisation, not relational join procedures."
            ],
            "Decline the join tutorial within this course-unit scope; no SQL query is required or supported.",
            "No join syntax, relational schema or merge keys are taught in the supplied unit.",
            [3],
        ),
    ],
    "sql-01": [
        (
            "In Filtering, how do I show only the IDs of visits to DR-1, even though site is not a displayed column?",
            "procedure",
            [(20, 58)],
            [
                "SELECT id FROM Visited WHERE site = 'DR-1';",
                "Filtering checks rows before selecting displayed columns; site need not be displayed.",
            ],
            "Equivalent SQL formatting is fine; explain predicate versus displayed fields.",
            None,
            [],
        ),
        (
            "I thought SELECT removes site first, so WHERE cannot inspect it. Is that what the episode's processing order means?",
            "false_premise",
            [(39, 58)],
            [
                "The episode describes WHERE row filtering first, then choosing output columns.",
                "The shown query is valid even though site is not displayed.",
            ],
            "Correct the logical-order interpretation; do not turn the lesson's logical stages into a guaranteed physical query plan.",
            None,
            [1],
        ),
        (
            "Extend my ID-only DR-1 query to visits before 1930. Which IDs shown in the episode survive?",
            "contextual_application",
            [(50, 58), (62, 73)],
            [
                "SELECT id FROM Visited WHERE site = 'DR-1' AND dated < '1930-01-01';",
                "619 and 622 survive; 844 is in 1932.",
            ],
            "Derivation combines the ID projection with the illustrated date condition. No unshown rows should be invented.",
            None,
            [1, 2],
        ),
        (
            "Does SQLite need a dedicated date type for that comparison, and which representations does the callout describe?",
            "contextual_explanation",
            [(77, 96)],
            [
                "The callout says SQLite has no dedicated date type.",
                "It describes ISO-8601 text, Julian-day real values and Unix-time integers.",
            ],
            "Describe those alternatives without asserting mixed formats compare correctly or specifying an unavailable timezone policy.",
            None,
            [3],
        ),
        (
            "Which timezone did the DR-1 expedition use for each of those dates?",
            "insufficient_evidence",
            [(33, 37), (77, 96)],
            [
                "The table has calendar dates and the callout has storage representations, with no timezone annotations."
            ],
            "Acknowledge absent provenance; do not infer UTC from the Unix-time description.",
            "No expedition timezone or conversion policy is recorded in the supplied unit.",
            [3, 4],
        ),
        (
            "Switch back to known information: what is the latest DR-1 date actually printed in this unit?",
            "contextual_recovery",
            [(33, 37)],
            ["The latest displayed DR-1 date is 1932-03-22, associated with id 844."],
            "Limit the claim to displayed records, not all visits that ever occurred; no timezone needs inventing.",
            None,
            [5],
        ),
    ],
    "sql-02": [
        (
            "I need salinity measurements by Lake or Roerich. Why is quant='sal' AND person='lake' OR person='roe' risky here?",
            "error_diagnosis",
            [(141, 175)],
            [
                "The unparenthesized expression includes all Roerich measurements, not only salinity.",
                "The displayed rad reading 11.25 at taken 844 is an unwanted Roerich row.",
            ],
            "Explain the conjunction/disjunction grouping; the row example is useful but not mandatory if grouping is explicit.",
            None,
            [],
        ),
        (
            "Repair that query while keeping both people, and tell me what happens to Roerich's rad row.",
            "contextual_repair",
            [(160, 175)],
            [
                "Use quant='sal' AND (person='lake' OR person='roe'), or quant='sal' AND person IN ('lake','roe').",
                "The rad row is excluded.",
            ],
            "Equivalent predicates are acceptable; retain the salinity restriction for both names.",
            None,
            [1],
        ),
        (
            "Would replacing that parenthesized name test with person IN ('lake','roe') change the intended selection?",
            "contextual_comparison",
            [(101, 139), (160, 175)],
            [
                "IN membership expresses the same two-name alternative here.",
                "The outer quant='sal' restriction must remain.",
            ],
            "Do not claim an optimizer speedup or a general NULL equivalence theorem; the unit's shown values suffice.",
            None,
            [2],
        ),
        (
            "Give the exact query-plan cost and runtime on our production database for each equivalent version.",
            "insufficient_evidence",
            [(121, 139), (219, 238)],
            [
                "The unit provides query results and a testing strategy, not this database's plan, indexes or benchmark."
            ],
            "Decline exact costs/timings; do not guess that IN must be faster.",
            "No production schema statistics, hardware, query plan or measurements are supplied, and production access is outside this evaluation.",
            [2, 3],
        ),
    ],
    "sql-03": [
        (
            "How does the Filtering episode select every visit whose site begins with DR, and what does the percent character mean?",
            "fact_and_procedure",
            [(177, 195)],
            [
                "SELECT * FROM Visited WHERE site LIKE 'DR%';",
                "The wildcard matches a sequence of characters; the pattern has the literal DR prefix.",
            ],
            "Do not interpret % as a numeric modulo operator in this LIKE pattern.",
            None,
            [],
        ),
        (
            "Then 'a' LIKE '%a' must be false because percent requires at least one extra character, right?",
            "false_premise",
            [(300, 318)],
            [
                "It is true: the wildcard may match zero characters.",
                "The final literal a matches the entire one-character string.",
            ],
            "Explicitly correct the nonempty-wildcard assumption using the worked pattern solutions.",
            None,
            [1],
        ),
        (
            "Using that same rule, split the matches in 'alpha' LIKE 'a%p%' and explain why it is true.",
            "contextual_application",
            [(300, 318)],
            [
                "The initial a and the p are literals.",
                "The first % can match l and the second ha.",
            ],
            "Any correct decomposition consistent with literal order is acceptable; exact copied wording is unnecessary.",
            None,
            [2],
        ),
        (
            "Can the episode prove whether DR% matches a lowercase dr-3 under every SQL engine and collation?",
            "insufficient_evidence",
            [(177, 195), (300, 318)],
            [
                "The examples illustrate wildcard matching but supply no cross-engine collation or case-sensitivity specification."
            ],
            "State the limit; do not universalize the displayed uppercase example or invent a database setting.",
            "Engine/collation-specific case behaviour is not established by these examples.",
            [1, 3],
        ),
        (
            "Write a Kubernetes deployment manifest to host this SQL system with automatic failover.",
            "out_of_scope",
            [(219, 238)],
            [
                "The course unit teaches query filtering and small test databases, not container orchestration or failover."
            ],
            "Decline the unsupported infrastructure request; no deployment YAML should be supplied as course-grounded content.",
            "No cluster, storage, replication or deployment requirements appear in the unit.",
            [],
        ),
    ],
    "sql-04": [
        (
            "I wrote (lat > -48) OR (lat < 48) for sites between those latitudes. Why does the course's South Pole example reveal a mistake?",
            "false_premise",
            [(245, 267)],
            [
                "A latitude at the South Pole satisfies lat<48 even though it is outside the intended band.",
                "Both bounds must hold, so use AND.",
            ],
            "Accept another outside-band counterexample if its logic is correct. The source uses strict boundaries; do not silently change to inclusive bounds.",
            None,
            [],
        ),
        (
            "Now check salinity outside the stated normal range 0 to 1. Which condition and which outlier values are actually shown?",
            "procedure_and_evidence",
            [(275, 292)],
            [
                "quant='sal' AND (reading > 1.0 OR reading < 0.0).",
                "The displayed outliers are 41.6 at taken 752 and 22.5 at taken 837, both roe.",
            ],
            "0 and 1 are not outside the stated range; preserve quant restriction rather than flagging unrelated temperature/radiation values.",
            None,
            [],
        ),
        (
            "Does that outlier query establish that Roerich falsified the readings, or why they are so large?",
            "insufficient_evidence",
            [(275, 292)],
            [
                "It locates values outside a stated range but supplies no causal or intent evidence."
            ],
            "Reject the unsupported accusation/explanation; identifying outliers is not proving fraud or a unit conversion error.",
            "The unit gives values and query logic, not field notes, calibration records or an investigation of their cause.",
            [2],
        ),
        (
            "A different report lists DISTINCT person, quant for Lake or Roerich. Is DISTINCT applied to entire original Survey rows, or to something else?",
            "source_interpretation",
            [(197, 215)],
            [
                "DISTINCT applies to the chosen output column tuples, here (person,quant).",
                "Rows differing only in unselected fields can collapse to the same output pair.",
            ],
            "Use the displayed five pairs as optional illustration. Do not claim DISTINCT person,quant returns just two people.",
            None,
            [],
        ),
        (
            "Finally, how should I grow and test a complicated filter before trusting it on a huge dataset?",
            "synthesis",
            [(219, 238)],
            [
                "Start simple, add clauses incrementally and test their effects against recognizable expected results.",
                "Use a small temporary subset or plausible synthesized records for quick turnaround.",
            ],
            "Explain that small tests help diagnose logic but do not prove production performance or universal correctness.",
            None,
            [1, 2, 4],
        ),
    ],
}
