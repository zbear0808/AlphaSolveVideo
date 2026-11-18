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

`LookAtCamera` is the same camera given by eye, look-at point and roll, the way the game's camera object holds
it on every frame: what `slp2alpha render --export-camera` writes (docs/camera-export.md).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

Vec3 = Tuple[float, float, float]
Size = Tuple[float, float]

ASPECT = 1.2173333          # HSD_CameraDescPerspective of the main camera (camera.c, cm_803BCB64)
XFB_WIDTH, XFB_HEIGHT = 640, 480
OUT_WIDTH, OUT_HEIGHT = 640, 528   # what Dolphin records at --scale 1 (the XFB stretched vertically by 1.1)


def picture_size(scale: float = 1.0, size: Optional[Size] = None) -> Size:
    """The picture's size in pixels: `size` if given (a recording's real size), else OUT_WIDTH x OUT_HEIGHT times
    scale. That product is only what Dolphin records at --scale 1 and 2: at 3 and 4 it records 1920 x 1580 and
    2560 x 2108, so pass the real size there (a camera export has it as render.width and render.height)."""
    return (float(size[0]), float(size[1])) if size is not None else (OUT_WIDTH * scale, OUT_HEIGHT * scale)


# What Dolphin records per --scale: the XFB stretched to the TV's shape (its height rounded up to a multiple of 4),
# or with `render --raw-resolution` the XFB itself, 640 x 480 per step.
RECORDING_SIZES = {1: (640, 528), 2: (1280, 1056), 3: (1920, 1580), 4: (2560, 2108)}


def recording_size(scale: int = 1, raw: bool = False) -> Tuple[int, int]:
    if raw:
        return XFB_WIDTH * scale, XFB_HEIGHT * scale
    return RECORDING_SIZES.get(scale, (OUT_WIDTH * scale, OUT_HEIGHT * scale))


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


def _game_sin(a: float) -> float:
    """lbvector_sin (lbvector.c): the game's fifth-order polynomial, not the true sine."""
    if a > math.pi:
        a -= 2 * math.pi
    elif a < -math.pi:
        a += 2 * math.pi
    return 0.9878619909286499 * a - 0.15527099370956421 * a ** 3 + 0.0056429998949170113 * a ** 5


def game_interest(eye: Sequence[float], vert_angle_deg: float, horz_angle_deg: float = 0.0) -> Vec3:
    """Stage_80224CAC as the game computes it, with lbVector_Rotate's polynomial sine and cosine. That's the
    fixed camera's look-at point that `--static-camera` really uses: 0.2 to 1 unit higher than Camera.interest,
    which uses the true sine and cosine (e.g. 37.066 instead of 36.233 on Battlefield). Matches a camera export
    to within 1e-5."""
    v = [0.0, 0.0, -100.0]
    for axis, deg in ((0, vert_angle_deg), (1, horz_angle_deg), (2, 0.0)):
        a = 0.0174532923847 * deg
        s, c = _game_sin(a), _game_sin(a + math.pi / 2)
        x, y, z = v
        if axis == 0:
            v = [x, y * c - z * s, y * s + z * c]
        elif axis == 1:
            v = [x * c + z * s, y, z * c - x * s]
        else:
            v = [x * c - y * s, x * s + y * c, z]
    t = eye[2] / -v[2]
    return (v[0] * t + eye[0], v[1] * t + eye[1], 0.0)


def roll_up(fwd: Vec3, roll: float = 0.0) -> Vec3:
    """roll2upvec (cobj.c): world up made perpendicular to the view direction `fwd`, turned by -roll about it."""
    e = fwd
    if 1.0 - abs(e[1]) < 0.0001:  # looking straight up or down
        x = math.sqrt(e[1] * e[1] + e[2] * e[2])
        v0 = (x, -e[1] * e[0] / x, -e[2] * e[0] / x)
    else:
        h = math.sqrt(e[0] * e[0] + e[2] * e[2])
        v0 = (-e[0] * e[1] / h, h, -e[2] * e[1] / h)
    if roll:
        c, s = math.cos(-roll), math.sin(-roll)  # PSMTXRotAxisRad(m, e, -roll), as Rodrigues' formula
        kv, kd = _cross(e, v0), _dot(e, v0)
        v0 = tuple(v0[i] * c + kv[i] * s + e[i] * kd * (1 - c) for i in range(3))
    return _unit(v0)


