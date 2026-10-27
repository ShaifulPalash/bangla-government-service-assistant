# Question-answering workflow

Every question goes through the steps below. The cheap steps come first, so many
questions end without calling a language model. The workflow is built with LangGraph
(`src/app/graph/workflow.py`); each box is a node, and each arrow is a rule that is
tested in `tests/unit/test_graph_workflow.py`.

```mermaid
flowchart TD
    Q(["Question"]) --> P["prepare: hide personal numbers, safety check, detect language"]
    P -->|"override attempt or someone else's data"| RS["refuse: safety"]
    P --> C["classify: passport, nid, both or unclear"]
    C -->|"service unclear and topic out of scope"| RO["refuse: out of scope"]
    C --> R["retrieve: meaning search, top 3, limited to the service"]
    R -->|"search failed"| U["unavailable"]
    R --> E{"evidence: best score at least 0.755?"}
    E -->|"no, service unclear"| CL["clarify: passport or NID?"]
    E -->|"no, service named"| RN["refuse: not in the documents"]
    E -->|"yes"| A["answer: Groq first, Gemini as backup"]
    A -->|"models failed or reply unreadable"| U
    A -->|"model says it cannot answer"| RM["refuse: model declined"]
    A --> V["respond: check citations and numbers"]
    V -->|"no valid citation or number not in the sources"| RN
    V -->|"all checks pass"| ANS(["Answer with sources and dates"])
```

## Outcomes

| Outcome | When | Model called? |
|---|---|---|
| answer | strong evidence, valid citations, numbers found in the sources | yes |
| clarify | the service is unclear and the best passage is weak | no |
| refuse | override attempt, someone else's data, out-of-scope topic, weak evidence, model declined, or an unverifiable answer | usually no |
| unavailable | search or all language models failed | depends |