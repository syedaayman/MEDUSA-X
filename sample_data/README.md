# Sample data

Only use synthetic, de-identified, or otherwise explicitly approved material here.
Never add real patient records, credentials, or documents containing personal health
information. The repository ignores common document formats and the `private/` and
`local/` directories as an additional safeguard; review `git status` before sharing.

## Add a small sample safely

1. Prefer a tiny synthetic PDF or a generated sample from a public synthetic source.
2. Verify that its contents do not identify a real person and that the source license
   permits your intended use.
3. Keep local-only files in `sample_data/local/` or `sample_data/private/`; these paths
   are ignored by Git. Do not force-add ignored files.
4. For a sample meant to be tracked, use a small text fixture with fully synthetic
   content, describe its origin and license here, and have a teammate review it before
   staging. Do not commit raw patient documents or dataset dumps.
5. Do not automatically download either planned dataset. Obtain and inspect samples
   manually under each provider's terms.

## Planned sources

- [EkaCare Medical Public Datasets](https://huggingface.co/collections/ekacare/ekacare-medical-public-datasets):
  evaluate document text extraction on Indian prescriptions and laboratory reports,
  subject to dataset access and license terms.
- [Synthea](https://synthetichealth.github.io/synthea/): generate synthetic
  longitudinal histories for timeline and reconciliation testing.

No datasets are included in this repository.
