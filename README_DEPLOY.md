# Coloring Book Forge — Deploy to Coolify (coolify.delquro.com)

## What's in this folder
- `server.py` — the backend (HTTP API, DALL-E 3 bridge, prompt serving)
- `Coloring_Book_Forge.html` / `index.html` — single-page frontend (served at /)
- `coloring_prompts_master_36000.json` — 36,000 prompts (30 categories × 4 age tiers × 300)
- `niche_packs/` — 6 niche packs (already folded into the 36k master, kept as source)
- `build_*.py` — generator scripts (run to add more prompts locally; NOT needed on server)
- `output_production/` — folder where forged images are stored (gitignored/can be empty)
- `sample_pages/` — sample PNGs for demo "test forge" mode

## Quick deploy to Coolify
1. **Push this folder to a git repo** (GitHub / GitLab / Gitea) or upload it as a .zip resource.
   - Recommended: create a private repo on GitHub called `coloring-book-forge` and push this folder.
2. In Coolify, click **+ New Resource → Application**.
3. Select your repo (or upload the zip as a "Dockerfile" / "static" resource if you're not using git).
4. **Build Pack:** choose `Python 3.11+` (or `Nixpacks` — it will auto-detect).
5. **Start command:**
   ```
   python3 server.py
   ```
6. **Ports:** set the application port to `8080` (the server binds 0.0.0.0:8080).
7. **Environment variables (only when forging images):**
   - `OPENAI_API_KEY=sk-proj-...` — optional; if not set, the app runs in Test Mode and copies sample_pages.
8. **Persistent storage (critical if you want forged images to survive restarts):**
   - Mount a persistent volume at `/app/output_production` so generated images survive redeploys.
   - Without a volume, forged images are lost every time Coolify rebuilds the container.
9. **Domains:** attach `coloring.delquro.com` (or a subdomain) and enable HTTPS (Coolify does this automatically).
10. **Deploy.** The first deploy takes ~1 minute to install Python deps (no external pip packages required — the server only uses stdlib).

## Verifying the deploy
Once Healthy:
- Open your domain in a browser.
- The top bar should report "36,000 Prompts • 4 Age Levels • DALL-E 3".
- Click any category; cards should load (100/200/300 depending on the batch toggle).
- In 💾 Data & Backups, click "Full Library (gzipped)" — you should get a ~2 MB download.
- In 📘 Build KDP Book, configure a book and download a package; this works entirely in the browser.

## DALL-E 3 production notes
- DALL-E 3 1024×1792 costs $0.08 / image (standard quality). A 50-page book ≈ $4 in API cost + front/back covers.
- Run the book forge from a strong network connection; the runner has retry logic.
- KDP requires 300 DPI images; the output 1024×1792 is ~240 DPI at 8.5×11 — acceptable for KDP, but if you want 300 DPI, edit `server.py` to request `size: "1792x1024"` and rotate, or upscale with a third-party tool. The current 1024×1792 is what KDP coloring books conventionally use.
- API key is stored client-side in localStorage; never committed to the repo. The server does not log keys.

## Adding new niches on the server
1. Build a new pack locally (e.g., `python3 -c "import build_niche_packs; ..."`).
2. Drop the new `.json` file into `niche_packs/` on the server (use Coolify's file manager or push via git).
3. Restart the application in Coolify. The server auto-discovers JSON files in that folder at boot.
4. The new category appears in the sidebar and in 💡 Discover Fresh Niches.

## Useful Coolify settings
- **Resource limits:** 0.25–0.5 CPU and 512 MB RAM is enough for serving the API; bump to 1 GB during bulk forging.
- **Health check:** HTTP `GET /api/meta` on port 8080.
- **Auto-deploy:** enable on push to main so any commit to your repo re-deploys.

## Troubleshooting
- **App loads but cards say "Error loading prompts":** check browser console; usually a CORS or domain issue. Ensure "force HTTPS" is on.
- **Forged images 404 after restart:** you didn't mount a persistent volume at `/app/output_production`.
- **502 after deploy:** check Coolify logs; most common cause is the port isn't set to 8080 or the start command is wrong.
- **"Address already in use":** the server is configured with `allow_reuse_address=True`; if you still hit this, set `PORT=8080` as an env var and ensure no other service is on 8080.
