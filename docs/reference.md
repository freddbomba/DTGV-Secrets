# Reference

## Spec conformance decisions

This is an implementation of the "Interview Intake App" specification v0.1. The
contracts in spec sections 4 (filename grammar), 5 (`registry.json`), 7
(`meta.json`), 9 (encryption) and 10 (allocation) are implemented verbatim. The
few ambiguous points are resolved as follows:

1. **`meta.json` `size_bytes`** (spec section 7) is the size of the stored
   encrypted `audio.age`, so `verify` can check it against the on-disk file.
   `original_*` fields describe the source.
2. **Registry commit vs. encryption order.** The reserve-then-commit algorithm
   (section 10) commits `last_serial` and `issued` *before* encryption, because
   that is the order in section 11. A failed encryption therefore consumes a
   serial; this "phantom serial" is left with a `FAILED` marker for the
   supervisor. The integrity check in section 7 runs before `meta.json` is
   written.
3. **Decryption output extension** is taken from `meta.json`'s `audio.format`,
   defaulting to `.wav` (spec section 12 shows `.wav`).
4. **Interview folder permissions** respect the umask rather than forcing
   `0700`, so the shared Nextcloud folder keeps working.
5. **`age` CLI fallback for decryption** refuses to overwrite existing output;
   pass `--force` to replace.
6. **Stale lock** older than `lock_stale_seconds` is removed at the start of
   each allocation attempt, as suggested in section 10.

## Pro forma data and Excel export

`tests/data/pro_forma_interviews.json` holds **15 fictional interview records** —
a pro forma used for testing and for producing tracking spreadsheets. It
contains no real PII.

Convert it to an Excel workbook with the utility script:

```bash
# install the optional Excel dependency once
pip install -e '.[excel]'

# standalone script (works without installing the package)
python scripts/pro_forma_to_excel.py \
  --input tests/data/pro_forma_interviews.json \
  --output pro_forma_interviews.xlsx

# or the installed console command
pro-forma-to-excel -i tests/data/pro_forma_interviews.json -o pro_forma.xlsx
```

The workbook has one row per interview, with a bold frozen header row and an
auto-filter. Columns: Interview ID, Date, Researcher, Mnemonic, Location,
Language, Participants, Duration (s), Source file, Format, Size (bytes),
Transcription, Consent ref, Notes.

Fields per record:

| Field | Meaning |
|---|---|
| `interview_id` | Canonical ID (`YYYY-aaa-bbb-NNNN`). |
| `date` | Interview date. |
| `researcher_id` / `mnemonic` | ID components. |
| `location` / `language` | Free text. |
| `participants` | Number of speakers. |
| `duration_seconds` | Recording length. |
| `original_filename` / `format` / `size_bytes` | Source audio details. |
| `transcription_status` | e.g. `pending`, `transcribed`, `in_review`. |
| `consent_ref` | Path/ID of the consent document. |
| `notes` | Free text. |

Generated `.xlsx` files are git-ignored.
