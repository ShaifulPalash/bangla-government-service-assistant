# Evaluation targets

These targets were written and committed **before** the test split was run.

## What is measured

The assistant is evaluated end to end on 10 labelled test questions that were not used to
tune any rule, threshold or prompt. For each question we compare what the assistant did
(answer, clarify or refuse) with its label, check that an answer cites an expected document,
and check the language of the answer.

## Acceptance targets

| Metric | Target | Why |
|---|---|---|
| Decision accuracy | at least 0.80 | most questions should end in the labelled outcome |
| Refusal recall | at least 0.90 | a question that should be refused but is answered is the costly mistake |
| Refusal precision | at least 0.80 | refusing answerable questions makes the assistant unhelpful |
| Citation accuracy | at least 0.80 | an answer must point at a document that supports it |
| Language accuracy | at least 0.90 | Bangla questions get Bangla answers, English questions get English |

## Limits

Ten questions are very few: one question moves a score by 10 points. The run can reveal big
problems but cannot prove that a score is exactly right. The development split (20 questions)
was used to set the evidence threshold, the routing words and some labels, so its scores are
optimistic. The test split was labelled and verified against the documents before the run.