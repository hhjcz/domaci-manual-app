# Domácí manuál — Home Assistant app

A Home Assistant App (formerly add-on) that turns a private GitHub repository
of Markdown household documentation into a pleasant, searchable, read-only
documentation site inside Home Assistant.

```text
private GitHub Markdown repo
  → read-only git clone/pull (SSH deploy key)
  → MkDocs + Material for MkDocs
  → Home Assistant App
  → Home Assistant Ingress
  → the normal Home Assistant UI, including remote access via Nabu Casa
```

The documentation lives in a **separate** repository (`domaci-manual`). This
repository (`domaci-manual-app`) contains only the application.

---

## Contents

- [Architecture](#architecture)
- [Repository layout](#repository-layout)
- [Configuration](#configuration)
- [GitHub deploy key setup](#github-deploy-key-setup)
- [Local development](#local-development)
- [Testing](#testing)
- [Installing in Home Assistant](#installing-in-home-assistant)
- [Security model](#security-model)
- [Design decisions](#design-decisions)
- [Future: AI assistant](#future-ai-assistant)

---

## Architecture

One container, one long-running Python process, no database and no message
bus. s6-overlay (from the Home Assistant base image) supervises it.

```text
s6-overlay
└── python -m domaci_manual                (single asyncio event loop)
    ├── coordinator.py   sync → build → serve cycle, backoff, status
    │   ├── ssh.py       deploy key + known_hosts in /data/ssh
    │   ├── gitsync.py   `git` subprocess: shallow clone, fetch, hard reset
    │   └── site.py      generates mkdocs.yml, runs `mkdocs build`
    └── server.py        aiohttp on :8099
        ├── /                static site from /data/site/gen-N
        ├── /_app/status     JSON runtime state
        ├── /_app/sync       force a sync
        ├── /_app/health     container health check
        └── /api/...         reserved for the future chat backend
```

**Data flow.** The coordinator wakes on a timer (or when `/_app/sync` is
called), fetches the branch and compares commits. If nothing moved, nothing
else happens. If it moved, the working tree is hard-reset to the remote and
MkDocs builds into a fresh `/data/site/gen-N` directory; only when the build
succeeds does the server start serving it. A failed build or sync therefore
never replaces a working site — the previous generation keeps being served and
the failure is reported in the log and on `/_app/status`.

**Ingress.** Home Assistant proxies the app under a dynamic prefix
(`/api/hassio_ingress/<token>/`) which the Supervisor strips before forwarding,
passing it in the `X-Ingress-Path` header. MkDocs is configured without
`site_url`, so every link and asset reference it emits is relative and survives
any prefix unchanged. The only place the prefix is needed is a redirect — the
trailing-slash redirect for `use_directory_urls` — where `server.py` puts it
back. This is covered by tests.

**Persistence.** `/data` is the app's private volume: the checkout in
`/data/repo`, SSH material in `/data/ssh`, generated `mkdocs.yml` and the built
site. Nothing is written anywhere else.

---

## Repository layout

```text
.devcontainer/          official Home Assistant app devcontainer
.vscode/tasks.json      "Start Home Assistant" and project tasks
brand/                  SVG sources for icon.png / logo.png
domaci_manual/          the app itself (slug: domaci_manual)
├── config.yaml         app manifest: ingress, options, schema, permissions
├── build.yaml          base images per architecture
├── Dockerfile
├── DOCS.md             user documentation (the app's Documentation tab)
├── translations/en.yaml  option labels shown in the Home Assistant UI
├── rootfs/             s6-overlay service + bundled GitHub known_hosts
└── src/domaci_manual/  the Python package
sample-docs/            sample Markdown knowledge base for development
scripts/                development fixtures
tests/                  pytest suite
repository.yaml         makes this repo installable as an app repository
Makefile                every development command
```

The Python package lives inside `domaci_manual/` because the Supervisor builds
with the app directory as the Docker build context.

---

## Configuration

| Option | Type | Default | Meaning |
| ------ | ---- | ------- | ------- |
| `repository` | str | `""` | SSH URL of the documentation repository. HTTPS works for public repositories. |
| `branch` | str | `main` | Branch to render. |
| `docs_subdir` | str? | `""` | Subdirectory holding the Markdown. Empty = repository root. |
| `exclude` | list(str) | `[]` | gitignore-style patterns for files and folders to keep out of the site. |
| `sync_interval` | int 1–10080 | `15` | Minutes between upstream checks. |
| `site_name` | str | `Domácí manuál` | Title of the rendered site. |
| `language` | str | `en` | Material for MkDocs interface language, e.g. `cs`. |
| `strict_host_key_checking` | bool | `true` | Verify the Git host's SSH key. |
| `extra_known_hosts` | list(str) | `[]` | `ssh-keyscan` lines for a non-GitHub host. |
| `deploy_key` | str? | `""` | Own OpenSSH private key instead of the generated one. |
| `log_level` | list | `info` | `debug`, `info`, `warning`, `error`. |

### The documentation repository contract

There is none, beyond "it contains Markdown". The app owns all MkDocs
configuration, the theme and the presentation, so the same repository keeps
working in GitHub, Obsidian or any Markdown reader.

```text
README.md
heating/heat-pump.md
water/main-shutoff.md
electricity/panel.md
network/network.md
```

- Navigation is MkDocs' own automatic navigation, derived from the directory
  tree. No `nav`, no `.pages`, nothing to maintain.
- Page titles come from the first `#` heading, falling back to the filename.
- `README.md` or `index.md` becomes the index of its directory.
- Dot-directories (`.obsidian`, `.github`) are ignored.
- If the repository root has no `README.md` or `index.md`, a small landing page
  is generated so the ingress entry point always resolves.

### Keeping pages out of the site

The `exclude` option takes gitignore-style patterns, relative to the
documentation root:

```yaml
exclude:
  - drafts/
  - "*.todo.md"
  - private/notes.md
  - "!drafts/published.md"
```

An excluded page is left out of the build entirely, so it is not published, not
reachable by URL and not in the search index — unlike hiding it from the
navigation, which would leave the content served. Patterns are passed straight
to MkDocs' own `exclude_docs`, so `!` re-includes and the usual gitignore
matching rules apply.

Excluding the root `README.md` would leave the site with no landing page; the
build refuses to publish that rather than serving a 404 at the ingress entry
point.

`sample-docs/` in this repository is a working example.

---

## GitHub deploy key setup

**The app generates its own key.** On first start it creates an ed25519 key
pair in `/data/ssh/id_ed25519` and shows the public half on its panel and in
its log. Nothing secret is ever baked into the image, typed into the options,
or copied between machines.

1. Install and start the app. Open **Domácí manuál** in the sidebar.
2. Copy the `ssh-ed25519 …` public key it shows.
3. On GitHub: documentation repository → **Settings → Deploy keys → Add deploy
   key**. Paste it and leave **Allow write access** unchecked.
4. Set `repository` to the SSH URL and restart the app.

No personal access token is needed, and none is supported.

GitHub's SSH host keys are baked into the image (from
`https://api.github.com/meta`; refresh with `scripts/update_known_hosts.sh`),
so host key verification works on the very first clone without a
trust-on-first-use window.

### Supplying your own key

Preferred: drop an unencrypted OpenSSH private key at
`/addon_configs/local_domaci_manual/deploy_key`. The app copies it to
`/data/ssh/user_key` with mode `0600` and uses it in preference to the
generated key. Alternatively paste it into the `deploy_key` option. The app
derives the public key with `ssh-keygen -y`, so a passphrase-protected or
malformed key fails immediately with a clear message rather than at clone time.

### Rotating

Delete the deploy key on GitHub, delete `/data/ssh/id_ed25519*` (or uninstall
and reinstall the app), restart, and register the new public key.

---

## Local development

Requirements: Linux, Docker, Python 3.12+, `make`. `make help` lists
everything.

### 1. Fastest loop — run on the host

```bash
make fixture   # create a local bare Git repo seeded from sample-docs/
make run       # http://localhost:8099
```

`make run` creates a virtualenv, points the app at `.dev/docs.git` and serves
the rendered site. In another terminal:

```bash
make change                                 # commit and push a documentation change
curl -X POST http://localhost:8099/_app/sync  # or just wait one minute
curl -s http://localhost:8099/_app/status | jq .
```

### 2. Container loop — the real image

```bash
make build     # docker build of domaci_manual/
make up        # run it with /data and the fixture repo mounted
```

Same URL, same fixture, but exercising the actual Dockerfile, s6-overlay
service and Alpine environment. The container runs as root, as Home Assistant
apps do, so `.dev/data` ends up root-owned on the host; `make clean` knows how
to remove it.

```bash
curl -s -H 'X-Ingress-Path: /api/hassio_ingress/TEST' http://localhost:8099/ | head
curl -sD- -o/dev/null -H 'X-Ingress-Path: /api/hassio_ingress/TEST' \
  http://localhost:8099/heating/heat-pump    # 301 → /api/hassio_ingress/TEST/heating/heat-pump/
```

### 3. Full Home Assistant with real ingress — the devcontainer

A plain `docker run` cannot tell you whether ingress works. For that, use the
official Home Assistant app devcontainer in `.devcontainer/`, which runs a real
Supervisor and Home Assistant.

1. Open the repository in VS Code and **Reopen in Container**
   (image `ghcr.io/home-assistant/devcontainer:6-apps`, privileged,
   docker-in-docker).
2. Run the **Start Home Assistant** task, or in the terminal:
   ```bash
   supervisor_run
   ```
3. Open <http://localhost:7123>, create an account.
4. **Settings → Add-ons → Add-on store**. *Domácí manuál* appears under **Local
   add-ons** — the Supervisor scans the mounted workspace recursively for
   `config.yaml`.
5. Install it, start it, and open it from the sidebar. That URL is a genuine
   ingress URL with a dynamic prefix.
6. To test against the local fixture instead of GitHub, the fixture repository
   is on the same filesystem; set `repository` to
   `file:///mnt/supervisor/apps/local/domaci-manual-app/.dev/docs.git`.

Rebuild after changing the code: **Settings → Add-ons → Domácí manuál →
Rebuild**.

The devcontainer is not needed for day-to-day work — options 1 and 2 are much
faster — but it is the only way to validate ingress, the sidebar panel, the
options schema and the non-admin permission behaviour.

---

## Testing

```bash
make test    # the whole suite; no network access required
```

The suite covers option parsing and validation, SSH key handling, Git
clone/pull/reset against local fixture repositories, MkDocs configuration and
build output, ingress path and redirect behaviour, path traversal, and the full
clone → build → serve → push → rebuild pipeline.

Anything touching Git uses a bare repository created in a temporary directory
from `sample-docs/`, so the tests are fast and offline.

### End-to-end against a real private GitHub repository

`tests/test_github_e2e.py` is the GitHub twin of the local integration test. It
is deselected by default and needs a small private test repository plus a
read-only deploy key registered on it:

```bash
DOMACI_MANUAL_E2E_REPO=git@github.com:you/domaci-manual-test.git \
DOMACI_MANUAL_E2E_DEPLOY_KEY=~/.ssh/domaci_manual_test_deploy \
make e2e-github
```

It asserts that:

1. the app clones the private repository with its read-only deploy key;
2. a change pushed with **your own** GitHub credentials (a separate clone using
   your ssh-agent) reaches the remote;
3. the app detects and pulls it;
4. the rendered HTML changes accordingly;
5. the app's deploy key **cannot** push — the write attempt must be rejected.

Two distinct credentials are involved on purpose: the app's key stays read-only
and is never used to write.

---

## Installing in Home Assistant

### From a public app repository

1. **Settings → Add-ons → Add-on store → ⋮ → Repositories**, add
   `https://github.com/hhjcz/domaci-manual-app`.
2. Install **Domácí manuál**, start it, and follow
   [GitHub deploy key setup](#github-deploy-key-setup).

This route requires the *app* repository to be publicly readable. The
Supervisor clones app repositories with a plain `git clone` and has no way to
authenticate (`supervisor/store/git.py`). Nothing in this repository is
sensitive — the deploy key is generated at runtime into `/data` — so making it
public costs nothing. Your documentation repository stays private either way.

### From a private app repository

Install it as a local app instead. The Supervisor picks up anything under its
local apps directory, which the Samba add-on exposes as the `addons` share.

1. Install and start the **Samba share** add-on (or **Terminal & SSH**, or
   **Studio Code Server**).
2. Copy the `domaci_manual/` directory of this repository to the root of the
   `addons` share, so it lands as `addons/domaci_manual/`:

   ```bash
   # from a clone of this repository, over the Samba share
   rsync -a --delete domaci_manual/ /run/user/1000/gvfs/smb-share:server=homeassistant,share=addons/domaci_manual/

   # or with the Terminal & SSH add-on, on the Home Assistant host
   git clone git@github.com:hhjcz/domaci-manual-app.git /tmp/dm \
     && rsync -a --delete /tmp/dm/domaci_manual/ /addons/domaci_manual/
   ```

3. **Settings → Add-ons → Add-on store → ⋮ → Check for updates**. *Domácí
   manuál* appears under **Local add-ons**.
4. Install and start it, then follow
   [GitHub deploy key setup](#github-deploy-key-setup).

Updating means repeating step 2 and pressing **Rebuild** on the add-on page.
There are no update notifications, which is the real cost of this route.

A third option exists — embedding a personal access token in the repository URL
(`https://<token>@github.com/hhjcz/domaci-manual-app`) — and the Supervisor's
URL validation and clone path do permit it. It is not recommended and not
tested here: the token is stored in plain text in the Supervisor configuration,
shown in the repositories dialog, and included in backups. It also reintroduces
exactly the personal access token this project set out to avoid.

The app has no prebuilt image, so the Supervisor builds it on your device on
first install. That takes a few minutes on a Raspberry Pi. To publish prebuilt
images later, add `image: ghcr.io/hhjcz/{arch}-addon-domaci-manual` to
`domaci_manual/config.yaml` and run the `Publish` workflow.

Supported architectures: `aarch64`, `amd64`.

---

## Security model

| Property | Choice |
| -------- | ------ |
| Network exposure | Ingress only. No `ports:`, nothing published on the LAN. |
| Authentication | Home Assistant's. The app trusts only requests from the Supervisor's ingress address `172.30.32.2`. |
| Who can read it | Any Home Assistant user. `panel_admin: false` makes the sidebar entry available to non-admin users, which is the point of a household manual. |
| Home Assistant access | None. No `hassio_api`, no `homeassistant_api`, no `auth_api`, no discovery. |
| Filesystem access | `/data` (private) plus the app's own config directory, mounted read-only, solely to read an optional user-supplied key. |
| Host access | None: no host network, no devices, no privileged flags, no D-Bus. |
| GitHub access | Read-only. A deploy key on one repository, never used to push. |
| Secrets in the image | None. The key is generated at runtime into `/data`. |
| Host key verification | GitHub's published host keys are bundled; `strict_host_key_checking` defaults to on. |
| Git hygiene | `BatchMode=yes`, `IdentitiesOnly=yes`, `GIT_TERMINAL_PROMPT=0` — the app can never hang on a credential prompt or silently try another key. |
| Untrusted content | Markdown is rendered to static HTML by MkDocs with no raw-HTML sanitiser, so treat write access to the documentation repository as equivalent to being able to put HTML in the panel. Restrict who can push to it. |

`/data` is part of Home Assistant backups, which therefore contain the private
deploy key. Use encrypted backups, or rotate the key if a backup is exposed.

---

## Design decisions

Where the brief left room, the simplest option that preserved the architecture
was taken.

- **The app generates its own deploy key** rather than asking the user to paste
  a private key. It removes the hardest part of the setup, keeps the secret
  inside `/data`, and makes "no secrets in the image" automatic. Supplying your
  own key is still supported.
- **MkDocs' built-in automatic navigation** instead of a generated `nav` or the
  `awesome-pages` plugin. It already does what the brief asks for, with no code
  and no extra dependency.
- **`git` and `mkdocs` as subprocesses**, not libraries. Crash isolation, exact
  error text to show the user, and no in-process logging or global-state
  surprises.
- **No `site_url` in the MkDocs config.** That is what keeps every generated URL
  relative and makes ingress work without rewriting HTML.
- **Google Fonts disabled** (`font: false`). A private household manual should
  not make a third-party request on every page load, and it must work offline.
- **A generation directory per build** (`/data/site/gen-N`) with an atomic
  rename, rather than building in place. A broken build cannot take down a
  working site.
- **Serving the last good site after a later failure**, reporting the error in
  the log and on `/_app/status` rather than replacing the documentation with an
  error page. Stale documentation beats no documentation during a network blip.
- **`sync_interval` in minutes.** The brief specified the name, not the unit;
  minutes suit a household documentation site and are documented in the UI.
- **No AppArmor profile in v1.** The app already runs unprivileged with minimal
  mappings; a subtly wrong profile would cost more than it buys. Worth adding
  later.
- **No prebuilt image in v1.** Local builds keep the release process to a git
  tag; the CI workflow to publish images is included but disabled.

---

## Future: AI assistant

Not implemented. Recorded here so the current structure stays compatible.

```text
Markdown documents in /data/repo
  → chunk by heading (page + anchor kept with each chunk)
  → index: SQLite FTS5 first; embeddings only if retrieval quality demands it
  → small RAG backend at POST /api/chat
  → OpenAI-compatible LLM provider (OpenRouter, OpenAI, Gemini-compatible, Ollama)
  → chat widget embedded in Material for MkDocs
  → answers cite clickable links back to the exact page and heading
```

What already exists for it:

- `domaci_manual/api/` with `setup_routes(app)`, called by `server.py`. Adding
  the endpoint is a new module plus one registration.
- The aiohttp server handles streaming responses and WebSockets, and Home
  Assistant's ingress gateway supports both.
- `domaci_manual/src/domaci_manual/web/overrides/main.html` is already wired in
  as the Material `custom_dir`, which is where the chat widget mounts. It must
  use MkDocs' relative `base_url`, never an absolute path, to survive ingress.
- The coordinator knows exactly when the documentation changed, which is the
  natural trigger for re-indexing.

What will need deciding: where the index lives (`/data/index.sqlite`, rebuilt
on change), how the provider API key is configured (an add-on option, or Home
Assistant secrets), and whether answers are generated per request or cached.

---

## Licence

MIT. See [LICENSE](LICENSE).
