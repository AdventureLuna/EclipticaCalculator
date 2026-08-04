# Ecliptica Build Forge

A static, browser-based build explorer for Ecliptica.

## Features

- Class-specific base health and healing values
- Class-themed backgrounds using the official class symbols
- Searchable and filterable upgrade catalog
- Stackable upgrades with persistent selections
- Live derived statistics
- Upper and lower soft-cap calculations
- Hover breakdowns showing every source influencing a statistic

## Upgrade data source

Upgrade names, descriptions, and numerical modifiers are checked against the English
[Ecliptica Wiki](https://ecliptica.miraheze.org/wiki/Main_Page). The crystal upgrade
data comes from the wiki's [Upgrades](https://ecliptica.miraheze.org/wiki/Upgrades)
page, while class-specific upgrades come from the individual English class pages.
The current data was reviewed against wiki revisions available on August 4, 2026.

## Run locally

Open `index.html` in a browser. No build step or web server is required.

The project is also suitable for GitHub Pages deployment from the repository root. The `.nojekyll` file ensures the static files are served directly.
