Some items failed the store's checks. Translate only these again, per the system prompt, fixing each problem;
return the same schema with these ids only. Problems: missing (no entry for this id); duplicate id; empty; korean
left; numbers changed (keep every listed number as written); codes lost (keep the listed Latin codes); too long
(shorten to the limit, keep numbers and codes; a title loses its least important facts first, from the end: what
it is made of, colours, the list of clubs, who it suits ("for beginners"), a second name for the same thing; it
keeps the brand, the model, the year, who it is for, what it is and the number of pieces); values not distinct (two values of one option became the same
English); not json / wrong shape (return exactly {"items":[{"id":"1","en":"..."}]}).
