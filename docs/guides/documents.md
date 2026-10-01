# Documents and citations

Documents let beliefs be grounded in exact spans of text, with the span checked by code.

## Registering documents

```python
kb.add_document("10-K", open("acme-10k.txt").read())

# or, with an agent
agent = Agent(model, documents={"10-K": text, "earnings-call": transcript})
```

Registered documents are shown to the model in a `# Documents` section of its context, truncated at
`Projector(max_document_chars=...)` (50,000 characters by default). Truncation is announced in the
prompt.

## Citing

```python
kb.cite(
    "revenue:Q2",
    4.3e9,
    document="10-K",
    quote="Total revenue for the second quarter was $4.3 billion",
    claim="Q2 revenue",
)
```

`cite` creates a premise with source `document:10-K`, after two checks:

1. **The quote appears in the document.** Matching ignores case, collapses whitespace and normalizes curly
   quotes and dashes. Otherwise it is exact: no paraphrases.
2. **The value is stated in the quote** (pass `check_value=False` to skip). Strings must appear in the
   quote. Numbers must match a number in the quote after rounding to its stated precision, at common scales
   (units, thousands, millions, billions, trillions, and percent). So `4.3e9` matches "$4.3 billion" and
   `0.0976` matches "9.76%".

The second check is what stops a model from citing a real sentence while extracting a number that isn't
in it.

A model cites with the `cite` action of the [claim contract](contract.md#cite). Failed checks are
rejected and fed back like any other contract violation.

## Verification

`CitationCheck` re-checks every cited premise in a proof against the current document text. If a document
is replaced after a citation was recorded, and the quote no longer appears, verification fails. If the
document isn't available (verifying a proof without its base), the citation produces a warning instead.

## Current limitations

- Documents are plain text. For PDFs or HTML, extract the text first.
- Quotes are matched as substrings. There are no character offsets yet, so a quote that appears twice
  isn't disambiguated.
- Large document sets should be retrieved per task rather than all registered at once. Retrieval
  integration is on the roadmap.
