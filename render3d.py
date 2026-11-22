"""3D board renderer (ModernGL, offscreen) for the Pygame UI.

The engine never imports this. `Renderer.render(state, exit_known)` draws the
maze, props and characters of a GameState into a pygame Surface that ui.py
blits into the board area; the HUD and panels stay ordinary Pygame. Models are
CC0 glTF files from assets/models (see assets/LICENSES.md); a missing model is
replaced by a primitive shape so the game always runs. Light theme: pale sky,
hemisphere ambient plus one sun, soft blob shadows.
"""

from __future__ import annotations

import math
import time
from pathlib import Path

import moderngl
import numpy as np
import pygame
import trimesh
from PIL import Image

import config as C
from game import SLEEP, GameState
from search import Cell

MODELS = Path(__file__).parent / "assets" / "models"
TWEEN_S = 0.12  # walk animation time; record.py sets 0 so each video frame shows the final cell
MSAA = 4
SKY = (0.93, 0.95, 0.98)
SUN = np.array([-0.45, 0.8, 0.4], dtype="f4")
SUN /= np.linalg.norm(SUN)
# recolour the grey CC0 models
TINT = {"tom": (1.9, 1.0, 0.35), "jerry": (1.3, 1.4, 1.8), "bruno": (1.5, 1.0, 0.7)}
# halo and pin colours
ROLE_RGB = {"tom": (1.0, 0.45, 0.05), "jerry": (0.1, 0.5, 1.0), "bruno": (0.6, 0.2, 0.9)}
LABEL = {"tom": "TOM", "jerry": "JERRY", "bruno": "BRUNO"}
WALL_H = 0.55
PITCH = math.radians(66)
FOV = math.radians(30)

VERT = """
#version 330
uniform mat4 vp; uniform mat4 model; uniform vec3 sun;
in vec3 in_pos; in vec3 in_norm; in vec3 in_col;
out vec3 col; out float lit;
void main() {
    vec3 n = normalize(mat3(model) * in_norm);
    lit = 0.55 + 0.10 * n.y + 0.38 * max(dot(n, sun), 0.0);   // hemisphere + sun
    col = in_col;
    gl_Position = vp * model * vec4(in_pos, 1.0);
}"""
FRAG = """
#version 330
uniform vec3 tint; uniform float alpha;
in vec3 col; in float lit; out vec4 frag;
void main() { frag = vec4(col * tint * lit, alpha); }"""

Mesh = tuple[moderngl.VertexArray, int]


def _rgb(c: tuple[int, int, int]) -> np.ndarray:
    return np.array(c, dtype="f4") / 255.0


def _pack(pos: np.ndarray, nrm: np.ndarray, col: np.ndarray) -> np.ndarray:
    return np.hstack([pos, nrm, np.broadcast_to(col, pos.shape)]).astype("f4")


def box(x0: float, y0: float, z0: float, x1: float, y1: float, z1: float,
        col: np.ndarray, top: np.ndarray | None = None) -> np.ndarray:
    """Axis-aligned box as 36 vertices; `top` colours the +y face."""
    corners = np.array([[x, y, z] for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)], "f4")
    faces = [  # (normal, 4 corner indices ccw seen from outside)
        ((1, 0, 0), (4, 5, 7, 6)), ((-1, 0, 0), (0, 2, 3, 1)), ((0, 1, 0), (2, 6, 7, 3)),
        ((0, -1, 0), (0, 1, 5, 4)), ((0, 0, 1), (1, 3, 7, 5)), ((0, 0, -1), (0, 4, 6, 2)),
    ]
    out = []
    for n, (a, b, c, d) in faces:
        p = corners[[a, b, c, a, c, d]]
        colour = top if (top is not None and n == (0, 1, 0)) else col
        out.append(_pack(p, np.tile(np.array(n, "f4"), (6, 1)), colour))
    return np.vstack(out)


def sphere(cx: float, cy: float, cz: float, rx: float, ry: float, rz: float, col: np.ndarray,
           seg: int = 16) -> np.ndarray:
    """Smooth UV ellipsoid."""
    out = []
    for i in range(seg):
        for j in range(2 * seg):
            def pt(a: int, b: int) -> np.ndarray:
                th, ph = math.pi * a / seg, math.pi * b / seg
                return np.array([math.sin(th) * math.cos(ph), math.cos(th),
                                 math.sin(th) * math.sin(ph)], "f4")
            n = np.array([pt(i, j), pt(i + 1, j), pt(i + 1, j + 1), pt(i, j), pt(i + 1, j + 1),
                          pt(i, j + 1)])
            p = n * np.array([rx, ry, rz], "f4") + np.array([cx, cy, cz], "f4")
            out.append(_pack(p, n, col))
    return np.vstack(out)


