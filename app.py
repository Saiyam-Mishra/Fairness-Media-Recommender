import sys
import os
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "agent"))

import streamlit as st
from graph import build_graph
from english_to_sql import schema as SQL_SCHEMA
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(
    page_title="Med-Rec · Fairness-Aware Movie Recommender",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&family=DM+Serif+Display&display=swap');

/* ── Reset & base ── */
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
.stApp { background: #0c0f1a; color: #e2e8f0; }
.block-container { padding: 0 !important; max-width: 100% !important; }

/* ── Layout columns ── */
.main-chat { height: 100vh; display: flex; flex-direction: column; }

/* ── Header ── */
.app-header {
    padding: 16px 28px;
    border-bottom: 1px solid rgba(255,255,255,0.07);
    background: rgba(12,15,26,0.95);
    text-align: center;
}
.app-header h1 {
    font-family: 'DM Serif Display', serif;
    font-size: 1.5rem; font-weight: 400;
    color: #f8fafc; margin: 0;
    letter-spacing: -0.02em;
}
.app-header .tagline {
    font-size: 0.76rem; color: #94a3b8; opacity: 1;
    font-weight: 400; margin: 4px 0 0 0;
}

/* ── Chat messages ── */
.chat-scroll {
    flex: 1; overflow-y: auto;
    padding: 24px 0 8px 0;
}
.msg-row { display: flex; margin-bottom: 20px; padding: 0 28px; }
.msg-row.user { justify-content: flex-end; }
.msg-row.assistant { justify-content: flex-start; }

.bubble {
    max-width: 72%;
    padding: 14px 18px;
    border-radius: 18px;
    font-size: 0.92rem;
    line-height: 1.65;
}
.bubble.user {
    background: #1d4ed8;
    color: #f0f6ff;
    border-bottom-right-radius: 4px;
}
.bubble.assistant {
    background: #141929;
    color: #cbd5e1;
    border: 1px solid rgba(255,255,255,0.07);
    border-bottom-left-radius: 4px;
}
.bubble .sender {
    font-size: 0.72rem; font-weight: 600;
    letter-spacing: 0.06em; text-transform: uppercase;
    margin-bottom: 6px; opacity: 0.55;
}

/* ── Input bar ── */
.input-bar {
    padding: 16px 28px 20px;
    border-top: 1px solid rgba(255,255,255,0.07);
    background: rgba(12,15,26,0.98);
}

/* ── Sidebar panels ── */
.panel-title {
    font-size: 0.72rem; font-weight: 600;
    letter-spacing: 0.08em; text-transform: uppercase;
    color: #475569; margin-bottom: 12px;
}
.movie-card {
    background: #141929;
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 12px;
    padding: 14px;
    margin-bottom: 10px;
    transition: border-color 0.2s;
}
.movie-card:hover { border-color: rgba(99,102,241,0.4); }
.movie-title {
    font-size: 0.95rem; font-weight: 600;
    color: #f1f5f9; margin-bottom: 4px;
}
.movie-meta {
    font-size: 0.76rem; color: #64748b;
    margin-bottom: 6px;
}
.movie-genres span {
    display: inline-block;
    background: rgba(99,102,241,0.15);
    color: #818cf8;
    border-radius: 20px;
    padding: 2px 8px;
    font-size: 0.7rem;
    margin: 2px 2px 2px 0;
}
.movie-overview {
    font-size: 0.78rem; color: #94a3b8;
    line-height: 1.5; margin-top: 6px;
    display: -webkit-box;
    -webkit-line-clamp: 3;
    -webkit-box-orient: vertical;
    overflow: hidden;
}
.rating-badge {
    display: inline-block;
    background: rgba(234,179,8,0.15);
    color: #fbbf24;
    border-radius: 6px;
    padding: 2px 7px;
    font-size: 0.75rem;
    font-weight: 600;
}

/* ── Fairness panel ── */
.fairness-label {
    font-size: 0.78rem; color: #94a3b8;
    margin-bottom: 2px;
}
.metric-row {
    display: flex; justify-content: space-between;
    align-items: center;
    padding: 7px 0;
    border-bottom: 1px solid rgba(255,255,255,0.05);
}
.metric-name { font-size: 0.82rem; color: #94a3b8; }
.metric-vals { display: flex; gap: 12px; }
.metric-before { font-size: 0.82rem; color: #f87171; font-variant-numeric: tabular-nums; }
.metric-after  { font-size: 0.82rem; color: #34d399; font-variant-numeric: tabular-nums; }
.bias-badge {
    display: inline-block;
    padding: 3px 10px; border-radius: 20px;
    font-size: 0.72rem; font-weight: 600;
    margin-bottom: 10px;
}
.bias-detected { background: rgba(239,68,68,0.15); color: #f87171; }
.bias-ok { background: rgba(52,211,153,0.15); color: #34d399; }

/* ── Streamlit widget overrides ── */
.stTextArea textarea {
    background: #141929 !important;
    border: 1px solid rgba(255,255,255,0.1) !important;
    border-radius: 12px !important;
    color: #e2e8f0 !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 0.9rem !important;
    resize: none !important;
}
.stTextArea textarea:focus {
    border-color: #4f46e5 !important;
    box-shadow: 0 0 0 2px rgba(79,70,229,0.25) !important;
}
.stButton > button {
    background: #4f46e5 !important;
    color: white !important;
    border: none !important;
    border-radius: 10px !important;
    padding: 10px 22px !important;
    font-size: 0.88rem !important;
    font-weight: 500 !important;
    width: 100% !important;
    transition: background 0.2s !important;
}
.stButton > button:hover { background: #4338ca !important; }
div[data-testid="stSidebar"] {
    background: #0e1220 !important;
    border-right: 1px solid rgba(255,255,255,0.06) !important;
}
</style>
""", unsafe_allow_html=True)

# ── Session state ──────────────────────────────────────────────────────────────
if "graph" not in st.session_state:
    st.session_state.graph = build_graph()

if "agent_state" not in st.session_state:
    st.session_state.agent_state = {
        "messages": [],
        "agent_output": None,
        "route": None,
        "db_schema": SQL_SCHEMA,
        "error": None,
        "query_result": None,
        "vector_search_query": None,
        "vector_embeddings": None,
        "use_vector_search": False,
        "latest_user_question": None,
        "sql_error": None,
        "sql_correction_attempted": False,
        "last_results": None,
        "last_query": None,
        "fairness_report": None,
    }

if "chat_display" not in st.session_state:
    st.session_state.chat_display = []  # list of {role, content} for display only

if "pending_input" not in st.session_state:
    st.session_state.pending_input = None

if "input_counter" not in st.session_state:
    st.session_state.input_counter = 0

# ── Helpers ────────────────────────────────────────────────────────────────────
def render_movie_card(r: dict, rank: int | None = None):
    title    = r.get("title", "Unknown")
    year     = r.get("release_year", "")
    rating   = r.get("vote_average") or r.get("ratings") or r.get("rating")
    genres   = r.get("genres") or []
    overview = r.get("overview", "")

    genre_tags  = "".join(f"<span>{g}</span>" for g in (genres if isinstance(genres, list) else []))
    directors = r.get("director_names") or []
    origin = r.get("origin_countries") or []
    lang = r.get("original_language") or ""

    if directors:
        st.markdown(f"<div style='font-size:0.75rem;color:#94a3b8;margin-top:4px'>🎬 {', '.join(directors)}</div>",
                    unsafe_allow_html=True)
    if origin:
        st.markdown(f"<div style='font-size:0.75rem;color:#94a3b8'>🌍 {', '.join(origin)} · {lang.upper()}</div>",
                    unsafe_allow_html=True)
    rating_html = f"<span class='rating-badge'>★ {float(rating):.1f}</span>" if rating else ""
    rank_prefix = f"#{rank} " if rank else ""
    label       = f"{rank_prefix}{title}  {f'★ {float(rating):.1f}' if rating else ''}  {year}"

    with st.expander(label, expanded=False):
        if genres:
            st.markdown(f"<div class='movie-genres'>{genre_tags}</div>", unsafe_allow_html=True)
        if overview:
            st.markdown(f"<div style='font-size:0.83rem;color:#94a3b8;line-height:1.6;margin-top:8px'>{overview}</div>", unsafe_allow_html=True)
        else:
            st.markdown("<div style='font-size:0.8rem;color:#475569'>No overview available.</div>", unsafe_allow_html=True)


def fmt_metric(val):
    if val is None:
        return "N/A"
    return f"{float(val):+.4f}"


# ── Layout: sidebar (results + fairness) | main (chat) ────────────────────────
sidebar = st.sidebar
main    = st.container()

# ── Sidebar: movie results ─────────────────────────────────────────────────────
with sidebar:
    state = st.session_state.agent_state

    fairness_report = state.get("fairness_report")
    display_results = None
    results_label   = "Recommendations"

    if fairness_report and fairness_report.get("reranked_results"):
        display_results = fairness_report["reranked_results"]
        results_label   = "Re-ranked Results"
    elif state.get("query_result"):
        display_results = state["query_result"]

    if display_results:
        st.markdown(f"<div class='panel-title'>{results_label}</div>", unsafe_allow_html=True)
        for i, r in enumerate(display_results, 1):
            render_movie_card(r, rank=i)

    # ── Fairness metrics panel ─────────────────────────────────────────────────
    if fairness_report:
        st.markdown("---")
        st.markdown("<div class='panel-title'>Fairness Assessment</div>", unsafe_allow_html=True)

        before = fairness_report.get("metrics_before", {})
        after  = fairness_report.get("metrics_after",  {})
        attr   = fairness_report.get("attribute", "")
        p_lbl  = fairness_report.get("protected_label", "Protected group")
        u_lbl  = fairness_report.get("unprotected_label", "Unprotected group")

        spd = before.get("spd")
        has_bias = spd is not None and spd < -0.2
        badge_cls  = "bias-detected" if has_bias else "bias-ok"
        badge_text = "Bias detected · re-ranked" if has_bias else "No significant bias"

        st.markdown(f"""
        <span class='bias-badge {badge_cls}'>{badge_text}</span>
        <div class='fairness-label'>Attribute: <strong style='color:#e2e8f0'>{attr}</strong></div>
        <div class='fairness-label' style='margin-bottom:10px'>
            G⁺ {p_lbl} &nbsp;·&nbsp; G⁻ {u_lbl}
        </div>
        """, unsafe_allow_html=True)

        metrics = [
            ("SPD",       before.get("spd"),  after.get("spd")),
            ("EOD",       before.get("eod"),  after.get("eod")),
            ("OAED",      before.get("oaed"), after.get("oaed")),
            ("Exp@K G⁺",  (before.get("exposure_k") or {}).get("protected"),
                          (after.get("exposure_k")  or {}).get("protected")),
            ("Exp@K G⁻",  (before.get("exposure_k") or {}).get("unprotected"),
                          (after.get("exposure_k")  or {}).get("unprotected")),
        ]

        header = """
        <div class='metric-row' style='border-bottom:1px solid rgba(255,255,255,0.1)'>
            <span class='metric-name' style='color:#64748b'>Metric</span>
            <div class='metric-vals'>
                <span style='font-size:0.72rem;color:#f87171;font-weight:600'>Before</span>
                <span style='font-size:0.72rem;color:#34d399;font-weight:600'>After</span>
            </div>
        </div>
        """
        rows = "".join(
            f"<div class='metric-row'>"
            f"<span class='metric-name'>{name}</span>"
            f"<div class='metric-vals'>"
            f"<span class='metric-before'>{fmt_metric(b)}</span>"
            f"<span class='metric-after'>{fmt_metric(a)}</span>"
            f"</div></div>"
            for name, b, a in metrics
        )
        st.markdown(header + rows, unsafe_allow_html=True)

    if not display_results and not fairness_report:
        st.markdown("<div class='panel-title'>Try asking</div>", unsafe_allow_html=True)
        prompts = [
            "Give me some popular action movies",
            "Recommend acclaimed dramas",
            "Show me highly rated non-English films",
            "Something slow-burn and atmospheric",
            "Feel-good comedies for a family night",
        ]
        for p in prompts:
            st.markdown(f"""
            <div style='background:#141929;border:1px solid rgba(255,255,255,0.06);
                        border-radius:10px;padding:10px 14px;margin-bottom:8px;
                        font-size:0.82rem;color:#94a3b8;cursor:pointer;'>
                {p}
            </div>
            """, unsafe_allow_html=True)

# ── Main: chat interface ───────────────────────────────────────────────────────
with main:
    st.markdown("""
    <div class='app-header'>
        <h1>🎬 Med-Rec</h1>
        <p class='tagline'>Ask for recommendations · Question the results · Get fairer suggestions</p>
    </div>
    """, unsafe_allow_html=True)

    # Chat history
    chat_container = st.container()
    with chat_container:
        for msg in st.session_state.chat_display:
            role    = msg["role"]
            content = msg["content"]
            css     = "user" if role == "user" else "assistant"
            label   = "You" if role == "user" else "Med-Rec"
            st.markdown(f"""
            <div class='msg-row {css}'>
                <div class='bubble {css}'>
                    <div class='sender'>{label}</div>
                    {content}
                </div>
            </div>
            """, unsafe_allow_html=True)

    if not st.session_state.chat_display:
        st.markdown("""
        <div style='text-align:center;padding:80px 20px;'>
            <div style='font-size:1.2rem;color:#e2e8f0;margin-bottom:6px;font-weight:500'>
                What would you like to watch?
            </div>
            <div style='font-size:0.8rem;color:#475569;'>
                Type a message below to get started
            </div>
        </div>
        """, unsafe_allow_html=True)

    # Input bar
    st.markdown("<div class='input-bar'>", unsafe_allow_html=True)
    col_input, col_btn = st.columns([5, 1])
    with col_input:
        prompt = st.text_area(
            "Message",
            value="",
            placeholder="Ask for a recommendation, or question the results above…",
            height=68,
            label_visibility="collapsed",
            key=f"chat_input_{st.session_state.input_counter}",
        )
    with col_btn:
        st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
        submitted = st.button("Send", use_container_width=True)
    st.markdown("</div>", unsafe_allow_html=True)

    # ── Handle submission ──────────────────────────────────────────────────────
    if submitted and prompt.strip():
        user_text = prompt.strip()

        # Fix 3: add user message to display first, rerun to show it
        # before processing starts, then clear the input key
        st.session_state.chat_display.append({"role": "user", "content": user_text})
        st.session_state.pending_input = user_text
        st.session_state.input_counter += 1  # forces textarea to reset
        st.session_state.agent_state["messages"].append({"role": "user", "content": user_text})
        st.session_state.agent_state["latest_user_question"] = user_text
        st.rerun()

    # Fix 3 & 4: process pending input on next render cycle (after user bubble is shown)
    if st.session_state.get("pending_input"):
        user_text = st.session_state.pending_input
        st.session_state.pending_input = None

        with st.spinner("Thinking…"):
            result = st.session_state.graph.invoke(st.session_state.agent_state)

        output = result.get("agent_output")
        display_text = ""

        if output:
            if isinstance(output, dict):
                display_text = output.get("explanation", "")
                reranked = output.get("results", [])
                result["messages"].append({"role": "assistant", "content": display_text})
                if reranked:
                    results_summary = "The improved recommendations are:\n" + "\n".join(
                        f"{i}. {r.get('title','Unknown')} ({r.get('release_year','?')}) "
                        f"— {r.get('vote_average','?')}★ — {', '.join(r.get('genres') or [])}. "
                        f"{r.get('overview','')}"
                        for i, r in enumerate(reranked, 1)
                    )
                    result["messages"].append({"role": "assistant", "content": results_summary})
            else:
                display_text = output
                result["messages"].append({"role": "assistant", "content": display_text})

        elif result.get("error"):
            display_text = f"⚠️ {result['error']}"

        if display_text:
            st.session_state.chat_display.append({"role": "assistant", "content": display_text})

        st.session_state.agent_state = result
        st.rerun()