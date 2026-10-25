""""
sharp_vawt.engine
=================

Pure math solvers and time-marching kernel for the Sharp cycloturbine.

This module contains absolutely ZERO file I/O, ZERO string parsers, and ZERO
external side effects. It contains only pure math: the Numba JIT-accelerated
time-marching kernel, the CycloturbineSim simulation class, and the
semi-implicit time-marching logic.

All file I/O, configuration parsing, and plotting are handled by the
scripts/ layer.
"""

from __future__ import annotations

import math
import warnings
from dataclasses import fields
from typing import Any

import numpy as np

from .config import (
    _ALIASES,
    NU_AIR,
    PI,
    TWO_PI,
    AeroConfig,
    Geometry,
    MassProps,
    SimConfig,
)
from .database import PolarDatabase, _lookup

try:
    from numba import njit
    HAVE_NUMBA = True
except Exception:  # pragma: no cover - numba unavailable; graceful degradation  # noqa: BLE001
    HAVE_NUMBA = False

    def njit(*a, **k):
        if a and callable(a[0]):
            return a[0]
        return lambda f: f

    warnings.warn("numba not found: sharp_vawt runs in pure Python and will be slow "
                  "(pip install numba).")


# =============================================================================
# 1. TABLE LOOKUP, STATIC SEPARATION FUNCTION, DYNAMIC-STALL STEP
# =============================================================================

@njit(cache=True)
def _wrap(a):
    return math.atan2(math.sin(a), math.cos(a))


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
                 logRe_grid, alpha_grid, cla_re, Cl_t, Cd_t, Cm_t=None,
                 cm_scale: float = 1.0):
    """
    Returns (Cl, Cd, Cl_nc, f, Cm).  Cl excludes the apparent-mass term Cl_nc (added once by the caller).
    ds = [alpha_eff, f_dyn, v_vortex, alpha_prev, initialised].
    dyn = 0 : static table lookup.
    dyn = 1 : delayed separation / vortex lift written as increments on the static polar, so that
              steady flow gives exactly the static polar.
    cm_scale scales the polar Cm before it is used; 1 = table value, 0 = no pitching moment.
    """
    logRe = math.log(max(Re, 1e3))
    if dyn == 0:
        Cl, Cd, Cm, cla = _lookup(logRe, alpha, logRe_grid, alpha_grid, cla_re, Cl_t, Cd_t, Cm_t)
        f, Clatt, Clsep = _fstat(alpha, Cl, cla)
        return Cl, Cd, 0.0, f, Cm * cm_scale

    if ds[4] < 0.5:  # first call: start from the steady state (no start-up spike)
        Cl0, _Cd0, _Cm0, cla0 = _lookup(logRe, alpha, logRe_grid, alpha_grid, cla_re, Cl_t, Cd_t, Cm_t)
        f0, _a0, _b0 = _fstat(alpha, Cl0, cla0)
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

    Cl_s, Cd_s, Cm_s, cla = _lookup(logRe, ae, logRe_grid, alpha_grid, cla_re, Cl_t, Cd_t, Cm_t)
    Cm_s *= cm_scale
    fst, Clatt, Clsep = _fstat(ae, Cl_s, cla)
    ds[1] += (fst - ds[1]) * min(1.0, dt / (Tf * tau))            # separation-point lag
    fd = ds[1]

    Cl = Cl_s + (fd - fst) * (Clatt - Clsep)
    cdsep = 1.98 * math.sin(ae) ** 2
    Cd = Cd_s + (fst - fd) * (cdsep - Cd_s)

    # Cm in dynamic stall: blend between static Cm and separated Cm
    # In deep stall, Cm becomes more negative (nose-down) for positive alpha,
    # and more positive for negative alpha (odd symmetry)
    # Use math.copysign for proper odd symmetry: sign of Cm follows -sign(ae).
    # The separated target is scaled by cm_scale as well, so cm_scale=0
    # really means "no pitching moment" rather than "static Cm only".
    Cm = Cm_s + (fst - fd) * (cm_scale * math.copysign(0.05, -ae) - Cm_s)

    # vortex lift: only while separation is lagging, decays to zero in steady flow
    sg = 1.0 if ae >= 0.0 else -1.0
    vt = sg * Kv * max(0.0, fd - fst) * abs(Clatt - Clsep)
    ds[2] += (vt - ds[2]) * min(1.0, dt / (Tv * tau))
    ds[2] = min(max(ds[2], -Clmax), Clmax)
    Cl += ds[2]
    Cd += 0.5 * abs(ds[2]) * abs(math.sin(ae))

    Cl_nc = 0.5 * math.pi * tau * adot                # Theodorsen apparent-mass lift, (pi/2)(c/W) alpha_dot
    return Cl, Cd, Cl_nc, fd, Cm


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
def _cm_moment(rho, W2, c, H, Cm):
    """Pitch moment about the pitch pivot from the section moment coefficient [N m].

    ``Q_Cm = 0.5 * rho * W^2 * c^2 * H * Cm``.  The dynamic pressure times the
    blade planform area is ``0.5 * rho * W^2 * c * H``; the additional chord
    factor comes from the pitching-moment coefficient reference length.
    """
    return 0.5 * rho * W2 * c * c * H * Cm