def disc(r: float, y: float, n: int = 28) -> np.ndarray:
    """Flat disc facing up (blob shadow / trap marker)."""
    ang = np.linspace(0, 2 * math.pi, n + 1)
    out = []
    for a, b in zip(ang[:-1], ang[1:], strict=True):
        p = np.array([[0, y, 0], [r * math.sin(b), y, r * math.cos(b)],
                      [r * math.sin(a), y, r * math.cos(a)]], "f4")
        out.append(_pack(p, np.tile(np.array([0, 1, 0], "f4"), (3, 1)), np.ones(3, "f4")))
    return np.vstack(out)


def ring(outer: float, inner: float, y: float, n: int = 32) -> np.ndarray:
    """Flat annulus facing up: the coloured halo under each character."""
    ang = np.linspace(0, 2 * math.pi, n + 1)
    out = []
    for a, b in zip(ang[:-1], ang[1:], strict=True):
        q = [(outer, a), (outer, b), (inner, b), (inner, a)]
        quad = np.array([[r * math.sin(t), y, r * math.cos(t)] for r, t in q], "f4")
        p = quad[[0, 1, 2, 0, 2, 3]]
        out.append(_pack(p, np.tile(np.array([0, 1, 0], "f4"), (6, 1)), np.ones(3, "f4")))
    return np.vstack(out)


def critter(body: tuple[int, int, int], ear: tuple[int, int, int], pointy: bool) -> np.ndarray:
    """Fallback primitive animal (facing +z): used only if a glTF model is missing."""
    b, e = _rgb(body), _rgb(ear)
    parts = [sphere(0, 0.28, 0, 0.26, 0.24, 0.34, b), sphere(0, 0.42, 0.3, 0.2, 0.19, 0.19, b),
             sphere(0, 0.4, 0.48, 0.05, 0.05, 0.05, e)]
    for s in (-1, 1):
        if pointy:
            parts.append(box(s * 0.16 - 0.05, 0.54, 0.24, s * 0.16 + 0.05, 0.72, 0.3, b))
        else:
            parts.append(sphere(s * 0.14, 0.58, 0.28, 0.09, 0.09, 0.03, e))
    return np.vstack(parts)


def load_gltf(name: str, size: float, fallback: np.ndarray, yaw: float = 0.0) -> np.ndarray:
    """Interleaved vertices of assets/models/<name>.glb, centred on the origin in x/z, resting
    on y=0, with its largest horizontal extent scaled to `size` cells. `yaw` turns it so
    the model faces +z. Falls back to a primitive when the file is absent or unreadable."""
    path = MODELS / f"{name}.glb"
    if not path.exists():
        return fallback
    try:
        scene = trimesh.load(path, force="scene")
        meshes = [g for g in scene.dump() if len(g.faces)]
    except Exception:  # unreadable asset: the primitive keeps the game playable
        return fallback
    png = path.with_suffix(".png")  # Kenney palette texture, shipped next to the model
    atlas = Image.open(png).convert("RGB") if png.exists() else None
    pos, nrm, col = [], [], []
    for m in meshes:
        f = m.faces
        pos.append(m.vertices[f].reshape(-1, 3))
        nrm.append(m.vertex_normals[f].reshape(-1, 3))
        uv = getattr(m.visual, "uv", None)
        if atlas is not None and uv is not None:  # Kenney models: colour palette image
            w, h = atlas.size
            rows = ((1 - uv[:, 1].clip(0, 1)) * (h - 1)).astype(int)  # trimesh uv: v points up
            px = np.asarray(atlas)[rows, (uv[:, 0].clip(0, 1) * (w - 1)).astype(int)]
            vc = px[:, :3] / 255.0
        else:  # flat material colour, glTF factors are linear: convert to sRGB
            vc = np.tile((m.visual.material.main_color[:3] / 255.0) ** (1 / 2.2),
                         (len(m.vertices), 1))
        col.append(vc[f].reshape(-1, 3))
    p, n, c = np.vstack(pos), np.vstack(nrm), np.vstack(col)
    ca, sa = math.cos(yaw), math.sin(yaw)
    rot = np.array([[ca, 0, sa], [0, 1, 0], [-sa, 0, ca]])
    p, n = p @ rot.T, n @ rot.T
    lo, hi = p.min(0), p.max(0)
    p = p - [(lo[0] + hi[0]) / 2, lo[1], (lo[2] + hi[2]) / 2]
    p *= size / max(hi[0] - lo[0], hi[2] - lo[2])
    return np.hstack([p, n, c]).astype("f4")


