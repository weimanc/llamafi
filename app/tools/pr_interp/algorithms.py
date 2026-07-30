# algorithms.py — the PROP-006 reconstruction ladder.
#
# Common contract: feed fixes as they "arrive" via update(fix); ask for a
# rendered position at any later t via position(t) -> (x_m, y_m) or None
# (None = nothing to draw yet, e.g. delayed algos still filling history).
#
# All algorithms use only what the firmware would have: the Fix fields
# (quantized track/gs included). No peeking at truth. History depth is the
# study's second axis and is intrinsic to each rung (1 / 1 / 2 / 3).

import math

from model import Fix, track_to_vxy, KNOTS_TO_MS


class Reconstructor:
    name = "base"
    depth = 0

    def update(self, fix: Fix) -> None:
        raise NotImplementedError

    def position(self, t: float):
        raise NotImplementedError


class DRSnap(Reconstructor):
    """Rung 1 — dead-reckon along track/gs from the latest fix; snap on update.

    This is the M-PLANERADAR design's original 'M4-style follow-up' idea and
    the cheapest possible smoother: zero latency, one fix of state. Its known
    defect is the snap: every fix teleports the plane by the accumulated
    prediction error.
    """
    name = "dr-snap"
    depth = 1

    def __init__(self):
        self.fix = None

    def update(self, fix: Fix) -> None:
        self.fix = fix

    def position(self, t: float):
        if self.fix is None:
            return None
        dt = max(0.0, t - self.fix.t)
        vx, vy = track_to_vxy(self.fix.track_deg, self.fix.gs_knots * KNOTS_TO_MS)
        return self.fix.x + vx * dt, self.fix.y + vy * dt


class DRDamped(Reconstructor):
    """Rung 2 — dead-reckon, but blend corrections in over tau seconds.

    On each fix the rendered position does NOT jump: we keep the current
    rendered estimate and exponentially decay the offset between it and the
    new prediction line (critically-damped feel; alpha-beta in spirit).
    tau is the only tuning knob; the study sweeps it.
    """
    name = "dr-damped"
    depth = 1

    def __init__(self, tau_s: float = 2.0):
        self.fix = None
        self.off_x = 0.0        # rendered - predicted offset being bled off
        self.off_y = 0.0
        self.tau = tau_s
        self.name = f"dr-damped(tau={tau_s:g})"

    def _predict(self, t: float):
        dt = max(0.0, t - self.fix.t)
        vx, vy = track_to_vxy(self.fix.track_deg, self.fix.gs_knots * KNOTS_TO_MS)
        return self.fix.x + vx * dt, self.fix.y + vy * dt

    def update(self, fix: Fix) -> None:
        if self.fix is not None:
            # Where were we rendering the instant before the new fix landed?
            px, py = self.position(fix.t)
            self.fix = fix
            nx, ny = self._predict(fix.t)
            self.off_x = px - nx
            self.off_y = py - ny
            self._off_t0 = fix.t
        else:
            self.fix = fix
            self.off_x = self.off_y = 0.0
            self._off_t0 = fix.t

    def position(self, t: float):
        if self.fix is None:
            return None
        nx, ny = self._predict(t)
        k = math.exp(-max(0.0, t - self._off_t0) / self.tau)
        return nx + self.off_x * k, ny + self.off_y * k


class DelayedLerp(Reconstructor):
    """Rung 3 — render one interval in the past, lerp between the last 2 fixes.

    Perfectly smooth between fixes and never overshoots a turn, but the plane
    on screen is a full poll interval stale — at 30 s cadence that is 30 s of
    staleness, which the score matrix will charge as position error.
    """
    name = "delayed-lerp"
    depth = 2

    def __init__(self):
        self.hist: list[Fix] = []

    def update(self, fix: Fix) -> None:
        self.hist = (self.hist + [fix])[-2:]

    def position(self, t: float):
        if len(self.hist) < 2:
            return None
        a, b = self.hist
        span = b.t - a.t
        rt = t - span                       # render one (actual) interval back
        f = 0.0 if span <= 0 else (rt - a.t) / span
        f = min(1.0, max(0.0, f))
        return a.x + (b.x - a.x) * f, a.y + (b.y - a.y) * f


class CatmullRom(Reconstructor):
    """Rung 4 — delayed Catmull-Rom through the last 3 fixes.

    Renders inside the [h1,h2] segment (one interval stale, like rung 3) but
    with curvature borrowed from h0, so turns arc instead of chording. The
    depth-3 history is the cost being interrogated.
    """
    name = "catmull-rom"
    depth = 3

    def __init__(self):
        self.hist: list[Fix] = []

    def update(self, fix: Fix) -> None:
        self.hist = (self.hist + [fix])[-3:]

    def position(self, t: float):
        if len(self.hist) < 3:
            return None
        h0, h1, h2 = self.hist
        span = h2.t - h1.t
        rt = t - span
        f = 0.0 if span <= 0 else (rt - h1.t) / span
        f = min(1.0, max(0.0, f))
        # Catmull-Rom with p0=h0, p1=h1, p2=h2, p3=h2 extrapolated along h1->h2
        p3x = h2.x + (h2.x - h1.x)
        p3y = h2.y + (h2.y - h1.y)

        def cr(p0, p1, p2, p3, u):
            u2, u3 = u * u, u * u * u
            return 0.5 * ((2 * p1) + (-p0 + p2) * u
                          + (2 * p0 - 5 * p1 + 4 * p2 - p3) * u2
                          + (-p0 + 3 * p1 - 3 * p2 + p3) * u3)

        return (cr(h0.x, h1.x, h2.x, p3x, f),
                cr(h0.y, h1.y, h2.y, p3y, f))


def ladder(tau_sweep=(1.0, 2.0, 4.0)):
    """Fresh instances of every contender (dr-damped once per tau)."""
    return ([DRSnap()] +
            [DRDamped(tau) for tau in tau_sweep] +
            [DelayedLerp(), CatmullRom()])
