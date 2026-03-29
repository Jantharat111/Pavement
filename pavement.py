"""
Pavement Structure Design Tool - AASHTO 1993
Supports: Flexible Pavement & Rigid (Concrete) Pavement
"""

import streamlit as st
import math
import io
from datetime import datetime

# ─── ReportLab PDF ───────────────────────────────────────────────────────────
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
    )
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    REPORTLAB_OK = True
except ImportError:
    REPORTLAB_OK = False

# ══════════════════════════════════════════════════════════════════════════════
# AASHTO 1993 CALCULATION FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════

def calc_esal(aadt, truck_pct, growth_rate, design_years, ldf=0.5):
    """Estimate design ESAL (Equivalent Single Axle Loads)."""
    trucks = aadt * (truck_pct / 100)
    gf = ((1 + growth_rate / 100) ** design_years - 1) / (growth_rate / 100) if growth_rate > 0 else design_years
    esal = trucks * 365 * gf * ldf * 1.0  # simplified truck factor ~1.0
    return esal


def flexible_design(W18, R, S0, delta_PSI, MR):
    """
    AASHTO 1993 Flexible Pavement: solve for SN.
    log10(W18) = ZR*S0 + 9.36*log10(SN+1) - 0.20
                 + log10(ΔPSI/(4.2-1.5))/(0.40 + 1094/(SN+1)^5.19)
                 + 2.32*log10(MR) - 8.07
    Solve iteratively for SN.
    """
    ZR_table = {50: 0.000, 75: -0.674, 80: -0.842, 85: -1.037,
                90: -1.282, 95: -1.645, 99: -2.327}
    ZR = ZR_table.get(R, -1.282)

    def lhs(SN):
        return (ZR * S0
                + 9.36 * math.log10(SN + 1) - 0.20
                + math.log10(delta_PSI / (4.2 - 1.5)) / (0.40 + 1094 / (SN + 1) ** 5.19)
                + 2.32 * math.log10(MR) - 8.07)

    target = math.log10(W18)
    # bisection
    lo, hi = 0.5, 20.0
    for _ in range(100):
        mid = (lo + hi) / 2
        if lhs(mid) < target:
            lo = mid
        else:
            hi = mid
    return round((lo + hi) / 2, 2)


def sn_to_layers(SN, a1=0.44, a2=0.14, a3=0.11,
                 m2=1.0, m3=1.0,
                 D1_min=2.0, D2_min=4.0):
    """Convert SN to layer thicknesses (inches)."""
    # Layer 1: AC surface
    D1 = max(D1_min, math.ceil(SN / a1 * 0.4))  # ~40% of SN from surface
    SN1 = a1 * D1
    # Layer 2: Base
    SN_rem = SN - SN1
    D2 = max(D2_min, math.ceil(SN_rem / (a2 * m2)))
    SN2 = a2 * m2 * D2
    # Layer 3: Subbase
    SN_rem2 = SN - SN1 - SN2
    D3 = max(0, math.ceil(SN_rem2 / (a3 * m3))) if SN_rem2 > 0 else 0
    return D1, D2, D3, SN1, SN2, a3 * m3 * D3


def rigid_design(W18, R, S0, delta_PSI, Sc, Cd, J, Ec, k):
    """
    AASHTO 1993 Rigid Pavement: solve for slab thickness D (inches).
    """
    ZR_table = {50: 0.000, 75: -0.674, 80: -0.842, 85: -1.037,
                90: -1.282, 95: -1.645, 99: -2.327}
    ZR = ZR_table.get(R, -1.282)

    def lhs(D):
        try:
            term1 = ZR * S0
            term2 = 7.35 * math.log10(D + 1) - 0.06
            term3 = math.log10(delta_PSI / (4.5 - 1.5)) / (1 + 1.624e7 / (D + 1) ** 8.46)
            term4 = (4.22 - 0.32 * 2.5) * math.log10(
                Sc * Cd * (D ** 0.75 - 1.132) /
                (215.63 * J * (D ** 0.75 - (18.42 / (Ec / k) ** 0.25)))
            )
            return term1 + term2 + term3 + term4
        except Exception:
            return -999

    target = math.log10(W18)
    lo, hi = 4.0, 30.0
    for _ in range(200):
        mid = (lo + hi) / 2
        val = lhs(mid)
        if val < target:
            lo = mid
        else:
            hi = mid
    return round((lo + hi) / 2, 1)


