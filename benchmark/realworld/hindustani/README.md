# Real-world benchmark: Hindustani

The honest number for Hindustani, the way the Carnatic set gives it for Carnatic. Phase 0's
studio cross-validation put the dual model around 0.81 on clean IAMRRD audio; that is the
ceiling, not the field. This set measures accuracy on **real-world** Hindustani clips (phone
mics, room acoustics, baithak and concert recordings) and breaks it down **by drone presence**,
so we can state a real number before claiming Hindustani support. Expect it to be well below the
studio figure, as the Carnatic real-world number (0.388 majority-vote) is below its studio 0.80.

## How to use

1. Put audio files in `audio/` (gitignored). Any format librosa/ffmpeg reads (`.m4a`, `.wav`, ...).
2. Copy the template and fill one row per clip:
   ```
   cp clips.example.csv clips.csv     # clips.csv is gitignored
   ```
   Columns: `file, raga, source, license, drone, notes` (see the template's header comments).
   The `raga` label is folded to the Hindustani-30 vocab (`raagas.hindustani.json`), so any
   spelling works; out-of-vocab or file-less rows are reported and skipped.
3. Scoring runs against the **dual model** (Carnatic + Hindustani). The eval harness gains a
   `--tradition hindustani` selector when the dual model ships; until then this directory is a
   curation target, not yet a runnable score. The clip format is final and safe to fill in now.

## Sourcing clips (curation + label-lookup, no ear test)

The raga of a **bandish** or an announced alap is a documented fact, so labeling is a lookup.
Hindustani concerts almost always announce the raga before the alap begins, which makes labels
even easier to source than for Carnatic.

- **Concert / baithak recordings on your phone**: 30 to 60 s. Exactly the target domain.
- **YouTube concerts**: titles and spoken intros name the raga. **Private-eval only**
  (`license=private-eval`); do not redistribute the audio.
- **archive.org / AIR / Sangeet Natak archives**: some CC or public-domain (can also seed the
  commons).
- **Vocalists and instrumentalists you know**: the slow-but-ideal path, and the commons seed.

Cover the 30 raagas in `raagas.hindustani.json`. Vary the instrument (vocal khayal and dhrupad,
sitar, sarod, bansuri, sarangi, santoor, violin, shehnai) so we can break accuracy down the way
the Carnatic set does. **~30 to 50 in-vocab clips is enough** for a meaningful read.

## Legal line (important)

Use clips **privately, to measure accuracy**: a defensible evaluation use. This is **separate**
from the rights-clean **CC-BY commons**: do not redistribute copyrighted audio. The `audio/` dir
and your filled `clips.csv` are gitignored for this reason; only this README and the
`*.example.csv` templates are tracked.
