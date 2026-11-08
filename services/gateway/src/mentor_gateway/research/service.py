"""ResearchService: the Nghiên cứu feature (CONTRACTS section 15). One object per app (`app.state.research`), built by
`create_app`; tests replace its edges (`llm`, `transport`, `arxiv_search`, `lit_client`, `frontier`, `fetch_pdf`, ...)."""

from mentor_gateway.research.jobs import JobsMixin
from mentor_gateway.research.overview import OverviewMixin
from mentor_gateway.research.profile_keys import ProfileMixin
from mentor_gateway.research.qa import QaMixin
from mentor_gateway.research.search import SearchMixin


class ResearchService(OverviewMixin, QaMixin, JobsMixin, SearchMixin, ProfileMixin):
    pass
