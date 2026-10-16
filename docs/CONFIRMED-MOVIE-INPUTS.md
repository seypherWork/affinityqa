# Confirm a film you already like

When the server advertises confirmed movie search, the new-case form offers **ADD A FILM YOU ALREADY LIKE**. You can enter up to two movie titles total across profiles A and B. They may be films outside the fixed twenty-film recommendation catalog.

1. Enter the musical interests and optionally add a film title to either profile. Typing makes no provider request.
2. Review the plan and its declared request bound. Execute **FIND ARTISTS & FILMS** to search the declared musicians and movies.
3. Select each artist and each exact film title/year from the saved Qloo candidates. Nothing is selected automatically. A film without a usable provider-backed year cannot be confirmed. If the search fails, its evidence is retained; no title, identifier or year is invented.
4. Confirm the reviewed choices. The movie IDs condition the actual Qloo Insights queries. The agent receives their confirmed metadata as positive taste inputs. The reference catalog remains twenty films; each profile receives five eligible discoveries. A known favorite in that catalog is excluded from discovery and delivery.
5. Inspect the confirmed film inputs and download the selected verification. Restoring the same session reads the saved choices and results without starting another case.

With n movie queries, a case allows at most `4+n` Qloo HTTP attempts (two musician searches, n film searches and two Insights queries), so n<=2 gives at most six. Groq remains the configured provider and the maximum is still two model decisions. The existing free-plan quota scheduler remains in force; capacity can require a wait. No provider upgrade, quota reset or automatic failed/unknown-send retry is included.

Selecting a different remake requires choosing its returned year explicitly. All selections are bound to the case owner, reviewed plan, original server receipt, profile and query slot. Posted names and years are not accepted as proof. Duplicate favorite IDs, conflicts with exclusions and more than five combined favorites within one profile are rejected. The same favorite can legitimately be used by both profiles.

Existing cases retain their original protocol and evidence. Requests with no new movie queries keep the old discovery route. A previously reviewed, unexecuted plan whose source hashes differ is preserved for inspection and requires a newly reviewed plan before dispatch; it is never silently rewritten to the new version.

## Evidence boundary

Confirmed identities appearing in both recorded Qloo inputs and actual agent inputs demonstrate conditioning. A changed ranking is neither required nor promised. These inputs are not independent human evaluations, and this feature does not certify satisfaction or general cultural quality. Any held-out ratings used in a separate study remain private and outside recommendation inputs.

The added protocol is `cinema-confirmed-discovery-v4`, request schema6. Older requests2–5 and their sealed core source files remain unchanged. Offline tests explicitly identify synthetic providers; a live integration claim requires a separately recorded real-provider acceptance run.
