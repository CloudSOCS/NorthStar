# GitHub setup for `poly`

Use this to keep the same code on both Macs (and back it up in the cloud).

## One-time: create the repo on GitHub

1. Log in at [github.com](https://github.com).
2. Click **+** → **New repository**.
3. Name: `poly` (or `polymarket-poly`).
4. Visibility: **Private** (recommended).
5. Do **not** check “Add a README” (you already have code).
6. Click **Create repository**.

Copy the HTTPS URL, e.g. `https://github.com/YOUR_USERNAME/poly.git`.

## One-time: push from the Mac that has the latest code

```bash
cd ~/Projects/poly
git remote add origin https://github.com/YOUR_USERNAME/poly.git
git branch -M main
git push -u origin main
```

When asked for password: use a **Personal Access Token**, not your GitHub password.

### Create a token (one time)

1. GitHub → **Settings** → **Developer settings** → **Personal access tokens** → **Tokens (classic)**.
2. **Generate new token (classic)**.
3. Note: `poly mac`, scope: check **repo**.
4. Copy the token (starts with `ghp_`).
5. Paste it when `git push` asks for a password. Username = your GitHub username.

macOS may save it in Keychain so you only do this once.

## On your other Mac (clone)

```bash
cd ~/Projects
git clone https://github.com/YOUR_USERNAME/poly.git
cd poly
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
poly --help
```

## Daily sync

**After you change code on Mac A:**

```bash
cd ~/Projects/poly
git add -A
git commit -m "Describe what you changed"
git push
```

**On Mac B:**

```bash
cd ~/Projects/poly
git pull
source .venv/bin/activate
pip install -e ".[dev]"
```

## SSH instead of HTTPS (optional, later)

If you add an SSH key to GitHub, use:

`git@github.com:YOUR_USERNAME/poly.git`

instead of the HTTPS URL.
