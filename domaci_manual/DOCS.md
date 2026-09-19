# Domácí manuál

## Installation

1. **Settings → Add-ons → Add-on store → ⋮ → Repositories** and add
   `https://github.com/hhjcz/domaci-manual-app`.
2. Install **Domácí manuál** from the new repository.
3. Start it once *before* configuring anything. It generates its own SSH key on
   the first start, and the panel shows you the public half.

If that repository is private, Home Assistant cannot add it: the Supervisor
clones app repositories without any credentials. Copy the `domaci_manual`
directory into the root of the `addons` Samba share instead and use **Check for
updates**; it then shows up under **Local add-ons**.

## Giving the app read access to your repository

The app authenticates to GitHub with an SSH key it generates itself. The
private key stays in the app's own data volume; you only ever handle the
public half.

1. Open **Domácí manuál** in the sidebar. The page shows a public key starting
   with `ssh-ed25519`. Copy it.
2. On GitHub, open your documentation repository →
   **Settings → Deploy keys → Add deploy key**.
3. Title it something like `Home Assistant — Domácí manuál`, paste the key, and
   leave **Allow write access** unchecked.
4. Back in Home Assistant, set the `repository` option to the repository's SSH
   URL and restart the app.

Deploy keys are per-repository. A key added to a different repository, or to
your GitHub account as a personal SSH key, will not work.

You do **not** need a personal access token.

## Configuration

```yaml
repository: git@github.com:you/domaci-manual.git
branch: main
docs_subdir: ""
exclude: []
sync_interval: 15
site_name: Domácí manuál
language: en
strict_host_key_checking: true
extra_known_hosts: []
deploy_key: ""
log_level: info
```

| Option | Description |
| ------ | ----------- |
| `repository` | SSH URL of the documentation repository. An HTTPS URL works for a public repository. |
| `branch` | Branch to render. |
| `docs_subdir` | Subdirectory inside the repository holding the Markdown. Empty means the repository root. |
| `exclude` | Files and folders to leave out of the site, as gitignore-style patterns. |
| `sync_interval` | Minutes between checks for new commits. The site is rebuilt only when the branch actually moved. |
| `site_name` | Title shown at the top of the site. |
| `language` | Interface language of the theme, for example `en` or `cs`. Your content is not translated. |
| `strict_host_key_checking` | Verify the Git host's SSH key. Keep this on for GitHub. |
| `extra_known_hosts` | Host keys for a self-hosted Git server, one `ssh-keyscan` line each. |
| `deploy_key` | An OpenSSH private key to use instead of the generated one. Normally left empty. |
| `log_level` | `debug`, `info`, `warning` or `error`. |

### Using your own key instead

If you already manage deploy keys elsewhere, you can supply the private key in
either of two ways. Both must be an **unencrypted** OpenSSH key.

- Put the key file in the app's config directory as
  `/addon_configs/local_domaci_manual/deploy_key` (reachable with the Samba,
  Studio Code Server or Terminal & SSH add-ons). This is preferred: the key
  never appears in the add-on options.
- Or paste it into the `deploy_key` option using the YAML editor.

A supplied key takes precedence over the generated one.

## How your repository should look

Any Markdown tree works. For example:

```text
README.md
heating/heat-pump.md
water/main-shutoff.md
electricity/panel.md
network/network.md
```

- Navigation is built automatically from the directory tree.
- A page's title comes from its first `#` heading, otherwise from its filename.
- `README.md` (or `index.md`) becomes the landing page of its directory.
- Directories and files starting with `.` are ignored, so an `.obsidian`
  folder is left out.
- Images and other files next to your Markdown are published alongside it.

### Hiding pages

Use `exclude` to keep parts of the repository out of the published site:

```yaml
exclude:
  - drafts/
  - "*.todo.md"
  - private/notes.md
```

Patterns are gitignore-style and relative to the documentation root. An
excluded page is not published at all, so it cannot be opened by URL and does
not appear in search — it is not merely hidden from the menu. Start a pattern
with `!` to re-include something a previous pattern matched.

Files and folders whose name starts with a dot, such as `.obsidian`, are always
skipped and need no pattern.

Do not exclude the root `README.md`: it is the site's front page, and the app
will refuse to publish a site without one.

## Updating the documentation

Push to the configured branch. The app notices within `sync_interval` minutes
and rebuilds. To pull immediately, restart the app or press **Sync now** on the
status page.

## Troubleshooting

The app's panel shows the current state, the public deploy key and the exact
error when something fails. Full detail is in **Settings → Add-ons → Domácí
manuál → Log**.

| Symptom | Cause |
| ------- | ----- |
| `Permission denied (publickey)` | The public key is not registered as a deploy key on *this* repository. |
| `Repository not found` | Wrong URL, or the deploy key belongs to another repository. |
| `Host key verification failed` | Non-GitHub host; add its key to `extra_known_hosts`. |
| `Branch ... does not exist on the remote` | Wrong `branch`. |
| `No Markdown files found` | Wrong `docs_subdir`, or an empty repository. |
| `built without a landing page` | An `exclude` pattern matches the root `README.md`. |

If a sync fails after the site has been built once, the app keeps serving the
last good version and reports the failure in the log.

The same holds after a restart with no working internet, which is exactly the
situation a power cut creates: the app renders the copy of the repository it
already has in `/data` and serves the manual as usual, while the log explains
that the remote could not be reached. It catches up on its own once the network
is back. Only a first start — before anything has ever been cloned — has
nothing to show.

## Security

- Ingress only. No port is published on your network; the site is reachable
  only through the authenticated Home Assistant frontend.
- The app has no access to the Home Assistant API, your configuration, or your
  devices.
- Access to GitHub is read-only by design and the app never pushes.
- The private key lives in the app's data volume and is included in Home
  Assistant backups. Use an encrypted backup if that matters to you; if a
  backup leaks, delete the deploy key on GitHub and restart the app to generate
  a new one.
