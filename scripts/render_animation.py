"""
Render an MP4 animation of the Sharp cycloturbine at the optimiser's design point.

Requires ffmpeg on PATH for MP4 output.  Falls back to GIF otherwise.
"""
import argparse, os, sys
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.animation as manim
from matplotlib.patches import Circle
from matplotlib.gridspec import GridSpec
from vawt_core import create_sim_from_params

DESIGN = dict(
    R=0.60, H=0.40, N=3, ar=0.50, sp=0.25,
    c=0.117607, tsr=2.14487, k_load=0.0015,
    pp0_deg=+5.156, pp1_deg=-6.329, pp2_deg=+2.758, pp3_deg=-0.085,
    pp_ph_deg=0.0,
    cd_add=0.002,
    prescribe_pitch=True, free=True,
    T_max=40.0, stride=1,
    w0_frac=0.9,
)


def render(out_path="docs/animation.mp4", fps=30, n_revs=3, dpi=120):
    print(f"Running simulation (T_max = {DESIGN['T_max']} s) ...")
    r = create_sim_from_params(DESIGN).run()
    out = r["out"]
    t, th, w, psi, beta, alpha = out[:, :6].T

    # --- steady-state window ---
    m = th >= th[-1] - n_revs * 2 * np.pi
    if m.sum() < 10:
        raise RuntimeError(f"steady-state window too small: {m.sum()} samples")

    t_w, th_w, w_w = t[m], th[m], w[m]
    psi_w, alpha_w = psi[m], alpha[m]

    # --- build single-revolution lookup keyed on raw rotor angle ---
    # The pitch schedule in the core is a function of phi = th + 2*pi*k/N.
    # Blade 0's recorded psi corresponds to raw angle th_w directly.
    az_raw = th_w % (2 * np.pi)
    order = np.argsort(az_raw)
    az_s = np.concatenate([az_raw[order], [az_raw[order][0] + 2 * np.pi]])
    psi_s = np.concatenate([psi_w[order], [psi_w[order][0]]])
    alpha_s = np.concatenate([alpha_w[order], [alpha_w[order][0]]])

    # --- geometry ---
    R, c, H, N = DESIGN["R"], DESIGN["c"], DESIGN["H"], DESIGN["N"]
    ar = DESIGN["ar"] * c
    Rp = R - ar
    xq_local = 0.25 * c - DESIGN["sp"] * c   # 0 for sp=0.25

    # --- frame timeline (slow motion) ---
    w_mean = w_w.mean()
    rev_period = 2 * np.pi / w_mean
    video_sec_per_rev = 2.0
    n_frames = int(fps * n_revs * video_sec_per_rev)
    frame_t = np.linspace(t_w[0], t_w[0] + n_revs * rev_period, n_frames)
    frame_idx = np.clip(np.searchsorted(t_w, frame_t), 0, len(t_w) - 1)

    # --- figure ---
    fig = plt.figure(figsize=(13, 6.5), dpi=dpi)
    gs = GridSpec(2, 2, width_ratios=[1.5, 1.0], hspace=0.35, wspace=0.25)
    ax_rotor = fig.add_subplot(gs[:, 0])
    ax_w = fig.add_subplot(gs[0, 1])
    ax_pitch = fig.add_subplot(gs[1, 1])

    pad = 1.15
    ax_rotor.set_aspect("equal")
    ax_rotor.set_xlim(-pad * R, pad * R); ax_rotor.set_ylim(-pad * R, pad * R)
    ax_rotor.set_xlabel("x [m]"); ax_rotor.set_ylabel("y [m]")
    ax_rotor.grid(alpha=0.25)
    ax_rotor.add_patch(Circle((0, 0), R, fill=False, edgecolor="0.55", ls="--", lw=0.8))
    ax_rotor.plot([0], [0], "o", color="0.3", ms=5)
    ax_rotor.annotate("", xy=(-pad * R, pad * R * 0.95),
                      xytext=(-pad * R * 0.85, pad * R * 0.95),
                      arrowprops=dict(arrowstyle="->", color="tab:blue", lw=1.8))
    ax_rotor.text(-pad * R * 0.98, pad * R * 0.98, "wind",
                  color="tab:blue", fontsize=9)

    cmap = plt.get_cmap("coolwarm")
    alpha_norm = plt.Normalize(-15.0, 15.0)
    blade_lines, blade_dots = [], []
    for _ in range(N):
        ln, = ax_rotor.plot([], [], lw=6, solid_capstyle="round")
        dt, = ax_rotor.plot([], [], "o", ms=4, color="0.2")
        blade_lines.append(ln); blade_dots.append(dt)

    sm = plt.cm.ScalarMappable(cmap=cmap, norm=alpha_norm); sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax_rotor, shrink=0.75, pad=0.02)
    cbar.set_label("blade angle of attack [deg]", fontsize=9)

    ax_w.plot(t_w, w_w, color="tab:green", lw=1.2)
    ax_w.set_xlabel("t [s]"); ax_w.set_ylabel("omega [rad/s]")
    ax_w.set_title("Rotor speed", fontweight="bold"); ax_w.grid(alpha=0.3)
    w_dot, = ax_w.plot([], [], "o", color="tab:red", ms=6, zorder=5)

    az_deg = np.degrees(az_s[:-1])
    ax_pitch.plot(az_deg, np.degrees(psi_s[:-1]), color="tab:blue", lw=1.2, label="psi")
    ax_pitch.plot(az_deg, np.degrees(alpha_s[:-1]), color="tab:orange", lw=1.2, label="alpha")
    ax_pitch.axhline(0, color="k", lw=0.3)
    ax_pitch.set_xlabel("rotor angle [deg]")
    ax_pitch.set_ylabel("angle [deg]")
    ax_pitch.set_title("Blade kinematics", fontweight="bold")
    ax_pitch.set_xlim(0, 360); ax_pitch.set_ylim(-20, 20)
    ax_pitch.grid(alpha=0.3); ax_pitch.legend(loc="upper right", fontsize=8)
    pitch_dot, = ax_pitch.plot([], [], "o", color="tab:orange", ms=6, zorder=5)

    def update(fi):
        i = frame_idx[fi]
        th_now, w_now = th_w[i], w_w[i]

        for k in range(N):
            phi_k = th_now + 2 * np.pi * k / N
            phi_wrapped = phi_k % (2 * np.pi)

            psi_k = float(np.interp(phi_wrapped, az_s, psi_s))
            alpha_k = float(np.interp(phi_wrapped, az_s, alpha_s))
            cp_, sp_ = np.cos(psi_k), np.sin(psi_k)

            # local frame: radial and tangential unit vectors (CCW)
            rx, ry = np.cos(phi_k), np.sin(phi_k)
            tx, ty = -np.sin(phi_k), np.cos(phi_k)

            # pivot position
            xp, yp = Rp * rx, Rp * ry

            # 1/4-chord position (physics formula, correct at sp=0.25)
            stq = -xq_local * cp_ - ar * sp_
            srq = -xq_local * sp_ + ar * cp_
            x_qc = xp + stq * tx + srq * rx
            y_qc = yp + stq * ty + srq * ry

            # chord direction: tangential at psi=0, rotates toward radial by psi
            cxk = cp_ * tx + sp_ * rx
            cyk = cp_ * ty + sp_ * ry

            # blade from LE (-1/4 c behind CoP along chord? no: LE is 1/4 c ahead)
            # In our convention, CoP is at 1/4 chord from LE.
            # Chord direction points from TE to LE.
            xs, ys = x_qc - 0.75 * c * cxk, y_qc - 0.75 * c * cyk  # TE
            xe, ye = x_qc + 0.25 * c * cxk, y_qc + 0.25 * c * cyk  # LE

            blade_lines[k].set_data([xs, xe], [ys, ye])
            blade_dots[k].set_data([x_qc], [y_qc])
            color = cmap(alpha_norm(np.degrees(alpha_k)))
            blade_lines[k].set_color(color)
            blade_dots[k].set_color(color)

        w_dot.set_data([t_w[i]], [w_now])
        az_now_deg = np.degrees(th_w[i] % (2 * np.pi))
        pitch_dot.set_data([az_now_deg], [np.degrees(alpha_w[i])])

        ax_rotor.set_title(
            f"Rotor - top-down view   |   t = {t_w[i]:.3f} s   |   "
            f"omega = {w_now:.2f} rad/s   |   Cp = {r['cp']:.3f}",
            fontweight="bold", fontsize=11)

        return blade_lines + blade_dots + [w_dot, pitch_dot]

    anim = manim.FuncAnimation(fig, update, frames=n_frames,
                                interval=1000.0 / fps, blit=False)

    out_path = (out_path if os.path.isabs(out_path) else os.path.join(_ROOT, out_path))
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    try:
        anim.save(out_path,
                  writer=manim.FFMpegWriter(fps=fps, bitrate=4000,
                                             metadata={"title": "Sharp cycloturbine"}),
                  dpi=dpi)
        print(f"Wrote {out_path}  ({n_frames} frames, {fps} fps)")
    except (FileNotFoundError, RuntimeError) as exc:
        gif_path = out_path.replace(".mp4", ".gif")
        print(f"ffmpeg failed ({exc!r}); falling back to GIF -> {gif_path}")
        anim.save(gif_path, writer=manim.PillowWriter(fps=fps), dpi=dpi)

    plt.close(fig)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="docs/animation.mp4")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--revs", type=int, default=3)
    ap.add_argument("--dpi", type=int, default=120)
    args = ap.parse_args()
    render(args.out, args.fps, args.revs, args.dpi)
