# ADR-0029 — Documentation site: MkDocs Material on GitHub Pages at docs.sandboxio.dev

**Status:** Accepted
**Date:** 2026-09-20
**Supersedes:** —
**Related:** [ADR-0010](0010-stable-error-codes.md), [ADR-0026](0026-docs-license-cc-by.md)

## Context

Every exception renders a link to `https://docs.sandboxio.dev/errors/<code>`, and
`Documentation` in the package metadata points at `https://docs.sandboxio.dev`. Neither
resolves: the domain serves nothing. The links ship in the v0.1 wheel, so the site is a
release blocker, not a nicety.

The material to publish already exists as Markdown under `docs/`, generated in part from
`sandboxio.errors` and gated by CI (samples parse, links and anchors resolve). Error-code
pages are semver-covered API ([ADR-0010](0010-stable-error-codes.md)): the URL is part of
the contract, not a rendering detail.

Thirteen relative links pointed outside `docs/` (`../examples/`, `../LICENSE`), which resolve
on GitHub and 404 on a site whose root is `docs/`. Heading anchors were written for
GitHub's slug algorithm, which Python-Markdown's default does not reproduce.

## Decision

We will publish `docs/` with **MkDocs + Material**, built by `mkdocs.yml` at the repository
root and deployed to **GitHub Pages** at **docs.sandboxio.dev** by `.github/workflows/docs.yml`
on every push to `main`.

- `use_directory_urls: true`, so `docs/errors/SBX_E1204.md` is served at `/errors/SBX_E1204`
  and `docs/errors/README.md` at `/errors`. `tests/test_docs_site.py` fails if any code in
  the catalog has no page there.
- `strict: true` with MkDocs link validation on; the build is a CI gate, like the rest of
  the docs gates.
- Heading anchors use `pymdownx.slugs.slugify(case="lower")`, so one anchor works both on
  the site and in the repository view.
- A relative link may not leave `docs/`; `scripts/check_doc_links.py` enforces it and the
  repository is linked by URL instead.
- A published URL is never renamed. A page that has to move leaves an entry in
  `redirect_maps`.
- `docs/README.md` is the site's landing page as well as the directory index: it opens with
  what the library is and where to go, and keeps the contributor material below.
- The site is **not versioned**. One set of URLs, always current.

Not decided here: an API reference generated from docstrings, and whether the landing page
eventually moves to a marketing domain.

## Consequences

The error links in the wheel resolve, and a code that loses its page fails CI rather than
shipping a dead link. The prose stays plain Markdown, readable in the repository, with the
site as a rendering of it rather than a fork of it.

We accept: one more CI gate and a `docs` dependency group; the Pages deployment needs the
repository to be public (or a paid plan); and `/errors/SBX_E1204` costs a redirect to the
trailing-slash form, which GitHub Pages serves automatically.

Versioned docs (`mike`) are ruled out for as long as error URLs are API — moving pages
under `/latest/` would break every link already shipped in a released wheel.

MkDocs 2.0 is announced as a breaking rewrite with no plugin system; the `docs` group is
therefore pinned below it, and a fork such as ProperDocs is the fallback if Material stops
tracking upstream. That choice, if forced, is a new ADR.
