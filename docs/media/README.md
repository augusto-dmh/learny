# Demo Media: Capture Guide

This guide produces the four assets the main README embeds: one GIF of the money path — upload a book, ask a cited question, generate a quiz, review a spaced-repetition card — and three stills. The assets are **committed** under `docs/media/` so the README renders them from any clone; keep the GIF at or under 10 MB and the stills as PNG.

## Asset slots

| File | Scene | What it must show |
|---|---|---|
| `docs/media/demo.gif` | The whole money path, one take, ≤ 90 s | Upload → cited answer → quiz → review, in that order |
| `docs/media/screenshot-library.png` | Library after upload | The sample book listed as ready |
| `docs/media/screenshot-ask.png` | A cited answer in the reader dock | Question, answer, and at least one inline citation resolving to a passage |
| `docs/media/screenshot-review.png` | A review card | The card, its passage context, and the recall rating buttons |

The README embeds exactly the files that exist here: `backend/tests/test_readme_truth.py` fails the suite if the demo section embeds any `docs/media/` file that is missing, or omits one of the four slots above that is present. Commit the four files together with the README change that embeds them.

## Prerequisites

- Docker with the Compose plugin, and `ffmpeg` for the GIF encode (`sudo apt install ffmpeg` on Debian/Ubuntu).
- A screen recorder: `wf-recorder` or `simplescreenrecorder` on Linux, QuickTime on macOS.
- **A funded Anthropic key and an OpenAI key.** The deterministic adapters that CI runs on return extractive snippets, not the product's answers; a demo recorded on them would misrepresent Learny. The containers read provider keys from `secrets/local-ai.env` (git-ignored; the local compose override loads it through `env_file` into `api`, `worker`, and `worker-pdf` — a host-side `backend/.env` is invisible to them). Create it with:

  ```
  LEARNY_GENERATION_PROVIDER=anthropic
  LEARNY_ANTHROPIC_API_KEY=sk-ant-...
  LEARNY_EMBEDDING_PROVIDER=openai
  LEARNY_OPENAI_API_KEY=sk-...
  ```

  Before recording, confirm the stack picked the keys up: the answer must stream token by token and the API log must show an `anthropic` generation call, not the deterministic adapter.

- The public-domain sample book. `make seed-sample` stores and ingests it as the shared sample (the same book every new account sees), so the recording shows real chapters and real citations without any copyrighted text.

## Capture (about twenty minutes)

1. **Bring the stack up with real providers.**

   ```bash
   docker compose up --build -d
   make seed-sample
   ```

   Wait until the sample's ingestion reads *ready* on the library page (`http://localhost:3000/sources`); embedding a full book takes a few minutes on first run.

2. **Register a fresh account** at `http://localhost:3000/register`. A new account opens onto the shared sample and the canned first Ask, which is the sequence the GIF should show.

3. **Record one take at 1280×720**, in this order, without narration:
   - Library: open the sample (or upload your own EPUB and wait for *ready*) — still 1.
   - Reader: ask a question the book answers; wait for the streamed answer with its inline citation; click the citation so the passage highlights — still 2.
   - Quiz: back on the library page, use **Generate quiz deck** on the sample and wait for the deck to be ready.
   - Review: open Review, grade one card — still 3.

4. **Encode the GIF** and check its size:

   ```bash
   ffmpeg -i demo.mp4 -vf "fps=10,scale=1280:-1:flags=lanczos" -loop 0 docs/media/demo.gif
   ls -l docs/media/demo.gif   # must be ≤ 10 MB; lower fps or scale if not
   ```

5. **Take the three stills** as PNG at the moments named above, and save them under the slot names.

6. **Embed and verify.** Replace the pending paragraph in the README's `## Demo` section with:

   ```markdown
   ![Demo: upload, ask, quiz, review](docs/media/demo.gif)

   | Library | Ask | Review |
   |---|---|---|
   | ![Library](docs/media/screenshot-library.png) | ![Ask](docs/media/screenshot-ask.png) | ![Review](docs/media/screenshot-review.png) |
   ```

   Then run `cd backend && uv run pytest tests/test_readme_truth.py -q` — it passes only when every embedded file exists and every present slot is embedded.

## Before committing

- The recording shows no real name, email, or key: register the demo account with a throwaway address and keep the account page out of frame.
- The GIF plays end to end in under 90 seconds and the text is readable at the README's embed width (~800 px).
- Nothing in the take was produced by the deterministic adapters — the answer streams, and the citation resolves to a passage in the book.
