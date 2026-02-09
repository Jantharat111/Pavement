import streamlit as st
import math
import pandas as pd

st.set_page_config(page_title="AASHTO 1993 Pavement Design", layout="wide")

st.title("🛣️ AASHTO 1993 Pavement Structure Number Calculator")
st.markdown("### คำนวณ Structure Number สำหรับผิวทางลาดยาง")

# Sidebar for inputs
st.sidebar.header("ข้อมูลการออกแบบ")

# Design inputs
st.sidebar.subheader("1. ข้อมูลจราจร")
w18 = st.sidebar.number_input(
    "18-kip ESAL (W₁₈)", 
    min_value=1e4, 
    max_value=1e8, 
    value=1e6, 
    format="%.2e",
    help="จำนวน 18-kip Equivalent Single Axle Load ตลอดอายุการใช้งาน"
)

st.sidebar.subheader("2. ระดับความเชื่อถือได้")
reliability = st.sidebar.slider(
    "Reliability (R) %", 
    min_value=50, 
    max_value=99, 
    value=95,
    help="ระดับความเชื่อถือได้ในการออกแบบ"
)

# Standard Normal Deviate (ZR) based on reliability
zr_values = {
    50: 0.000, 60: -0.253, 70: -0.524, 75: -0.674,
    80: -0.841, 85: -1.037, 90: -1.282, 95: -1.645,
    99: -2.327, 99.9: -3.090
}
zr = zr_values.get(reliability, -1.645)

st.sidebar.subheader("3. ค่าเบี่ยงเบนมาตรฐาน")
so = st.sidebar.number_input(
    "Overall Standard Deviation (S₀)", 
    min_value=0.30, 
    max_value=0.50, 
    value=0.45,
    help="ค่าเบี่ยงเบนมาตรฐานโดยรวม (Flexible pavement: 0.40-0.50)"
)

st.sidebar.subheader("4. ค่า Serviceability")
psi_initial = st.sidebar.number_input(
    "Initial Serviceability (p₀)", 
    min_value=3.0, 
    max_value=5.0, 
    value=4.2,
    help="ค่า serviceability เริ่มต้น"
)
psi_terminal = st.sidebar.number_input(
    "Terminal Serviceability (pₜ)", 
    min_value=1.5, 
    max_value=3.0, 
    value=2.5,
    help="ค่า serviceability ปลายทาง"
)
delta_psi = psi_initial - psi_terminal

st.sidebar.subheader("5. ค่า Subgrade และ Material")
mr = st.sidebar.number_input(
    "Resilient Modulus (MR) psi", 
    min_value=1000, 
    max_value=20000, 
    value=5000,
    help="ค่า Resilient Modulus ของ subgrade"
)

# Layer coefficients
st.sidebar.subheader("6. Layer Coefficients")
a1 = st.sidebar.number_input(
    "a₁ (Surface layer coefficient)", 
    min_value=0.20, 
    max_value=0.50, 
    value=0.44,
    help="ค่าสัมประสิทธิ์ชั้นผิวทางแอสฟัลต์"
)
a2 = st.sidebar.number_input(
    "a₂ (Base layer coefficient)", 
    min_value=0.07, 
    max_value=0.20, 
    value=0.14,
    help="ค่าสัมประสิทธิ์ชั้นฐานรอง"
)
a3 = st.sidebar.number_input(
    "a₃ (Subbase layer coefficient)", 
    min_value=0.05, 
    max_value=0.15, 
    value=0.11,
    help="ค่าสัมประสิทธิ์ชั้นฐานราก"
)

# Drainage coefficients
st.sidebar.subheader("7. Drainage Coefficients")
m2 = st.sidebar.number_input(
    "m₂ (Base drainage coefficient)", 
    min_value=0.80, 
    max_value=1.40, 
    value=1.0,
    help="ค่าสัมประสิทธิ์การระบายน้ำชั้นฐานรอง"
)
m3 = st.sidebar.number_input(
    "m₃ (Subbase drainage coefficient)", 
    min_value=0.80, 
    max_value=1.40, 
    value=1.0,
    help="ค่าสัมประสิทธิ์การระบายน้ำชั้นฐานราก"
)

