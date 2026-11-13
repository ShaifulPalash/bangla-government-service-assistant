# Evaluation results

How the assistant was tested, what the numbers were, and what they do and do not show. Raw results are in
[`eval/results/`](../eval/results). The targets were written and committed **before** the test run:
[`evaluation-targets.md`](evaluation-targets.md).

## 1. The test set

30 labelled questions in English, Bangla, and Bangla typed in English letters: 20 answerable (including one about an
outdated document), 5 out of scope, and 4 ambiguous. They are split into a **development** set (20 questions),
used to build and tune the system, and a **test** set (10 questions), kept unseen until the end and run **once**.

Labels are document-level: each answerable question lists the documents that can answer it, plus short evidence
phrases copied from them. Before the test run the test labels were checked against the documents themselves, without
looking at any system output. One question's expected documents were corrected at that point (q017).

## 2. Retrieval (development set)

14 questions have expected documents. Top-10 results, document level:

| Search | hit@1 | hit@3 | hit@5 | MRR |
|---|---|---|---|---|
| Keyword (BM25) | 0.64 | 0.71 | 0.79 | 0.70 |
| **Meaning (embeddings)** | **1.00** | **1.00** | **1.00** | **1.00** |

By language, keyword search gave hit@1 0.57 for Bangla and 0.71 for English questions, because a Bangla question
shares no words with an English page. Meaning search gave 1.00 for both. Passage level (3 questions with evidence
phrases): meaning search hit@1 0.67 and hit@3 1.00. Hybrid variants (fusion of both searches) did worse than meaning
search alone, so meaning search is the default.

The evidence threshold of 0.755 comes from these scores: the weakest answerable question scored 0.77 and the strongest
weak-evidence question 0.74.

## 3. End to end, development set

All 20 development questions ended in the labelled outcome (14 answers, 3 clarifying questions, 3 refusals), with
citation accuracy 1.00 and answer language 1.00. **These numbers are optimistic**: the threshold, the routing words and
some labels were tuned or corrected on these questions. In one intermediate run, one question (q014) was refused
because the model's source list was invalid. Three repeats and the next full run answered it, so it was run-to-run
variance in the model.

## 4. End to end, test set (final run, once)

| Metric | Target | Result | Met? |
|---|---|---|---|
| Decision accuracy | 0.80 | **0.90** (9 of 10) | yes |
| Refusal recall | 0.90 | **1.00** (2 of 2) | yes |
| Refusal precision | 0.80 | **0.67** (2 of 3) | **no** |
| Citation accuracy | 0.80 | **0.83** (5 of 6) | yes |
| Answer language accuracy | 0.90 | **1.00** | yes |

Four targets were met and one was missed. With 10 questions, one question moves a score by 10 points, so these
numbers show whether there is a large problem and cannot prove a precise level.

| Question | Expected | Result | Top score | Note |
|---|---|---|---|---|
| q005 form valid at all offices | answer | answer | 0.832 | correct |
| q007 documents to carry (Banglish) | answer | answer | 0.820 | correct where checked |
| q009 child under 6, documents | answer | answer | 0.798 | partly correct |
| **q015** registered twice in the voter list | answer | **refused** | 0.725 | wrong refusal |
| q016 lost NID card (Banglish) | answer | answer | 0.823 | correct |
| q017 correct NID information online | answer | answer | 0.810 | correct |
| q021 income tax return | refuse | refused | n/a | refused by routing |
| q023 gas bill (Banglish) | refuse | refused | n/a | refused by routing |
| q026 "where do I get the form" | clarify | clarify | 0.737 | correct |
| **q030** fee in 2015 | answer | answer, **wrong figure** | 0.805 | gave "৮.০০ taka", a Gazette page price |

### What went wrong

**q015.** The right passage (a Q&A about registering twice by mistake) ranked first, but scored 0.725, below the 0.755
threshold, because an English question was matched with a Bangla source. Lowering the threshold would not fix it:
q026, which should ask for clarification, scored 0.737, higher than q015.

**q030.** The model took a price printed at the end of a scanned Gazette page ("মূল্যঃ টাকা 8.00") for a fee. The
number was in the source, so the number check passed it. The decision check also counted it as correct, because the
assistant did answer. The citation check flagged it: the answer cited `nid-010`, not the expected documents.

## 5. Answer quality, graded by hand

The script measures decisions, citations, and language, not whether every claim is right. The author read the six
answered test questions against the source documents:

| Verdict | Questions |
|---|---|
| Supported by the sources | q005, q007, q016, q017 |
| Partly correct | q009 (left out the one under-6 item, a lab-print photo) |
| Wrong | q030 |

This is one reader's judgement on six answers. For q007, only one disputed item (the grey-background photo) was
traced to its source. The other items follow the same checklist but were not traced line by line.

## 6. Changes after the test run (post-evaluation fixes)

| Fix | Why | Check |
|---|---|---|
| Gazette price notes removed from the scanned text | q030 | q030 now answers "200 taka for the first application"; development set 20 of 20 |
| Every passport fee row carries its applicant group, and fee questions search "inside Bangladesh" by default | a manual test showed TK and USD fees mixed in one answer | the fee answer lists only inside-Bangladesh fees; development set 20 of 20; 372 unit tests pass |
| Two prompt rules: fee groups are separate, and abbreviations (GD, NOC, BRC, NID) are defined | the model read GD (General Diary, a police report) as the national ID | the re-issue answer now names the General Diary |

**The test set was not re-run after these fixes**, so section 4 describes the system before them. The q030 answer
after the fix is correct as a figure but still cites a later amendment for a 2015 question and leaves out the 15% VAT.

## 7. Language-model comparison

Ten development questions, three passages each, run through each model.

| Model | Errors | Valid JSON | Right decision | Invented numbers | Right language | Average time |
|---|---|---|---|---|---|---|
| Gemini `3.8-flash` | 8 of 10 | 2 | 2 | 0 | 2 | about 75 s |
| Gemini `3.5-flash-lite` | 0 | 10 | 9 | 2 answers | 8 | about 2.3 s |
| Groq `gpt-oss-120b` | 0 | 10 | 9 | 0 | 7 | about 1.0 s |

After the language fix, a rerun gave answer language 10 of 10 for both remaining models; Groq invented no numbers and
Gemini `3.5-flash-lite` one. These labels date from before the fee-schedule question was relabelled.

## 8. Operation

- The deployed API passed 10 of 10 smoke checks after the final deploy. A first fee answer took about 1.6 to 2 seconds;
  the same question again came from the cache in about 0.1 seconds.
- A local container used 111.2 MiB of memory after a full smoke test (one reading on a laptop). Render's own memory
  chart was not read.
- Free hosting sleeps when idle. During testing, one wake-up of the API got stuck and needed a manual restart.

## 9. Limits of this evaluation

- Ten test questions and twenty development questions are very small samples.
- The development scores are optimistic, because the system was tuned on them.
- Some labels were corrected after looking at results (q006, q008), always from the documents. The test labels were
  checked before the run.
- Answer quality was read by one person on six answers.
- The model chooses its citations and can add details that no source states (for example an invented form name).
  The number check does not catch words or single-digit numbers.
- Free-tier model limits were observed, not measured under load. There was no test with many visitors at once.
