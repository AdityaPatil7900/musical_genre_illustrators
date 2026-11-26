# Case Study 4 -- product URLs (Team 12)

GCP: https://genre-api-pzputmgawa-uc.a.run.app
Azure: https://genre-api.politehill-0ba96f06.westus2.azurecontainerapps.io
AWS: BLOCKED - see CS4_STATUS.md (support case <CASE NUMBER, fill in when issued>)

Both live URLs were re-verified on 2026-11-26: the Gradio UI loads (HTTP 200)
and an MP3 request returns genre `blues` (0.82). Image generation currently
uses the static fallback on both -- see "Image generation" in CS4_STATUS.md.
Both services scale to zero, so the first request after idle is slower.

## What to paste into the Sheet (Case Study 4 tab, Team 12 row)
- GCP product link:   https://genre-api-pzputmgawa-uc.a.run.app
- Azure product link: https://genre-api.politehill-0ba96f06.westus2.azurecontainerapps.io
- AWS product link:   BLOCKED - SCP denies ECS/ECR/ELB/EC2 (support case <CASE NUMBER>)
