"""
Pavement Structure Design Tool - AASHTO 1993
Supports: Flexible Pavement & Rigid (Concrete) Pavement
With SVG cross-section diagram for each design result.
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
    REPORTLAB_OK = True
except ImportError:
    REPORTLAB_OK = False

# ══════════════════════════════════════════════════════════════════════════════
# AASHTO 1993 CALCULATION FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════

def calc_esal(aadt, truck_pct, growth_rate, design_years, ldf=0.5):
    trucks = aadt * (truck_pct / 100)
    gf = ((1 + growth_rate / 100) ** design_years - 1) / (growth_rate / 100) if growth_rate > 0 else design_years
    return trucks * 365 * gf * ldf


def flexible_design(W18, R, S0, delta_PSI, MR):
    ZR_table = {50: 0.000, 75: -0.674, 80: -0.842, 85: -1.037,
                90: -1.282, 95: -1.645, 99: -2.327}
    ZR = ZR_table.get(R, -1.282)

    def lhs(SN):
        return (ZR * S0
                + 9.36 * math.log10(SN + 1) - 0.20
                + math.log10(delta_PSI / (4.2 - 1.5)) / (0.40 + 1094 / (SN + 1) ** 5.19)
                + 2.32 * math.log10(MR) - 8.07)

    target = math.log10(W18)
    lo, hi = 0.5, 20.0
    for _ in range(100):
        mid = (lo + hi) / 2
        if lhs(mid) < target:
            lo = mid
        else:
            hi = mid
    return round((lo + hi) / 2, 2)


def sn_to_layers(SN, a1=0.44, a2=0.14, a3=0.11, m2=1.0, m3=1.0, D1_min=2.0, D2_min=4.0):
    D1 = max(D1_min, math.ceil(SN / a1 * 0.4))
    SN1 = a1 * D1
    SN_rem = SN - SN1
    D2 = max(D2_min, math.ceil(SN_rem / (a2 * m2)))
    SN2 = a2 * m2 * D2
    SN_rem2 = SN - SN1 - SN2
    D3 = max(0, math.ceil(SN_rem2 / (a3 * m3))) if SN_rem2 > 0 else 0
    return D1, D2, D3, SN1, SN2, a3 * m3 * D3


def rigid_design(W18, R, S0, delta_PSI, Sc, Cd, J, Ec, k):
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
        if lhs(mid) < target:
            lo = mid
        else:
            hi = mid
    return round((lo + hi) / 2, 1)


def inches_to_cm(inches):
    return round(inches * 2.54, 1)


# ══════════════════════════════════════════════════════════════════════════════
# SVG CROSS-SECTION DIAGRAM
# ══════════════════════════════════════════════════════════════════════════════

def make_svg_diagram(layers_data):
    """
    layers_data: list of dicts:
      name (str), name_en (str), thickness_in (float|None),
      fill, stroke, text_light (bool),
      dashed (bool, optional), pattern (str, optional)
    Last layer with thickness_in=None => subgrade (infinite).
    """
    SVG_W     = 700
    LEFT      = 150
    BAR_W     = 310
    LABEL_X   = LEFT + BAR_W + 14   # right bracket anchor
    TOP       = 30
    SUB_H     = 52                  # subgrade display height
    PX_PER_IN = 18                  # scale: pixels per inch

    known = [l for l in layers_data if l.get('thickness_in') is not None]
    total_in = sum(l['thickness_in'] for l in known)
    DRAW_H = max(280, int(total_in * PX_PER_IN))

    # proportional pixel heights
    for l in known:
        l['_h'] = max(28, int((l['thickness_in'] / total_in) * DRAW_H))
    diff = DRAW_H - sum(l['_h'] for l in known)
    if known:
        known[-1]['_h'] += diff

    for l in layers_data:
        if l.get('thickness_in') is None:
            l['_h'] = SUB_H

    # Y positions
    y = TOP
    for l in layers_data:
        l['_y'] = y
        y += l['_h']

    SVG_H = y + 36

    out = []
    out.append(f'<svg width="100%" viewBox="0 0 {SVG_W} {SVG_H}" '
               f'xmlns="http://www.w3.org/2000/svg" style="font-family:sans-serif;">')

    # ── Patterns ──────────────────────────────────────────────────────────────
    out.append('<defs>')
    out.append('''<pattern id="p-asphalt" patternUnits="userSpaceOnUse" width="12" height="12">
  <line x1="0" y1="12" x2="12" y2="0" stroke="#000" stroke-width="1" opacity="0.14"/>
</pattern>
<pattern id="p-concrete" patternUnits="userSpaceOnUse" width="38" height="1">
  <line x1="0" y1="0" x2="0" y2="100" stroke="#9aa0a8" stroke-width="0.8"
        opacity="0.45" stroke-dasharray="4 3"/>
</pattern>
<pattern id="p-gravel" patternUnits="userSpaceOnUse" width="14" height="10">
  <circle cx="4"  cy="4"  r="1.6" fill="#5a4020" opacity="0.20"/>
  <circle cx="10" cy="7"  r="1.2" fill="#5a4020" opacity="0.15"/>
  <circle cx="2"  cy="8"  r="0.9" fill="#5a4020" opacity="0.12"/>
</pattern>
<pattern id="p-soil" patternUnits="userSpaceOnUse" width="22" height="10">
  <path d="M0 6 Q5.5 3 11 6 Q16.5 9 22 6" fill="none"
        stroke="#6b4c1e" stroke-width="0.9" opacity="0.28"/>
</pattern>''')
    out.append('</defs>')

    # ── Road surface bar ───────────────────────────────────────────────────
    road_y = TOP - 16
    out.append(f'<rect x="{LEFT}" y="{road_y}" width="{BAR_W}" height="16" '
               f'fill="#111" rx="3"/>')
    out.append(f'<text x="{LEFT + BAR_W/2:.0f}" y="{road_y + 10}" '
               f'text-anchor="middle" font-size="9" fill="#888" letter-spacing="2">'
               f'▶  ROAD SURFACE  ◀</text>')

    # ── Draw layers ────────────────────────────────────────────────────────
    for i, l in enumerate(layers_data):
        yy   = l['_y']
        h    = l['_h']
        is_sg = l.get('thickness_in') is None
        dash  = 'stroke-dasharray="6 3"' if l.get('dashed') else ''

        # Base fill
        out.append(f'<rect x="{LEFT}" y="{yy}" width="{BAR_W}" height="{h}" '
                   f'fill="{l["fill"]}" stroke="{l["stroke"]}" stroke-width="1.2" {dash}/>')

        # Texture
        pat = l.get('pattern')
        if pat and h > 8:
            out.append(f'<rect x="{LEFT}" y="{yy}" width="{BAR_W}" height="{h}" '
                       f'fill="url(#p-{pat})" stroke="none"/>')

        # Subgrade hatch lines at bottom
        if is_sg:
            for hx in range(LEFT, LEFT + BAR_W + 1, 14):
                out.append(f'<line x1="{hx}" y1="{yy+h}" x2="{hx+10}" y2="{yy+h-10}" '
                           f'stroke="{l["stroke"]}" stroke-width="1.1" opacity="0.35"/>')

        # Text inside bar
        tc = '#ffffff' if l.get('text_light') else '#1a1208'
        cx = LEFT + BAR_W / 2
        cy = yy + h / 2

        if h >= 36:
            out.append(f'<text x="{cx:.1f}" y="{cy - 8:.1f}" text-anchor="middle" '
                       f'dominant-baseline="central" font-size="12" font-weight="700" fill="{tc}">'
                       f'{l["name_en"]}</text>')
            out.append(f'<text x="{cx:.1f}" y="{cy + 9:.1f}" text-anchor="middle" '
                       f'dominant-baseline="central" font-size="10" fill="{tc}" opacity="0.88">'
                       f'{l["name"]}</text>')
        elif h >= 20:
            out.append(f'<text x="{cx:.1f}" y="{cy:.1f}" text-anchor="middle" '
                       f'dominant-baseline="central" font-size="11" font-weight="700" fill="{tc}">'
                       f'{l["name_en"]}</text>')

        # ── Right bracket + thickness label ─────────────────────────────
        if not is_sg:
            bx  = LEFT + BAR_W
            brx = LABEL_X + 5
            midy = yy + h / 2
            out.append(f'<line x1="{bx}" y1="{yy+1}"   x2="{brx}" y2="{yy+1}"   stroke="#aaa" stroke-width="0.7"/>')
            out.append(f'<line x1="{bx}" y1="{yy+h-1}" x2="{brx}" y2="{yy+h-1}" stroke="#aaa" stroke-width="0.7"/>')
            out.append(f'<line x1="{brx}" y1="{yy+1}"  x2="{brx}" y2="{yy+h-1}" stroke="#aaa" stroke-width="0.7"/>')

            th_in = l['thickness_in']
            th_cm = inches_to_cm(th_in)
            lx2 = brx + 10

            if h >= 34:
                out.append(f'<text x="{lx2}" y="{midy - 8:.1f}" dominant-baseline="central" '
                           f'font-size="14" font-weight="700" fill="#1a3a6b">{th_in}"</text>')
                out.append(f'<text x="{lx2}" y="{midy + 9:.1f}" dominant-baseline="central" '
                           f'font-size="11" fill="#555">{th_cm} cm</text>')
            else:
                out.append(f'<text x="{lx2}" y="{midy:.1f}" dominant-baseline="central" '
                           f'font-size="11" font-weight="700" fill="#1a3a6b">'
                           f'{th_in}" / {th_cm} cm</text>')

    # ── Left depth axis ────────────────────────────────────────────────────
    axis_bot = TOP + DRAW_H
    out.append(f'<line x1="{LEFT}" y1="{TOP}" x2="{LEFT}" y2="{axis_bot}" '
               f'stroke="#ccc" stroke-width="1"/>')
    out.append(f'<text x="{LEFT - 6}" y="{TOP}" text-anchor="end" dominant-baseline="central" '
               f'font-size="9" fill="#aaa">0"</text>')
    cum = 0
    for l in known:
        cum += l['thickness_in']
        ty = l['_y'] + l['_h']
        out.append(f'<line x1="{LEFT-4}" y1="{ty}" x2="{LEFT}" y2="{ty}" stroke="#ccc" stroke-width="1"/>')
        out.append(f'<text x="{LEFT-6}" y="{ty}" text-anchor="end" dominant-baseline="central" '
                   f'font-size="9" fill="#aaa">{cum}"</text>')

    # ── Total label ────────────────────────────────────────────────────────
    total_cm = inches_to_cm(total_in)
    bot_label_y = TOP + DRAW_H + 22
    out.append(f'<rect x="{LEFT}" y="{TOP + DRAW_H + 6}" width="{BAR_W}" height="22" '
               f'fill="#1a3a6b" rx="4"/>')
    out.append(f'<text x="{LEFT + BAR_W/2:.0f}" y="{bot_label_y}" text-anchor="middle" '
               f'dominant-baseline="central" font-size="12" font-weight="700" fill="#fff">'
               f'รวมโครงสร้างทาง: {total_in}" = {total_cm} cm</text>')

    out.append('</svg>')
    return '\n'.join(out)


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
                                 fontSize=16, textColor=colors.HexColor('#1a3a6b'), spaceAfter=6)
    h2_style = ParagraphStyle('H2', parent=styles['Heading2'],
                               fontSize=12, textColor=colors.HexColor('#2563eb'),
                               spaceBefore=12, spaceAfter=4)
    normal = styles['Normal']
    normal.fontSize = 10

    story = []
    story.append(Paragraph("รายงานการออกแบบโครงสร้างผิวทาง", title_style))
    story.append(Paragraph("Pavement Structure Design Report — AASHTO 1993", styles['Heading3']))
    story.append(Paragraph(f"วันที่ออกแบบ: {datetime.now().strftime('%d/%m/%Y %H:%M')}", normal))
    story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor('#2563eb')))
    story.append(Spacer(1, 0.3*cm))

    dtype_th = "ผิวทางคอนกรีต (Rigid)" if design_type == "rigid" else "ผิวทางยืดหยุ่น (Flexible)"
    story.append(Paragraph(f"ประเภทโครงสร้าง: {dtype_th}", h2_style))
    story.append(Spacer(1, 0.2*cm))

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
    h1 { color: #1a3a6b !important; }
    .stButton > button {
        background: #2563eb; color: white; border-radius: 8px;
        font-weight: 600; padding: 0.5rem 1.5rem;
    }
    .stButton > button:hover { background: #1d4ed8; }
    .section-title { color: #1e40af; font-weight: 700; font-size: 16px; margin-bottom: 8px; }
    .svg-wrap { background: #fff; border-radius: 14px; padding: 16px;
                box-shadow: 0 2px 12px rgba(0,0,0,.08); margin-bottom: 12px; }
</style>
""", unsafe_allow_html=True)

