# Case Study 4 -- product URLs (Team 12)

Paste these into the class Google Sheet, "Case Study 4" tab, Team 12 row.

| Column | URL | Status |
|---|---|---|
| GCP product link | https://genre-api-pzputmgawa-uc.a.run.app | Verified end to end |
| Azure product link | https://genre-api.politehill-0ba96f06.westus2.azurecontainerapps.io | Verified end to end |
| AWS product link | _not deployed_ | Blocked, see CS4_STATUS.md |

Verified = Gradio UI loads, and a real request with an MP3 returned
genre `blues` (confidence 0.82), an LLM-written visual prompt, and an image.
Both services scale to zero, so the first request after idle takes longer.
