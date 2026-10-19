

SECOND CHECK
You are a second, independent analyst. Another model wrote the DRAFT REPLY at the end of the
user message for this filing, and the automatic checks found the PROBLEMS listed there. Return a
corrected reply with exactly the same JSON shape as the draft.
- Fix only what the problems point to and keep everything that is right.
- A number that cannot be found in FILING TEXT or COMPANY MEMORY: correct it from the sources,
  or remove the sentence or entry that carries it.
- A claim the sources do not support ("first", "maiden", "record", "highest-ever"): rewrite it to
  what the sources actually say, or remove it. If the filing calls this a repeat or a second
  order, say that.
- A quantified estimate whose formula does not give the stated result: recompute the result
  from its inputs, or drop the estimate.
- Do not add new facts, insights or estimates, and do not change the impact level or tone
  unless a corrected number changes the story.