st.markdown("# 🛣️ ระบบออกแบบโครงสร้างผิวทาง — AASHTO 1993")
st.markdown("**Pavement Structure Design Tool** | ผิวทางคอนกรีตและผิวทางยืดหยุ่น ตามมาตรฐาน AASHTO 1993")
st.markdown("---")

tab1, tab2 = st.tabs(["🔩 ผิวทางยืดหยุ่น (Flexible)", "🏗️ ผิวทางคอนกรีต (Rigid)"])

# ════════════════════════════════════════════════
# TAB 1 — FLEXIBLE
# ════════════════════════════════════════════════
with tab1:
    col_in, col_out = st.columns([1, 1], gap="large")

    with col_in:
        st.markdown("### 📋 ข้อมูลนำเข้า")
        st.markdown('<p class="section-title">🚗 ปริมาณจราจรและอายุการออกแบบ</p>', unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        with c1:
            aadt_f  = st.number_input("AADT (คัน/วัน)", 1000, 200000, 10000, 500, key="aadt_f")
            truck_f = st.slider("สัดส่วนรถบรรทุก (%)", 5, 60, 20, key="truck_f")
        with c2:
            growth_f = st.number_input("อัตราการเติบโต (%/ปี)", 0.0, 10.0, 3.0, 0.5, key="growth_f")
            years_f  = st.selectbox("อายุการออกแบบ (ปี)", [10, 15, 20, 25, 30], index=2, key="years_f")

        st.markdown('<p class="section-title">📊 พารามิเตอร์การออกแบบ</p>', unsafe_allow_html=True)
        c3, c4 = st.columns(2)
        with c3:
            R_f  = st.selectbox("ความน่าเชื่อถือ R (%)", [75, 80, 85, 90, 95, 99], index=3, key="R_f")
            S0_f = st.number_input("S₀", 0.30, 0.50, 0.45, 0.01, key="S0_f")
        with c4:
            pi_f = st.number_input("PSI เริ่มต้น (p₀)", 3.5, 5.0, 4.2, 0.1, key="pi_f")
            pt_f = st.number_input("PSI สิ้นสุด (pₜ)", 1.5, 3.0, 2.5, 0.1, key="pt_f")

        st.markdown('<p class="section-title">🌍 คุณสมบัติดินรองพื้น</p>', unsafe_allow_html=True)
        MR_f  = st.number_input("MR (psi)", 2000, 30000, 7500, 500, key="MR_f")
        CBR_f = st.number_input("CBR (%)", 1, 30, 8, 1, key="CBR_f")
        if st.checkbox("คำนวณ MR จาก CBR อัตโนมัติ", key="use_cbr_f"):
            MR_f = 1500 * CBR_f
            st.info(f"MR = 1500 × {CBR_f} = **{MR_f:,} psi**")

        st.markdown('<p class="section-title">🧱 สัมประสิทธิ์ชั้นทาง</p>', unsafe_allow_html=True)
        c5, c6, c7 = st.columns(3)
        with c5: a1 = st.number_input("a₁ (AC)", 0.30, 0.50, 0.44, 0.01, key="a1")
        with c6: a2 = st.number_input("a₂ (Base)", 0.10, 0.20, 0.14, 0.01, key="a2")
        with c7: a3 = st.number_input("a₃ (Sub)", 0.08, 0.14, 0.11, 0.01, key="a3")

        calc_btn_f = st.button("🔍 คำนวณออกแบบผิวทางยืดหยุ่น", use_container_width=True, key="calc_f")

    with col_out:
        st.markdown("### 📐 ผลการออกแบบ")

        if calc_btn_f:
            delta_PSI_f = pi_f - pt_f
            W18_f = calc_esal(aadt_f, truck_f, growth_f, years_f)
            SN = flexible_design(W18_f, R_f, S0_f, delta_PSI_f, MR_f)
            D1, D2, D3, SN1, SN2, SN3 = sn_to_layers(SN, a1, a2, a3)
            st.session_state['flex_results'] = {
                'W18': W18_f, 'SN': SN, 'D1': D1, 'D2': D2, 'D3': D3,
                'inputs': {
                    'AADT': (f"{aadt_f:,}", 'คัน/วัน'),
                    'สัดส่วนรถบรรทุก': (f"{truck_f}", '%'),
                    'อัตราการเติบโต': (f"{growth_f}", '%/ปี'),
                    'อายุการออกแบบ': (f"{years_f}", 'ปี'),
                    'R': (f"{R_f}", '%'), 'S₀': (f"{S0_f}", '-'),
                    'DELTA_PSI': (f"{delta_PSI_f:.1f}", '-'), 'MR': (f"{MR_f:,}", 'psi'),
                    'a1/a2/a3': (f"{a1}/{a2}/{a3}", '-'),
                    'W18 (ESAL)': (f"{W18_f:,.0f}", 'ESAL'),
                    'Structural Number (SN)': (f"{SN}", '-'),
                }
            }

        if 'flex_results' in st.session_state:
            r   = st.session_state['flex_results']
            W18_f = r['W18']; SN = r['SN']
            D1 = r['D1']; D2 = r['D2']; D3 = r['D3']

            mc1, mc2 = st.columns(2)
            mc1.metric("W18 (ESAL)", f"{W18_f:,.0f}")
            mc2.metric("Structural Number (SN)", f"{SN}")

            # ── SVG cross-section diagram ──────────────────────────────
            layers_flex = [
                dict(name="ผิวแอสฟัลต์", name_en="AC Surface",
                     thickness_in=D1, fill="#2c2c2c", stroke="#111",
                     text_light=True, pattern="asphalt"),
                dict(name="ชั้นรองพื้นทาง", name_en="Granular Base",
                     thickness_in=D2, fill="#8B5E3C", stroke="#6b4528",
                     text_light=True, pattern="gravel"),
            ]
            if D3 > 0:
                layers_flex.append(dict(
                    name="ชั้นรองฐานราก", name_en="Granular Subbase",
                    thickness_in=D3, fill="#C49A6C", stroke="#a07848",
                    text_light=False, pattern="gravel"))
            layers_flex.append(dict(
                name="ดินรองพื้น", name_en="Subgrade",
                thickness_in=None, fill="#B5936A", stroke="#8f7050",
                text_light=False, dashed=True, pattern="soil"))

            st.markdown("#### 🖼️ แผนภาพโครงสร้างชั้นทาง")
            st.markdown('<div class="svg-wrap">', unsafe_allow_html=True)
            st.markdown(make_svg_diagram(layers_flex), unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)

            # Summary table
            st.markdown("#### 📊 ตารางสรุปความหนา")
            import pandas as pd
            total_in = D1 + D2 + D3
            rows = [
                ["AC Surface (ผิวแอสฟัลต์)", f'{D1}"', f"{inches_to_cm(D1)} cm"],
                ["Granular Base (ชั้นรองพื้นทาง)", f'{D2}"', f"{inches_to_cm(D2)} cm"],
            ]
            if D3 > 0:
                rows.append(["Granular Subbase (ชั้นรองฐานราก)", f'{D3}"', f"{inches_to_cm(D3)} cm"])
            rows.append(["รวม (Total)", f'{total_in}"', f"{inches_to_cm(total_in)} cm"])
            df = pd.DataFrame(rows, columns=["ชั้นทาง", "ความหนา (นิ้ว)", "ความหนา (ซม.)"])
            st.dataframe(df, use_container_width=True, hide_index=True)

            if REPORTLAB_OK:
                pdf_buf = generate_pdf("flexible", r['inputs'], rows)
                st.download_button("📄 ดาวน์โหลด PDF Report", pdf_buf,
                                   file_name="flexible_pavement_design.pdf",
                                   mime="application/pdf", use_container_width=True)


# ════════════════════════════════════════════════
# TAB 2 — RIGID
# ════════════════════════════════════════════════
with tab2:
    col_in2, col_out2 = st.columns([1, 1], gap="large")

    with col_in2:
        st.markdown("### 📋 ข้อมูลนำเข้า")
        st.markdown('<p class="section-title">🚗 ปริมาณจราจรและอายุการออกแบบ</p>', unsafe_allow_html=True)
        c1r, c2r = st.columns(2)
        with c1r:
            aadt_r  = st.number_input("AADT (คัน/วัน)", 1000, 200000, 10000, 500, key="aadt_r")
            truck_r = st.slider("สัดส่วนรถบรรทุก (%)", 5, 60, 20, key="truck_r")
        with c2r:
            growth_r = st.number_input("อัตราการเติบโต (%/ปี)", 0.0, 10.0, 3.0, 0.5, key="growth_r")
            years_r  = st.selectbox("อายุการออกแบบ (ปี)", [10, 15, 20, 25, 30], index=2, key="years_r")

        st.markdown('<p class="section-title">📊 พารามิเตอร์การออกแบบ</p>', unsafe_allow_html=True)
        c3r, c4r = st.columns(2)
        with c3r:
            R_r  = st.selectbox("ความน่าเชื่อถือ R (%)", [75, 80, 85, 90, 95, 99], index=3, key="R_r")
            S0_r = st.number_input("S₀", 0.30, 0.40, 0.35, 0.01, key="S0_r")
        with c4r:
            pi_r = st.number_input("PSI เริ่มต้น (p₀)", 3.5, 5.0, 4.5, 0.1, key="pi_r")
            pt_r = st.number_input("PSI สิ้นสุด (pₜ)", 2.0, 3.5, 2.5, 0.1, key="pt_r")

        st.markdown('<p class="section-title">🏗️ คุณสมบัติคอนกรีต</p>', unsafe_allow_html=True)
        c5r, c6r = st.columns(2)
        with c5r:
            Sc = st.number_input("Sc — Modulus of Rupture (psi)", 400, 1000, 650, 10, key="Sc")
            Ec = st.number_input("Ec — Elastic Modulus (psi)", 2000000, 6000000, 4000000, 100000,
                                  key="Ec", format="%d")
        with c6r:
            Cd = st.number_input("Cd — Drainage Coefficient", 0.70, 1.25, 1.00, 0.05, key="Cd")
            J  = st.number_input("J — Load Transfer", 2.5, 4.5, 3.2, 0.1, key="J")

        st.markdown('<p class="section-title">🌍 ค่า k ดินรองพื้น</p>', unsafe_allow_html=True)
        k_r   = st.number_input("k — Subgrade Reaction (pci)", 50, 500, 150, 10, key="k_r")
        CBR_r = st.number_input("CBR (%)", 1, 30, 8, 1, key="CBR_r")
        if st.checkbox("ประมาณ k จาก CBR (k ≈ 10×CBR)", key="use_cbr_r"):
            k_r = 10 * CBR_r
            st.info(f"k ≈ 10 × {CBR_r} = **{k_r} pci**")

        st.markdown('<p class="section-title">🧱 ชั้นรองพื้น (Optional)</p>', unsafe_allow_html=True)
        with st.expander("กำหนดชั้นรองคอนกรีต"):
            has_base        = st.checkbox("มีชั้น Base", value=True, key="has_base_r")
            base_thick_r    = st.number_input("ความหนา Base (นิ้ว)", 4, 16, 6, 1, key="base_r") if has_base else 0
            has_subbase     = st.checkbox("มีชั้น Subbase", value=False, key="has_sub_r")
            subbase_thick_r = st.number_input("ความหนา Subbase (นิ้ว)", 4, 16, 6, 1, key="subbase_r") if has_subbase else 0

        calc_btn_r = st.button("🔍 คำนวณออกแบบผิวทางคอนกรีต", use_container_width=True, key="calc_r")

    with col_out2:
        st.markdown("### 📐 ผลการออกแบบ")

        if calc_btn_r:
            delta_PSI_r = pi_r - pt_r
            W18_r  = calc_esal(aadt_r, truck_r, growth_r, years_r)
            D_slab = rigid_design(W18_r, R_r, S0_r, delta_PSI_r, Sc, Cd, J, Ec, k_r)
            st.session_state['rigid_results'] = {
                'W18': W18_r, 'D_slab': D_slab,
                'base': base_thick_r, 'subbase': subbase_thick_r,
                'inputs': {
                    'AADT': (f"{aadt_r:,}", 'คัน/วัน'),
                    'สัดส่วนรถบรรทุก': (f"{truck_r}", '%'),
                    'อัตราการเติบโต': (f"{growth_r}", '%/ปี'),
                    'อายุการออกแบบ': (f"{years_r}", 'ปี'),
                    'R': (f"{R_r}", '%'), 'S₀': (f"{S0_r}", '-'),
                    'DELTA_PSI': (f"{delta_PSI_r:.1f}", '-'),
                    'Sc': (f"{Sc}", 'psi'), 'Cd': (f"{Cd}", '-'),
                    'J': (f"{J}", '-'), 'Ec': (f"{Ec:,}", 'psi'),
                    'k': (f"{k_r}", 'pci'),
                    'W18 (ESAL)': (f"{W18_r:,.0f}", 'ESAL'),
                }
            }

        if 'rigid_results' in st.session_state:
            rr = st.session_state['rigid_results']
            W18_r = rr['W18']; D_slab = rr['D_slab']
            base_thick_r = rr['base']; subbase_thick_r = rr['subbase']

            mc1r, mc2r = st.columns(2)
            mc1r.metric("W18 (ESAL)", f"{W18_r:,.0f}")
            mc2r.metric("ความหนา Slab", f'{D_slab}" / {inches_to_cm(D_slab)} cm')

            # ── SVG cross-section diagram ──────────────────────────────
            layers_rigid = [
                dict(name="แผ่นคอนกรีต", name_en="Concrete Slab",
                     thickness_in=D_slab, fill="#C0C5CC", stroke="#8c9199",
                     text_light=False, pattern="concrete"),
            ]
            if base_thick_r > 0:
                layers_rigid.append(dict(
                    name="ชั้นรองพื้นทาง", name_en="Base Course",
                    thickness_in=base_thick_r, fill="#8B5E3C", stroke="#6b4528",
                    text_light=True, pattern="gravel"))
            if subbase_thick_r > 0:
                layers_rigid.append(dict(
                    name="ชั้นรองฐานราก", name_en="Subbase",
                    thickness_in=subbase_thick_r, fill="#C49A6C", stroke="#a07848",
                    text_light=False, pattern="gravel"))
            layers_rigid.append(dict(
                name="ดินรองพื้น", name_en="Subgrade",
                thickness_in=None, fill="#B5936A", stroke="#8f7050",
                text_light=False, dashed=True, pattern="soil"))

            st.markdown("#### 🖼️ แผนภาพโครงสร้างชั้นทาง")
            st.markdown('<div class="svg-wrap">', unsafe_allow_html=True)
            st.markdown(make_svg_diagram(layers_rigid), unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)

            # Table
            st.markdown("#### 📊 ตารางสรุปความหนา")
            import pandas as pd
            total_in_r = D_slab + base_thick_r + subbase_thick_r
            rows_r = [["Concrete Slab (แผ่นคอนกรีต)", f'{D_slab}"', f"{inches_to_cm(D_slab)} cm"]]
            if base_thick_r > 0:
                rows_r.append(["Base Course (ชั้นรองพื้นทาง)", f'{base_thick_r}"', f"{inches_to_cm(base_thick_r)} cm"])
            if subbase_thick_r > 0:
                rows_r.append(["Subbase (ชั้นรองฐานราก)", f'{subbase_thick_r}"', f"{inches_to_cm(subbase_thick_r)} cm"])
            rows_r.append(["รวม (Total)", f'{total_in_r}"', f"{inches_to_cm(total_in_r)} cm"])
            df_r = pd.DataFrame(rows_r, columns=["ชั้นทาง", "ความหนา (นิ้ว)", "ความหนา (ซม.)"])
            st.dataframe(df_r, use_container_width=True, hide_index=True)

            if REPORTLAB_OK:
                pdf_buf_r = generate_pdf("rigid", rr['inputs'], rows_r)
                st.download_button("📄 ดาวน์โหลด PDF Report", pdf_buf_r,
                                   file_name="rigid_pavement_design.pdf",
                                   mime="application/pdf", use_container_width=True)

# Footer
st.markdown("---")
st.markdown(
    "<small>📚 อ้างอิง: AASHTO Guide for Design of Pavement Structures, 1993 &nbsp;|&nbsp; "
    "⚠️ ผลการออกแบบนี้เป็นการประมาณเบื้องต้น ควรตรวจสอบโดยวิศวกรผู้เชี่ยวชาญ</small>",
    unsafe_allow_html=True
)
