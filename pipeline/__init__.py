"""Batch jobs (PRD §13, §17).

consolidate.py -> incoming/ -> dedup/validate -> dataset shards (nightly cron, D18).
retrain.py     -> verified data -> new model -> score vs frozen benchmark (D17).
"""
