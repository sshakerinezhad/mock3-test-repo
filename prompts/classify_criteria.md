<!-- source: mine. Failure taxonomy over rubric criteria. Edit the category list for the dataset (from the task, or from your own reading of failures.md); the code reads categories from the '- name: description' lines. -->
You are given one failed rubric check: the criterion, the judge's reason it was not met, and the model's response.
Pick exactly one category from the list below.
Reply with one JSON object and nothing else:
{"category": "<name>", "why": "<one sentence, quoting the response or the criterion>"}

Categories:
- information_gathering: the response missed or misread a fact that was in the context files
- instruction_following: the response ignored a stated requirement of the prompt (rounding, format, which items to include, where to answer)
- reasoning: the facts were gathered but the calculation or logic is wrong
- tool_use: a spreadsheet, file or computation was handled wrongly (wrong sheet, wrong column, parse error)
- planning_reflection: the response did not check its own work, gave conflicting values, or stopped before finishing
- communication: the right answer is present but stated so the criterion cannot find it (buried, ambiguous, several candidates)
- other: none of the above; say why in the why field

If multiple categories apply, pick the one higher in the list.
