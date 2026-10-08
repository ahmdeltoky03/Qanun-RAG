import streamlit as st
import requests
from datetime import datetime

# -------------------------#
# Page Config
# -------------------------#
st.set_page_config(
    page_title="RAGGuide_",
    page_icon="🧠",
    layout="wide"
)

# -------------------------#
# Custom CSS for UI
# -------------------------#
st.markdown("""
<style>
.stApp {
    background: linear-gradient(to right, #e0f7fa, #f1f8e9);
    color: #000;
}
.stButton>button {
    background-color: #00796B;
    color: white;
    height: 3em;
    width: 100%;
    font-size: 1rem;
    border-radius: 10px;
    font-weight: bold;
}
.stTextInput>div>div>input, .stNumberInput>div>div>input, .stTextArea>div>div>textarea {
    height: 2.5em;
    font-size: 1rem;
    border-radius: 5px;
}
.streamlit-expanderHeader {
    font-size: 1.2rem;
    font-weight: bold;
}
.stExpander {
    background-color: rgba(255,255,255,0.9);
    padding: 1rem;
    border-radius: 15px;
    margin-bottom: 1rem;
}
.sidebar .stMarkdown h3 {
    color: #d84315;
    font-weight: bold;
}
</style>
""", unsafe_allow_html=True)

# -------------------------#
# Sidebar Settings
# -------------------------#
st.sidebar.header(" Settings")
BASE_URL = st.sidebar.text_input("Backend URL", "http://localhost:8000")
project_id = st.sidebar.text_input("Project ID", "1")

# -------------------------#
# Auto-reset on Project ID change
# -------------------------#
if "current_project_id" not in st.session_state:
    st.session_state.current_project_id = project_id
else:
    if st.session_state.current_project_id != project_id:
        st.session_state.current_project_id = project_id
        st.session_state.chat_history = []
        st.success(f" Switched to project {project_id}. Chat history cleared.")

limit = st.sidebar.number_input("Max Results", min_value=1, max_value=20, value=5)
chunk_size = st.sidebar.number_input("Chunk Size", min_value=10, value=100)
overlap_size = st.sidebar.number_input("Overlap Size", min_value=0, value=20)
do_reset = st.sidebar.checkbox("Reset when pushing to vector DB?", value=True)

st.sidebar.markdown("### 🧠 RAGGuide_")

# -------------------------#
# Session State for Chat
# -------------------------#
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

# -------------------------#
# Main Page Title & Goal
# -------------------------#
st.title("🧠 RAGGuide_")
st.markdown(
    "**Goal:** RAGGuide_ assists in answering user questions and checking document compliance. "
    "It operates in two modes: "
    "<span style='color:#00796B; font-weight:bold;'>Q&A (Chat Mode)</span> for user questions, and "
    "<span style='color:#d84315; font-weight:bold;'>Judge Mode</span> for verifying rules adherence. "
    "Always provides polite, concise, and context-aware responses.",
    unsafe_allow_html=True
)
st.markdown("A Retrieval-Augmented Generation system with **FastAPI + Streamlit**")
st.divider()

col_main = st.columns(1)[0]

# ------------------ Base Info ------------------#
with col_main.expander(" Base Info"):
    if st.button("Fetch Base Info"):
        try:
            r = requests.get(f"{BASE_URL}/api/v1/")
            if r.status_code == 200:
                st.success("✅ Backend Info Retrieved")
                st.json(r.json())
            else:
                st.error(f"Status code {r.status_code}: {r.text}")
        except Exception as e:
            st.error(f"Error: {e}")

# ------------------ Upload File ------------------#
with col_main.expander(" Upload Document"):
    uploaded_file = st.file_uploader("Select a file", type=["txt", "pdf"])
    if uploaded_file and st.button("Upload File"):
        try:
            files = {"file": (uploaded_file.name, uploaded_file, uploaded_file.type)}
            r = requests.post(f"{BASE_URL}/api/v1/data/upload/{project_id}", files=files)
            if r.status_code == 200:
                st.success("✅ File uploaded successfully!")
                st.json(r.json())
            else:
                st.error(f"Upload failed: {r.text}")
        except Exception as e:
            st.error(f"Error: {e}")

