"""
============================================================
  การออกแบบผิวทางคอนกรีต (Rigid Pavement Design)
  ตามมาตรฐาน AASHTO 1993
============================================================
  อ้างอิง: AASHTO Guide for Design of Pavement Structures, 1993
============================================================
"""

import math


# ─────────────────────────────────────────────
# 1. ฟังก์ชันหลัก: คำนวณหา Slab Thickness (D)
# ─────────────────────────────────────────────

def design_rigid_pavement(
    W18: float,
    ZR: float,
    S0: float,
    delta_PSI: float,
    Sc: float,
    Cd: float,
    J: float,
    Ec: float,
    k: float,
    tol: float = 1e-4,
    D_min: float = 100.0,
    D_max: float = 600.0
) -> dict:
    """
    ออกแบบความหนาแผ่นคอนกรีต (Rigid Pavement) ตาม AASHTO 1993

    สมการหลัก:
    log10(W18) = ZR*S0 + 7.35*log10(D+1) - 0.06
                 + [log10(delta_PSI/(4.5-1.5))] / [1 + 1.624e7/(D+1)^8.46]
                 + (4.22 - 0.32*pt) * log10[ Sc*Cd*(D^0.75 - 1.132) /
                   (215.63*J*(D^0.75 - 18.42/(Ec/k)^0.25)) ]

    Parameters
    ----------
    W18        : จำนวนแกนมาตรฐาน 18-kip (ESAL) ตลอดอายุการใช้งาน
    ZR         : ค่า Standard Normal Deviate (ขึ้นกับ Reliability)
    S0         : Combined Standard Error (ปกติ 0.30-0.40 สำหรับ Rigid)
    delta_PSI  : ความต่างของ PSI (pi - pt), ปกติ pi=4.5, pt=2.5 → delta_PSI=2.0
    Sc         : Modulus of Rupture ของคอนกรีต (psi)
    Cd         : Drainage Coefficient
    J          : Load Transfer Coefficient
    Ec         : Elastic Modulus ของคอนกรีต (psi)
    k          : Modulus of Subgrade Reaction (pci)
    tol        : ความแม่นยำในการ iterate (นิ้ว)
    D_min/max  : ขอบเขตการค้นหาความหนา (มม.)

    Returns
    -------
    dict ผลลัพธ์การออกแบบ
    """

    pt = 4.5 - delta_PSI  # Terminal Serviceability

    def log10_W18_calc(D_mm: float) -> float:
        """คำนวณ log10(W18) จากความหนา D (มม.) → แปลงเป็นนิ้วก่อน"""
        D = D_mm / 25.4  # มม. → นิ้ว

        term1 = ZR * S0
        term2 = 7.35 * math.log10(D + 1) - 0.06
        term3_num = math.log10(delta_PSI / (4.5 - 1.5))
        term3_den = 1 + (1.624e7 / (D + 1) ** 8.46)
        term3 = term3_num / term3_den

        # ตรวจสอบ argument ของ log ให้เป็นบวก
        inner_num = Sc * Cd * (D ** 0.75 - 1.132)
        inner_den = 215.63 * J * (D ** 0.75 - 18.42 / (Ec / k) ** 0.25)

        if inner_num <= 0 or inner_den <= 0:
            return -999  # ค่าไม่ถูกต้อง

        term4 = (4.22 - 0.32 * pt) * math.log10(inner_num / inner_den)
        return term1 + term2 + term3 + term4

    target = math.log10(W18)

    # Binary Search หาค่า D
    lo, hi = D_min, D_max
    D_solution = None

    for _ in range(200):
        mid = (lo + hi) / 2.0
        val = log10_W18_calc(mid)

        if abs(val - target) < tol:
            D_solution = mid
            break

        if val < target:
            lo = mid
        else:
            hi = mid

    if D_solution is None:
        D_solution = (lo + hi) / 2.0

    D_inch = D_solution / 25.4
    D_rounded_mm = math.ceil(D_solution / 5) * 5  # ปัดขึ้นทุก 5 มม.

    return {
        "D_mm":         round(D_solution, 1),
        "D_inch":       round(D_inch, 2),
        "D_design_mm":  D_rounded_mm,
        "W18":          W18,
        "log10_W18":    round(target, 4),
        "log10_W18_check": round(log10_W18_calc(D_solution), 4),
        "ZR":           ZR,
        "S0":           S0,
        "delta_PSI":    delta_PSI,
        "pt":           pt,
        "Sc_psi":       Sc,
        "Cd":           Cd,
        "J":            J,
        "Ec_psi":       Ec,
        "k_pci":        k,
    }


