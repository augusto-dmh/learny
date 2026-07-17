# Demo Media: Capture Guide

This guide scripts a <90-second demo of Learny's core user flows: upload a book → ask a question
and receive a cited answer → generate a quiz → review a spaced-repetition card. This guide defines
the asset structure and capture checklist; Phase E's README will embed these assets.

## Money-Path Script (≤90 seconds)

The demo captures four moments in sequence:

| Scene | Action | Timing | Asset Slot | Notes |
|---|---|---|---|---|
| **1. Library** | Upload a book (EPUB) to the learner's library | 0–15s | `docs/media/screenshot-library.png` | Static screenshot after upload succeeds; shows the uploaded title in the list |
| **2. Ask** | Open the book, ask a cited question, receive a grounded answer with citations | 15–50s | `docs/media/screenshot-ask.png` | Static screenshot of the Q&A interface with visible citations; shows question + answer + cited passage |
| **3. Quiz** | Generate a quiz from the same passage | 50–70s | Implied in video flow | (Video only; no static screenshot required; shows quiz generation UX) |
| **4. Review** | Review a spaced-repetition card for the passage | 70–90s | `docs/media/screenshot-review.png` | Static screenshot of the card-review interface; shows the card, passage context, and recall rating options |

Total runtime: ≤90 seconds. Total assets: 1 video (demo.gif) + 3 screenshots.

## Capture Checklist

### Prerequisites

- A Learny instance running locally or on staging (all features green locally; no deploy required)
- A test book (EPUB format) loaded and ready to upload
- Tooling:
  - **Screen capture**: QuickTime (macOS), OBS/SimpleScreenRecorder (Linux), or Windows 10+ Screen Recorder
  - **GIF encoding** (if recording as video): `ffmpeg` (e.g., `brew install ffmpeg` on macOS)
  - **Screenshot tool**: Built-in screenshot tool (Cmd+Shift+3 macOS, Shift+Print Windows/Linux)

### Capture Steps

1. **Test walkthrough locally**
   - Start Learny: `docker compose up -d` (or your local dev server)
   - Log in as a test user (or create one)
   - Verify the upload, Q&A, quiz, and review flows work end-to-end
   - Timing: ~5 minutes

2. **Record the money-path video**
   - Open screen recorder (OBS, QuickTime, or built-in)
   - Set resolution: 1920×1080 or 1280×720 (readable text at typical embed sizes)
   - Perform the four scenes in order (upload → ask → quiz → review), speaking naturally about each step
   - Target: one continuous take, ≤90 seconds
   - Save as `.mp4` or `.webm`

3. **Encode video as GIF** (optional; helps GitHub + READMEs render inline)
   - If recording as video, convert to GIF:
     ```bash
     ffmpeg -i demo.mp4 -vf fps=10,scale=1280:-1 -loop 0 demo.gif
     ```
   - Target size: <10 MB (readable at standard embed width ~800px)
   - Save to `docs/media/demo.gif`

4. **Capture scene stills**
   - After the video, take individual static screenshots for scenes 1, 2, and 4:
     - **Library screenshot**: Show the list of uploaded books (scene 1 state)
     - **Ask screenshot**: Show the Q&A panel with question, answer, and visible citations (scene 2 result)
     - **Review screenshot**: Show the card review interface with the card, passage context, and rating buttons (scene 4 state)
   - Save as `PNG` format for lossless quality:
     - `docs/media/screenshot-library.png`
     - `docs/media/screenshot-ask.png`
     - `docs/media/screenshot-review.png`

## Asset Files

Place completed media in `docs/media/`:

```
docs/media/
├── README.md                    (this file)
├── demo.gif                     (or .mp4/.webm if GIF conversion not used)
├── screenshot-library.png
├── screenshot-ask.png
└── screenshot-review.png
```

**File naming:** lowercase, hyphen-separated, no spaces. Filenames are referenced in the main README
as `docs/media/<filename>`.

**Not committed:** `.gitignore` excludes `*.gif`, `*.png`, and video files. Commit this guide only;
media is stored separately (e.g., in a release or external CDN after QA).

## Verification

Before submitting the demo for review:

1. **Video flow**: Play the GIF/video end-to-end; confirm it's <90 seconds, audio is clear, and all four
   scenes are present.
2. **Screenshot clarity**: Verify each `.png` is readable (text size >10px on typical screen), shows
   the intended UI state, and the filename matches the asset slot name.
3. **Asset slot mapping**: Confirm filenames match the table above exactly.

## Embedding in README

The main README (Phase E) will reference these assets as:

```markdown
## Demo

<video or GIF embed here>
![Library Screenshot](docs/media/screenshot-library.png)
![Ask Screenshot](docs/media/screenshot-ask.png)
![Review Screenshot](docs/media/screenshot-review.png)
```

If any asset slot is missing, the README link will break at review time. No other tooling is required;
the README will handle markdown/HTML embedding.
