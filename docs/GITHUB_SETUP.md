# GitHub setup for NorthStar

Use this to keep the same code on both Macs (and back it up in the cloud).

The GitHub repo is **https://github.com/CloudSOCS/NorthStar**.

## One-time: create the repo on GitHub

1. Log in at [github.com](https://github.com).
2. Click **+** → **New repository**.
3. Name: `NorthStar`.
4. Visibility: **Private** (recommended).
5. Do **not** check “Add a README” (you already have code).
6. Click **Create repository**.

Copy the HTTPS URL, e.g. `https://github.com/CloudSOCS/NorthStar.git`.

## One-time: push from the Mac that has the latest code

```bash
cd /Volumes/App/NorthStar
git remote add origin https://github.com/CloudSOCS/NorthStar.git
git branch -M main
git push -u origin main
```

When asked for password: use a **Personal Access Token**, not your GitHub password.

### Create a token (one time)

1. GitHub → **Settings** → **Developer settings** → **Personal access tokens** → **Tokens (classic)**.
2. **Generate new token (classic)**.
3. Note: `northstar mac`, scope: check **repo**.
4. Copy the token (starts with `ghp_`).
5. Paste it when `git push` asks for a password. Username = your GitHub username.

macOS may save it in Keychain so you only do this once.

## On your other Mac (clone)

```bash
cd ~/Projects
git clone https://github.com/CloudSOCS/NorthStar.git NorthStar
cd NorthStar
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
northstar --help
```

## Daily sync

**After you change code on Mac A:**

```bash
cd /Volumes/App/NorthStar
git add -A
git commit -m "Describe what you changed"
git push
```

**On Mac B:**

```bash
cd /path/to/NorthStar
git pull
source .venv/bin/activate
pip install -e ".[dev]"
```

## SSH instead of HTTPS (optional, later)

If you add an SSH key to GitHub, use:

`git@github.com:CloudSOCS/NorthStar.git`

instead of the HTTPS URL.