@njit(cache=True)
def _kernel(U_arr, dt, stride, rho, R, Rp, N, c, H, ar, sp, M, xg, Ip, J_hub,
            win, ks, cs, cb, kc, mu_c, r_b, arm_k, k_load, free, w_init, psi0,
            prescribe, pp0, pp1, pp2, pp3, ppph, dmst, tau_rev, a_fix, dyn, Tf, Tv, Ta, Kv,
            curv, c_scale, fin_span, f_ar, ind_k, cd_add, Clmax, Knc,
            logRe_grid, alpha_grid, cla_re, Cl_t, Cd_t, Cm_t, cm_scale):
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
    xm = 0.50 * c - sp
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
            Cl, Cd, Clnc, wt, Cm = _aero_coeffs(ds[k], a_in, W, c, dt, Re, dyn, Tf, Tv, Ta, Kv, Clmax,
                                            logRe_grid, alpha_grid, cla_re, Cl_t, Cd_t, Cm_t, cm_scale)
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

            # Pitch moment from Cm: Qa_cm = 0.5 * rho * W^2 * c^2 * H * Cm.
            # q = 0.5 * rho * W2 * c * H already contains c * H, so multiply by c only.
            Qa_cm = _cm_moment(rho, W2, c, H, Cm)

            xcp = (0.25 + 0.25 * (1.0 - wt)) * c - sp      # centre of pressure moves aft in stall
            stc = -xcp * cp_ - ar * sn_
            src = -xcp * sn_ + ar * cp_
            stm = -xm * cp_ - ar * sn_
            srm = -xm * sn_ + ar * cp_
            Tk = (Rp + src) * Ft - stc * Fr + (Rp + srm) * Fnt - stm * Fnr
            Qa = stc * Fr - src * Ft + stm * Fnr - srm * Fnt + Qa_cm
            Fx = -(Ft + Fnt) * sphi + (Fr + Fnr) * cphi
            Fxp[k] = Fx
            Fxs += Fx
            Tsum += Tk - Qa_cm

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
            Pbl += (Tk - Qa_cm) * w + Qa * psd[k]
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
# SIMULATION CLASS
# =============================================================================

OUT_COLS = ["t", "theta", "omega", "psi_rad", "pitch_rad", "aoa_rad",
            "torque_total", "Q_shaft", "a_ind", "Fx_total", "P_aero", "psidot_0"]

# Every raw output column carries an explicit unit.  Angular columns are
# radians: ``pitch_deg``/``aoa_deg`` used to name radians, which was misleading.
OUT_UNITS = {
    "t": "s",
    "theta": "rad",
    "omega": "rad/s",
    "psi_rad": "rad",
    "pitch_rad": "rad",
    "aoa_rad": "rad",
    "torque_total": "N m",
    "Q_shaft": "N m",
    "a_ind": "1",
    "Fx_total": "N",
    "P_aero": "W",
    "psidot_0": "rad/s",
}

OUT_DESCRIPTIONS = {
    "t": "time at the start of the integration step",
    "theta": "rotor azimuth angle",
    "omega": "rotor angular velocity",
    "psi_rad": "blade-0 rocking pitch angle about its pivot, relative to the arm nominal orientation",
    "pitch_rad": "total geometric chord pitch psi + delta of blade 0 relative to the rotor radial line",
    "aoa_rad": "blade-0 angle of attack used by the aerodynamic lookup",
    "torque_total": "sum of blade aerodynamic torques about the rotor axis excluding the Cm moment",
    "Q_shaft": "shaft/load torque delivered while holding the rotor speed",
    "a_ind": "blade-0 axial induction factor",
    "Fx_total": "sum of blade force components in the wind direction",
    "P_aero": "aerodynamic power into the rotor plus pitch degrees of freedom",
    "psidot_0": "blade-0 rocking pitch angular velocity",
}