# ─────────────────────────────────────────────
# 2. ฟังก์ชันช่วย: แปลงค่า Reliability → ZR
# ─────────────────────────────────────────────

RELIABILITY_TABLE = {
    50:  -0.000,
    60:  -0.253,
    70:  -0.524,
    75:  -0.674,
    80:  -0.842,
    85:  -1.037,
    90:  -1.282,
    91:  -1.340,
    92:  -1.405,
    93:  -1.476,
    94:  -1.555,
    95:  -1.645,
    96:  -1.751,
    97:  -1.881,
    98:  -2.054,
    99:  -2.327,
    99.9:-3.090,
}

def get_ZR(reliability_percent: float) -> float:
    """แปลงค่า Reliability (%) เป็น ZR"""
    if reliability_percent in RELIABILITY_TABLE:
        return RELIABILITY_TABLE[reliability_percent]
    # interpolate
    keys = sorted(RELIABILITY_TABLE.keys())
    for i in range(len(keys) - 1):
        r1, r2 = keys[i], keys[i + 1]
        if r1 <= reliability_percent <= r2:
            t = (reliability_percent - r1) / (r2 - r1)
            return RELIABILITY_TABLE[r1] + t * (RELIABILITY_TABLE[r2] - RELIABILITY_TABLE[r1])
    raise ValueError(f"Reliability {reliability_percent}% อยู่นอกช่วง 50–99.9%")


# ─────────────────────────────────────────────
# 3. ฟังก์ชันช่วย: คำนวณ ESAL (Equivalent Single Axle Load)
# ─────────────────────────────────────────────

def truck_factor_rigid(axle_load_kip: float, axle_type: str = "single") -> float:
    """
    คำนวณ Truck Factor (LEF) สำหรับผิวทางแข็ง
    ใช้สูตรประมาณของ AASHTO

    axle_type: 'single' หรือ 'tandem'
    """
    if axle_type == "single":
        return (axle_load_kip / 18.0) ** 4.5
    elif axle_type == "tandem":
        return (axle_load_kip / 36.0) ** 4.5
    else:
        raise ValueError("axle_type ต้องเป็น 'single' หรือ 'tandem'")


def compute_W18(ADT: float, truck_percent: float, T_factor: float,
                growth_rate: float, design_life: int,
                lane_dist: float = 1.0, direction_dist: float = 0.5) -> float:
    """
    คำนวณจำนวน ESAL รวมตลอดอายุการใช้งาน

    Parameters
    ----------
    ADT           : ปริมาณจราจรเฉลี่ยรายวัน (คัน/วัน)
    truck_percent : สัดส่วนรถบรรทุก (0-1)
    T_factor      : Truck Factor เฉลี่ย
    growth_rate   : อัตราการเติบโต (0-1) เช่น 0.03 = 3%
    design_life   : อายุการออกแบบ (ปี)
    lane_dist     : Lane Distribution Factor (0-1)
    direction_dist: Directional Distribution Factor (0-1)
    """
    ADTT = ADT * truck_percent  # Average Daily Truck Traffic
    GF = ((1 + growth_rate) ** design_life - 1) / growth_rate if growth_rate > 0 else design_life
    W18 = ADTT * T_factor * 365 * GF * lane_dist * direction_dist
    return W18


# ─────────────────────────────────────────────
# 4. ฟังก์ชันแสดงผล
# ─────────────────────────────────────────────

