# TheBrain API Reference (for Memory Tree sync)

## Authentication
```
Authorization: Bearer <THEBRAIN_API_KEY>
```

## List brains
```
GET https://api.bra.in/brains
→ [{"id": "4a1ef771-4108-48ed-9ee9-2630c02f930d", "name": "vincent", "homeThoughtId": "940b92ed-..."}]
```
**IMPORTANT:** Brain IDs are FULL UUIDs. Short prefixes (e.g. "4a1ef771") return 404.

## Create thought
```
POST https://api.bra.in/thoughts/{brainId}
Content-Type: application/json

{"name": "Thought Name", "kind": 1, "acType": 0, "sourceThoughtId": "<parentThoughtId>", "relation": 1}
```
- `kind`: 1 = normal thought
- `acType`: 0 = default
- `relation`: 1 = child, 3 = jump link
- `sourceThoughtId`: parent thought to link from (use homeThoughtId for top-level)

**WRONG endpoint:** `/brains/{brainId}/thoughts` → 404
**RIGHT endpoint:** `/thoughts/{brainId}`

## Add note to thought
```
POST https://api.bra.in/thoughts/{brainId}/{thoughtId}/notes
Content-Type: application/json

{"markdown": "# Note content in markdown"}
```

## Create link between thoughts
```
POST https://api.bra.in/links/{brainId}
Content-Type: application/json

{"thoughtIdA": "...", "thoughtIdB": "...", "relation": 3}
```
- `relation`: 1 = parent-child, 2 = sibling (jump), 3 = jump link

## Rate limits
~50 requests/minute observed. Use 2.0s delay between calls in batch operations.
The populate_brain_p*.py scripts at ~/Desktop/website/ use this pattern.