# Documented normalisation of the energy-ledger residual.  The throughput form
# is reported separately; it is never a substitute for the absolute error.
ENERGY_BALANCE_SCALE_BASIS = "max(|E_in|, |E_shaft| + |E_arm|)"
ENERGY_BALANCE_THROUGHPUT_BASIS = (
    "sum(|E_in|, |E_shaft|, |E_arm|, |E_vis|, |E_cou|, |E_stop|, |dE_stored|)")
ENERGY_BALANCE_NEAR_ZERO_J = 1e-9


def _energy_diagnostics(led) -> dict[str, float | bool | str]:
    """Return absolute and normalised energy-closure diagnostics from a ledger.

    ``led`` is ``[E_in, E_shaft, E_arm, E_vis, E_cou, E_stop, E0, E1]`` in
    joules.  The historical ``energy_balance`` normalisation is preserved for
    compatibility.  The absolute closure error is always reported in joules,
    and a separately named throughput-based ratio is also provided.  When the
    chosen denominator is below ``ENERGY_BALANCE_NEAR_ZERO_J`` the ratio is
    undefined (NaN) rather than dividing by an arbitrary epsilon.
    """
    E_in, E_sh, E_arm, E_vis, E_cou, E_stop, E0, E1 = (float(x) for x in led)
    d_stored = E1 - E0
    resid_abs = E_in - (E_sh + E_arm + E_vis + E_cou + E_stop + d_stored)
    primary_scale = max(abs(E_in), abs(E_sh) + abs(E_arm), ENERGY_BALANCE_NEAR_ZERO_J)
    primary_defined = primary_scale > ENERGY_BALANCE_NEAR_ZERO_J
    throughput = (
        abs(E_in) + abs(E_sh) + abs(E_arm) + abs(E_vis)
        + abs(E_cou) + abs(E_stop) + abs(d_stored)
    )
    throughput_defined = throughput > ENERGY_BALANCE_NEAR_ZERO_J
    return {
        "energy_balance": resid_abs / primary_scale if primary_defined else float("nan"),
        "energy_balance_abs_J": resid_abs,
        "energy_balance_scale_J": primary_scale,
        "energy_balance_scale_basis": ENERGY_BALANCE_SCALE_BASIS,
        "energy_balance_defined": primary_defined,
        "energy_balance_throughput": (
            resid_abs / throughput if throughput_defined else float("nan")),
        "energy_balance_throughput_defined": throughput_defined,
        "energy_balance_throughput_basis": ENERGY_BALANCE_THROUGHPUT_BASIS,
        "d_stored_J": d_stored,
    }


