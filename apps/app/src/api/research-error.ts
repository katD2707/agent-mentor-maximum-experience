// Error of a /api/research call. Its own file so the mock can throw it without importing the client.
export class ResearchError extends Error {
  constructor(
    public status: number,
    /** a `ResearchErrorCode`, or "network" / "unauthorized" / "unknown" */
    public code: string,
    public extra: { job_id?: string; retry_after?: number } = {},
  ) {
    super(code);
    this.name = "ResearchError";
  }
}
