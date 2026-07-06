# Real-world benchmark

The frozen benchmark is clean **studio** audio (top1 0.798 / top3 0.938). This measures the
number that actually matters, accuracy on **real-world** clips (phone mics, room acoustics,
concert halls), and breaks it down **by drone presence**, which directly tests whether the
tonic step is the coverage bottleneck.

## How to use

1. Put audio files in `audio/` (gitignored). Any format librosa/ffmpeg reads (`.m4a`, `.wav`, …).
2. Copy the template and fill one row per clip:
   ```
   cp clips.example.csv clips.csv     # clips.csv is gitignored
   ```
   Columns: `file, raga, source, license, drone, notes` (see the template's header comments).
   The `raga` label is folded to the 40-raaga vocab, so any spelling works; out-of-vocab or
   file-less rows are reported and skipped.
3. Run (in the **numpy<2 inference env**, same as the demo):
   ```
   python -m tools.realworld_eval
   ```
   It prints per-clip predictions and an aggregate top1/top3 vs the studio number, plus a
   `drone=yes / no / unknown` breakdown and a count of clips that produced **no prediction**
   (no tonic/melody found, itself a real-world failure mode).

## Sourcing clips (no singing required: it's curation + label-lookup)

You identify the **composition**, not the raga by ear: a kriti's raga is a documented fact
("Endaro Mahānubhāvulu" is always Śrī). So labeling is a lookup, not an ear test.

- **Your own concerts**: 30–60 s on your phone from your seat. Exactly the target domain;
  the raga is usually announced or inferable from the kriti. Best source.
- **YouTube concerts**: titles often name the raga. **Private-eval only** (`license=private-eval`).
- **archive.org / AIR**: kutcheri recordings, some CC / public-domain (can also seed the commons).
- **Volunteers / music schools**: the slow-but-ideal path; also the data-commons seed.

**~30–50 in-vocab clips is enough** for a meaningful read. Keep clips whose raga is one of the 40.

## Legal line (important)

Use clips **privately, to measure accuracy**: that is a defensible evaluation use. This is
**separate** from the rights-clean **CC-BY commons**: do not redistribute copyrighted audio.
The `audio/` dir and your filled `clips.csv` are gitignored for this reason; only this README,
the `clips.example.csv` template, and `tools/realworld_eval.py` are tracked.
