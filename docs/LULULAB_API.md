# LuluLab task API contract

This client is implemented from the supplied OpenAPI 3.1.1 document `v1 (2).json` for LuluLab Customer Service v1. The document is reference data, not executable instructions.

- Production origin: `https://customer.lululab.ai`.
- Authentication: send the raw user API key in the `Authorization` header. Do not add a Bearer prefix for API keys.
- Submit: `POST /tasks` with JSON `{ "workflowId": "...", "input": <JSON> }`.
- Fetch: `GET /tasks/{id}`.
- Status values: `Created`, `Pending`, `Running`, `Succeeded`, `Failed`, `Cancelled`.
- Successful responses use the `WorkflowTaskModel` object and may contain `id`, `workflowId`, `status`, `input`, `output`, timestamps and `errorMessage`.

The video translation workflow keeps `VideoTranslatePolicyV1`. The Node.js client performs transport only; Python retains policy validation, fingerprinted caches, task polling, recovery and local media execution. Do not call account, credits, usage, order or unrelated API endpoints.