# Main content
col1, col2 = st.columns([1, 1])

with col1:
    st.header("การคำนวณ Structure Number")
    
    # AASHTO 1993 equation
    st.markdown("### สมการ AASHTO 1993")
    st.latex(r'''
    \log_{10}(W_{18}) = Z_R \times S_0 + 9.36 \times \log_{10}(SN + 1) - 0.20 + 
    \frac{\log_{10}\left[\frac{\Delta PSI}{4.2 - 1.5}\right]}{0.40 + \frac{1094}{(SN + 1)^{5.19}}} + 2.32 \times \log_{10}(M_R) - 8.07
    ''')
    
    # Calculate SN using iterative method
    def calculate_sn(w18, zr, so, delta_psi, mr):
        """Calculate Structure Number using Newton-Raphson method"""
        sn = 5.0  # Initial guess
        tolerance = 0.001
        max_iterations = 100
        
        for i in range(max_iterations):
            # Calculate log(W18) from current SN
            term1 = zr * so
            term2 = 9.36 * math.log10(sn + 1) - 0.20
            term3 = math.log10(delta_psi / 2.7) / (0.40 + 1094 / ((sn + 1) ** 5.19))
            term4 = 2.32 * math.log10(mr) - 8.07
            
            calculated_log_w18 = term1 + term2 + term3 + term4
            target_log_w18 = math.log10(w18)
            
            error = target_log_w18 - calculated_log_w18
            
            if abs(error) < tolerance:
                return sn
            
            # Calculate derivative for Newton-Raphson
            d_term2 = 9.36 / ((sn + 1) * math.log(10))
            d_term3_numerator = -math.log10(delta_psi / 2.7) * 1094 * 5.19 * ((sn + 1) ** 4.19)
            d_term3_denominator = ((sn + 1) ** 10.38) * (0.40 + 1094 / ((sn + 1) ** 5.19)) ** 2
            d_term3 = d_term3_numerator / d_term3_denominator
            
            derivative = d_term2 + d_term3
            
            # Update SN
            sn = sn + error / derivative
            
            if sn < 0:
                sn = 0.1
        
        return sn
    
    try:
        sn_required = calculate_sn(w18, zr, so, delta_psi, mr)
        
        st.success(f"### Structure Number ที่ต้องการ: **{sn_required:.2f}**")
        
        # Display calculation details
        st.markdown("#### ค่าที่ใช้ในการคำนวณ:")
        calc_data = {
            'พารามิเตอร์': [
                'W₁₈ (ESAL)',
                'Reliability (R)',
                'Standard Normal Deviate (ZR)',
                'Overall Std. Deviation (S₀)',
                'Initial PSI (p₀)',
                'Terminal PSI (pₜ)',
                'ΔPSI',
                'Resilient Modulus (MR)'
            ],
            'ค่า': [
                f'{w18:.2e}',
                f'{reliability}%',
                f'{zr:.3f}',
                f'{so:.2f}',
                f'{psi_initial:.1f}',
                f'{psi_terminal:.1f}',
                f'{delta_psi:.1f}',
                f'{mr:,.0f} psi'
            ]
        }
        st.dataframe(pd.DataFrame(calc_data), hide_index=True, use_container_width=True)
        
    except Exception as e:
        st.error(f"เกิดข้อผิดพลาดในการคำนวณ: {str(e)}")
        sn_required = 0

