# API guide

[Back to Novad](../README.md)

Use [Swagger UI](http://localhost:8000/docs) for the full request/response schemas. Authentication uses a session cookie, not a bearer token. Most application routes require login; there is no public registration route.

| Route | Purpose |
| --- | --- |
| `POST /api/auth/login`, `GET /api/auth/me`, `POST /api/auth/logout` | Create, inspect, and end an authenticated session |
| `POST /api/documents/upload`, `GET /api/documents` | Upload a PDF and list the current user's documents |
| `GET /api/documents/{id}`, `POST /api/documents/{id}/analyze` | Inspect processing status or queue extraction again |
| `POST /api/documents/{id}/ask` | Local Q&A, analysis, or suggestions |
| `POST /api/documents/{id}/summarize`, `/content-review`, `/layout-review` | Summary, text review, or sampled page-image review |
| `GET /api/documents/{id}/download`, `DELETE /api/documents/{id}` | Download or delete a document |
| `GET /api/dashboard/summary` | Aggregate document metrics for the signed-in user |
| `POST /api/tools/compress`, `/word-to-pdf`, `/pdf-to-word` | Queue local conversion or compression jobs |
| `POST /api/tools/redaction/preview`, `/api/tools/jobs/{id}/apply-redaction` | Preview findings and apply confirmed regions |
| `GET /api/tools/jobs`, `GET /api/tools/artifacts` | Tool history, results, and protected artifacts |
| `POST /api/ai/jobs`, `GET /api/ai/jobs/{id}` | Queue and inspect protected-document AI analysis |
| `POST /api/ai/jobs/{id}/cancel`, `DELETE /api/ai/jobs/{id}/remote-file` | Cancel analysis or request provider-file deletion |

<details>
<summary>PowerShell example: authenticate, list documents, and ask a question</summary>

Run this after uploading and processing a PDF through the web console. It prompts for credentials instead of putting a password in shell history.

```powershell
$credential = Get-Credential -UserName admin -Message 'Novad login'
$login = @{
    username = $credential.UserName
    password = $credential.GetNetworkCredential().Password
} | ConvertTo-Json
Invoke-RestMethod http://localhost:8000/api/auth/login -Method Post -ContentType 'application/json' -Body $login -SessionVariable novadSession
$documents = Invoke-RestMethod http://localhost:8000/api/documents -WebSession $novadSession
$documents | Select-Object id, filename, status
$documentId = Read-Host 'Enter the id of a processed PDF'
$question = @{ question = 'What is this document about?'; mode = 'question' } | ConvertTo-Json
Invoke-RestMethod "http://localhost:8000/api/documents/$documentId/ask" -Method Post -ContentType 'application/json' -Body $question -WebSession $novadSession
```

The response includes `answer`, structured `conclusions`, `limitations`, `pages_reviewed`, and `retrieval_method`. An unprocessed document returns HTTP 400 for chat.

</details>
