Some items failed the store's checks. Translate only these again, per the system prompt, fixing each problem;
return the same schema with these ids only. Problems: missing (no entry for this id); duplicate id; empty; korean
left; numbers changed (keep every listed number as written); codes lost (keep the listed Latin codes); too long
(shorten to the limit, keep numbers and codes); values not distinct (two values of one option became the same
English); not json / wrong shape (return exactly {"items":[{"id":"1","en":"..."}]}).
