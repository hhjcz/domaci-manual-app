# Changelog

## 0.3.0

- The manual is now served after a restart with no network. Previously a failed
  sync on startup left nothing to render and the panel showed an error page,
  even though a complete checkout was sitting in `/data` — the worst case being
  a power cut, which reboots the house and takes the internet with it. The app
  now builds from the local checkout and catches up once the remote is
  reachable again.

## 0.2.1

- Wider content area on desktop: the page grid grows from Material's default
  61rem to 72rem, which goes entirely to the reading column.

## 0.2.0

- New `exclude` option: gitignore-style patterns for files and folders to keep
  out of the published site. Excluded pages are neither linkable nor
  searchable.
- A build that would produce no landing page now fails with an explanation
  instead of serving a 404 at the ingress entry point.
- Editing an option that affects the output now rebuilds on the next sync,
  instead of waiting for the next commit in the documentation repository.

## 0.1.0

First release.

- Renders a Git repository of Markdown files as a MkDocs Material site.
- Home Assistant ingress with a sidebar entry, available to non-admin users.
- Read-only Git synchronisation over SSH with a self-generated deploy key.
- Periodic upstream checks, rebuilding only when the repository changed.
- Status page with the public deploy key and actionable error messages.
