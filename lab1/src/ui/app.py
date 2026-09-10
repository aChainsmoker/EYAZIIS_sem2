import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import streamlit as st
import pandas as pd

from src.db import repository as repo
from src.search.bm25 import bm25_search
from src.search.rerank import search_with_rerank
from src.search.snippet import generate_snippet
from src.nlp.pipeline import preprocess
from src.indexer.watcher import index_existing_files, backfill_embeddings
from src.metrics.evaluation import evaluate_from_db
from src.charts.plots import plot_11point_pr, plot_precision_recall_at_k
from src.storage import s3
from src.storage.reader import get_document_text
from src.ui.help_texts import HELP_TEXT

st.set_page_config(page_title="Text Corpus Search", layout="wide")

if "db_initialized" not in st.session_state:
    if repo.init_db():
        index_existing_files()
    backfill_embeddings()
    st.session_state.db_initialized = True


def search_page():
    st.title("Search")
    query = st.text_input("Enter query:")
    k1 = st.slider("Term Frequency Saturation", 0.0, 3.0, 1.2, 0.1)
    b = st.slider("Length Normalization", 0.0, 1.5, 0.75, 0.05)
    use_rerank = st.checkbox("Use Embedding Reranking", value=False)

    if query:
        with st.spinner("Searching..."):
            if use_rerank:
                results = search_with_rerank(query, k1=k1, b=b, top_n=20)
            else:
                results = bm25_search(query, k1=k1, b=b, limit=20)

        if not results:
            st.info("No results found.")
        else:
            st.write(f"Found **{len(results)}** results:")
            query_terms = preprocess(query)
            for r in results:
                doc_text = get_document_text(r["doc_id"])
                positions = r.get("positions", [])
                snippet = ""
                if doc_text:
                    snippet = generate_snippet(doc_text, positions, query_terms)

                display_score = r.get("final_score", r["score"]) if use_rerank else r["score"]
                with st.expander(f"**{r['title']}** (Score: {display_score})"):
                    st.markdown(snippet, unsafe_allow_html=True)
                    if use_rerank and "cosine_score" in r:
                        st.write(f"BM25: {r['score']} | Cosine: {r['cosine_score']} | Final: {r['final_score']}")
                    key = r.get("s3_original_key") or r.get("s3_key")
                    if key:
                        doc_url = s3.presigned_url(key)
                        st.markdown(f"Document: [{doc_url}]({doc_url})")
                    else:
                        st.write(f"File: `{r['file_path']}`")


def administration_page():
    st.title("Administration")
    doc_count = repo.count_documents()
    term_count = repo.count_terms()

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Documents", doc_count)
    with col2:
        stats = repo.get_collection_stats()
        st.metric("Avg Doc Length", f"{stats[1]:.1f}" if stats else "0.0")
    with col3:
        st.metric("Total amount of terms", term_count)


def quality_assessment_page():
    st.title("Quality Assessment")

    st.subheader("1. Add query to assess")
    new_query = st.text_input("Enter Query:")
    if st.button("Add Query"):
        if new_query.strip():
            repo.add_evaluation_query(new_query.strip())
            st.success("Query is added.")
            st.rerun()
        else:
            st.warning("Enter query text")

    st.divider()
    st.subheader("2. Query Relevancy Assessment")

    eval_queries = repo.get_all_evaluation_queries()

    if not eval_queries:
        st.info("No queries. Add one!")
    else:
        options = {f"#{q.id}: {q.query_text}": q.id for q in eval_queries}
        selected_label = st.selectbox("Choose a query:", list(options.keys()))
        selected_query = options[selected_label]
        selected_query_text = selected_label.split(": ", 1)[1]

        doc_rels = repo.get_judgments(selected_query)
        if doc_rels:
            st.write("Documents assessed:", len(doc_rels))

        results = bm25_search(selected_query_text, limit=50)

        for r in results:
            doc_id = r["doc_id"]
            title = r["title"]
            current = doc_rels.get(doc_id)
            c1, c2, c3 = st.columns([3, 1, 1])
            with c1:
                st.write(f"**{title}** (score: {r['score']})")
            with c2:
                if current == True:
                    st.write(":green[Relevant ✓]")
                elif current == False:
                    st.write(":red[Irrelevant ✗]")
                else:
                    st.write("Not Assessed")
            with c3:
                if st.button("Yes", key=f"yes-{selected_query}-{doc_id}"):
                    repo.upsert_judgment(selected_query, doc_id, True)
                    st.rerun()
                if st.button("No", key=f"no-{selected_query}-{doc_id}"):
                    repo.upsert_judgment(selected_query, doc_id, False)
                    st.rerun()

        if st.button("Delete Query"):
            repo.delete_evaluation_query(selected_query)
            st.success("Query is deleted.")
            st.rerun()

    st.divider()
    st.subheader("3. Metrics assessment")

    if st.button("Assess metrics"):
        if not eval_queries:
            st.warning("No queries to assess.")
        else:
            metrics = evaluate_from_db()
            k_values = sorted(metrics["avg"]["precision"].keys())

            st.subheader("Average Metrics")
            avg_data = []
            for k in k_values:
                avg_data.append({
                    "k": k,
                    "Precision@k": round(metrics["avg"]["precision"][k], 4),
                    "Recall@k": round(metrics["avg"]["recall"][k], 4),
                    "F1@k": round(metrics["avg"]["f1"][k], 4),
                })
            st.table(pd.DataFrame(avg_data))
            st.write(f"**MAP (Mean Average Precision):** {metrics['avg']['map']:.4f}")

            st.subheader("Per-Query AP")
            per_query_data = []
            for qid, qm in metrics["per_query"].items():
                per_query_data.append({
                    "Query": qid,
                    "AP": round(qm["map"], 4),
                    "Relevant docs": qm["total_relevant"],
                })
            st.table(pd.DataFrame(per_query_data))

            st.subheader("Precision-Recall Curve")
            pr_img = plot_11point_pr(metrics["pr_curves"])
            st.image(f"data:image/png;base64,{pr_img}")

            st.subheader("Precision@k and Recall@k")
            pr_k_img = plot_precision_recall_at_k(metrics["avg"])
            st.image(f"data:image/png;base64,{pr_k_img}")


def help_page():
    st.title("Help")
    st.markdown(HELP_TEXT)


pg = st.navigation({
    "Navigation": [
        st.Page(search_page, title="Search", url_path="search"),
        st.Page(administration_page, title="Administration", url_path="administration"),
        st.Page(quality_assessment_page, title="Quality Assessment", url_path="quality"),
        st.Page(help_page, title="Help", url_path="help", default=True),
    ],
})
pg.run()