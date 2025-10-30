Developer tip — local embeddings (no server vectorizer)
------------------------------------------------------

If you want a fast local development workflow that avoids installing or configuring Weaviate vectorizer modules (for example `text2vec-transformers`), the application supports computing embeddings locally and pushing vectors with objects directly to Weaviate. This is ideal for laptops or development machines where you prefer the app to handle embeddings.

Key env vars and behavior:

- `USE_LOCAL_EMBEDDINGS=1` or `WEAVIATE_USE_LOCAL=true` — instructs the app to compute embeddings locally using the sentence-transformers paraphrase model in `models/paraphrase-MiniLM-L12-v2` (the project ships a downloader script under `scripts/`).
- `ENABLE_MODULES=none` and `DEFAULT_VECTORIZER_MODULE=none` in `docker-compose.weaviate.yml` — prevents Weaviate from attempting to load `text2vec-transformers` (avoids runtime errors when TRANSFORMERS_* variables are not set).
- `SKIP_WEAVIATE_VECTORIZER_CHECK=1` — (optional) skip the server-side module availability check at startup. When using local embeddings this is not required because the schema is adjusted in-memory to use `vectorizer: "none"` for section/document classes before applying the schema.

Quick sanity checks (Windows cmd.exe):

```cmd
set WEAVIATE_USE_LOCAL=true
set ENABLE_MODULES=none
set DEFAULT_VECTORIZER_MODULE=none
docker compose -f docker-compose.weaviate.yml up -d

# Verify the paraphrase embedding provider loads and returns a vector
python -c "from utils.paraphrase_client import ParaphraseClient; v=ParaphraseClient().text_to_embedding('hello world'); print('len=', len(v))"

# Run the fast Weaviate-related test that creates schema and upserts a CV/section
python -m pytest -q tests/test_weaviate_local.py
```

Notes:
- When local embeddings are enabled the application mutates the loaded `data/weaviate_schema.json` in-memory to set `vectorizer: "none"` for classes that previously requested server-side vectorizers. This lets the app push object vectors directly and keeps the server configuration minimal for development.
- To switch back to server-side vectorization (e.g., production), set `ENABLE_MODULES=text2vec-transformers` and provide the required `TRANSFORMERS_*` environment variables in your compose or environment. See the Weaviate docs for proper transformer inference configuration.
