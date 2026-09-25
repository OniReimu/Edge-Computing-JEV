# EdgeIntent v1

EdgeIntent v1 is a benchmark of natural-language requests to edge services. Each request is paired with the typed
intent contract it expresses. It has 8,280 cases in 23 generated conditions and 10 further conditions derived
programmatically from verified text. Each condition has 300 test cases and 60 development cases.
The same files are on Hugging Face as [datasets/OniReimu/Edge-Computing-JEV](https://huggingface.co/datasets/OniReimu/Edge-Computing-JEV),
with one dataset config per condition.

## How the cases were made

1. Label tuples were sampled first, with balanced marginals per field and disjoint seeds per condition and split
   (`scripts/eb_build_corpus.py tuples`).
2. A generator model wrote a request text for each tuple. The generators were Gemini-3.8-Flash and Claude-Opus-5.5.
3. A blind verifier (Claude-Opus-5.5, in a separate session) labelled each text without seeing the tuple. A case was
   kept only when the verifier's labels matched the tuple on every field. Lint checks rejected texts that leaked field
   names or enumeration values.
4. Noise, padded lengths (RQ1a), and multi-request bundles (RQ1b) were derived programmatically from verified text.

The generator and verifier of every case are recorded in `meta.generator` and `meta.verifier`, and in
`manifest.json`. None of these models is among the evaluated interpreters.

## Files

| Path | Content |
|---|---|
| `<RQ>/<condition>/test.jsonl`, `dev.jsonl` | Evaluation and development cases |
| `<RQ>/<condition>/timing_subset.txt` | Case IDs of the timing subset |
| `catalog/services.json`, `catalog/catalogs.json` | The 254-service catalog in 16 families, novel services for the churn conditions, and the nested catalogs used by RQ4 |
| `_accepted/` | Accepted generation and verification records per generated condition and split |
| `manifest.json` | Provenance: seed, generators, verifier, per-item records, yields, and file hashes |
| `_frozen.json`, `_yields.json` | Freeze status and first-pass and final yield of the verification gate |
| `stats.md` | Input-length percentiles and yields per condition (the paper's condition table) |
| `ocr/selection.json`, `ocr/manifest.json` | IIIT5K image identifiers selected for RQ5 Part B (40 calibration, 200 test). The images are downloaded by `scripts/eb_iiit5k.py`. |

## Case format

```json
{"case_id": "clean_test_0000",
 "text": "Ward 7B bedside monitor feed: please tally how many IV drip bags are hanging ...",
 "fields": ["service_type", "locality", "quality_floor", "urgency"],
 "service_options": null,
 "bundle_size": 1,
 "truth": [{"service_type": "count", "locality": "remote_allowed", "quality_floor": "high", "urgency": "unspecified"}],
 "meta": {"wording_family": "operator ticket", "scenario": "hospital ward patient monitor", "generator": "claude-opus-5.5",
          "verifier": "claude-opus-5.5", "...": "..."}}
```

`fields` lists the contract fields the interpreter must fill: four core fields, and six or eight in RQ3.
`service_options` carries the request-time service catalog in RQ4. `truth` holds one label dictionary per request in the
message, so a message can contain more than one request (RQ1b).
