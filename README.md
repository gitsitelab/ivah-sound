# Ivah Sound

The Ivah Sound website: a one-page site for the sound system, a journal that keeps
the whole Ivah Sound blog and the Top Shelf drum & bass blog online, and a hidden
artists page.

Live: https://gitsitelab.github.io/ivah-sound/

## Pages

| Page | What it is |
| --- | --- |
| `index.html` | Hero, who we are, the system, history, community, booking, store, social, latest stories |
| `journal.html` + `journal/*.html` | Every post from blog.ivahsound.com (34) and topshelf.ivahsound.com (13), hosted here |
| `artists.html` | The crew from the old ivahsound.com with bios, links and players. Not in the menu and marked `noindex` |

## How it is built

- `src/` holds the page templates, CSS and JavaScript.
- `archive/` holds the original media and posts copied from the old sites. It is filled
  by `tools/import_media.py` (run by the GitHub Action) and committed, so the site keeps
  working after the old sites disappear.
- `tools/build.py` resizes the images, turns the old posts into pages and writes `_site/`.
- `.github/workflows/publish.yml` runs the import, the build and the GitHub Pages deploy on every push to `main`.

Build locally:

```sh
pip install pillow beautifulsoup4
npm install
python tools/import_media.py   # only fetches what is missing from archive/
python tools/build.py          # writes _site/
```

## Booking form (Formspree)

The form currently opens a prefilled email to bookings@ivahsound.com. To receive requests
by Formspree instead:

1. Create a free form at https://formspree.io with bookings@ivahsound.com as the recipient.
2. Copy the form ID (the part after `/f/`).
3. In `src/index.html`, replace `REPLACE_WITH_FORM_ID` in `data-endpoint="https://formspree.io/f/REPLACE_WITH_FORM_ID"`.

## Brand

- Orange `#E97421`, black `#0a0a0a`, off-white `#f2ede4`
- Bebas Neue (headlines), Barlow and Barlow Condensed (text), self-hosted from the
  @fontsource packages, so the site makes no requests to Google Fonts.
- The © year updates automatically.

## Own domain

To serve it at ivahsound.com later: add the domain under Settings → Pages → Custom domain,
then point the DNS records to GitHub Pages.
