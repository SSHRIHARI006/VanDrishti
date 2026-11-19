---
title: Van-drishti AI
emoji: 🌳
colorFrom: green
colorTo: yellow
sdk: gradio
sdk_version: 6.30.0
app_file: app.py
python_version: "3.12"
pinned: false
short_description: Tree inventory from satellite and drone data
---

# Van-drishti AI

Tree enumeration, species, height and canopy density for a forest block, from a boundary file (satellite mode)
or a drone survey (survey mode).

- Two finished sample runs are included: a satellite run for a forest block near Chandrapur, India, and a
  survey run on an IDTReeS benchmark plot.
- New satellite runs use Google Earth Engine through the `GEE_PROJECT` and `GEE_SERVICE_ACCOUNT_KEY` secrets
  in the Space settings.

Source code: https://github.com/sujalappa/Vandrishti-AI
