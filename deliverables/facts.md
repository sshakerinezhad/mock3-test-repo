<!-- source: mine, 2026-09-28. Copy to results/<run>/facts.md at minute 0. The assistant fills it as numbers land; slides come only from here. -->
# Facts

## Findings (one line each, newest first)
- Finding: the provided judge shipped with an off-by-one in gold_outputs pairing each task with the previous task's gold; gold scored 1/89 (gpt-4.1) and 0/89 (gemini) before the fix, 86/86 judged and 89/89 after. The broken run doubles as a negative control: the judge rejects wrong answers. Source: results/gold_* metrics.json, commit 4021299.
- Finding: 129 of 151 formula cells across 39 workbooks carry no cached value; the loader renders every TOTAL row blank; the model never saw a total. Source: openpyxl check; Task 30 luna run 1 prompt field in results/apex_acc_v1/raw.jsonl.
- Judges: gemini vs gpt-4.1 kappa 0.849 on 212 luna pairs (92.9% agreement, 15 disagreements), 0.856 on 169 sol pairs (93.5%, 11); disagreements cluster on multi-value answers; 0 judge nulls via OpenRouter. Source: results/kappa_v1_*.txt.
- Failures: 193 failed criteria (gemini judge, v1) classified by gemini into the paper's L1s; reasoning 91/134 luna (68%), 44/59 sol (75%); information_gathering 23 and 8; instruction_following 12 and 4; communication 5 and 2; tool_use and planning_reflection 0 by construction (classifier sees only the final answer); 3 unparsed; classifier accuracy unmeasured. Source: results/classify/judge/scores.json.
- Harness errors: 13 of 60 model calls failed with 429 at 500k TPM per model; rerun at workers 1 recovered all 13 ($7.63, 7.1 min); 60/60 rows; n = 10 tasks x 3 runs x 2 models, 89 criteria per run. Source: results/apex_acc_v1b/raw.jsonl.
- Guard criteria: 8 of 89 pass on a blank answer ("no more than N", "$0.00"); Task 4's guard passed on rotated gold. Source: dev.jsonl rubric; results/gold_gpt41 (broken run).
- Cut: judge stability (one run at temperature 0); classifier accuracy; explorer pointers not confirmed by ID (Task 7 rate cell, Task 26 offset, rubric dependency chains).
- calibration first run showed that judge script bugged and gave each task previous tasks answer. none passed. rerun with fixed script showed 100% pass on golds
- tasks 30, 23, 7, 17 all fit in 200k context (all 33k or under). 4, 13, 14, 6, 5 take between 213k–253k, 26 takes about 442k. leaving room left for answer all are handled by 5.6 luna and sol
- total tasks had chance of taking too lon, did 4 workers each for both models (because of possible rate limits) and ran shortest tasks first so if the long ones wouldnt fit only those get cut
- rate limit: 500k TPM per model on OpenAI; big tasks 250k to 600k tokens each; 8 of the first 36 calls failed with 429 after 4 retries; mean successful call 70 s. Source: results/apex_acc_v1/raw.jsonl errors field.
- kappa on gold: 86 pairs, 100% agreement, kappa undefined since both judges said met on every pair; the meaningful kappa needs model outputs.

## What question did this answer, and what decision follows?
-

## What exactly is the dataset? Did I check the references?
- n tasks: [ ]  source file: [ ]  rows read by eye: [ ]  duplicates / missing files / odd rows: [ ]

## Is the gap real? The interval on the difference.
- model A mean [ ] (95% CI [ ], n [ ])   model B mean [ ]   diff [ ] CI [ ]   up/down/same [ ]

## What is the resampling unit?
- tasks (task-level bootstrap, [ ] draws); samples per task [ ]

## What is the smallest difference this n could detect?
- interval width [ ]; a difference under [ ] is noise here

## Judge validation
- Judge tiebreak on 6 of the 26 disagreements (1 hand label by me, 5 by a third LLM grader, Opus 5.5): gpt-4.1 matched 4 of 6, gemini 2 of 6; gemini's misses were passes on compound criteria the response only half met (Task 14 run 1, items #4 #5; Task 13 run 3, #3). Not a random slice; says nothing about overall accuracy. Source: results/labels_sheet.md, results/labels.csv.
- labelled [ ]; accuracy [ ]; precision on Met [ ]; recall on Met [ ]; kappa [ ]; base rate Met [ ]; disagreements [ ]

## Judge errors
- timeouts [ ]  api errors [ ]  unparsed [ ]; mean with errors as fail [ ] vs dropped [ ]
- gold rerun, gpt-4.1 direct on OpenAI: 3 of 89 criteria null after 6 attempts each, all HTTP 429 (TPM limit 30000), all on Task 14 (24 criteria); counted as not met by the script, so 98.75% is a harness number, not a judge number. Of the 86 judged, 86 met. Workers 8→3 cut nulls 7→3, not to 0. Source: results/gold_gpt41/results.jsonl error field.

## Failures
- read by hand [ ]; taxonomy: [category: count] ...; examples: [task id], [task id]

## Cost
- calls [ ]; dollars [ ]; minutes of wall clock [ ]; cost per point [ ]

## What was cut
-

## Every number, one line: value · denominator · source file
-