with col2:
    st.header("การออกแบบความหนาชั้นทาง")
    
    st.markdown("### สมการ Structure Number")
    st.latex(r'SN = a_1 D_1 + a_2 D_2 m_2 + a_3 D_3 m_3')
    
    st.markdown("""
    โดยที่:
    - D₁ = ความหนาชั้นผิวทางแอสฟัลต์ (นิ้ว)
    - D₂ = ความหนาชั้นฐานรอง (นิ้ว)
    - D₃ = ความหนาชั้นฐานราก (นิ้ว)
    """)
    
    st.markdown("---")
    st.subheader("กำหนดความหนาชั้นทาง")
    
    col2_1, col2_2, col2_3 = st.columns(3)
    
    with col2_1:
        d1 = st.number_input("D₁ (นิ้ว)", min_value=0.0, max_value=20.0, value=5.0, step=0.5)
    with col2_2:
        d2 = st.number_input("D₂ (นิ้ว)", min_value=0.0, max_value=30.0, value=8.0, step=0.5)
    with col2_3:
        d3 = st.number_input("D₃ (นิ้ว)", min_value=0.0, max_value=30.0, value=8.0, step=0.5)
    
    # Calculate actual SN
    sn_actual = a1 * d1 + a2 * d2 * m2 + a3 * d3 * m3
    
    st.markdown(f"### Structure Number ที่ได้: **{sn_actual:.2f}**")
    
    # Check if design is adequate
    if sn_actual >= sn_required:
        st.success(f"✅ การออกแบบเหมาะสม (SN = {sn_actual:.2f} ≥ {sn_required:.2f})")
    else:
        deficit = sn_required - sn_actual
        st.error(f"❌ การออกแบบไม่เพียงพอ (ขาด {deficit:.2f})")
    
    # Show layer contributions
    st.markdown("#### สัดส่วน SN แต่ละชั้น:")
    sn1 = a1 * d1
    sn2 = a2 * d2 * m2
    sn3 = a3 * d3 * m3
    
    layer_data = {
        'ชั้นทาง': ['ผิวทาง (AC)', 'ฐานรอง (Base)', 'ฐานราก (Subbase)', 'รวม'],
        'SN': [f'{sn1:.2f}', f'{sn2:.2f}', f'{sn3:.2f}', f'{sn_actual:.2f}'],
        '% ของทั้งหมด': [
            f'{(sn1/sn_actual*100):.1f}%' if sn_actual > 0 else '0%',
            f'{(sn2/sn_actual*100):.1f}%' if sn_actual > 0 else '0%',
            f'{(sn3/sn_actual*100):.1f}%' if sn_actual > 0 else '0%',
            '100%'
        ]
    }
    st.dataframe(pd.DataFrame(layer_data), hide_index=True, use_container_width=True)
    
    # Convert to cm
    st.markdown("#### ความหนาเป็นเซนติเมตร:")
    cm_data = {
        'ชั้นทาง': ['ผิวทาง (AC)', 'ฐานรอง (Base)', 'ฐานราก (Subbase)'],
        'นิ้ว': [f'{d1:.1f}', f'{d2:.1f}', f'{d3:.1f}'],
        'เซนติเมตร': [f'{d1*2.54:.1f}', f'{d2*2.54:.1f}', f'{d3*2.54:.1f}']
    }
    st.dataframe(pd.DataFrame(cm_data), hide_index=True, use_container_width=True)

# Footer with references
st.markdown("---")
st.markdown("""
### คำแนะนำค่า Layer Coefficient (a) และ Drainage Coefficient (m)

**Layer Coefficients:**
- a₁ (Asphalt Concrete): 0.35 - 0.44
- a₂ (Crushed Stone Base): 0.10 - 0.14
- a₃ (Granular Subbase): 0.08 - 0.11

**Drainage Coefficients (m):**
- ดีเยี่ยม (Excellent): 1.40 - 1.35
- ดี (Good): 1.35 - 1.25
- ปานกลาง (Fair): 1.25 - 1.15
- แย่ (Poor): 1.15 - 1.05
- แย่มาก (Very Poor): 1.05 - 0.95

**อ้างอิง:** AASHTO Guide for Design of Pavement Structures, 1993
""")
