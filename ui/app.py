"""Streamlit front-end for the Civil Code Q&A API.   streamlit run ui/app.py"""

import os

import httpx
import streamlit as st

API = os.environ.get("PRODML_API_URL", "http://localhost:8080")
st.set_page_config(page_title="القانون المدني المصري", page_icon="⚖️")
st.title("⚖️ القانون المدني المصري — اسأل")
st.caption("Answers are grounded in article text only. General information, not legal advice.")
api = st.sidebar.text_input("API URL", API)
q = st.text_area("سؤالك / Your question", height=90)
if st.button("اسأل / Ask", type="primary", disabled=not q.strip()):
    res = httpx.post(f"{api}/ask", json={"question": q}, timeout=120).json()
    st.markdown(res["answer"])
    for s in res.get("source_details", []):
        with st.expander(f"{s['citation']} · {s['chapter']}" + (" · (ملغاة)" if s["is_repealed"] else "")):
            st.markdown(f"<div dir='rtl' style='text-align:right'>{s['text_ar']}</div>", unsafe_allow_html=True)
            st.markdown(f"---\n{s['text_en']}")
    st.caption(f"trace {res.get('trace_id', '')} · {res.get('latency_ms', 0)} ms · flags {res.get('flags') or '-'}")
