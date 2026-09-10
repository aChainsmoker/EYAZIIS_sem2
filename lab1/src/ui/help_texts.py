HELP_TEXT = """### Text Corpus Search System

This system indexes a corpus of English text documents, lets you search them using the BM25 ranking model (with optional AI reranking), and provides tools to assess and measure search quality.

Below is a guide to each section of the application.

---

### 1. Search

**What you can do:** enter an English query and see the most relevant documents, each with a highlighted snippet.

**How to use it:**
1. Type your query into the **Enter query** field.
2. Optionally adjust the scoring parameters:
   - **Term Frequency Saturation (k1)** — controls how much term frequency affects the score (default 1.2).
   - **Length Normalization (b)** — controls how much document length is penalized (default 0.75).
3. Check **Use Embedding Reranking** to apply semantic reranking with sentence-transformers (`all-MiniLM-L6-v2`) on top of BM25.
4. The system returns the top-20 documents. Expand each result to see:
   - a snippet with matched words highlighted,
   - the **BM25** score (and **Cosine** / **Final** score if reranking is enabled),
   - the path to the source **File**.

---

### 2. Administration

**What you can do:** view database statistics about the indexed corpus.

**How to use it:**
- The page shows three metrics: **Total Documents**, **Average Document Length**, and **Total Amount of Terms**.
- No actions are required here — documents are indexed automatically from `data/incoming/` when the application starts, and new files are picked up as they are added.

---

### 3. Quality Assessment

This section lets you build a ground truth by judging which documents are relevant to real queries, and then compute quality metrics from those judgments. Queries and judgments are stored in PostgreSQL.

**Step 1 — Add Query to Assess**
- Type the real query text (as a user would search) into the **Enter Query** field and click **Add Query**.
- The query is saved to the database and will appear in the dropdown above.

**Step 2 — Query Relevancy Assessment**
- Select one of your queries from the **Choose a query** dropdown.
- The system shows the top-50 retrieved documents for that query.
- For each document, click **Yes** if it is relevant to the query, or **No** if it is not.
- The status is shown next to each document: `Relevant ✓`, `Irrelevant ✗`, or `Not Assessed`.
- Judgments overwrite previous ones, so you can change your mind at any time.
- Use **Delete Query** to remove the selected query together with all of its judgments.

**Step 3 — Metrics Assessment**
- Click **Assess metrics** to calculate evaluation metrics from all judged queries.
- The system displays:
  - **Average Metrics** table — Precision@k, Recall@k, and F1@k for k = 5, 10, 20, ... up to the total number of documents,
  - **MAP (Mean Average Precision)** — the average of the per-query Average Precision values,
  - **Per-Query AP** table — Average Precision for each query and the number of relevant documents,
  - **Precision-Recall Curve** plot,
  - **Precision@k and Recall@k** plot.

> Note: metrics are only meaningful for queries that have at least one judgment. The more documents you assess for each query, the more accurate the metrics become.

---

### How it works

1. Documents from `data/incoming/` are automatically indexed into PostgreSQL.
2. The NLP pipeline processes text: lowercase → remove punctuation → tokenize → remove stopwords → lemmatize.
3. Search uses the Okapi BM25 model for ranking.
4. Optional AI reranking uses sentence-transformers (`all-MiniLM-L6-v2`) for semantic similarity."""