# 1. Finding
The provided judge graded every task against the previous task's gold. One character. Fixed, it passes 89/89 gold.
sol 57.9% Criteria@3 [39.7, 74.6] vs luna 38.5% [25.2, 51.4]. n = 10 tasks, 3 runs, judge gpt-4.1.
Every spreadsheet total was blank to both models.

# 2. Numbers
luna 0.385 [0.252, 0.514] · sol 0.579 [0.397, 0.746] · sol − luna +0.194 [+0.065, +0.340] · up 6 / down 0 / same 4
gemini judge: luna 0.368, sol 0.606, diff +0.238 [+0.086, +0.412], same 6/0/4
Judge agreement gemini vs gpt-4.1: kappa 0.849 (212 luna pairs), 0.856 (169 sol pairs), first run
On 6 disputed rows gpt-4.1 matched the tiebreak 4 times, gemini 2. Not random, n = 6, 5 labels by Opus.
Rotated-gold run: 1/89 and 0/89 met. The judge rejects wrong answers.

# 3. Failures (193 failed criteria, first run, gemini judge)
reasoning 91/134 luna, 44/59 sol · information_gathering 23, 8 · instruction_following 12, 4 · communication 5, 2
tool_use and planning_reflection 0: classifier sees only the final answer
Classifier cannot see the source files; misreads land in reasoning. Accuracy unmeasured.
Task 13 run 3: $23,693.10 vs accepted $23,818.10. Task 14 run 1: three soft-cost rows listed, never reclassified.

# 4. What is wrong with this eval
129 of 151 formula cells carry no cached value; the loader sent every TOTAL row blank.
8 of 89 criteria pass on a blank answer ("no more than N", "$0.00"); Task 4's guard passed on rotated gold.
13 of 60 model calls hit 429 at 500k TPM; recovered by rerun at workers 1, $7.63.
One judge run per criterion at temperature 0; judge stability not measured.
n = 10 tasks from one firm; the CI spans 26 points.

# 5. Next steps, and what was cut
Recompute formulas at load, rerun: changes the headline, likely up.
Label 40 random rows; add a rounding rule to the judge prompt.
Verify Task 7's rate cell and Task 26's $198,000 offset (explorer pointers, unconfirmed).
Cut: judge stability, classifier accuracy, taxonomy on the rerun rows.
