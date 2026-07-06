---
title: twelveswaras
emoji: 🎶
colorFrom: yellow
colorTo: red
sdk: gradio
app_file: app.py
pinned: false
license: mit
short_description: Shazam for raagas, identify the raaga of a Carnatic clip
---

# 🎶 twelveswaras: identify the raaga

An open "Shazam for raagas": upload or record a short Carnatic clip and it identifies
the **raaga**. Fully automatic: it extracts the predominant-melody pitch and the tonic
(Sa), builds a tonic-normalized pitch-class distribution, and classifies it.

**Tip:** works best with a **tanpura / shruti-box drone** under the melody (that's how the
tonic is found). Solo voice with no drone is unreliable.

Non-commercial, open-source public good · Carnatic first · CC-BY data commons.
Code MIT · model trained on Saraga (CC-BY-NC-SA) + IAMRRD. github.com/twelveswaras
