"""
vawt_core.py  --  Sharp cycloturbine (centrifugal-pendulum pitch control) physics core, v3.1

2D blade-element model of a 3-blade H-rotor whose blades rock about a pivot at the end of the
support arm (Sharp geometry).  The rotor and the rocking blade units are fully coupled through
the Lagrange equations (derived and cross-checked against vawt_lab.py v1).

What is modelled
  * rotor + N rocking blade units, coupled Lagrangian dynamics (no hand-added "active lift")
  * double-multiple-streamtube induction with a one-revolution-scale relaxation and the
    Sharpe/Glauert empirical correction at high loading
  * static polars as tables over (log Re, alpha); analytic NACA-0012-like surrogate or CSV files
  * optional dynamic stall: lag-based, Beddoes-Leishman-style, written as an INCREMENT on the static
    polar, so steady flow reproduces the static polar exactly (constants are literature-typical,
    NOT fitted to data)
  * optional apparent-mass (non-circulatory) lift, counted once
  * optional Adams (2018) curvilinear-flow shifts, scaled by c/R / 0.418 (scaling is an assumption)
  * optional finite-span correction (lift-slope reduction + induced drag)
  * arm drag, strut/interference drag (cd_add), viscous + Coulomb pivot friction, limit lines
  * gusts / turbulence, prescribed-pitch mode (Ham 1979 style), energy ledger

What is NOT modelled (be aware when interpreting results)
  * quarter-chord pitching moment Cm (stall moment only enters through the centre-of-pressure shift)
  * flow expansion (flux-line theory), 3D flow, tip vortices, blade-wake interaction, gravity
  * unsteady/dynamic-stall constants are uncalibrated; the default analytic polar is a surrogate

Sign conventions: azimuth phi, wind towards +x, rotor turns counter-clockwise, upwind half is
cos(phi) < 0, psi > 0 = blade rocked nose-out.  alpha < 0 upwind, alpha > 0 downwind.
Numerical scheme: semi-implicit (symplectic) Euler.
"""
from __future__ import annotations

import math
import warnings
import os
import glob
import re
from dataclasses import dataclass, fields
from typing import Dict, Any, Optional

import numpy as np

try:
    from numba import njit
    HAVE_NUMBA = True
except Exception:  # pragma: no cover
    HAVE_NUMBA = False

    def njit(*a, **k):
        if a and callable(a[0]):
            return a[0]
        return lambda f: f

    warnings.warn("numba not found: vawt_core runs in pure Python and will be slow "
                  "(pip install numba).")

PI = math.pi
TWO_PI = 2.0 * PI
NU_AIR = 1.5e-5

OUT_COLS = ["t", "th", "w", "psi", "beta", "alpha", "Tsum", "Qshaft", "a", "Fx", "P_blade", "psd"]


# =============================================================================
# 1. TABLE LOOKUP, STATIC SEPARATION FUNCTION, DYNAMIC-STALL STEP
# =============================================================================
@njit(cache=True)
def _wrap(a):
    return math.atan2(math.sin(a), math.cos(a))


@njit(cache=True)
def _lookup(logRe, alpha, logRe_grid, alpha_grid, cla_re, Cl_t, Cd_t):
    """Bilinear lookup on a uniform alpha grid and a uniform log-Re grid. Returns Cl, Cd, Cl_alpha."""
    nRe = Cl_t.shape[0]
    nA = Cl_t.shape[1]
    a = min(max(alpha, alpha_grid[0]), alpha_grid[nA - 1])
    ia = (a - alpha_grid[0]) / (alpha_grid[nA - 1] - alpha_grid[0]) * (nA - 1)
    i0 = min(int(ia), nA - 2)
    i1 = i0 + 1
    wa = ia - i0
    if nRe == 1:
        j0 = 0
        j1 = 0
        wr = 0.0
    else:
        lr = min(max(logRe, logRe_grid[0]), logRe_grid[nRe - 1])
        ir = (lr - logRe_grid[0]) / (logRe_grid[nRe - 1] - logRe_grid[0]) * (nRe - 1)
        j0 = min(int(ir), nRe - 2)
        j1 = j0 + 1
        wr = ir - j0
    Cl = (Cl_t[j0, i0] * (1.0 - wa) * (1.0 - wr) + Cl_t[j0, i1] * wa * (1.0 - wr)
          + Cl_t[j1, i0] * (1.0 - wa) * wr + Cl_t[j1, i1] * wa * wr)
    Cd = (Cd_t[j0, i0] * (1.0 - wa) * (1.0 - wr) + Cd_t[j0, i1] * wa * (1.0 - wr)
          + Cd_t[j1, i0] * (1.0 - wa) * wr + Cd_t[j1, i1] * wa * wr)
    cla = cla_re[j0] * (1.0 - wr) + cla_re[j1] * wr
    return Cl, Cd, cla


