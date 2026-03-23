from __future__ import annotations

import streamlit as st


def inject_styles() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700&family=Noto+Sans+SC:wght@400;500;700&display=swap');
        :root {
          --bg: #f5f7fb;
          --panel: rgba(255, 255, 255, 0.94);
          --line: rgba(15, 23, 42, 0.08);
          --line-strong: rgba(15, 23, 42, 0.14);
          --text: #111827;
          --muted: #6b7280;
          --accent: #0f172a;
          --accent-hover: #1e293b;
          --shadow: 0 18px 60px rgba(15, 23, 42, 0.08);
        }
        html, body, [class*="css"] {
          font-family: "Manrope", "Noto Sans SC", sans-serif !important;
          color: var(--text);
        }
        .stApp {
          background:
            radial-gradient(circle at 10% 8%, rgba(191, 219, 254, 0.34), transparent 24%),
            radial-gradient(circle at 90% 2%, rgba(226, 232, 240, 0.44), transparent 22%),
            linear-gradient(180deg, #f8fafc 0%, #f3f5fa 100%);
        }
        [data-testid="stHeader"],
        [data-testid="stToolbar"],
        #MainMenu,
        footer {
          display: none !important;
        }
        [data-testid="stSidebar"] > div {
          background: linear-gradient(180deg, #fbfcff 0%, #f4f6fb 100%);
          border-right: 1px solid var(--line);
        }
        [data-testid="stSidebarNav"] {
          display: none !important;
        }
        [data-testid="stSidebar"] .block-container {
          padding-top: 1rem;
          padding-bottom: 1rem;
        }
        [data-testid="stSidebar"] .stButton button {
          min-height: 44px !important;
          border-radius: 999px !important;
          justify-content: flex-start !important;
          padding: 0.62rem 0.92rem !important;
        }
        .stButton button {
          border-radius: 14px !important;
          border: 1px solid transparent !important;
          background: var(--accent) !important;
          color: #fff !important;
          padding: 0.62rem 1rem !important;
          box-shadow: none !important;
          font-weight: 600 !important;
        }
        .stButton button:hover {
          background: var(--accent-hover) !important;
        }
        .stButton button[kind="secondary"] {
          background: rgba(255,255,255,0.9) !important;
          color: var(--text) !important;
          border: 1px solid var(--line) !important;
        }
        .stButton button[kind="secondary"]:hover {
          background: #ffffff !important;
        }
        .stButton button[kind="tertiary"] {
          background: transparent !important;
          color: var(--muted) !important;
          border: none !important;
          box-shadow: none !important;
        }
        .stTextInput input,
        .stTextArea textarea,
        .stSelectbox [data-baseweb="select"] > div {
          border-radius: 14px !important;
          border: 1px solid var(--line) !important;
          background: #ffffff !important;
        }
        .stTabs [data-baseweb="tab-list"] {
          gap: 0.55rem;
          margin-bottom: 1rem;
        }
        .stTabs [data-baseweb="tab"] {
          border-radius: 999px;
          border: 1px solid var(--line);
          background: rgba(255,255,255,0.84);
          padding: 0.45rem 1rem;
        }
        .stTabs [aria-selected="true"] {
          background: var(--accent);
          color: #fff;
        }
        .page-shell {
          max-width: 1180px;
          margin: 0 auto;
          padding: 1.2rem 0 2rem 0;
        }
        .login-shell {
          max-width: 560px;
          margin: 10vh auto 0 auto;
          padding: 0 0.5rem;
        }
        .login-card {
          background: rgba(255,255,255,0.86);
          border: 1px solid rgba(15, 23, 42, 0.06);
          border-radius: 24px;
          padding: 1.4rem 1.35rem;
          box-shadow: 0 16px 44px rgba(15, 23, 42, 0.08);
        }
        .login-title {
          font-size: 1.82rem;
          font-weight: 700;
          line-height: 1.15;
          margin-bottom: 0.6rem;
        }
        .login-copy {
          color: var(--muted);
          font-size: 0.94rem;
          line-height: 1.65;
          margin-bottom: 1.05rem;
        }
        .login-note {
          background: #f8fafc;
          border: 1px dashed var(--line-strong);
          border-radius: 14px;
          padding: 0.75rem 0.9rem;
          color: var(--muted);
          font-size: 0.86rem;
          line-height: 1.55;
        }
        .surface-card,
        .hero-card,
        .metric-card,
        .sidebar-card {
          background: var(--panel);
          border: 1px solid var(--line);
          box-shadow: var(--shadow);
        }
        .hero-card {
          border-radius: 24px;
          padding: 1.2rem 1.3rem;
          margin-bottom: 1rem;
        }
        .hero-kicker {
          color: var(--muted);
          font-size: 0.8rem;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: 0.08em;
        }
        .hero-title {
          font-size: 1.72rem;
          line-height: 1.1;
          font-weight: 700;
          margin: 0.35rem 0 0.45rem 0;
        }
        .hero-copy {
          color: var(--muted);
          font-size: 0.94rem;
          line-height: 1.65;
          max-width: 820px;
        }
        .surface-card {
          border-radius: 20px;
          padding: 1.05rem 1.15rem;
          margin-bottom: 0.95rem;
        }
        .surface-title {
          font-size: 1rem;
          font-weight: 700;
          margin-bottom: 0.3rem;
        }
        .surface-copy {
          color: var(--muted);
          font-size: 0.9rem;
          line-height: 1.62;
        }
        .metric-card {
          border-radius: 18px;
          padding: 0.9rem 1rem;
          min-height: 118px;
        }
        .metric-label {
          color: var(--muted);
          font-size: 0.78rem;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: 0.08em;
        }
        .metric-value {
          margin-top: 0.45rem;
          font-size: 1.2rem;
          line-height: 1.4;
          font-weight: 700;
          white-space: pre-wrap;
        }
        .metric-footnote,
        .mini-note {
          margin-top: 0.55rem;
          color: var(--muted);
          font-size: 0.83rem;
          line-height: 1.52;
        }
        .status-chip {
          display: inline-flex;
          align-items: center;
          gap: 0.42rem;
          border-radius: 999px;
          padding: 0.38rem 0.74rem;
          background: rgba(255,255,255,0.95);
          border: 1px solid var(--line);
          color: var(--muted);
          font-size: 0.8rem;
          font-weight: 600;
        }
        .sidebar-brand {
          font-size: 1.08rem;
          font-weight: 800;
          margin-bottom: 0.2rem;
        }
        .sidebar-copy {
          color: var(--muted);
          font-size: 0.83rem;
          line-height: 1.55;
          margin-bottom: 0.85rem;
        }
        .sidebar-section {
          color: var(--muted);
          font-size: 0.76rem;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: 0.08em;
          margin: 0.95rem 0 0.45rem 0;
        }
        .sidebar-card {
          border-radius: 18px;
          padding: 0.85rem 0.95rem;
          margin-top: 1rem;
        }
        .chat-bubble-user,
        .chat-bubble-assistant {
          padding: 0.68rem 0;
          margin-bottom: 0.28rem;
          border: none;
          background: transparent;
          line-height: 1.72;
        }
        .chat-bubble-user {
          color: var(--text);
          font-weight: 600;
        }
        .chat-bubble-assistant {
          color: #334155;
        }
        .assistant-meta {
          margin-top: 0.45rem;
          color: var(--muted);
          font-size: 0.8rem;
        }
        .chat-thread {
          margin: 0.3rem 0 0.95rem 0;
        }
        .score-grid-card {
          border-radius: 16px;
          background: #fff;
          border: 1px solid var(--line);
          padding: 0.85rem 0.95rem;
          margin-bottom: 0.7rem;
        }
        .score-grid-card strong {
          display: block;
          margin-bottom: 0.26rem;
        }
        .score-grid-card span {
          color: var(--muted);
          font-size: 0.86rem;
          line-height: 1.52;
        }
        .placeholder-card {
          border-radius: 16px;
          padding: 0.92rem 1rem;
          border: 1px dashed var(--line-strong);
          background: rgba(255,255,255,0.72);
          color: var(--muted);
        }
        .hypergraph-shell {
          background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
          border: 1px solid var(--line);
          border-radius: 20px;
          padding: 0.75rem;
          overflow: hidden;
        }
        @media (max-width: 980px) {
          .page-shell {
            padding-top: 0.7rem;
          }
          .login-shell {
            margin-top: 6vh;
          }
          .hero-title,
          .login-title {
            font-size: 1.45rem;
          }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