def print_results(result: dict, project_name: str = "โครงการออกแบบผิวทางคอนกรีต"):
    line = "=" * 60
    print(f"\n{line}")
    print(f"  {project_name}")
    print(f"  การออกแบบผิวทางคอนกรีต (Rigid Pavement) - AASHTO 1993")
    print(line)
    print(f"\n{'─'*60}")
    print("  ข้อมูลนำเข้า (Input Parameters)")
    print(f"{'─'*60}")
    print(f"  ESAL (W18)                    : {result['W18']:,.0f} แกน")
    print(f"  log10(W18)                    : {result['log10_W18']:.4f}")
    print(f"  ZR (Standard Normal Deviate)  : {result['ZR']:.3f}")
    print(f"  S0 (Combined Std. Error)      : {result['S0']:.2f}")
    print(f"  ΔPSI (delta_PSI)              : {result['delta_PSI']:.1f}")
    print(f"  pt (Terminal Serviceability)  : {result['pt']:.1f}")
    print(f"  Sc (Modulus of Rupture)       : {result['Sc_psi']:,.0f} psi")
    print(f"  Cd (Drainage Coefficient)     : {result['Cd']:.2f}")
    print(f"  J  (Load Transfer Coeff.)     : {result['J']:.1f}")
    print(f"  Ec (Elastic Modulus)          : {result['Ec_psi']:,.0f} psi")
    print(f"  k  (Subgrade Reaction)        : {result['k_pci']:.0f} pci")
    print(f"\n{'─'*60}")
    print("  ผลการออกแบบ (Design Results)")
    print(f"{'─'*60}")
    print(f"  ความหนาแผ่นคอนกรีตที่คำนวณ  : {result['D_mm']:.1f} มม. ({result['D_inch']:.2f} นิ้ว)")
    print(f"  ความหนาที่ใช้ออกแบบ (ปัดขึ้น) : {result['D_design_mm']} มม.")
    print(f"  log10(W18) ตรวจสอบ            : {result['log10_W18_check']:.4f}")
    print(f"{'─'*60}")
    diff = abs(result['log10_W18'] - result['log10_W18_check'])
    status = "✓ ผ่าน" if diff < 0.01 else "✗ ตรวจสอบอีกครั้ง"
    print(f"  ความถูกต้อง (|Δlog10W18|)     : {diff:.6f}  {status}")
    print(f"{'─'*60}\n")


# ─────────────────────────────────────────────
# 5. ตัวอย่างการใช้งาน (Main Program)
# ─────────────────────────────────────────────