def perspective(fov: float, aspect: float, near: float, far: float) -> np.ndarray:
    f = 1 / math.tan(fov / 2)
    return np.array([[f / aspect, 0, 0, 0], [0, f, 0, 0],
                     [0, 0, (far + near) / (near - far), 2 * far * near / (near - far)],
                     [0, 0, -1, 0]], "f4")


def look_at(eye: np.ndarray, target: np.ndarray) -> np.ndarray:
    f = target - eye
    f /= np.linalg.norm(f)
    s = np.cross(f, [0, 1, 0])
    s /= np.linalg.norm(s)
    u = np.cross(s, f)
    m = np.eye(4, dtype="f4")
    m[0, :3], m[1, :3], m[2, :3] = s, u, -f
    m[:3, 3] = -m[:3, :3] @ eye
    return m


def model_matrix(x: float, y: float, z: float, yaw: float = 0.0, s: float = 1.0) -> np.ndarray:
    ca, sa = math.cos(yaw), math.sin(yaw)
    m = np.eye(4, dtype="f4")
    m[:3, :3] = np.array([[ca, 0, sa], [0, 1, 0], [-sa, 0, ca]]) * s
    m[:3, 3] = (x, y, z)
    return m


class Grid3D:
    """Screen geometry of the 3D board, for 2D overlays (same API as ui.Geometry)."""

    def __init__(self, project: Renderer, tile: int) -> None:
        self._r = project
        self.tile = tile

    def center(self, cell: Cell) -> tuple[int, int]:
        return self._r.project(cell[1] + 0.5, 0.02, cell[0] + 0.5)

    def quad(self, cell: Cell) -> list[tuple[int, int]]:
        r, c = cell
        return [self._r.project(x, 0.02, z) for x, z in
                ((c + .06, r + .06), (c + .94, r + .06), (c + .94, r + .94), (c + .06, r + .94))]