def inches_to_cm(inches):
    return round(inches * 2.54, 1)

# ══════════════════════════════════════════════════════════════════════════════
# PDF GENERATION
# ══════════════════════════════════════════════════════════════════════════════

def generate_pdf(design_type, inputs, results):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            rightMargin=2*cm, leftMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('Title2', parent=styles['Title'],
                                 fontSize=16, textColor=colors.HexColor('#1a3a6b'),
                                 spaceAfter=6)
    h2_style = ParagraphStyle('H2', parent=styles['Heading2'],
                               fontSize=12, textColor=colors.HexColor('#2563eb'),
                               spaceBefore=12, spaceAfter=4)
    normal = styles['Normal']
    normal.fontSize = 10

    story = []

    # Header
    story.append(Paragraph("รายงานการออกแบบโครงสร้างผิวทาง", title_style))
    story.append(Paragraph("Pavement Structure Design Report — AASHTO 1993", styles['Heading3']))
    story.append(Paragraph(f"วันที่ออกแบบ: {datetime.now().strftime('%d/%m/%Y %H:%M')}", normal))
    story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor('#2563eb')))
    story.append(Spacer(1, 0.3*cm))

    # Design Type
    dtype_th = "ผิวทางคอนกรีต (Rigid)" if design_type == "rigid" else "ผิวทางยืดหยุ่น (Flexible)"
    story.append(Paragraph(f"ประเภทโครงสร้าง: {dtype_th}", h2_style))
    story.append(Spacer(1, 0.2*cm))

    # Input Parameters table
    story.append(Paragraph("1. ข้อมูลนำเข้า (Input Parameters)", h2_style))
    input_data = [["พารามิเตอร์", "ค่า", "หน่วย"]]
    for k, v in inputs.items():
        input_data.append([k, str(v[0]), v[1]])

    t = Table(input_data, colWidths=[9*cm, 4*cm, 3*cm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#2563eb')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 9),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.HexColor('#f0f4ff'), colors.white]),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#c7d2fe')),
        ('ALIGN', (1,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
    ]))
    story.append(t)
    story.append(Spacer(1, 0.4*cm))

    # Results table
    story.append(Paragraph("2. ผลการออกแบบโครงสร้างชั้นทาง (Design Results)", h2_style))
    res_data = [["ชั้นทาง (Layer)", "หนา (นิ้ว / in)", "หนา (เซนติเมตร / cm)"]]
    for row in results:
        res_data.append(row)

    t2 = Table(res_data, colWidths=[9*cm, 4*cm, 3*cm])
    t2.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#059669')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 9),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.HexColor('#ecfdf5'), colors.white]),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#6ee7b7')),
        ('ALIGN', (1,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('FONTNAME', (0,-1), (-1,-1), 'Helvetica-Bold'),
        ('BACKGROUND', (0,-1), (-1,-1), colors.HexColor('#d1fae5')),
    ]))
    story.append(t2)
    story.append(Spacer(1, 0.4*cm))

    # Note
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#c7d2fe')))
    story.append(Spacer(1, 0.2*cm))
    story.append(Paragraph(
        "หมายเหตุ: การออกแบบนี้อ้างอิงมาตรฐาน AASHTO Guide for Design of Pavement Structures (1993) "
        "ควรตรวจสอบกับวิศวกรผู้เชี่ยวชาญก่อนนำไปใช้งานจริง",
        ParagraphStyle('Note', parent=normal, fontSize=8, textColor=colors.gray)
    ))

    doc.build(story)
    buf.seek(0)
    return buf

# ══════════════════════════════════════════════════════════════════════════════
# STREAMLIT UI
# ══════════════════════════════════════════════════════════════════════════════

st.set_page_config(page_title="Pavement Design – AASHTO 1993",
                   page_icon="🛣️", layout="wide")

