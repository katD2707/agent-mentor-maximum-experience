# Third-party notices

Mentor itself is not covered by the licences below, except where a file says so.

## DeepTutor (vendored code)

- Source: https://github.com/HKUDS/DeepTutor, release v1.7.2, commit `60fb3bdfddb30b7740c7ce3bd9b28d908f2af6db`
- Licence: Apache License 2.0. Copyright (c) HKUDS and the DeepTutor authors.
- Where: `services/gateway/src/mentor_gateway/research/vendor/deeptutor/` (LICENSE and NOTICE in that folder).
- What: arXiv paper search, knowledge-frontier discovery and the literature pass, modified to use Mentor's model router
  and plain parameters. Each file keeps a provenance header and a "Modified by Mentor" note.

## education-agent-skills (adapted text)

- Source: https://github.com/garethmanning/education-agent-skills by Gareth Manning
- Licence: Creative Commons Attribution-ShareAlike 4.0 International (https://creativecommons.org/licenses/by-sa/4.0/).
- Where: `services/gateway/src/mentor_gateway/planner/skills/` (the eight skill files; see `ATTRIBUTION.md` there).
  These files, and only these, stay under CC BY-SA 4.0.

## Python dependencies added for paper research

| Package | Licence | Use |
|---|---|---|
| arxiv | MIT | arXiv API client (`paper_search_tool.py`) |
| defusedxml | PSF-2.0 | safe parsing of arXiv Atom feeds (`research_primitives.py`) |

arxiv also installs lxml (BSD-3-Clause) and requests (Apache-2.0).
