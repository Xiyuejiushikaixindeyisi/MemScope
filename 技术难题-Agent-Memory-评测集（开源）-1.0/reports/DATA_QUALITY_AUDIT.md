# Guide-compatible data audit

This report is diagnostic only. The main evaluation pack was not modified.

## Temporal information

- Selected LoCoMo questions: 500
- Selected temporal questions: 167
- Temporal questions whose evidence contains relative-time language: 117
- Session date values copied verbatim into Add content: 0

The guide-compatible converter omits upstream `session.date_time`. Relative expressions
such as “yesterday” may therefore lose the calendar anchor needed for an absolute date.

## Other omitted upstream context

- Selected multimodal LoCoMo questions: 207
- Selected questions with multimodal evidence: 244
- Selected MemOps questions with candidate options upstream: 100
- Candidate-option fields omitted in the main pack: 100

These are compatibility findings, not silent corrections. See the JSON reports for details.