class _Pinhole:
    """What both cameras share: from eye, axes, vertical field of view and aspect to a picture's pixels."""

    eye: Vec3
    fov_deg: float
    aspect: float

    @property
    def axes(self) -> Tuple[Vec3, Vec3, Vec3]:
        raise NotImplementedError

    @property
    def tan_half_v(self) -> float:
        return math.tan(math.radians(self.fov_deg) / 2)

    @property
    def tan_half_h(self) -> float:
        return self.tan_half_v * self.aspect

    def project(self, p: Sequence[float], scale: float = 1.0, size: Optional[Size] = None) -> Tuple[float, float]:
        """(u, v) pixel of a world point in a recording at --scale `scale`, or of the given size (u to the right,
        v down, (0, 0) the picture's top-left corner)."""
        right, up, fwd = self.axes
        d = (p[0] - self.eye[0], p[1] - self.eye[1], p[2] - self.eye[2])
        depth = _dot(d, fwd)
        if depth <= 0:
            raise ValueError("point is behind the camera")
        w, h = picture_size(scale, size)
        u = w / 2 + (w / 2) * _dot(d, right) / (depth * self.tan_half_h)
        v = h / 2 - (h / 2) * _dot(d, up) / (depth * self.tan_half_v)
        return u, v

    def unproject(self, u: float, v: float, z: float = 0.0, scale: float = 1.0,
                  size: Optional[Size] = None) -> Tuple[float, float]:
        """The world (x, y) on the plane `z` that shows at pixel (u, v)."""
        right, up, fwd = self.axes
        w, h = picture_size(scale, size)
        a, b = (u - w / 2) / (w / 2) * self.tan_half_h, -(v - h / 2) / (h / 2) * self.tan_half_v
        ray = tuple(fwd[i] + a * right[i] + b * up[i] for i in range(3))
        t = (z - self.eye[2]) / ray[2]
        return self.eye[0] + t * ray[0], self.eye[1] + t * ray[1]

    def size(self, scale: int = 1) -> Tuple[int, int]:
        return OUT_WIDTH * scale, OUT_HEIGHT * scale

    def pixels_per_unit(self, x: float = 0.0, y: float = 0.0, z: float = 0.0, scale: float = 1.0,
                        size: Optional[Size] = None) -> Tuple[float, float]:
        """Local pixels per world unit across and up at a point (for sizing things)."""
        u0, v0 = self.project((x, y, z), scale, size)
        u1, _ = self.project((x + 1.0, y, z), scale, size)
        _, v1 = self.project((x, y + 1.0, z), scale, size)
        return u1 - u0, v0 - v1


@dataclass(frozen=True)
class Camera(_Pinhole):
    """A stage's fixed camera, from its grGroundParam: eye, field of view and the two angles."""

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


@dataclass(frozen=True)
class LookAtCamera(_Pinhole):
    """A camera given by eye, look-at point and roll, as Melee's camera object holds it: what a camera export
    (`render --export-camera`) has on every frame. The axes are built as HSD_CObjSetupViewingMtx builds them
    (roll2upvec, then C_MTXLookAt); with roll 0 and no up vector they match Camera's."""

    eye: Vec3
    interest: Vec3
    fov_deg: float
    roll: float = 0.0
    aspect: float = ASPECT
    up: Optional[Vec3] = None

    @property
    def axes(self) -> Tuple[Vec3, Vec3, Vec3]:
        fwd = _unit((self.interest[0] - self.eye[0], self.interest[1] - self.eye[1], self.interest[2] - self.eye[2]))
        hint = _unit(self.up) if self.up is not None else roll_up(fwd, self.roll)
        look = (-fwd[0], -fwd[1], -fwd[2])
        right = _unit(_cross(hint, look))
        return right, _cross(look, right), fwd


def from_sample(sample: dict, aspect: float = ASPECT) -> LookAtCamera:
    """The camera of one sample of a camera export (docs/camera-export.md)."""
    up = sample.get("up")
    return LookAtCamera(tuple(sample["eye"]), tuple(sample["interest"]), float(sample["fov"]),
                        float(sample.get("roll", 0.0)), float(aspect), tuple(up) if up else None)


def project_all(camera: _Pinhole, points: List[Sequence[float]], scale: float = 1.0) -> List[Tuple[float, float]]:
    return [camera.project(p, scale) for p in points]


def from_ground_param(eye: Sequence[float], fov: float, vert_angle: float, horz_angle: float = 0.0,
                      aspect: Optional[float] = None) -> Camera:
    return Camera(tuple(float(c) for c in eye), float(fov), float(vert_angle), float(horz_angle),
                  ASPECT if aspect is None else aspect)
