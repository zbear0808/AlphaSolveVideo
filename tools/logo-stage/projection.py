"""Melee's stage camera as a pinhole model: where a point of the game world lands in a recording.

With the fixed camera (`slp2alpha render --static-camera`) the game shows each stage through one camera whose
numbers are in the stage's .dat file (`grGroundParam`: eye, vertical field of view, two angles). From the decomp
(NTSC 1.02):

* `Stage_80224CAC` turns the eye and the angles into the point the camera looks at. It rotates (0, 0, -100)
  about X by the vertical angle, then about Y by the horizontal angle (right-handed, `lbVector_ApplyEulerRotation`),
  and follows that ray from the eye to the plane z = 0. A negative vertical angle looks down.
* `Camera_8002DDC4` eases the camera to that eye, point and field of view (settled long before frame 1), and
  `Camera_8002AF68` hands them to the camera object. With "Disable Screen Shake" nothing is added.
* The camera object is a perspective camera with a vertical field of view, aspect 1.2173333 (`cm_803BCB64`),
  looking from the eye to the point with +Y up, no roll. Viewport 640 x 480.
* The recording is that 640 x 480 picture stretched to 640 x 528 (x 1.1 vertically), and `--scale N` multiplies
  both sizes.

World axes: +X to the right of the picture, +Y up, +Z towards the camera. Fighters, ledges and the stage's
collision are all on z = 0 and the replay's positions are x, y in the same units.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

Vec3 = Tuple[float, float, float]

ASPECT = 1.2173333          # HSD_CameraDescPerspective of the main camera (camera.c, cm_803BCB64)
XFB_WIDTH, XFB_HEIGHT = 640, 480
OUT_WIDTH, OUT_HEIGHT = 640, 528   # what Dolphin records at --scale 1 (the XFB stretched vertically by 1.1)


def _dot(a: Sequence[float], b: Sequence[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _cross(a: Sequence[float], b: Sequence[float]) -> Vec3:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _unit(a: Sequence[float]) -> Vec3:
    n = math.sqrt(_dot(a, a))
    return (a[0] / n, a[1] / n, a[2] / n)


def euler_rotate(v: Vec3, rx: float, ry: float, rz: float = 0.0) -> Vec3:
    """lbVector_ApplyEulerRotation: about X, then Y, then Z; angles in radians, right-handed."""
    x, y, z = v
    c, s = math.cos(rx), math.sin(rx)
    y, z = y * c - z * s, y * s + z * c
    c, s = math.cos(ry), math.sin(ry)
    x, z = x * c + z * s, -x * s + z * c
    c, s = math.cos(rz), math.sin(rz)
    x, y = x * c - y * s, x * s + y * c
    return (x, y, z)


@dataclass(frozen=True)
class Camera:
    eye: Vec3
    fov_deg: float
    vert_angle_deg: float = 0.0
    horz_angle_deg: float = 0.0
    aspect: float = ASPECT

    @property
    def interest(self) -> Vec3:
        """Where the camera looks: its view ray cut with the plane z = 0 (Stage_80224CAC)."""
        d = euler_rotate((0.0, 0.0, -100.0), math.radians(self.vert_angle_deg), math.radians(self.horz_angle_deg))
        t = self.eye[2] / -d[2]
        return (d[0] * t + self.eye[0], d[1] * t + self.eye[1], 0.0)

    @property
    def axes(self) -> Tuple[Vec3, Vec3, Vec3]:
        """(right, up, forward) unit vectors of the camera; forward points from the eye to the interest."""
        i = self.interest
        fwd = _unit((i[0] - self.eye[0], i[1] - self.eye[1], i[2] - self.eye[2]))
        right = _unit(_cross(fwd, (0.0, 1.0, 0.0)))
        return right, _cross(right, fwd), fwd

    @property
    def tan_half_v(self) -> float:
        return math.tan(math.radians(self.fov_deg) / 2)

    @property
    def tan_half_h(self) -> float:
        return self.tan_half_v * self.aspect

    def project(self, p: Sequence[float], scale: float = 1.0) -> Tuple[float, float]:
        """(u, v) pixel of a world point in a recording at --scale `scale` (u to the right, v down)."""
        right, up, fwd = self.axes
        d = (p[0] - self.eye[0], p[1] - self.eye[1], p[2] - self.eye[2])
        depth = _dot(d, fwd)
        if depth <= 0:
            raise ValueError("point is behind the camera")
        w, h = OUT_WIDTH * scale, OUT_HEIGHT * scale
        u = w / 2 + (w / 2) * _dot(d, right) / (depth * self.tan_half_h)
        v = h / 2 - (h / 2) * _dot(d, up) / (depth * self.tan_half_v)
        return u, v

    def unproject(self, u: float, v: float, z: float = 0.0, scale: float = 1.0) -> Tuple[float, float]:
        """The world (x, y) on the plane `z` that shows at pixel (u, v)."""
        right, up, fwd = self.axes
        w, h = OUT_WIDTH * scale, OUT_HEIGHT * scale
        a, b = (u - w / 2) / (w / 2) * self.tan_half_h, -(v - h / 2) / (h / 2) * self.tan_half_v
        ray = tuple(fwd[i] + a * right[i] + b * up[i] for i in range(3))
        t = (z - self.eye[2]) / ray[2]
        return self.eye[0] + t * ray[0], self.eye[1] + t * ray[1]

    def size(self, scale: int = 1) -> Tuple[int, int]:
        return OUT_WIDTH * scale, OUT_HEIGHT * scale

    def pixels_per_unit(self, x: float = 0.0, y: float = 0.0, z: float = 0.0, scale: float = 1.0) -> Tuple[float, float]:
        """Local pixels per world unit across and up at a point (for sizing things)."""
        u0, v0 = self.project((x, y, z), scale)
        u1, _ = self.project((x + 1.0, y, z), scale)
        _, v1 = self.project((x, y + 1.0, z), scale)
        return u1 - u0, v0 - v1


def project_all(camera: Camera, points: List[Sequence[float]], scale: float = 1.0) -> List[Tuple[float, float]]:
    return [camera.project(p, scale) for p in points]


def from_ground_param(eye: Sequence[float], fov: float, vert_angle: float, horz_angle: float = 0.0,
                      aspect: Optional[float] = None) -> Camera:
    return Camera(tuple(float(c) for c in eye), float(fov), float(vert_angle), float(horz_angle),
                  ASPECT if aspect is None else aspect)
