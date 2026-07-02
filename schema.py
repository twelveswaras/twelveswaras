"""The data-commons schema (PRD §18.1).

A `datasets.Features` spec is defined even though v0 has no contributions yet — it
future-proofs the commons so the v1 contribute/verify loop writes into a stable
shape. Dataset license: CC-BY-4.0 (D9), kept separate from Saraga-derived artifacts.
"""
from __future__ import annotations

from datasets import Audio, Features, Sequence, Value

FEATURES = Features(
    {
        "id": Value("string"),
        "audio": Audio(sampling_rate=16_000),
        "audio_sha256": Value("string"),      # dedup key (D12)
        "raaga": Value("string"),             # canonical vocab (raagas.json)
        "tradition": Value("string"),         # carnatic | hindustani (D3)
        "contributor_id": Value("string"),    # optional pseudonym, never PII (D12)
        "is_own_performance": Value("bool"),  # rights gate (§12)
        "license": Value("string"),
        "consent_version": Value("string"),
        "created_at": Value("string"),
        "label_source": Value("string"),      # model_confirmed | contributor_declared | expert
        "model_prediction": Value("string"),
        "model_confidence": Value("float32"),
        "verification_status": Value("string"),  # unverified | verified | disputed (D13)
        "split": Value("string"),             # pending | train | test | disputed
        "votes_agree": Value("int32"),
        "votes_disagree": Value("int32"),
        # nice-to-have
        "tonic_hz": Value("float32"),
        "tonic_source": Value("string"),
        "instrument": Value("string"),
        "voice_type": Value("string"),
        "form": Value("string"),
        "tala": Value("string"),
        "annotations": Sequence(
            {
                "type": Value("string"),      # phrase | tonic | swara_boundary
                "start_s": Value("float32"),
                "end_s": Value("float32"),
                "value": Value("string"),
                "annotator_id": Value("string"),
            }
        ),
    }
)
