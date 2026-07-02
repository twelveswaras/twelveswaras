"""twelveswaras — raaga identification pipeline.

An open "Shazam for raagas": infer the raaga of any Carnatic performance, paired
with a CC-BY-4.0 data commons. Non-commercial, open-source only (PRD D1).

Pipeline order (PRD §6.7):
    audio -> [tonic ID + predominant-melody] -> normalize to Sa
          -> features (swara histogram / TDMS / mel-CQT) -> model -> top-3.

The tonic step (PRD D5, essentia/compIAM) is Phase 2 — Phase 1 is a librosa-only
floor so we get a working baseline without native-lib pain on Apple Silicon.
"""
