"""twelveswaras: raaga identification for Carnatic and Hindustani music.

An open "Shazam for raagas", paired with a CC-BY-4.0 data commons. Non-commercial, open source.

Pipeline (pitch_extract -> features -> model):
    audio -> predominant-melody pitch + tonic (Sa), both with essentia
          -> windowed TDMS surfaces and swara phrases, relative to Sa
          -> XGBoost, fused with per-raaga swara chains -> calibrated top-3.
"""