class Renderer:
    """Owns the GL context, meshes and one offscreen MSAA framebuffer."""

    def __init__(self, size: int = C.BOARD_PX) -> None:
        self.size = size
        self.ctx = moderngl.create_standalone_context()
        self.prog = self.ctx.program(vertex_shader=VERT, fragment_shader=FRAG)
        self.fbo = self.ctx.framebuffer(
            self.ctx.renderbuffer((size, size), samples=MSAA),
            self.ctx.depth_renderbuffer((size, size), samples=MSAA))
        self.out = self.ctx.framebuffer(self.ctx.renderbuffer((size, size)))
        self.meshes: dict[str, Mesh] = {}
        for name, data in {
            "tom": load_gltf("cat", 1.6, critter(C.COLOR_TOM, (0xFF, 0xC0, 0x90), True)),
            "jerry": load_gltf("mouse", 1.4, critter(C.COLOR_JERRY, C.COLOR_JERRY_EAR, False)),
            "bruno": load_gltf("dog", 1.6, critter(C.COLOR_BRUNO, (0x3E, 0x2A, 0x22), True)),
            "key": load_gltf("cheese", 0.85, box(-.2, 0, -.2, .2, .3, .2, _rgb(C.COLOR_CHEESE))),
            "exit": load_gltf("door", 1.1, box(-.3, 0, -.08, .3, .9, .08, np.ones(3, "f4"))),
            "kennel": load_gltf("kennel", 1.3, np.vstack([
                box(-.4, 0, -.35, .4, .4, .35, _rgb(C.COLOR_KENNEL)),
                box(-.46, .4, -.4, .46, .55, .4, _rgb((0x6D, 0x4C, 0x41)))])),
            "star": box(-.06, -.06, -.06, .06, .06, .06, _rgb(C.COLOR_STAR)),
            "shadow": disc(0.3, 0.012), "ring": ring(0.55, 0.42, 0.03),
            "pin": sphere(0, 0, 0, 0.13, 0.2, 0.13, np.ones(3, "f4"), seg=4),
            "trap": disc(0.28, 0.02),
        }.items():
            self.meshes[name] = self._mesh(data)
        self.maze_key: int | None = None
        self.static: Mesh | None = None
        self.vp = np.eye(4, dtype="f4")
        self.grid = Grid3D(self, 1)
        self.actors: dict[str, tuple[tuple[float, float], tuple[float, float], float, float]] = {}
        self.t0 = time.monotonic()

    def _mesh(self, data: np.ndarray) -> Mesh:
        vbo = self.ctx.buffer(data.tobytes())
        fmt = (vbo, "3f 3f 3f", "in_pos", "in_norm", "in_col")
        return self.ctx.vertex_array(self.prog, [fmt]), len(data)

    # -- scene setup
    def _build_static(self, state: GameState) -> None:
        maze = state.maze
        floor_a, floor_b = _rgb(C.COLOR_FLOOR), _rgb(C.COLOR_FLOOR) * 0.94
        wall, top = _rgb(C.COLOR_WALL), _rgb(C.COLOR_WALL_EDGE)
        base = _rgb((0xCF, 0xD6, 0xE4))
        parts = [box(-0.5, -0.3, -0.5, maze.cols + 0.5, 0.0, maze.rows + 0.5, base)]
        for r in range(maze.rows):
            for c in range(maze.cols):
                if (r, c) in maze.floor:
                    shade = floor_a if (r + c) % 2 else floor_b
                    parts.append(box(c, 0, r, c + 1, 0.01, r + 1, shade))
                else:
                    parts.append(box(c, 0, r, c + 1, WALL_H, r + 1, wall, top))
        self.static = self._mesh(np.vstack(parts))
        self.maze_key = id(maze)
        self.actors.clear()
        cx, cz = maze.cols / 2, maze.rows / 2
        target = np.array([cx, 0.0, cz], "f4")
        proj = perspective(FOV, 1.0, 0.5, 200.0)
        dist = 4.0
        while True:  # pull back until every board corner is inside the view
            eye = target + dist * np.array([0, math.sin(PITCH), math.cos(PITCH)], "f4")
            vp = proj @ look_at(eye, target)
            pts = [vp @ np.array([x, y, z, 1.0], "f4") for x in (0, maze.cols)
                   for z in (0, maze.rows) for y in (0.0, WALL_H)]
            if max(max(abs(p[0] / p[3]), abs(p[1] / p[3])) for p in pts) < 0.97:
                break
            dist += 0.5
        self.vp = vp
        self.grid = Grid3D(self, round(self.project(1.5, 0, 1)[0] - self.project(0.5, 0, 1)[0]))

    def project(self, x: float, y: float, z: float) -> tuple[int, int]:
        """World point -> pixel on the main canvas (board area offset included)."""
        p = self.vp @ np.array([x, y, z, 1.0], "f4")
        return (int(C.BOARD_X + (p[0] / p[3] + 1) / 2 * self.size),
                int(C.BOARD_Y + (1 - p[1] / p[3]) / 2 * self.size))

    # -- per-frame
    def _actor(self, name: str, cell: Cell, now: float) -> tuple[float, float, bool]:
        """Displayed (x, z) with walk tween; True while moving. Also keeps the facing yaw."""
        tgt = (cell[1] + 0.5, cell[0] + 0.5)
        src, dst, t0, yaw = self.actors.get(name, (tgt, tgt, now, 0.0))
        k = 1.0 if TWEEN_S <= 0 else min(1.0, (now - t0) / TWEEN_S)
        cur = (src[0] + (dst[0] - src[0]) * k, src[1] + (dst[1] - src[1]) * k)
        if dst != tgt:  # new target: start walking from where the piece is drawn now
            if abs(tgt[0] - cur[0]) + abs(tgt[1] - cur[1]) > 1e-6:
                yaw = math.atan2(tgt[0] - cur[0], tgt[1] - cur[1])
            src, dst, t0 = cur, tgt, now
            k, cur = (1.0, tgt) if TWEEN_S <= 0 else (0.0, cur)
        self.actors[name] = (src, dst, t0, yaw)
        return cur[0], cur[1], k < 1.0

    def _draw(self, mesh: str | Mesh, model: np.ndarray,
              tint: tuple[float, float, float] = (1, 1, 1),
              alpha: float = 1.0) -> None:
        vao, n = self.meshes[mesh] if isinstance(mesh, str) else mesh
        self.prog["model"].write(model.T.astype("f4").tobytes())
        self.prog["tint"].value = tint
        self.prog["alpha"].value = alpha
        vao.render(moderngl.TRIANGLES, vertices=n)

    def render(self, state: GameState, exit_known: bool) -> pygame.Surface:
        """Draw the whole state; returns a size x size RGB surface."""
        if self.maze_key != id(state.maze) or self.static is None:
            self._build_static(state)
        now = time.monotonic()
        t = now - self.t0
        self.labels: dict[str, tuple[int, int]] = {}
        self.fbo.use()
        self.ctx.clear(*SKY)
        self.ctx.enable(moderngl.DEPTH_TEST | moderngl.BLEND)
        self.ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
        self.prog["vp"].write(self.vp.T.astype("f4").tobytes())
        self.prog["sun"].value = tuple(SUN)
        ident = np.eye(4, dtype="f4")
        self._draw(self.static, ident)

        def put(x: float, z: float, y: float = 0.0, yaw: float = 0.0) -> np.ndarray:
            return model_matrix(x, y, z, yaw)

        self.ctx.depth_mask = False  # flat shadows / markers must not occlude each other
        for cell in state.traps:
            self._draw("trap", put(cell[1] + .5, cell[0] + .5), (0.9, 0.22, 0.2), 0.9)
        self.ctx.depth_mask = True
        kr, kc = state.maze.kennel
        self._draw("kennel", put(kc + .5, kr + .5))
        if exit_known:
            er, ec = state.maze.exit
            open_ = state.exit_open
            tint = (0.55, 0.95, 0.65) if open_ else (1, 0.55, 0.5)
            self._draw("exit", put(ec + .5, er + .5), tint)
        for kr, kc in state.keys:
            self._draw("key", put(kc + .5, kr + .5, 0.12 + 0.04 * math.sin(t * 3 + kc),
                                  t * 1.5 + kr))
        actors = [("tom", state.tom), ("jerry", state.jerry)]
        if state.bruno is not None:
            actors.append(("bruno", state.bruno.pos))
        for name, cell in actors:
            x, z, moving = self._actor(name, cell, now)
            if name == "bruno" and cell in (state.tom, state.jerry):
                x, z = x + 0.25, z + 0.25  # shared cell: nudge so he stays visible
            hop = 0.1 * abs(math.sin(t * 14)) if moving else 0.0
            yaw = self.actors[name][3]
            self.ctx.depth_mask = False
            self._draw("shadow", put(x, z), (0, 0, 0), 0.22)
            pulse = 1.0 + 0.08 * math.sin(t * 5)
            self._draw("ring", model_matrix(x, 0, z, 0, 1.15 * pulse), ROLE_RGB[name], 0.95)
            self.ctx.depth_mask = True
            self._draw("pin", put(x, z, 1.25 + 0.08 * math.sin(t * 4), t * 2), ROLE_RGB[name])
            self.labels[name] = self.project(x, 2.3, z)
            sleepy = name == "bruno" and state.bruno is not None and state.bruno.state == SLEEP
            tilt = (0.5, 0.5, 0.55) if sleepy else TINT.get(name, (1, 1, 1))
            self._draw(name, put(x, z, hop, yaw), tilt)
            if name == "tom" and state.tom_stun > 0:
                for i in range(3):
                    a = t * 4 + i * 2.1
                    self._draw("star", put(x + .3 * math.cos(a), z + .3 * math.sin(a), 1.0, a))
        self.ctx.copy_framebuffer(self.out, self.fbo)
        raw = self.out.read(components=3)
        img = pygame.image.frombuffer(raw, (self.size, self.size), "RGB")
        return pygame.transform.flip(img, False, True)

    def bruno_label_pos(self, state: GameState) -> tuple[int, int] | None:
        """Screen point above a sleeping Bruno, for the 'z' glyph."""
        b = state.bruno
        if b is None or b.state != SLEEP:
            return None
        return self.project(b.pos[1] + 0.8, 1.2, b.pos[0] + 0.5)


_renderer: Renderer | None = None
_failed = False


def get_renderer() -> Renderer | None:
    """Shared renderer, or None when no GL context can be made (UI then draws the 2D board)."""
    global _renderer, _failed
    if _renderer is None and not _failed:
        try:
            _renderer = Renderer()
        except Exception:  # no GL driver: fall back to the 2D board
            _failed = True
    return _renderer