@njit(cache=True)
def _fstat(alpha, Cl_tab, cla):
    """Static separation parameter f in [0,1] such that Cl_tab = f*Cl_att + (1-f)*Cl_sep."""
    Cl_att = cla * math.sin(alpha) * math.cos(alpha)
    Cl_sep = math.sin(2.0 * alpha)
    den = Cl_att - Cl_sep
    if abs(den) < 1e-3:
        return 1.0, Cl_att, Cl_sep
    f = (Cl_tab - Cl_sep) / den
    return min(1.0, max(0.0, f)), Cl_att, Cl_sep


@njit(cache=True)
def _aero_coeffs(ds, alpha, W, c, dt, Re, dyn, Tf, Tv, Ta, Kv, Clmax,
                 logRe_grid, alpha_grid, cla_re, Cl_t, Cd_t):
    """
    Returns (Cl, Cd, Cl_nc, f).  Cl excludes the apparent-mass term Cl_nc (added once by the caller).
    ds = [alpha_eff, f_dyn, v_vortex, alpha_prev, initialised].
    dyn = 0 : static table lookup.
    dyn = 1 : delayed separation / vortex lift written as increments on the static polar, so that
              steady flow gives exactly the static polar.
    """
    logRe = math.log(max(Re, 1e3))
    if dyn == 0:
        Cl, Cd, cla = _lookup(logRe, alpha, logRe_grid, alpha_grid, cla_re, Cl_t, Cd_t)
        f, Clatt, Clsep = _fstat(alpha, Cl, cla)
        return Cl, Cd, 0.0, f

    if ds[4] < 0.5:  # first call: start from the steady state (no start-up spike)
        Cl0, Cd0, cla0 = _lookup(logRe, alpha, logRe_grid, alpha_grid, cla_re, Cl_t, Cd_t)
        f0, a0, b0 = _fstat(alpha, Cl0, cla0)
        ds[0] = alpha
        ds[1] = f0
        ds[2] = 0.0
        ds[3] = alpha
        ds[4] = 1.0

    tau = c / max(W, 1e-3)                       # convective time scale
    adot = _wrap(alpha - ds[3]) / dt
    ds[3] = alpha
    ds[0] = _wrap(ds[0] + _wrap(alpha - ds[0]) * min(1.0, dt / (Ta * tau)))   # attached-flow lag, kept in [-pi, pi]
    ae = ds[0]

    Cl_s, Cd_s, cla = _lookup(logRe, ae, logRe_grid, alpha_grid, cla_re, Cl_t, Cd_t)
    fst, Clatt, Clsep = _fstat(ae, Cl_s, cla)
    ds[1] += (fst - ds[1]) * min(1.0, dt / (Tf * tau))            # separation-point lag
    fd = ds[1]

    Cl = Cl_s + (fd - fst) * (Clatt - Clsep)
    cdsep = 1.98 * math.sin(ae) ** 2
    Cd = Cd_s + (fst - fd) * (cdsep - Cd_s)

    # vortex lift: only while separation is lagging, decays to zero in steady flow
    sg = 1.0 if ae >= 0.0 else -1.0
    vt = sg * Kv * max(0.0, fd - fst) * abs(Clatt - Clsep)
    ds[2] += (vt - ds[2]) * min(1.0, dt / (Tv * tau))
    ds[2] = min(max(ds[2], -Clmax), Clmax)
    Cl += ds[2]
    Cd += 0.5 * abs(ds[2]) * abs(math.sin(ae))

    Cl_nc = 0.5 * PI * tau * adot                # Theodorsen apparent-mass lift, (pi/2)(c/W) alpha_dot
    return Cl, Cd, Cl_nc, fd


@njit(cache=True)
def _energy(w, psi, psd, N, M, xg, ar, Rp, Ip, J_hub, ks, kc, win):
    """Kinetic (homogeneous quadratic in w, psi_dot) + elastic energy of the coupled system."""
    T = 0.5 * J_hub * w * w
    V = 0.0
    for k in range(N):
        s_r = -xg * math.sin(psi[k]) + ar * math.cos(psi[k])
        Om = w - psd[k]
        T += 0.5 * M * Rp * Rp * w * w + M * Rp * w * s_r * Om + 0.5 * Ip * Om * Om
        V += 0.5 * kc * psi[k] * psi[k]
        if psi[k] > win:
            V += 0.5 * ks * (psi[k] - win) ** 2
        elif psi[k] < -win:
            V += 0.5 * ks * (psi[k] + win) ** 2
    return T + V


