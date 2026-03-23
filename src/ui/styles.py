from __future__ import annotations

import streamlit as st


def inject_styles() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&family=Noto+Sans+SC:wght@400;500;700;800&display=swap');
        :root {
          --bg: #eef2f7;
          --panel: rgba(255, 255, 255, 0.82);
          --panel-strong: rgba(255, 255, 255, 0.92);
          --line: rgba(22, 36, 56, 0.10);
          --line-strong: rgba(22, 36, 56, 0.18);
          --text: #152238;
          --muted: #607089;
          --accent: #11243a;
          --accent-hover: #1b314c;
          --accent-soft: #dbe7f4;
          --warm: #d98943;
          --shadow: 0 20px 60px rgba(20, 34, 56, 0.08);
          --shadow-soft: 0 10px 28px rgba(20, 34, 56, 0.06);
        }
        html, body, [class*="css"] {
          font-family: "Manrope", "Noto Sans SC", sans-serif !important;
          color: var(--text);
        }
        .stApp {
          background:
            radial-gradient(circle at 12% 12%, rgba(182, 210, 238, 0.56), transparent 24%),
            radial-gradient(circle at 88% 8%, rgba(249, 228, 205, 0.42), transparent 20%),
            linear-gradient(180deg, #f7f9fc 0%, #edf2f7 100%);
        }
        [data-testid="stAppViewContainer"] > .main .block-container {
          max-width: 100%;
          padding-top: 0.35rem !important;
          padding-bottom: 0.4rem !important;
          padding-left: 1.1rem !important;
          padding-right: 1.1rem !important;
        }
        [data-testid="stHeader"],
        [data-testid="stToolbar"],
        #MainMenu,
        footer {
          display: none !important;
        }
        [data-testid="stSidebar"] > div {
          background:
            linear-gradient(180deg, rgba(250, 252, 255, 0.96) 0%, rgba(242, 246, 251, 0.94) 100%);
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
          min-height: 46px !important;
          border-radius: 999px !important;
          justify-content: flex-start !important;
          padding: 0.72rem 1rem !important;
        }
        .stButton button {
          border-radius: 18px !important;
          border: 1px solid transparent !important;
          background: var(--accent) !important;
          color: #fff !important;
          padding: 0.72rem 1.08rem !important;
          box-shadow: var(--shadow-soft) !important;
          font-weight: 700 !important;
          transition: transform 180ms ease, background 180ms ease, border-color 180ms ease, box-shadow 180ms ease !important;
        }
        .stButton button:hover {
          background: var(--accent-hover) !important;
          transform: translateY(-1px);
        }
        .stButton button[kind="secondary"] {
          background: rgba(255,255,255,0.78) !important;
          color: var(--text) !important;
          border: 1px solid var(--line) !important;
          box-shadow: none !important;
        }
        .stButton button[kind="secondary"]:hover {
          background: rgba(255,255,255,0.96) !important;
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
          border-radius: 18px !important;
          border: 1px solid var(--line) !important;
          background: rgba(255, 255, 255, 0.9) !important;
          transition: border-color 180ms ease, box-shadow 180ms ease, background 180ms ease !important;
        }
        .stTextInput input:focus,
        .stTextArea textarea:focus,
        .stSelectbox [data-baseweb="select"] > div:focus-within {
          border-color: rgba(17, 36, 58, 0.28) !important;
          box-shadow: 0 0 0 4px rgba(17, 36, 58, 0.08) !important;
          background: #ffffff !important;
        }
        .stTabs [data-baseweb="tab-list"] {
          gap: 0.65rem;
          margin-bottom: 1.15rem;
        }
        .stTabs [data-baseweb="tab"] {
          border-radius: 999px;
          border: 1px solid var(--line);
          background: rgba(255,255,255,0.7);
          padding: 0.52rem 1.05rem;
          color: var(--muted);
          transition: background 180ms ease, color 180ms ease, border-color 180ms ease, transform 180ms ease;
        }
        .stTabs [aria-selected="true"] {
          background: var(--accent);
          color: #fff;
          border-color: rgba(17, 36, 58, 0.16);
          transform: translateY(-1px);
        }
        .stTabs [data-baseweb="tab-highlight"] {
          display: none !important;
          height: 0 !important;
          background: transparent !important;
        }
        .stTabs [role="tablist"]::after,
        .stTabs [data-testid="stDecoration"] {
          display: none !important;
        }
        .page-shell {
          max-width: 1200px;
          margin: 0 auto;
          padding: 0.6rem 0 0.8rem 0;
          animation: page-enter 520ms cubic-bezier(.2,.8,.2,1) both;
        }
        .login-shell {
          min-height: auto;
          display: flex;
          align-items: flex-start;
          padding: 0.15rem 0 0 0;
        }
        .auth-stage {
          display: grid;
          grid-template-columns: minmax(0, 1.12fr) minmax(340px, 420px);
          gap: 2.15rem;
          align-items: start;
          width: 100%;
        }
        .auth-copy {
          max-width: 610px;
          animation: fade-up 620ms cubic-bezier(.2,.8,.2,1) both;
        }
        .auth-kicker {
          color: var(--warm);
          font-size: 0.78rem;
          font-weight: 800;
          letter-spacing: 0.16em;
          text-transform: uppercase;
          margin-bottom: 1rem;
        }
        .auth-title {
          font-size: clamp(2.55rem, 4.4vw, 4.15rem);
          line-height: 1.02;
          font-weight: 800;
          letter-spacing: -0.045em;
          max-width: 11ch;
          margin: 0;
          color: var(--accent);
        }
        .auth-subtitle {
          margin-top: 0.85rem;
          font-size: 0.96rem;
          line-height: 1.7;
          color: var(--muted);
          max-width: 34rem;
        }
        .auth-visual {
          margin-top: 1rem;
          width: min(100%, 620px);
          height: 196px;
          position: relative;
          overflow: hidden;
          border-radius: 28px;
          border: 1px solid rgba(17, 36, 58, 0.08);
          background:
            linear-gradient(135deg, rgba(17, 36, 58, 0.95) 0%, rgba(26, 50, 78, 0.92) 56%, rgba(216, 137, 67, 0.72) 140%);
          box-shadow: 0 34px 70px rgba(17, 36, 58, 0.16);
          animation: float-in 760ms cubic-bezier(.2,.8,.2,1) both;
        }
        .auth-visual::before {
          content: "";
          position: absolute;
          inset: 0;
          background:
            radial-gradient(circle at 18% 26%, rgba(255,255,255,0.22), transparent 18%),
            linear-gradient(transparent 96%, rgba(255,255,255,0.08) 100%),
            linear-gradient(90deg, transparent 96%, rgba(255,255,255,0.08) 100%);
          background-size: auto, 100% 28px, 28px 100%;
          opacity: 0.8;
        }
        .auth-visual-content {
          position: absolute;
          inset: 0;
          padding: 1.25rem;
          display: flex;
          flex-direction: column;
          justify-content: flex-end;
          gap: 0.72rem;
        }
        .auth-ribbon {
          width: fit-content;
          padding: 0.42rem 0.76rem;
          border-radius: 999px;
          background: rgba(255,255,255,0.14);
          color: rgba(255,255,255,0.92);
          font-size: 0.74rem;
          font-weight: 700;
          letter-spacing: 0.04em;
          backdrop-filter: blur(10px);
        }
        .auth-scene-line {
          max-width: 78%;
          padding: 0.68rem 0.84rem;
          border-radius: 16px;
          background: rgba(255,255,255,0.12);
          color: rgba(255,255,255,0.94);
          line-height: 1.5;
          font-size: 0.82rem;
          backdrop-filter: blur(10px);
          border: 1px solid rgba(255,255,255,0.08);
        }
        .auth-scene-line.alt {
          margin-left: auto;
          background: rgba(255,255,255,0.18);
        }
        .login-title {
          font-size: 1.22rem;
          font-weight: 800;
          line-height: 1.15;
          margin-bottom: 0.42rem;
        }
        .login-copy {
          color: var(--muted);
          font-size: 0.86rem;
          line-height: 1.62;
          margin-bottom: 0.82rem;
        }
        .login-note {
          background: rgba(17, 36, 58, 0.04);
          border: 1px dashed var(--line-strong);
          border-radius: 18px;
          padding: 0.68rem 0.8rem;
          color: var(--muted);
          font-size: 0.8rem;
          line-height: 1.48;
        }
        .login-panel-scope {
          height: 0;
        }
        [data-testid="column"]:has(.login-panel-scope) > div > [data-testid="stVerticalBlock"] {
          background: var(--panel-strong);
          border: 1px solid rgba(17, 36, 58, 0.08);
          border-radius: 24px;
          padding: 1.02rem 1.02rem 0.9rem 1.02rem;
          box-shadow: 0 20px 46px rgba(17, 36, 58, 0.10);
          backdrop-filter: blur(14px);
          animation: fade-up 740ms cubic-bezier(.2,.8,.2,1) both;
        }
        [data-testid="column"]:has(.login-panel-scope) .stTextInput input,
        [data-testid="column"]:has(.login-panel-scope) .stTextArea textarea,
        [data-testid="column"]:has(.login-panel-scope) .stSelectbox [data-baseweb="select"] > div {
          min-height: 44px !important;
          padding-top: 0.2rem !important;
          padding-bottom: 0.2rem !important;
        }
        [data-testid="column"]:has(.login-panel-scope) .stButton button {
          min-height: 44px !important;
          padding-top: 0.6rem !important;
          padding-bottom: 0.6rem !important;
        }
        .surface-card,
        .metric-card,
        .sidebar-card {
          background: var(--panel);
          border: 1px solid var(--line);
          box-shadow: var(--shadow);
        }
        .hero-card {
          position: relative;
          overflow: hidden;
          padding: 1.8rem 0 1.3rem 0;
          margin-bottom: 1.2rem;
          border: none;
          background: transparent;
          box-shadow: none;
          animation: fade-up 620ms cubic-bezier(.2,.8,.2,1) both;
        }
        .hero-card::after {
          content: "";
          position: absolute;
          left: 0;
          right: 0;
          bottom: 0;
          height: 1px;
          background: linear-gradient(90deg, rgba(17,36,58,0.12), rgba(17,36,58,0.02));
        }
        .hero-kicker {
          color: var(--warm);
          font-size: 0.8rem;
          font-weight: 800;
          text-transform: uppercase;
          letter-spacing: 0.14em;
        }
        .hero-title {
          font-size: clamp(1.95rem, 3vw, 2.8rem);
          line-height: 1.02;
          font-weight: 800;
          letter-spacing: -0.03em;
          margin: 0.42rem 0 0.56rem 0;
        }
        .hero-copy {
          color: var(--muted);
          font-size: 0.97rem;
          line-height: 1.75;
          max-width: 760px;
        }
        .surface-card {
          border-radius: 24px;
          padding: 1.15rem 1.2rem;
          margin-bottom: 1rem;
          background: var(--panel-strong);
          box-shadow: 0 14px 42px rgba(17, 36, 58, 0.06);
        }
        .surface-title {
          font-size: 1.02rem;
          font-weight: 800;
          margin-bottom: 0.34rem;
        }
        .surface-copy {
          color: var(--muted);
          font-size: 0.92rem;
          line-height: 1.68;
        }
        .metric-card {
          border-radius: 22px;
          padding: 1rem 1.05rem;
          min-height: 118px;
          background: rgba(255, 255, 255, 0.72);
          box-shadow: 0 14px 30px rgba(17, 36, 58, 0.05);
        }
        .metric-label {
          color: var(--muted);
          font-size: 0.78rem;
          font-weight: 800;
          text-transform: uppercase;
          letter-spacing: 0.12em;
        }
        .metric-value {
          margin-top: 0.45rem;
          font-size: 1.22rem;
          line-height: 1.4;
          font-weight: 800;
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
          background: rgba(255,255,255,0.8);
          border: 1px solid var(--line);
          color: var(--muted);
          font-size: 0.8rem;
          font-weight: 700;
        }
        .sidebar-brand {
          font-size: 1rem;
          font-weight: 800;
          margin-bottom: 0.18rem;
        }
        .sidebar-copy {
          color: var(--muted);
          font-size: 0.82rem;
          line-height: 1.62;
          margin-bottom: 0.95rem;
        }
        .sidebar-section {
          color: var(--muted);
          font-size: 0.76rem;
          font-weight: 800;
          text-transform: uppercase;
          letter-spacing: 0.14em;
          margin: 0.95rem 0 0.45rem 0;
        }
        .sidebar-card {
          border-radius: 24px;
          padding: 0.85rem 0.95rem;
          margin-top: 1rem;
          background: rgba(255,255,255,0.76);
          box-shadow: 0 12px 24px rgba(17,36,58,0.05);
        }
        .chat-bubble-user,
        .chat-bubble-assistant {
          padding: 0.78rem 0;
          margin-bottom: 0.32rem;
          border: none;
          background: transparent;
          line-height: 1.8;
        }
        .chat-bubble-user {
          color: var(--text);
          font-weight: 700;
        }
        .chat-bubble-assistant {
          color: #334764;
        }
        .assistant-meta {
          margin-top: 0.45rem;
          color: var(--muted);
          font-size: 0.8rem;
        }
        .chat-thread {
          margin: 0.4rem 0 1rem 0;
        }
        .score-grid-card {
          border-radius: 20px;
          background: rgba(255,255,255,0.9);
          border: 1px solid var(--line);
          padding: 0.95rem 1rem;
          margin-bottom: 0.78rem;
          box-shadow: 0 10px 24px rgba(17, 36, 58, 0.04);
        }
        .score-grid-card strong {
          display: block;
          margin-bottom: 0.28rem;
        }
        .score-grid-card span {
          color: var(--muted);
          font-size: 0.86rem;
          line-height: 1.58;
        }
        .placeholder-card {
          border-radius: 20px;
          padding: 1rem 1.05rem;
          border: 1px dashed var(--line-strong);
          background: rgba(255,255,255,0.68);
          color: var(--muted);
        }
        .hypergraph-shell {
          background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
          border: 1px solid var(--line);
          border-radius: 28px;
          padding: 0.8rem;
          overflow: hidden;
        }
        @keyframes page-enter {
          from { opacity: 0; transform: translateY(10px); }
          to { opacity: 1; transform: translateY(0); }
        }
        @keyframes fade-up {
          from { opacity: 0; transform: translateY(20px); }
          to { opacity: 1; transform: translateY(0); }
        }
        @keyframes float-in {
          from { opacity: 0; transform: translateY(26px) scale(0.985); }
          to { opacity: 1; transform: translateY(0) scale(1); }
        }
        @media (max-width: 980px) {
          [data-testid="stAppViewContainer"] > .main .block-container {
            padding-top: 0.2rem !important;
            padding-left: 0.8rem !important;
            padding-right: 0.8rem !important;
          }
          .page-shell {
            padding-top: 0.45rem;
          }
          .login-shell {
            min-height: auto;
            display: block;
            padding-top: 0.1rem;
          }
          .auth-stage {
            grid-template-columns: 1fr;
            gap: 1.1rem;
          }
          .hero-title,
          .login-title,
          .auth-title {
            font-size: 1.5rem;
          }
          .auth-visual {
            height: 176px;
            border-radius: 22px;
          }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