# ── CSS ──────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .main { background: #f8fafc; }
    .block-container { padding-top: 1.5rem; }
    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    .stTabs [data-baseweb="tab"] {
        background: #e0e7ff; border-radius: 8px 8px 0 0;
        padding: 8px 20px; font-weight: 600;
    }
    .stTabs [aria-selected="true"] { background: #2563eb; color: white; }
    .metric-box {
        background: white; border-radius: 12px; padding: 16px 20px;
        box-shadow: 0 2px 8px rgba(0,0,0,.08); margin-bottom: 12px;
        border-left: 5px solid #2563eb;
    }
    .layer-block {
        border-radius: 10px; padding: 14px 18px; margin: 6px 0;
        font-size: 15px; font-weight: 600; color: white;
        display: flex; justify-content: space-between; align-items: center;
    }
    .result-card {
        background: white; border-radius: 14px; padding: 20px;
        box-shadow: 0 4px 16px rgba(0,0,0,.10);
    }
    h1 { color: #1a3a6b !important; }
    .stButton > button {
        background: #2563eb; color: white; border-radius: 8px;
        font-weight: 600; padding: 0.5rem 1.5rem;
    }
    .stButton > button:hover { background: #1d4ed8; }
    .section-title { color: #1e40af; font-weight: 700; font-size: 16px; margin-bottom: 8px; }
</style>
""", unsafe_allow_html=True)

# ── Title ─────────────────────────────────────────────────────────────────────
st.markdown("# 🛣️ ระบบออกแบบโครงสร้างผิวทาง — AASHTO 1993")
st.markdown("**Pavement Structure Design Tool** | ออกแบบโครงสร้างผิวทางคอนกรีตและผิวทางยืดหยุ่นตามมาตรฐาน AASHTO 1993")
st.markdown("---")

# ── Design Type Tabs ──────────────────────────────────────────────────────────
tab1, tab2 = st.tabs(["🔩 ผิวทางยืดหยุ่น (Flexible Pavement)", "🏗️ ผิวทางคอนกรีต (Rigid Pavement)"])

# ════════════════════════════════════════════════
# TAB 1 — FLEXIBLE PAVEMENT
# ════════════════════════════════════════════════
with tab1:
    col_in, col_out = st.columns([1, 1], gap="large")

    with col_in:
        st.markdown("### 📋 ข้อมูลนำเข้า (Input Parameters)")

        st.markdown('<p class="section-title">🚗 ปริมาณจราจรและอายุการออกแบบ</p>', unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        with c1:
            aadt_f = st.number_input("AADT (คัน/วัน)", 1000, 200000, 10000, 500, key="aadt_f")
            truck_f = st.slider("สัดส่วนรถบรรทุก (%)", 5, 60, 20, key="truck_f")
        with c2:
            growth_f = st.number_input("อัตราการเติบโต (%/ปี)", 0.0, 10.0, 3.0, 0.5, key="growth_f")
            years_f = st.selectbox("อายุการออกแบบ (ปี)", [10, 15, 20, 25, 30], index=2, key="years_f")

        st.markdown('<p class="section-title">📊 พารามิเตอร์การออกแบบ</p>', unsafe_allow_html=True)
        c3, c4 = st.columns(2)
        with c3:
            R_f = st.selectbox("ความน่าเชื่อถือ R (%)", [75, 80, 85, 90, 95, 99], index=3, key="R_f")
            S0_f = st.number_input("S₀ (Overall Std Dev)", 0.30, 0.50, 0.45, 0.01, key="S0_f")
        with c4:
            pi_f = st.number_input("PSI เริ่มต้น (p₀)", 3.5, 5.0, 4.2, 0.1, key="pi_f")
            pt_f = st.number_input("PSI สิ้นสุด (pₜ)", 1.5, 3.0, 2.5, 0.1, key="pt_f")

        st.markdown('<p class="section-title">🌍 คุณสมบัติดินพื้นทาง</p>', unsafe_allow_html=True)
        MR_f = st.number_input("Resilient Modulus ของดินรองพื้น MR (psi)", 2000, 30000, 7500, 500, key="MR_f")
        CBR_f = st.number_input("CBR ดินรองพื้น (%)", 1, 30, 8, 1, key="CBR_f",
                                 help="ใช้ประมาณ MR = 1500×CBR (psi) หากไม่มีข้อมูล MR โดยตรง")

        use_cbr = st.checkbox("คำนวณ MR จาก CBR อัตโนมัติ", key="use_cbr_f")
        if use_cbr:
            MR_f = 1500 * CBR_f
            st.info(f"MR = 1500 × {CBR_f} = **{MR_f:,} psi**")

        st.markdown('<p class="section-title">🧱 สัมประสิทธิ์ชั้นทาง</p>', unsafe_allow_html=True)
        c5, c6, c7 = st.columns(3)
        with c5:
            a1 = st.number_input("a₁ (AC Surface)", 0.30, 0.50, 0.44, 0.01, key="a1")
        with c6:
            a2 = st.number_input("a₂ (Base)", 0.10, 0.20, 0.14, 0.01, key="a2")
        with c7:
            a3 = st.number_input("a₃ (Subbase)", 0.08, 0.14, 0.11, 0.01, key="a3")

        calc_btn_f = st.button("🔍 คำนวณออกแบบผิวทางยืดหยุ่น", use_container_width=True, key="calc_f")

    with col_out:
        st.markdown("### 📐 ผลการออกแบบ (Results)")

        if calc_btn_f:
            delta_PSI_f = pi_f - pt_f
            W18_f = calc_esal(aadt_f, truck_f, growth_f, years_f)
            SN = flexible_design(W18_f, R_f, S0_f, delta_PSI_f, MR_f)
            D1, D2, D3, SN1, SN2, SN3 = sn_to_layers(SN, a1, a2, a3)

            st.session_state['flex_results'] = {
                'W18': W18_f, 'SN': SN,
                'D1': D1, 'D2': D2, 'D3': D3,
                'SN1': SN1, 'SN2': SN2, 'SN3': SN3,
                'inputs': {
                    'AADT': (f"{aadt_f:,}", 'คัน/วัน'),
                    'สัดส่วนรถบรรทุก': (f"{truck_f}", '%'),
                    'อัตราการเติบโต': (f"{growth_f}", '%/ปี'),
                    'อายุการออกแบบ': (f"{years_f}", 'ปี'),
                    'ความน่าเชื่อถือ R': (f"{R_f}", '%'),
                    'S₀': (f"{S0_f}", '-'),
                    'ΔPSI': (f"{delta_PSI_f:.1f}", '-'),
                    'MR': (f"{MR_f:,}", 'psi'),
                    'a₁ / a₂ / a₃': (f"{a1} / {a2} / {a3}", '-'),
                    'W18 (ESAL)': (f"{W18_f:,.0f}", 'ESAL'),
                    'Structural Number (SN)': (f"{SN}", '-'),
                }
            }

        if 'flex_results' in st.session_state:
            r = st.session_state['flex_results']
            W18_f = r['W18']; SN = r['SN']
            D1 = r['D1']; D2 = r['D2']; D3 = r['D3']

            # Key metrics
            mc1, mc2 = st.columns(2)
            mc1.metric("📦 W18 (ESAL)", f"{W18_f:,.0f}")
            mc2.metric("🔢 Structural Number (SN)", f"{SN}")

            # Layer diagram
            st.markdown('<div class="result-card">', unsafe_allow_html=True)
            st.markdown("#### 🏗️ โครงสร้างชั้นทาง")

            total_in = D1 + D2 + D3
            layers = [
                ("🖤 AC Surface (ผิวแอสฟัลต์)", D1, "#374151"),
                ("🟤 Granular Base (ชั้นรองพื้นทาง)", D2, "#92400e"),
                ("🟡 Granular Subbase (ชั้นรองฐานราก)", D3, "#b45309"),
                ("⬛ Subgrade (ดินรองพื้น)", None, "#6b7280"),
            ]

            for name, thick, color in layers:
                if thick is not None and thick > 0:
                    pct = int((thick / (total_in + 6)) * 100) + 15
                    st.markdown(f"""
                    <div class="layer-block" style="background:{color}; min-height:{pct}px;">
                        <span>{name}</span>
                        <span>{thick}" &nbsp;|&nbsp; {inches_to_cm(thick)} cm</span>
                    </div>""", unsafe_allow_html=True)
                elif thick is None:
                    st.markdown(f"""
                    <div class="layer-block" style="background:{color}; min-height:30px; opacity:0.7;">
                        <span>{name}</span><span>∞</span>
                    </div>""", unsafe_allow_html=True)

            st.markdown("</div>", unsafe_allow_html=True)

            # Summary table
            st.markdown("#### 📊 ตารางสรุปความหนา")
            rows = [
                ["AC Surface (ผิวแอสฟัลต์)", f"{D1}\"", f"{inches_to_cm(D1)} cm"],
                ["Granular Base (ชั้นรองพื้นทาง)", f"{D2}\"", f"{inches_to_cm(D2)} cm"],
                ["Granular Subbase (ชั้นรองฐานราก)", f"{D3}\"", f"{inches_to_cm(D3)} cm"],
                ["**รวม (Total)**", f"**{total_in}\"**", f"**{inches_to_cm(total_in)} cm**"],
            ]
            import pandas as pd
            df = pd.DataFrame(rows, columns=["ชั้นทาง", "ความหนา (นิ้ว)", "ความหนา (ซม.)"])
            st.dataframe(df, use_container_width=True, hide_index=True)

            # PDF Download
            if REPORTLAB_OK:
                pdf_rows = [
                    ["AC Surface (ผิวแอสฟัลต์)", f'{D1}"', f"{inches_to_cm(D1)} cm"],
                    ["Granular Base (ชั้นรองพื้นทาง)", f'{D2}"', f"{inches_to_cm(D2)} cm"],
                    ["Granular Subbase (ชั้นรองฐานราก)", f'{D3}"', f"{inches_to_cm(D3)} cm"],
                    ["รวม (Total)", f'{total_in}"', f"{inches_to_cm(total_in)} cm"],
                ]
                pdf_buf = generate_pdf("flexible", r['inputs'], pdf_rows)
                st.download_button("📄 ดาวน์โหลด PDF Report", pdf_buf,
                                   file_name="flexible_pavement_design.pdf",
                                   mime="application/pdf", use_container_width=True)

# ════════════════════════════════════════════════
# TAB 2 — RIGID PAVEMENT
# ════════════════════════════════════════════════
with tab2:
    col_in2, col_out2 = st.columns([1, 1], gap="large")

    with col_in2:
        st.markdown("### 📋 ข้อมูลนำเข้า (Input Parameters)")

        st.markdown('<p class="section-title">🚗 ปริมาณจราจรและอายุการออกแบบ</p>', unsafe_allow_html=True)
        c1r, c2r = st.columns(2)
        with c1r:
            aadt_r = st.number_input("AADT (คัน/วัน)", 1000, 200000, 10000, 500, key="aadt_r")
            truck_r = st.slider("สัดส่วนรถบรรทุก (%)", 5, 60, 20, key="truck_r")
        with c2r:
            growth_r = st.number_input("อัตราการเติบโต (%/ปี)", 0.0, 10.0, 3.0, 0.5, key="growth_r")
            years_r = st.selectbox("อายุการออกแบบ (ปี)", [10, 15, 20, 25, 30], index=2, key="years_r")

        st.markdown('<p class="section-title">📊 พารามิเตอร์การออกแบบ</p>', unsafe_allow_html=True)
        c3r, c4r = st.columns(2)
        with c3r:
            R_r = st.selectbox("ความน่าเชื่อถือ R (%)", [75, 80, 85, 90, 95, 99], index=3, key="R_r")
            S0_r = st.number_input("S₀ (Overall Std Dev)", 0.30, 0.40, 0.35, 0.01, key="S0_r")
        with c4r:
            pi_r = st.number_input("PSI เริ่มต้น (p₀)", 3.5, 5.0, 4.5, 0.1, key="pi_r")
            pt_r = st.number_input("PSI สิ้นสุด (pₜ)", 2.0, 3.5, 2.5, 0.1, key="pt_r")

        st.markdown('<p class="section-title">🏗️ คุณสมบัติวัสดุคอนกรีต</p>', unsafe_allow_html=True)
        c5r, c6r = st.columns(2)
        with c5r:
            Sc = st.number_input("Sc — Modulus of Rupture (psi)", 400, 1000, 650, 10, key="Sc")
            Ec = st.number_input("Ec — Elastic Modulus คอนกรีต (psi)", 2000000, 6000000, 4000000, 100000,
                                  key="Ec", format="%d")
        with c6r:
            Cd = st.number_input("Cd — Drainage Coefficient", 0.70, 1.25, 1.00, 0.05, key="Cd")
            J = st.number_input("J — Load Transfer Coefficient", 2.5, 4.5, 3.2, 0.1, key="J")

        st.markdown('<p class="section-title">🌍 ค่า k ดินรองพื้น</p>', unsafe_allow_html=True)
        k_r = st.number_input("k — Modulus of Subgrade Reaction (pci)", 50, 500, 150, 10, key="k_r")
        CBR_r = st.number_input("CBR ดินรองพื้น (%)", 1, 30, 8, 1, key="CBR_r",
                                 help="ใช้ประมาณ k จาก CBR หากต้องการ")
        use_cbr_r = st.checkbox("ประมาณ k จาก CBR อัตโนมัติ (k ≈ 10×CBR)", key="use_cbr_r")
        if use_cbr_r:
            k_r = 10 * CBR_r
            st.info(f"k ≈ 10 × {CBR_r} = **{k_r} pci**")

        st.markdown('<p class="section-title">🧱 ชั้นรองพื้น (Sub-layers)</p>', unsafe_allow_html=True)
        with st.expander("กำหนดชั้นรองคอนกรีต (Optional)"):
            has_base = st.checkbox("มีชั้น Base", value=True, key="has_base_r")
            base_thick_r = st.number_input("ความหนา Base (นิ้ว)", 4, 16, 6, 1, key="base_r") if has_base else 0
            has_subbase = st.checkbox("มีชั้น Subbase", value=False, key="has_sub_r")
            subbase_thick_r = st.number_input("ความหนา Subbase (นิ้ว)", 4, 16, 6, 1, key="subbase_r") if has_subbase else 0

        calc_btn_r = st.button("🔍 คำนวณออกแบบผิวทางคอนกรีต", use_container_width=True, key="calc_r")

    with col_out2:
        st.markdown("### 📐 ผลการออกแบบ (Results)")

        if calc_btn_r:
            delta_PSI_r = pi_r - pt_r
            W18_r = calc_esal(aadt_r, truck_r, growth_r, years_r)
            D_slab = rigid_design(W18_r, R_r, S0_r, delta_PSI_r, Sc, Cd, J, Ec, k_r)

            st.session_state['rigid_results'] = {
                'W18': W18_r, 'D_slab': D_slab,
                'base': base_thick_r, 'subbase': subbase_thick_r,
                'inputs': {
                    'AADT': (f"{aadt_r:,}", 'คัน/วัน'),
                    'สัดส่วนรถบรรทุก': (f"{truck_r}", '%'),
                    'อัตราการเติบโต': (f"{growth_r}", '%/ปี'),
                    'อายุการออกแบบ': (f"{years_r}", 'ปี'),
                    'ความน่าเชื่อถือ R': (f"{R_r}", '%'),
                    'S₀': (f"{S0_r}", '-'),
                    'ΔPSI': (f"{delta_PSI_r:.1f}", '-'),
                    'Sc (Modulus of Rupture)': (f"{Sc}", 'psi'),
                    'Cd (Drainage Coeff.)': (f"{Cd}", '-'),
                    'J (Load Transfer)': (f"{J}", '-'),
                    'Ec': (f"{Ec:,}", 'psi'),
                    'k': (f"{k_r}", 'pci'),
                    'W18 (ESAL)': (f"{W18_r:,.0f}", 'ESAL'),
                }
            }

        if 'rigid_results' in st.session_state:
            rr = st.session_state['rigid_results']
            W18_r = rr['W18']; D_slab = rr['D_slab']
            base_thick_r = rr['base']; subbase_thick_r = rr['subbase']

            mc1r, mc2r = st.columns(2)
            mc1r.metric("📦 W18 (ESAL)", f"{W18_r:,.0f}")
            mc2r.metric("📏 ความหนาแผ่นคอนกรีต", f"{D_slab}\" / {inches_to_cm(D_slab)} cm")

            # Layer diagram
            st.markdown('<div class="result-card">', unsafe_allow_html=True)
            st.markdown("#### 🏗️ โครงสร้างชั้นทาง")

            rigid_layers = [
                ("🔲 Concrete Slab (แผ่นคอนกรีต)", D_slab, "#1e40af"),
            ]
            if base_thick_r > 0:
                rigid_layers.append(("🟤 Base Course (ชั้นรองพื้นทาง)", base_thick_r, "#78350f"))
            if subbase_thick_r > 0:
                rigid_layers.append(("🟡 Subbase (ชั้นรองฐานราก)", subbase_thick_r, "#b45309"))
            rigid_layers.append(("⬛ Subgrade (ดินรองพื้น)", None, "#6b7280"))

            total_in_r = D_slab + base_thick_r + subbase_thick_r
            for name, thick, color in rigid_layers:
                if thick is not None:
                    pct = int((thick / (total_in_r + 4)) * 100) + 20
                    st.markdown(f"""
                    <div class="layer-block" style="background:{color}; min-height:{pct}px;">
                        <span>{name}</span>
                        <span>{thick}" &nbsp;|&nbsp; {inches_to_cm(thick)} cm</span>
                    </div>""", unsafe_allow_html=True)
                else:
                    st.markdown(f"""
                    <div class="layer-block" style="background:{color}; min-height:28px; opacity:0.7;">
                        <span>{name}</span><span>∞</span>
                    </div>""", unsafe_allow_html=True)

            st.markdown("</div>", unsafe_allow_html=True)

            # Table
            st.markdown("#### 📊 ตารางสรุปความหนา")
            rows_r = [["Concrete Slab (แผ่นคอนกรีต)", f'{D_slab}"', f"{inches_to_cm(D_slab)} cm"]]
            if base_thick_r > 0:
                rows_r.append(["Base Course (ชั้นรองพื้นทาง)", f'{base_thick_r}"', f"{inches_to_cm(base_thick_r)} cm"])
            if subbase_thick_r > 0:
                rows_r.append(["Subbase (ชั้นรองฐานราก)", f'{subbase_thick_r}"', f"{inches_to_cm(subbase_thick_r)} cm"])
            rows_r.append([f"**รวม (Total)**", f"**{total_in_r}\"**", f"**{inches_to_cm(total_in_r)} cm**"])

            import pandas as pd
            df_r = pd.DataFrame(rows_r, columns=["ชั้นทาง", "ความหนา (นิ้ว)", "ความหนา (ซม.)"])
            st.dataframe(df_r, use_container_width=True, hide_index=True)

            if REPORTLAB_OK:
                pdf_rows_r = [
                    ["Concrete Slab (แผ่นคอนกรีต)", f'{D_slab}"', f"{inches_to_cm(D_slab)} cm"],
                ]
                if base_thick_r:
                    pdf_rows_r.append(["Base Course", f'{base_thick_r}"', f"{inches_to_cm(base_thick_r)} cm"])
                if subbase_thick_r:
                    pdf_rows_r.append(["Subbase", f'{subbase_thick_r}"', f"{inches_to_cm(subbase_thick_r)} cm"])
                pdf_rows_r.append(["รวม (Total)", f'{total_in_r}"', f"{inches_to_cm(total_in_r)} cm"])
                pdf_buf_r = generate_pdf("rigid", rr['inputs'], pdf_rows_r)
                st.download_button("📄 ดาวน์โหลด PDF Report", pdf_buf_r,
                                   file_name="rigid_pavement_design.pdf",
                                   mime="application/pdf", use_container_width=True)

# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown(
    "<small>📚 อ้างอิง: AASHTO Guide for Design of Pavement Structures, 1993 &nbsp;|&nbsp; "
    "⚠️ ผลการออกแบบนี้เป็นการประมาณเบื้องต้น ควรตรวจสอบโดยวิศวกรผู้เชี่ยวชาญ</small>",
    unsafe_allow_html=True
)