# =============================================================================
# 2. TIME-MARCHING KERNEL
# =============================================================================
@njit(cache=True)
def _kernel(U_arr, dt, stride, rho, R, Rp, N, c, H, ar, sp, M, xg, Ip, J_hub,
            win, ks, cs, cb, kc, mu_c, r_b, arm_k, k_load, free, w_init, psi0,
            prescribe, pp0, pp1, pp2, pp3, ppph, dmst, tau_rev, a_fix, dyn, Tf, Tv, Ta, Kv,
            curv, c_scale, fin_span, f_ar, ind_k, cd_add, Clmax, Knc,
            logRe_grid, alpha_grid, cla_re, Cl_t, Cd_t):
    n = U_arr.shape[0]
    nb = 180
    atab = np.full(nb, 0.2)
    ak = np.full(N, 0.2 if dmst else a_fix)
    psi = np.full(N, psi0)
    psd = np.zeros(N)
    Fxp = np.zeros(N)
    Xk = np.zeros(N)
    SR = np.zeros(N)
    ds = np.zeros((N, 5))
    w = w_init
    th = 0.0
    xq = 0.25 * c - sp
    xm = 0.5 * c - sp
    out = np.zeros((n // stride + 2, 12))
    j = 0
    E_in = 0.0
    E_shaft = 0.0
    E_arm = 0.0
    E_vis = 0.0
    E_cou = 0.0
    E_stop = 0.0
    E0 = _energy(w, psi, psd, N, M, xg, ar, Rp, Ip, J_hub, ks, kc, win)
    al0 = 0.0
    dl0 = 0.0
    for i in range(n):
        Uc = U_arr[i]
        Tsum = 0.0
        Fxs = 0.0
        sumL = 0.0
        Jeff = J_hub
        Pbl = 0.0
        Pvis = 0.0
        Pcou = 0.0
        Pstop = 0.0
        for k in range(N):
            phi = th + TWO_PI * k / N
            cphi = math.cos(phi)
            sphi = math.sin(phi)
            if prescribe:
                psi[k] = (pp0 + pp1 * math.cos(phi + ppph)
                    + pp2 * math.cos(2 * (phi + ppph))
                    + pp3 * math.sin(2 * (phi + ppph)))
                psd[k] = (-pp1 * math.sin(phi + ppph)
                    - 2 * pp2 * math.sin(2 * (phi + ppph))
                    + 2 * pp3 * math.cos(2 * (phi + ppph))) * w

            # ---- induction (double multiple streamtube, relaxed) --------------------------------
            if dmst:
                if cphi < 0.0:
                    Uch = Uc
                    idx = min(nb - 1, max(0, int((phi % TWO_PI - 0.5 * PI) / PI * nb)))
                else:
                    pu = (PI - phi) % TWO_PI
                    idx = min(nb - 1, max(0, int((pu - 0.5 * PI) / PI * nb)))
                    Uch = max(0.05 * Uc, Uc * (1.0 - 2.0 * atab[idx]))
                K = N * Fxp[k] / (4.0 * PI * rho * R * H * max(abs(cphi), 0.1) * Uch * Uch)
                CT = 4.0 * K
                if K <= 0.0:
                    tgt = 0.0
                elif CT <= 0.879:
                    tgt = 0.5 * (1.0 - math.sqrt(1.0 - 4.0 * K))
                else:   # Sharpe/Glauert empirical branch (CT1 = 1.816)
                    tgt = min(0.95, 1.0 - (1.816 - CT) / (4.0 * (math.sqrt(1.816) - 1.0)))
                ak[k] += min(1.0, dt * w / (tau_rev * TWO_PI)) * (tgt - ak[k])
                if cphi < 0.0:
                    atab[idx] = ak[k]
                Uf = Uch * (1.0 - ak[k])
            else:
                Uf = Uc * (1.0 - a_fix)

            # ---- blade kinematics at the quarter chord -------------------------------------------
            cp_ = math.cos(psi[k])
            sn_ = math.sin(psi[k])
            stq = -xq * cp_ - ar * sn_
            srq = -xq * sn_ + ar * cp_
            Om = w - psd[k]
            vt = w * Rp + Om * srq
            vr = -Om * stq
            u1 = Uf * sphi + vt
            u2 = Uf * cphi - vr
            W2 = u1 * u1 + u2 * u2
            W = math.sqrt(W2) + 1e-9
            pf = math.atan2(u2, u1)
            alpha = _wrap(pf + psi[k])
            Re = W * c / NU_AIR

            # ---- aerodynamics ---------------------------------------------------------------------
            a_in = alpha
            dCl = 0.0
            dCd = 0.0
            if curv:
                lam = w * R / max(Uc, 0.05)
                pe = lam * lam / (1.0 + lam * lam)
                a_in = alpha + pe * (-0.0742) * c_scale
                dCl = pe * (-0.402) * c_scale
                dCd = pe * 0.0156 * c_scale
            Cl, Cd, Clnc, wt = _aero_coeffs(ds[k], a_in, W, c, dt, Re, dyn, Tf, Tv, Ta, Kv, Clmax,
                                            logRe_grid, alpha_grid, cla_re, Cl_t, Cd_t)
            Clnc *= Knc
            Cl += dCl
            Cd += dCd
            if fin_span:
                Cl *= f_ar
                Cd += Cl * Cl * ind_k
            Cd += cd_add
            q = 0.5 * rho * W2 * c * H
            Ft = q * Cl * math.sin(pf) - q * Cd * math.cos(pf)
            Fr = q * Cl * math.cos(pf) + q * Cd * math.sin(pf)
            Fnt = q * Clnc * math.sin(pf)          # apparent-mass force, acts at mid-chord
            Fnr = q * Clnc * math.cos(pf)

            xcp = (0.25 + 0.25 * (1.0 - wt)) * c - sp      # centre of pressure moves aft in stall
            stc = -xcp * cp_ - ar * sn_
            src = -xcp * sn_ + ar * cp_
            stm = -xm * cp_ - ar * sn_
            srm = -xm * sn_ + ar * cp_
            Tk = (Rp + src) * Ft - stc * Fr + (Rp + srm) * Fnt - stm * Fnr
            Qa = stc * Fr - src * Ft + stm * Fnr - srm * Fnt
            Fx = -(Ft + Fnt) * sphi + (Fr + Fnr) * cphi
            Fxp[k] = Fx
            Fxs += Fx
            Tsum += Tk

            # ---- pitch (rocking) dynamics -------------------------------------------------------
            s_t = -xg * cp_ - ar * sn_
            s_r = -xg * sn_ + ar * cp_
            Fcen = M * w * w * (Rp + s_r)
            Qfr = mu_c * Fcen * r_b * math.tanh(psd[k] / 0.5)
            Qp = Qa - cb * psd[k] - kc * psi[k] - Qfr
            if psi[k] > win:
                Qp += -ks * (psi[k] - win) - cs * psd[k]
                Pstop += cs * psd[k] * psd[k]
            elif psi[k] < -win:
                Qp += -ks * (psi[k] + win) - cs * psd[k]
                Pstop += cs * psd[k] * psd[k]
            X = M * Rp * s_t * w * w + Qp
            Xk[k] = X
            SR[k] = s_r
            sumL += M * Rp * s_t * psd[k] * (2.0 * w - psd[k]) - (1.0 + M * Rp * s_r / Ip) * X
            Jeff += M * Rp * Rp * (1.0 - M * s_r * s_r / Ip)
            Pvis += cb * psd[k] * psd[k]
            Pcou += Qfr * psd[k]
            Pbl += Tk * w + Qa * psd[k]
            if k == 0:
                al0 = alpha
                dl0 = math.atan2(stq, Rp + srq)

        Qarm = arm_k * w * w
        if prescribe:
            sumL = 0.0
        if free:
            wd = (Tsum - k_load * w * w - Qarm - sumL) / Jeff
            Qdel = k_load * w * w
        else:
            wd = 0.0
            Qdel = Tsum - sumL - Qarm        # shaft torque delivered while holding omega

        E_in += Pbl * dt
        E_shaft += Qdel * w * dt
        E_arm += Qarm * w * dt
        E_vis += Pvis * dt
        E_cou += Pcou * dt
        E_stop += Pstop * dt

        if i % stride == 0:
            out[j, 0] = i * dt
            out[j, 1] = th
            out[j, 2] = w
            out[j, 3] = psi[0]
            out[j, 4] = psi[0] + dl0
            out[j, 5] = al0
            out[j, 6] = Tsum
            out[j, 7] = Qdel
            out[j, 8] = ak[0]
            out[j, 9] = Fxs
            out[j, 10] = Pbl
            out[j, 11] = psd[0]
            j += 1

        if not prescribe:
            for k in range(N):
                acc = ((Ip + M * Rp * SR[k]) * wd + Xk[k]) / Ip
                psd[k] += acc * dt                 # velocity += acceleration * dt
            for k in range(N):
                psi[k] += psd[k] * dt              # position uses the updated velocity
        if free:
            w += wd * dt
        th += w * dt

    E1 = _energy(w, psi, psd, N, M, xg, ar, Rp, Ip, J_hub, ks, kc, win)
    ledger = np.array([E_in, E_shaft, E_arm, E_vis, E_cou, E_stop, E0, E1])
    return out[:j], ledger


# =============================================================================
# 3. CONFIGURATION
# =============================================================================
@dataclass(frozen=True)
class Geometry:
    R: float = 0.6
    c: float = 0.07
    H: float = 0.4
    N: int = 3
    ar: float = 0.5          # rocking arm / chord
    sp: float = 0.10         # spar position from LE / chord
    arm_d: float = 0.0       # support-arm width for drag (m)
    n_arm: int = 2           # arms per blade (top + bottom)
    arm_cd: float = 1.0

    def __post_init__(self):
        if self.c * self.ar >= self.R:
            raise ValueError("Rocking arm longer than rotor radius")


@dataclass(frozen=True)
class MassProps:
    mb: float = 0.010
    xbcg: float = 0.20
    mc: float = 0.004
    dcw: float = 0.5
    balance: int = 1         # 0: use mc,dcw as given; 1: solve dcw from mc; 2: solve mc from dcw
    bias_deg: float = 0.0
    J_hub: float = 0.02
    mu_friction: float = 3.0e-4     # <-- add this


@dataclass(frozen=True)
class AeroConfig:
    polar_dir: str = "polars/naca0012"   # folder of Re_<number>.csv (alpha_deg,cl,cd); else surrogate
    use_dynamic_stall: bool = True
    use_tip_loss: bool = False           # finite-span correction (lift slope + induced drag)
    use_hub_loss: bool = False           # unused (kept for compatibility)
    use_rotational_aug: bool = False     # unused (kept for compatibility)
    use_dmst: bool = True
    use_dynamic_inflow: bool = True      # False -> near-instant induction (tau = 0.02 rev)
    use_flow_curvature: bool = False     # Adams (2018) shifts, scaled by (c/R)/0.418
    cd_add: float = 0.005                # strut / interference drag (Ham 1979 used 0.005)
    win_deg: float = 45.0
    wstop: float = 300.0
    cb: float = 2e-5
    kc: float = 0.0
    mu_c: float = 0.0
    r_bearing: float = 0.002
    prescribe_pitch: bool = False        # psi = pp0 + pp1*cos(phi + ph)   (use ar=0, sp=0.25 for pure pitch)
    pp0_deg: float = 0.0
    pp1_deg: float = 0.0
    pp2_deg: float = 0.0
    pp3_deg: float = 0.0
    pp_ph_deg: float = 0.0
    a_fix: float = 0.2                   # induction when use_dmst is False
    tau_rev: float = 0.1                 # induction lag in revolutions
    e_osw: float = 0.9
    ds_Tf: float = 3.0                   # separation lag  (convective times c/W)
    ds_Tv: float = 6.0                   # vortex-lift lag
    ds_Ta: float = 0.1                   # attached-flow lag (>~0.5 can excite pitch flutter, see docs)
    ds_Kv: float = 0.5                   # vortex-lift strength (0 disables)
    ds_Knc: float = 1.0                  # apparent-mass lift multiplier (0 disables)
    c_scale_override: float = 0.0       # 0 = geometry-derived; else use this
    tip_loss_floor_override: float = 0.0  # 0 = default 0.85; else use this


@dataclass(frozen=True)
class SimConfig:
    U: float = 8.0
    tsr: float = 3.0
    free: bool = False
    w0_frac: float = 0.2
    psi0_deg: float = 0.0
    dt: float = 2e-4
    T_max: float = 30.0
    stride: int = 5
    gust_g: float = 0.0
    gust_t0: float = 0.0
    gust_tg: float = 0.0
    turb_I: float = 0.0
    turb_L: float = 30.0
    k_load: float = 0.0004
    n_span: int = 1          # deprecated: all span stations are identical in this 2D model
    rho: float = 1.225
    seed: int = 0
    n_rev_fixed: int = 16    # length of fixed-rpm runs in revolutions


# =============================================================================
# 4. POLARS
# =============================================================================
_RE_PTS = np.log10([5e4, 1e5, 3e5, 1e6, 1e7])
_CLA = [5.0, 5.5, 5.9, 6.06, 6.06]        # per rad
_CLMAX = [0.80, 0.90, 1.15, 1.40, 1.50]
_CD0 = [0.020, 0.015, 0.010, 0.0075, 0.0065]


def surrogate_cla(Re):
    return float(np.interp(math.log10(max(Re, 1.0)), _RE_PTS, _CLA))


def surrogate_polar(Re, alpha):
    """Analytic NACA-0012-like surrogate (NOT measured data): attached/flat-plate blend, 360 deg."""
    lr = math.log10(max(Re, 1.0))
    cla = float(np.interp(lr, _RE_PTS, _CLA))
    clmax = float(np.interp(lr, _RE_PTS, _CLMAX))
    cd0 = float(np.interp(lr, _RE_PTS, _CD0))
    s = clmax / cla
    a = np.arctan2(np.sin(alpha), np.cos(alpha))
    w = 1.0 / (1.0 + np.exp((np.abs(a) - s) / 0.04))
    cl_att = cla * np.sin(a) * np.cos(a)
    cl = w * cl_att + (1.0 - w) * np.sin(2.0 * a)
    cd = cd0 + w * 0.02 * cl_att ** 2 + (1.0 - w) * 1.98 * np.sin(a) ** 2
    return cl, cd


class PolarDatabase:
    """Static polar tables (Cl, Cd over log Re x alpha). Cm is not used by the kernel."""

    def __init__(self, polar_dir: str = "", geo: Optional[Geometry] = None, n_span: int = 1,
                 use_rotational_aug: bool = False):
        self.polar_dir = polar_dir
        self.n_span = max(1, int(n_span))
        self.r_stations = np.linspace(-0.5, 0.5, self.n_span) * (geo.H if geo else 1.0)
        self.alpha_grid = np.radians(np.linspace(-180.0, 180.0, 721))
        files = sorted(glob.glob(os.path.join(polar_dir, "*.csv"))) if polar_dir else []
        if files:
            self._load_csv(files)
            self.source = "csv:" + polar_dir
        else:
            self.logRe_grid = np.log(np.array([2e4, 6.3e4, 2e5, 6.3e5, 2e6]))
            Cl = np.zeros((len(self.logRe_grid), len(self.alpha_grid)))
            Cd = np.zeros_like(Cl)
            for r, lre in enumerate(self.logRe_grid):
                Cl[r], Cd[r] = surrogate_polar(math.exp(lre), self.alpha_grid)
            self.Cl, self.Cd = Cl, Cd
            self.cla_re = np.array([surrogate_cla(math.exp(l)) for l in self.logRe_grid])
            self.source = "analytic surrogate"
        self._finish()

    @classmethod
    def from_callable(cls, fn, cla: float, geo: Optional[Geometry] = None):
        """Re-independent table from fn(alpha_array) -> (Cl, Cd); cla = attached lift slope (per rad)."""
        self = cls.__new__(cls)
        self.polar_dir = ""
        self.n_span = 1
        self.r_stations = np.zeros(1)
        self.alpha_grid = np.radians(np.linspace(-180.0, 180.0, 721))
        self.logRe_grid = np.array([math.log(1e5)])
        cl, cd = fn(self.alpha_grid)
        self.Cl, self.Cd = np.array([cl]), np.array([cd])
        self.cla_re = np.array([float(cla)])
        self.source = "callable"
        self._finish()
        return self

    def _load_csv(self, files):
        res, cls_, cds = [], [], []
        ag = np.degrees(self.alpha_grid)
        for f in files:
            m = re.search(r"[Rr][Ee]_(\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)", os.path.basename(f))
            if not m:
                continue
            Re = float(m.group(1))
            d = np.genfromtxt(f, delimiter=",", comments="#")
            d = d[~np.isnan(d).any(axis=1)] if d.ndim == 2 else d
            a, cl, cd = d[:, 0], d[:, 1], d[:, 2]
            o = np.argsort(a)
            res.append(Re)
            cls_.append(np.interp(ag, a[o], cl[o], period=None))
            cds.append(np.interp(ag, a[o], cd[o]))
        o = np.argsort(res)
        self.logRe_grid = np.log(np.array(res)[o])
        self.Cl = np.array(cls_)[o]
        self.Cd = np.array(cds)[o]
        sel = np.abs(ag) <= 4.0
        self.cla_re = np.array([np.polyfit(self.alpha_grid[sel], self.Cl[r][sel], 1)[0]
                                for r in range(len(res))])
        if len(self.logRe_grid) > 1:
            d = np.diff(self.logRe_grid)
            if np.max(np.abs(d - d[0])) > 1e-6:      # kernel assumes a uniform log-Re grid
                lg = np.linspace(self.logRe_grid[0], self.logRe_grid[-1], len(self.logRe_grid))
                self.Cl = np.array([[np.interp(l, self.logRe_grid, self.Cl[:, i])
                                     for i in range(self.Cl.shape[1])] for l in lg])
                self.Cd = np.array([[np.interp(l, self.logRe_grid, self.Cd[:, i])
                                     for i in range(self.Cd.shape[1])] for l in lg])
                self.cla_re = np.interp(lg, self.logRe_grid, self.cla_re)
                self.logRe_grid = lg

    def _finish(self):
        self.Cl = np.ascontiguousarray(self.Cl, dtype=np.float64)
        self.Cd = np.ascontiguousarray(self.Cd, dtype=np.float64)
        self.logRe_grid = np.ascontiguousarray(self.logRe_grid, dtype=np.float64)
        self.cla_re = np.ascontiguousarray(self.cla_re, dtype=np.float64)
        sel = np.abs(self.alpha_grid) <= math.radians(30.0)
        self.Cl_max = float(np.max(np.abs(self.Cl[:, sel])))
        self.Cd_min = float(np.min(self.Cd[:, sel]))
        self.alpha_stall = float(self.alpha_grid[sel][np.argmax(self.Cl[-1][sel])])
        self.Cl_alpha = float(np.mean(self.cla_re))
        self.Cl_3d = np.repeat(self.Cl[None], self.n_span, axis=0)
        self.Cd_3d = np.repeat(self.Cd[None], self.n_span, axis=0)
        self.Cm_3d = np.zeros_like(self.Cl_3d)

    def get_numba_data(self):
        return (self.logRe_grid, self.alpha_grid, self.Cl_3d, self.Cd_3d, self.Cm_3d,
                self.n_span, len(self.logRe_grid), len(self.alpha_grid),
                self.Cl_alpha, self.Cl_max, self.alpha_stall, self.Cd_min)


# =============================================================================
# 5. SIMULATION CLASS
# =============================================================================
class CycloturbineSim:
    def __init__(self, geo: Geometry, mass: MassProps, aero: AeroConfig, sim: SimConfig,
                 polar_db: Optional[PolarDatabase] = None):
        self.geo, self.mass, self.aero, self.sim = geo, mass, aero, sim
        self.ar_len = geo.ar * geo.c
        self.sp_len = geo.sp * geo.c
        self.Rp = geo.R - self.ar_len
        self.xq = 0.25 * geo.c - self.sp_len
        self.xm = 0.50 * geo.c - self.sp_len
        self.xb = -self.sp_len + mass.xbcg * geo.c
        self._resolve_balance()
        self.polar_db = polar_db or PolarDatabase(aero.polar_dir, geo, sim.n_span,
                                                  aero.use_rotational_aug)
        self.wstop = aero.wstop
        self.win = math.radians(aero.win_deg)
        self.ks = self.Ip * self.wstop ** 2
        self.cs = 2.0 * self.Ip * self.wstop
        self.arm_k = (geo.N * geo.n_arm * sim.rho * geo.arm_cd * geo.arm_d * geo.R ** 4 / 8.0)
        AR = geo.H / geo.c
        self.AR = AR
        # 3D finite-span correction.  The classic formula 1/(1 + 2/(e*AR))
        # is derived for an elliptical finite wing, where the entire span
        # loses lift.  A VAWT blade only loses lift in the last ~10-15 % of
        # span near each tip, so the midspan correction should be close to
        # 1.  We cap the reduction at 15 % and the induced-drag coefficient
        # at 0.02 to keep the correction physically bounded.
        f_ar_raw  = 1.0 / (1.0 + 2.0 / (aero.e_osw * AR))
        ind_k_raw = 1.0 / (PI * aero.e_osw * AR)
        self.f_ar  = max(0.85, f_ar_raw)
        self.ind_k = min(0.02, ind_k_raw)
        if aero.c_scale_override > 0.0:
            self.c_scale = float(aero.c_scale_override)
        else:
            self.c_scale = min(1.0, (geo.c / geo.R) / 0.418)   # Adams fit at c/r=0.418
        self.freq_ratio = 1.0 / self.fn_ratio if self.fn_ratio > 0 else float("inf")

    # ---------------------------------------------------------------- balance
    def _resolve_balance(self):
        c, ar, sp = self.geo.c, self.ar_len, self.sp_len
        Rp, xb, mb = self.Rp, self.xb, self.mass.mb
        beta = math.radians(self.mass.bias_deg)
        xcl = 0.25 * c - sp
        psi = beta
        for _ in range(60):
            dl = math.atan2(-xcl * math.cos(psi) - ar * math.sin(psi),
                            Rp - xcl * math.sin(psi) + ar * math.cos(psi))
            psi = beta - dl
        xgt = -ar * math.tan(psi)           # CM must lie on the support-arm line at equilibrium

        if self.mass.balance == 0:
            mc, dcw = self.mass.mc, self.mass.dcw
        elif self.mass.balance == 1:
            mc = self.mass.mc
            xcw = (xgt * (mb + mc) - mb * xb) / mc          # from  M*xg = mb*xb + mc*xcw
            dcw = (-xcw - sp) / c
        else:
            dcw = self.mass.dcw
            xcw = -sp - dcw * c
            mc = mb * (xgt - xb) / (xcw - xgt)
        xcw = -sp - dcw * c
        M = mb + mc
        self.M, self.mc, self.dcw = M, mc, dcw
        self.xg = (mb * xb + mc * xcw) / M
        self.Ip = mb * (c * c / 12.0 + xb * xb + ar * ar) + mc * (xcw * xcw + ar * ar)
        # natural pitching frequency / rotor frequency (Sharp: >= 1.5).  Pawsey's ratio is the inverse.
        self.fn_ratio = math.sqrt(M * Rp * ar / self.Ip) if ar > 0 else 0.0

    # ---------------------------------------------------------------- wind
    def _make_wind(self, n):
        sim = self.sim
        dt = sim.dt
        t = np.arange(n) * dt
        U = np.full(n, sim.U)
        if sim.gust_g > 0 and sim.gust_tg > 0:
            m = (t >= sim.gust_t0) & (t <= sim.gust_t0 + sim.gust_tg)
            U[m] *= 1.0 + sim.gust_g * 0.5 * (1.0 - np.cos(TWO_PI * (t[m] - sim.gust_t0) / sim.gust_tg))
        if sim.turb_I > 0:
            rng = np.random.default_rng(sim.seed)
            tl = sim.turb_L / sim.U
            x = np.zeros(n)
            sd = sim.turb_I * sim.U * math.sqrt(2.0 * dt / tl)
            r = rng.standard_normal(n)
            for i in range(1, n):
                x[i] = x[i - 1] * (1.0 - dt / tl) + sd * r[i]
            U = np.maximum(0.3 * sim.U, U + x)
        return t, U

    # ---------------------------------------------------------------- run
    def run(self, wind_series=None, store_history: bool = False):
        g, ms, ae, s = self.geo, self.mass, self.aero, self.sim
        w0 = s.tsr * s.U / g.R
        if wind_series is None:
            T = s.T_max if s.free else min(s.T_max, s.n_rev_fixed * TWO_PI / max(w0, 1e-6))
            n = int(T / s.dt) + 1
            t_arr, U_arr = self._make_wind(n)
        else:
            U_arr = np.asarray(wind_series, dtype=np.float64)
            t_arr = np.arange(len(U_arr)) * s.dt
        w_init = s.w0_frac * w0 if s.free else w0
        pdb = self.polar_db
        out, led = _kernel(
            U_arr, s.dt, int(s.stride), s.rho, g.R, self.Rp, int(g.N), g.c, g.H, self.ar_len,
            self.sp_len, self.M, self.xg, self.Ip, ms.J_hub, self.win, self.ks, self.cs, ae.cb,
            ae.kc, ae.mu_c, ae.r_bearing, self.arm_k, s.k_load, bool(s.free), w_init,
            math.radians(s.psi0_deg), bool(ae.prescribe_pitch),math.radians(ae.pp0_deg),
            math.radians(ae.pp1_deg),
            math.radians(ae.pp2_deg),
            math.radians(ae.pp3_deg),
            math.radians(ae.pp_ph_deg),
            bool(ae.use_dmst),
            ae.tau_rev if ae.use_dynamic_inflow else 0.02, ae.a_fix, int(ae.use_dynamic_stall),
            ae.ds_Tf, ae.ds_Tv, ae.ds_Ta, ae.ds_Kv, bool(ae.use_flow_curvature), self.c_scale,
            bool(ae.use_tip_loss), self.f_ar, self.ind_k, ae.cd_add, pdb.Cl_max, ae.ds_Knc,
            pdb.logRe_grid, pdb.alpha_grid, pdb.cla_re, pdb.Cl, pdb.Cd)
        return self._post(out, led, t_arr, U_arr, store_history)

    def _post(self, out, led, t_arr, U_arr, store_history):
        g, s, ae = self.geo, self.sim, self.aero
        E_in, E_sh, E_arm, E_vis, E_cou, E_stop, E0, E1 = led
        resid_abs = E_in - (E_sh + E_arm + E_vis + E_cou + E_stop + (E1 - E0))
        scale = max(abs(E_in), abs(E_sh) + abs(E_arm), 1e-9)
        resid = resid_abs / scale
        valid = not ae.prescribe_pitch      # prescribed pitch: actuator work is not in the ledger
        if valid and abs(resid) > 0.02:
            warnings.warn(f"Energy balance residual {resid * 100:.2f}% (dt too large or stiff stops?)")

        nrev = 4
        th = out[:, 1]
        m = th > th[-1] - TWO_PI * nrev
        if m.sum() < 5:
            m = np.ones(len(th), bool)
        w = out[m, 2]
        A = 0.5 * s.rho * s.U ** 3 * 2.0 * g.R * g.H
        cp = float(np.mean(out[m, 7] * w) / A)
        tsr_eq = float(w.mean() * g.R / s.U)
        half = len(w) // 2
        steady = bool(abs(w[half:].mean() - w[:half].mean()) < 0.01 * max(w.mean(), 1e-9)) if half else True
        beta = np.degrees(out[m, 4])
        res = dict(
            out=out, columns=OUT_COLS, t=t_arr, U=U_arr,
            cp=cp, cq=cp / max(tsr_eq, 1e-3), tsr_eq=tsr_eq, rpm=float(w.mean() * 60.0 / TWO_PI),
            steady=steady,
            pitch_min=float(beta.min()), pitch_max=float(beta.max()), pitch_rms=float(beta.std()),
            aoa_max=float(np.degrees(np.abs(out[m, 5]).max())),
            stop_pct=float(100.0 * np.mean(np.abs(out[m, 3]) > 0.98 * self.win)) if self.win > 0 else 100.0,
            ct=float(out[m, 9].mean() / (0.5 * s.rho * s.U ** 2 * 2.0 * g.R * g.H)),
            energy_balance=float(resid), energy_balance_valid=valid,
            energies=dict(aero=E_in, shaft=E_sh, arm=E_arm, piv_vis=E_vis, piv_cou=E_cou,
                          stop=E_stop, d_stored=E1 - E0),
            history={},
        )
        if store_history:
            res["history"] = {k: out[:, i] for i, k in enumerate(OUT_COLS)}
        return res


# =============================================================================
# 6. FACTORY
# =============================================================================
_ALIASES = {"bias": "bias_deg", "win": "win_deg"}


def create_sim_from_params(param_dict: Dict[str, Any]) -> CycloturbineSim:
    """Build a sim from a flat dict of dataclass field names."""
    # 1. Build the set of legal keys (dataclass fields + aliases)
    known = set()
    for cls in (Geometry, MassProps, AeroConfig, SimConfig):
        known |= {f.name for f in fields(cls)}
    known |= set(_ALIASES.keys())

    # 2. Reject unknown keys BEFORE doing anything else
    unknown = set(param_dict) - known
    if unknown:
        raise KeyError(
            f"create_sim_from_params: unknown parameter(s): {sorted(unknown)}"
        )

    # 3. Normal path — aliases first, then defaults
    p = dict(param_dict)
    for a, b in _ALIASES.items():
        if a in p and b not in p:
            p[b] = p.pop(a)
    p.setdefault("free", True)

    def pick(cls):
        kw = {f.name: p[f.name] for f in fields(cls) if f.name in p}
        if cls is Geometry and "N" in kw:
            kw["N"] = int(kw["N"])
        return cls(**kw)

    return CycloturbineSim(pick(Geometry), pick(MassProps),
                           pick(AeroConfig), pick(SimConfig))