if __name__ == "__main__":

    print("\n" + "=" * 60)
    print("  AASHTO 1993 Rigid Pavement Design Tool")
    print("  พัฒนาด้วย Python")
    print("=" * 60)

    # ────────────────────────────────────────
    # ตัวอย่างที่ 1: ถนนทางหลวงระหว่างเมือง
    # ────────────────────────────────────────
    print("\n\n[ตัวอย่างที่ 1] ถนนทางหลวงระหว่างเมือง (Urban Arterial)")

    # คำนวณ W18 จากข้อมูลจราจร
    W18_1 = compute_W18(
        ADT=15000,          # คัน/วัน
        truck_percent=0.15, # รถบรรทุก 15%
        T_factor=1.2,       # Truck Factor เฉลี่ย
        growth_rate=0.03,   # การเติบโต 3%/ปี
        design_life=20,     # 20 ปี
        lane_dist=0.9,      # 2 ช่องจราจร
        direction_dist=0.5
    )
    print(f"  W18 ที่คำนวณได้ = {W18_1:,.0f} ESAL")

    R1   = 95.0             # Reliability 95%
    ZR1  = get_ZR(R1)
    print(f"  Reliability = {R1}% → ZR = {ZR1:.3f}")

    result1 = design_rigid_pavement(
        W18=W18_1,
        ZR=ZR1,
        S0=0.35,
        delta_PSI=2.0,      # pi=4.5, pt=2.5
        Sc=650,             # psi (~4.5 MPa)
        Cd=1.0,
        J=3.2,
        Ec=4_000_000,       # psi (~27.6 GPa)
        k=150               # pci (ดินแน่น)
    )
    print_results(result1, "ตัวอย่างที่ 1 - ถนนทางหลวงระหว่างเมือง")

    # ────────────────────────────────────────
    # ตัวอย่างที่ 2: ถนนในเมือง (Collector Road)
    # ────────────────────────────────────────
    print("\n[ตัวอย่างที่ 2] ถนนในเมือง (Collector Road)")

    W18_2 = compute_W18(
        ADT=5000,
        truck_percent=0.08,
        T_factor=0.8,
        growth_rate=0.02,
        design_life=15,
        lane_dist=1.0,
        direction_dist=0.5
    )
    print(f"  W18 ที่คำนวณได้ = {W18_2:,.0f} ESAL")

    R2   = 85.0
    ZR2  = get_ZR(R2)
    print(f"  Reliability = {R2}% → ZR = {ZR2:.3f}")

    result2 = design_rigid_pavement(
        W18=W18_2,
        ZR=ZR2,
        S0=0.35,
        delta_PSI=1.7,      # pi=4.2, pt=2.5
        Sc=600,
        Cd=0.9,
        J=3.5,
        Ec=3_800_000,
        k=100
    )
    print_results(result2, "ตัวอย่างที่ 2 - ถนนในเมือง")

    # ────────────────────────────────────────
    # ตัวอย่างที่ 3: ลานจอดรถ/ถนนในนิคมอุตสาหกรรม
    # ────────────────────────────────────────
    print("\n[ตัวอย่างที่ 3] ถนนในนิคมอุตสาหกรรม (Heavy Industrial)")

    W18_3 = 5_000_000       # กำหนด ESAL โดยตรง

    R3   = 99.0
    ZR3  = get_ZR(R3)
    print(f"  W18 = {W18_3:,.0f} ESAL")
    print(f"  Reliability = {R3}% → ZR = {ZR3:.3f}")

    result3 = design_rigid_pavement(
        W18=W18_3,
        ZR=ZR3,
        S0=0.30,
        delta_PSI=2.0,
        Sc=700,             # คอนกรีตกำลังสูง
        Cd=1.0,
        J=2.8,              # มี Dowel Bar
        Ec=4_200_000,
        k=200               # ฐานรากแข็งแรง
    )
    print_results(result3, "ตัวอย่างที่ 3 - ถนนในนิคมอุตสาหกรรม")

    # ────────────────────────────────────────
    # ตารางสรุปผล
    # ────────────────────────────────────────
    print("=" * 60)
    print("  ตารางสรุปผลการออกแบบ")
    print("=" * 60)
    print(f"  {'โครงการ':<30} {'W18':>12} {'ความหนา (มม.)':>14}")
    print(f"  {'-'*30} {'-'*12} {'-'*14}")
    examples = [
        ("ทางหลวงระหว่างเมือง", result1),
        ("ถนนในเมือง",           result2),
        ("นิคมอุตสาหกรรม",       result3),
    ]
    for name, r in examples:
        print(f"  {name:<30} {r['W18']:>12,.0f} {r['D_design_mm']:>14}")
    print("=" * 60)

    # ────────────────────────────────────────
    # ตาราง ZR Reference
    # ────────────────────────────────────────
    print("\n  ตาราง Reliability → ZR (AASHTO 1993)")
    print(f"  {'Reliability (%)':<18} {'ZR':>8}")
    print(f"  {'-'*18} {'-'*8}")
    for r_val in [50, 70, 80, 85, 90, 95, 99]:
        print(f"  {r_val:<18} {get_ZR(r_val):>8.3f}")
    print()

    # ────────────────────────────────────────
    # คำแนะนำค่าพารามิเตอร์
    # ────────────────────────────────────────
    print("  คำแนะนำค่าพารามิเตอร์ (AASHTO 1993)")
    print("  " + "-" * 56)
    guidance = [
        ("J (Load Transfer Coeff.)",   "2.5-3.1 (มี Dowel), 3.2-4.4 (ไม่มี Dowel)"),
        ("Cd (Drainage Coeff.)",        "0.7-1.25 ขึ้นกับระบบระบายน้ำ"),
        ("S0 (Combined Std. Error)",    "0.30-0.40 สำหรับ Rigid Pavement"),
        ("k (Subgrade Reaction)",       "25-300 pci ขึ้นกับชนิดดิน"),
        ("Sc (Modulus of Rupture)",     "550-750 psi ทั่วไป"),
        ("pi (Initial Serviceability)", "4.5 (ค่ามาตรฐาน)"),
        ("pt (Terminal Serviceability)","2.0-2.5 ทางหลวง / 1.5-2.0 ถนนรอง"),
    ]
    for param, val in guidance:
        print(f"  {param:<32} : {val}")
    print("  " + "-" * 56 + "\n")