class CycloturbineSim:
    """High-level simulation orchestrator.  Wraps the engine kernel with
    configuration management, wind generation, and post-processing."""

    def __init__(self, geo: Geometry, mass: MassProps, aero: AeroConfig, sim: SimConfig,
                 polar_db: PolarDatabase | None = None):
        from .database import PolarDatabase

        self.geo, self.mass, self.aero, self.sim = geo, mass, aero, sim
        self.ar_len = geo.ar * geo.c
        self.sp_len = geo.sp * geo.c
        self.Rp = geo.R - self.ar_len
        self.xq = 0.25 * geo.c - self.sp_len
        self.xm = 0.50 * geo.c - self.sp_len
        self.xb = -self.sp_len + mass.xbcg * geo.c
        self._resolve_balance()
        self.polar_db = polar_db or PolarDatabase(aero.polar_dir, geo,
                                                  variant=aero.polar_variant)
        self.wstop = aero.wstop
        self.win = math.radians(aero.win_deg)
        self.ks = self.Ip * self.wstop ** 2
        self.cs = 2.0 * self.Ip * self.wstop
        self.arm_k = (geo.N * geo.n_arm * sim.rho * geo.arm_cd * geo.arm_d * geo.R ** 4 / 8.0)
        AR = geo.H / geo.c
        self.AR = AR
        # Finite-span lift-slope correction: Helmbold (1942).
        #   a   = a0 / (sqrt(1 + (a0/(pi*AR))^2) + a0/(pi*AR)),  a0 = 2*pi
        #   f_ar = a/a0 = 1 / (sqrt(1 + (2/AR)^2) + 2/AR)
        # The previous generalized-Prandtl form 1/(1 + 1.8/(e*AR)) matched
        # Helmbold at high AR but was ~12 % too generous at the Sharp AR of
        # 2.86: it gave f_ar = 0.588 (lift slope 3.70/rad) where Helmbold
        # gives 0.520 (3.27/rad).  The empirical Oswald factor now enters only
        # the induced-drag term, where it belongs.
        # tip_loss_multiplier is a residual model-form multiplier around the
        # Helmbold central estimate; tip_loss_floor_override is retained for
        # back-compat and applied last.
        f_ar_raw  = 1.0 / (math.sqrt(1.0 + (2.0 / AR) ** 2) + 2.0 / AR)
        ind_k_raw = 1.0 / (math.pi * aero.e_osw * AR)
        f_ar_scaled = min(1.0, max(0.0, f_ar_raw * aero.tip_loss_multiplier))
        self.f_ar  = max(aero.tip_loss_floor_override, f_ar_scaled)
        self.ind_k = ind_k_raw * aero.ind_drag_scale
        if aero.c_scale_override > 0.0:
            self.c_scale = float(aero.c_scale_override)
        else:
            self.c_scale = min(1.0, (geo.c / geo.R) / 0.418)   # Adams fit at c/r=0.418

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
        # natural pitching frequency / rotor frequency (Sharp's design rule: >= 1.5).
        # Reported in run() results as 'pitch_freq_ratio'.  Pawsey's ratio is the inverse.
        self.fn_ratio = math.sqrt(self.M * self.Rp * self.ar_len / self.Ip) if self.ar_len > 0 else 0.0

    def _make_wind(self, n):
        """Generate wind time series with optional gust and turbulence.

        Supports two turbulence models:
        - Dryden:    Phi(k) = 2 * sigma^2 * L / (1 + (k*L)^2)
        - von Karman: Phi(k) = 0.47 * sigma^2 * L / (1 + (k*L)^2)^(5/6)

        where k = 2*pi*f / U is the wavenumber, L is integral length scale.
        Both implemented via state-space representation (shaping filter).
        """
        sim = self.sim
        dt = sim.dt
        t = np.arange(n) * dt
        U = np.full(n, sim.U)

        if sim.gust_g > 0 and sim.gust_tg > 0:
            m = (t >= sim.gust_t0) & (t <= sim.gust_t0 + sim.gust_tg)
            U[m] *= 1.0 + sim.gust_g * 0.5 * (1.0 - np.cos(TWO_PI * (t[m] - sim.gust_t0) / sim.gust_tg))

        if sim.turb_I > 0:
            rng = np.random.default_rng(sim.seed)

            U_mean = sim.U
            L = sim.turb_L
            I = sim.turb_I
            model = getattr(sim, "turb_model", "dryden")

            tau = L / max(U_mean, 1e-3)  # integral time scale
            sigma = I * U_mean

            if model == "vonkarman":
                # von Kármán spectrum: Phi(f) = 0.47 * sigma^2 * L/U / (1 + (2*pi*f*L/U)^2)^(5/6)
                # Generated via FFT synthesis with exact spectral control.
                # The 0.47 is the spectral amplitude coefficient; the spectrum
                # integrates to sigma^2 (the target variance). Output is scaled
                # to have exact standard deviation sigma = I * U_mean.

                if tau <= 0:
                    x = np.zeros(n)
                else:
                    # Frequency axis for rfft (non-negative frequencies)
                    f = np.fft.rfftfreq(n, d=dt)

                    # One-sided von Kármán spectral shape
                    k = 2.0 * np.pi * f * L / U_mean
                    shape = 1.0 / (1.0 + k**2)**(5/6)

                    # Random phases
                    rng = np.random.default_rng(sim.seed)
                    n_freq = len(f)

                    re = rng.standard_normal(n_freq)
                    im = rng.standard_normal(n_freq)

                    # DC and Nyquist: real only
                    im[0] = 0.0
                    if n % 2 == 0:
                        im[-1] = 0.0

                    # Apply spectral shaping
                    X = np.sqrt(shape) * (re + 1j * im)

                    # Inverse FFT to get real time series
                    x = np.fft.irfft(X, n)

                    # Remove mean and scale to exact target std
                    x -= np.mean(x)
                    x_std = np.std(x)
                    if x_std > 0:
                        x = x * sigma / x_std
            else:
                    # Dryden spectrum shaping filter (1st order)
                    # dx/dt = -x/tau + w,  u = x  (no output scaling needed)
                    # where tau = L / U, sigma = turb_I * U
                    # Continuous-time w has intensity Q = 2*sigma^2/tau
                    # Discrete-time: x[k] = a*x[k-1] + b*w[k-1]
                    # a = exp(-dt/tau), b = sigma * sqrt(1 - a^2)
                    # This gives exact stationary variance sigma^2
                    a = math.exp(-dt / tau) if tau > 0 else 0.0
                    b = sigma * math.sqrt(1.0 - a * a) if tau > 0 else 0.0

                    rng = np.random.default_rng(sim.seed)
                    x = np.zeros(n)
                    if b > 0:
                        x[0] = rng.normal(0.0, sigma)
                        for i in range(1, n):
                            x[i] = a * x[i - 1] + b * rng.standard_normal()
                    else:
                        x[:] = 0.0

            U += x
            U = np.maximum(0.3 * U_mean, U)  # prevent negative wind

        if sim.gust_g > 0 and sim.gust_tg > 0:
            m = (t >= sim.gust_t0) & (t <= sim.gust_t0 + sim.gust_tg)
            U[m] *= 1.0 + sim.gust_g * 0.5 * (1.0 - np.cos(TWO_PI * (t[m] - sim.gust_t0) / sim.gust_tg))

        return t, U

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
            math.radians(s.psi0_deg), bool(ae.prescribe_pitch), math.radians(ae.pp0_deg),
            math.radians(ae.pp1_deg),
            math.radians(ae.pp2_deg),
            math.radians(ae.pp3_deg),
            math.radians(ae.pp_ph_deg),
            bool(ae.use_dmst),
            ae.tau_rev if ae.use_dynamic_inflow else 0.02, ae.a_fix, int(ae.use_dynamic_stall),
            ae.ds_Tf, ae.ds_Tv, ae.ds_Ta, ae.ds_Kv, bool(ae.use_flow_curvature), self.c_scale,
            bool(ae.use_tip_loss), self.f_ar, self.ind_k, ae.cd_add, pdb.Cl_max, ae.ds_Knc,
            pdb.logRe_grid, pdb.alpha_grid, pdb.cla_re, pdb.Cl, pdb.Cd, pdb.Cm, ae.cm_scale)
        return self._post(out, led, t_arr, U_arr, store_history)

    def _post(self, out, led, t_arr, U_arr, store_history):
        g, s, ae = self.geo, self.sim, self.aero
        E_in, E_sh, E_arm, E_vis, E_cou, E_stop, E0, E1 = led
        diag = _energy_diagnostics(led)
        resid = float(diag["energy_balance"])
        valid = not ae.prescribe_pitch      # prescribed pitch: actuator work is not in the ledger
        if valid and diag["energy_balance_defined"] and abs(resid) > 0.02:
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
        res = {
            "out": out, "columns": OUT_COLS, "column_units": OUT_UNITS,
            "column_descriptions": OUT_DESCRIPTIONS, "t": t_arr, "U": U_arr,
            "cp": cp, "cq": cp / max(tsr_eq, 1e-3), "tsr_eq": tsr_eq, "rpm": float(w.mean() * 60.0 / TWO_PI),
            "steady": steady,
            "pitch_min": float(beta.min()), "pitch_max": float(beta.max()), "pitch_rms": float(beta.std()),
            "aoa_max": float(np.degrees(np.abs(out[m, 5]).max())),
            "stop_pct": float(100.0 * np.mean(np.abs(out[m, 3]) > 0.98 * self.win)) if self.win > 0 else 100.0,
            "pitch_freq_ratio": float(self.fn_ratio),
            "ct": float(out[m, 9].mean() / (0.5 * s.rho * s.U ** 2 * 2.0 * g.R * g.H)),
            "energy_balance": resid,
            "energy_balance_abs_J": float(diag["energy_balance_abs_J"]),
            "energy_balance_scale_J": float(diag["energy_balance_scale_J"]),
            "energy_balance_scale_basis": diag["energy_balance_scale_basis"],
            "energy_balance_defined": bool(diag["energy_balance_defined"]),
            "energy_balance_throughput": float(diag["energy_balance_throughput"]),
            "energy_balance_throughput_defined": bool(
                diag["energy_balance_throughput_defined"]),
            "energy_balance_throughput_basis": diag["energy_balance_throughput_basis"],
            "energy_balance_valid": valid,
            "pitch_summary_units": "deg",
            "pitch_summary_convention": (
                "pitch_min/max/rms are degrees of psi + delta over the last four revolutions"),
            "energies": {"aero": E_in, "shaft": E_sh, "arm": E_arm, "piv_vis": E_vis, "piv_cou": E_cou,
                          "stop": E_stop, "d_stored": E1 - E0},
            "history": {},
        }
        if store_history:
            res["history"] = {k: out[:, i] for i, k in enumerate(OUT_COLS)}
        return res


# =============================================================================
# 6. FACTORY
# =============================================================================

def create_sim_from_params(param_dict: dict[str, Any]) -> CycloturbineSim:
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

    def pick(cls):
        kw = {f.name: p[f.name] for f in fields(cls) if f.name in p}
        if cls is Geometry and "N" in kw:
            kw["N"] = int(kw["N"])
        return cls(**kw)

    return CycloturbineSim(pick(Geometry), pick(MassProps),
                           pick(AeroConfig), pick(SimConfig))