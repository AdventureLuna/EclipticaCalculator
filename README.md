# EclipticaCalculator

A stat calculator to design builds and test the impact of upgrades in Ecliptica.

This repository currently includes a minimal static GitHub Pages test site for verifying that the project can be published from the repository root.

## Expected GitHub Pages URL

After GitHub Pages is enabled, the site is expected to be available at:

```text
https://<username>.github.io/EclipticaCalculator/
```

Replace `<username>` with the GitHub account or organization that owns this repository.

## Enable GitHub Pages

If Pages is not already enabled, configure it manually:

1. Open the repository on GitHub.
2. Open **Settings**.
3. Select **Pages**.
4. Under **Build and deployment**, choose **Deploy from a branch**.
5. Select the repository's default branch.
6. Select **/ (root)**.
7. Save.

## Test locally

Open `index.html` directly in a browser. The page should show:

- The title `Ecliptica Calculator`
- The text `GitHub Pages is working`
- A `Test JavaScript` button

Click the button and confirm the status message changes to `JavaScript is working`.

## .nojekyll

The `.nojekyll` file disables Jekyll processing on GitHub Pages, so GitHub serves the static files in this repository directly.