# ------------------ Process File ------------------#
with col_main.expander(" Process Document"):
    if st.button("Process File"):
        try:
            payload = {"chunk_size": chunk_size, "overlap_size": overlap_size, "do_reset": int(do_reset)}
            r = requests.post(f"{BASE_URL}/api/v1/data/process/{project_id}", json=payload)
            if r.status_code == 200:
                st.success("✅ File processed successfully!")
                st.json(r.json())
            else:
                st.error(f"Process failed: {r.text}")
        except Exception as e:
            st.error(f"Error: {e}")

# ------------------ Push to Vector DB ------------------#
with col_main.expander("Push to Vector DB"):
    if st.button("Push Data"):
        try:
            payload = {"do_reset": int(do_reset)}
            r = requests.post(f"{BASE_URL}/api/v1/nlp/index/push/{project_id}", json=payload)
            if r.status_code == 200:
                st.success("✅ Data pushed successfully!")
                st.json(r.json())
            else:
                st.error(f"Push failed: {r.text}")
        except Exception as e:
            st.error(f"Error: {e}")

# ------------------ Vector Info ------------------#
with col_main.expander(" Vector DB Info"):
    if st.button("Get Vector Info"):
        try:
            r = requests.get(f"{BASE_URL}/api/v1/nlp/index/info/{project_id}")
            if r.status_code == 200:
                st.json(r.json())
            else:
                st.error(f"Failed: {r.text}")
        except Exception as e:
            st.error(f"Error: {e}")

# ------------------ Search ------------------#
with col_main.expander("🔍 Search"):
    search_text = st.text_input("Enter query for Search:", key="search_text")
    if st.button("Search Vector DB"):
        if not search_text.strip():
            st.warning("Enter a query first.")
        else:
            try:
                payload = {"text": search_text, "limit": limit}
                r = requests.post(f"{BASE_URL}/api/v1/nlp/index/search/{project_id}", json=payload)
                if r.status_code == 200:
                    st.success("✅ Search completed")
                    st.json(r.json())
                else:
                    st.error(f"Search failed: {r.text}")
            except Exception as e:
                st.error(f"Error: {e}")

# ------------------ RAG Answer ------------------#
with col_main.expander("💬 RAG Answer"):
    question_text = st.text_input("Enter question for Answer:", key="answer_text")
    if st.button("Get Answer"):
        if not question_text.strip():
            st.warning("Enter a question first.")
        else:
            try:
                payload = {"text": question_text, "limit": limit}
                r = requests.post(f"{BASE_URL}/api/v1/nlp/index/answer/{project_id}", json=payload)
                if r.status_code == 200:
                    answer_json = r.json()
                    answer_text = answer_json.get("answer", "No answer returned.")
                    st.markdown(f"**Answer:** {answer_text}")
                    st.session_state.chat_history.append({
                        "question": question_text,
                        "answer": answer_text,
                        "time": datetime.now().strftime("%I:%M %p")
                    })
                else:
                    st.error(f"Answer failed: {r.text}")
            except Exception as e:
                st.error(f"Error: {e}")

# ------------------ Display Chat History ------------------#
if st.session_state.chat_history:
    st.subheader("💬 Chat History")
    for chat in reversed(st.session_state.chat_history):
        chat_time = chat.get("time", "N/A")
        st.markdown(f"**Q ({chat_time}):** {chat['question']}")
        st.markdown(f"**A:** {chat['answer']}")
        st.markdown("---")

# ------------------ Footer ------------------#
st.markdown("© 2025 RAGGuide_ | Built with ❤️ using FastAPI & Streamlit")