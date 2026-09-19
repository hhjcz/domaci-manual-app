# Project conventions

Read this before changing anything. It records the decisions that are easy to
break by accident.

## What this is

A Home Assistant App (formerly "add-on") that renders a private Git repository
of Markdown household documentation as a MkDocs Material site behind Home
Assistant ingress. The documentation lives in a **separate** repository
(`domaci-manual`); this repository is the application only.

Read `README.md` for the architecture and `domaci_manual/DOCS.md` for the
user-facing behaviour.

## Language

Everything is in English: code, comments, docs, commit messages, option
descriptions. The single exception is the product name **Domácí manuál**, which
is what users see in Home Assistant. Internal identifiers stay ASCII
(`domaci_manual`, `domaci-manual`).

## Layout

- `domaci_manual/` is the app directory. Its name matters: the slug in
  `config.yaml` is `domaci_manual`.
- The Python package is at `domaci_manual/src/domaci_manual/` because the
  Supervisor builds with the app directory as the Docker build context. It
  cannot move to the repository root.
- `tests/` is at the root; `pyproject.toml` puts `domaci_manual/src` on
  `pythonpath`.
- `domaci_manual/rootfs/` is copied to `/` in the image. Supervisor's add-on
  scanner deliberately ignores anything under a `rootfs` directory, so never
  put a `config.yaml` there.

## Invariants — breaking these breaks ingress

1. **Never set `site_url` in the generated MkDocs config.** Without it MkDocs
   emits only relative URLs, which is the entire reason the site survives the
   dynamic `/api/hassio_ingress/<token>/` prefix.
2. **Never emit an absolute path in HTML or a theme override.** Use MkDocs'
   `base_url`. `tests/test_site.py` asserts this for the built output.
3. **Any HTTP redirect must be prefixed with `X-Ingress-Path`.** See
   `server.ingress_prefix`. This is the one place the prefix is needed, and
   `tests/test_server.py` covers it.
4. **Do not add `ports:` to `config.yaml`.** Ingress only.
5. **Do not request new permissions** (`hassio_api`, `homeassistant_api`,
   `host_network`, extra `map:` entries) without a concrete need. The security
   table in `README.md` is a promise.
6. **Keep `panel_admin: false`.** Non-admin household members are the audience.

## Git access is read-only

The app must never push, force-push, or otherwise write to the documentation
remote. `gitsync.py` only clones, fetches and resets the *local* tree.
`tests/test_github_e2e.py` asserts that the deploy key cannot push. The app's
credential is a read-only GitHub deploy key; a personal access token is never
required or supported.

## Secrets

Nothing secret goes into the image, the repository, or a test fixture. The
deploy key is generated at runtime into `/data/ssh/`. `/data` is the only
writable location the app uses.

## Failure handling

A failed sync or build must not take down a working site. The coordinator keeps
`status.site_dir` pointing at the last successful generation and records the
failure in `status` and the log. Every user-visible error should carry an
actionable hint — see `Repository._explain` for the pattern, and add a case
there rather than letting raw git output reach the user.

## Code style

- Straightforward Python, standard library first. Current runtime dependencies
  are aiohttp, mkdocs, mkdocs-material, pymdown-extensions — adding another
  needs a reason.
- Comments explain *why*, not *what*. Most functions need none.
- No new abstraction layers, plugin systems or config frameworks. If something
  can be a function, it is a function.
- Subprocesses (`git`, `mkdocs`, `ssh-keygen`) over in-process libraries, for
  crash isolation and exact error text.
- Line length 90, ruff config in `pyproject.toml`.

## Working on this

```bash
make help      # every command
make test      # the full offline suite — run this before finishing
make fixture   # local bare Git repo seeded from sample-docs/
make run       # host-side run against the fixture, http://localhost:8099
make build     # build the app image
make up        # run the built image against the fixture
make change    # push a documentation change to the fixture
```

Tests must not touch the network. Git tests use a bare repository created in a
temporary directory from `sample-docs/`. The only networked test is
`tests/test_github_e2e.py`, which is deselected by default via the `github`
marker.

A plain `docker run` does not validate Home Assistant behaviour. Ingress, the
sidebar panel, the options schema and non-admin access can only be checked in
the devcontainer (`.devcontainer/`, `supervisor_run`, <http://localhost:7123>).

## Versioning and releases

`version` in `domaci_manual/config.yaml` is the single source of truth and must
match `__version__` in `domaci_manual/src/domaci_manual/__init__.py`. Bump both
together and add a `CHANGELOG.md` entry; the Supervisor offers users an update
when `version` changes.

## Planned, not built

`POST /api/chat` — retrieval over the Markdown (SQLite FTS5 first) plus an
OpenAI-compatible LLM, with a chat widget in the Material theme and answers
that link back to the exact page and heading. The seams are
`domaci_manual/src/domaci_manual/api/` and
`domaci_manual/src/domaci_manual/web/overrides/main.html`. Do not start it
without being asked; do not restructure the project "in preparation" for it.
