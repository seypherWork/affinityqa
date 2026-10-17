# Open film discovery

Status: bounded real local capture acceptance, 17 October 2026. Hosted rollout
and a real hosted-browser journey are not established for this protocol yet.

John Wick (2014) and Scary Movie (2000) each produced twenty actual Qloo candidates
and five eligible choices with individual Groq interpretations. Their pools had
no overlap: forty distinct movie identities. Total fresh work: four Qloo requests
and two Groq sends, with no retry of failed or unknown sent work. The conservative
local minute-token admission deferred Scary Movie's model operation before any
send; a separately approved continuation reconstructed its two accepted Qloo
observations and completed the original pending Groq operation. Original files,
partial evidence and accepted operations were preserved. Both final orders equal
their Qloo baselines; neither a model improvement nor human satisfaction is proved.

The new route starts with one favorite film instead of combining a musician and
an optional film in the older twenty-film comparison. A new Qloo query retrieves
up to twenty real movie candidates for each confirmed film. Groq ranks that
specific pool and returns five eligible choices with short interpretations.

## Visitor journey

1. Open **START WITH A FILM** and restore or open the ownership session.
2. Enter a title and an optional direction, such as the tone or pacing you want.
   Review the plan; preparing it makes no provider requests.
3. Select **FIND MY FILM**. One typed Qloo search returns titles and release years.
   Choose the exact identity; no film is selected automatically.
4. Confirm once. One Qloo Insights request retrieves the candidate pool and one
   Groq request ranks it. Inspect the five choices, baseline, source pool and
   explanations. Download the selected verification.
5. Restore the same session after reloading. A saved case reads retained evidence;
   it does not run the providers again.

The plan permits at most **two Qloo requests and one Groq request**. Groq remains
on its existing free plan, with the existing shared durable quota scheduler.
There is no guaranteed instant response or unlimited free provider capacity.

## Input and result contract

- Request8 / `qloo-open-movie-discovery-v1`, a separate protocol from earlier cases.
- Confirmed canonical movie identity, provider title and integer release year.
- Optional direction up to 600 characters; hard exclusions up to fifteen UUIDs.
- Typed Insights query seeded by that movie, with no global
  `filter.results.entities` whitelist. Retrieval is broad; each saved ranking
  still has a bounded pool of five to twenty actual movies.
- The confirmed seed and exclusions cannot enter the delivered five. Missing
  identities, years, insufficient candidates and invalid model output stop the
  case; they do not cause a fallback to the old catalog or invented titles.
- One structured ranking and one explanation for each delivered film. Explanations
  are unverified model interpretations, potentially using model knowledge. They
  are not facts or causes certified by Qloo, a satisfaction score or human evidence.
- Qloo's baseline receives the movie identity, whereas the model also receives
  the optional direction. With such text present, their information differs;
  ranking changes do not establish improvement over an equal-information baseline.

The UI is advertised only by the new backend capability. Earlier source/server
combinations keep their existing workflow. The musical-comparison route, recorded
repairs and old cases retain their original schemas and meaning.

## Checks and boundaries

The offline suites test the actual capture, verifier, owned HTTP API, shared quota
scheduler and persistence using explicitly synthetic providers. These tests cannot
establish future Qloo responses, future Groq compliance or personal recommendation
quality. The two real captures above provide separate bounded compatibility
evidence, not a person's assessment. No simulated profile counts as a human
participant, and no new preference-quality score is claimed here.
