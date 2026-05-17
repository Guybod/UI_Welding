"""GLB 加载 — 保留关节层级，供 CRI 关节角驱动。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from pygltflib import GLTF2

_SKIP_NAME_PREFIX = ("arrow",)
_SKIP_NAMES = frozenset({"size", "Camera"})
_LINK_RE = re.compile(r"^Link(\d+)$", re.IGNORECASE)


@dataclass
class MeshPrimitive:
    vertices: np.ndarray  # (N,3) float32, 节点局部坐标 (m)
    normals: np.ndarray  # (N,3) float32
    indices: np.ndarray  # (M,) uint32
    node_index: int


@dataclass
class ArticulatedModel:
    nodes: list[str]
    parents: list[int]  # -1 = root
    bind_local: list[np.ndarray]  # 4x4 float64, glTF 静止姿态
    joint_node: list[int]  # node_index -> joint_index 0..5, -1 非关节
    parts: list[MeshPrimitive] = field(default_factory=list)
    center: np.ndarray = field(default_factory=lambda: np.zeros(3, dtype=np.float32))
    radius: float = 1.0
    orbit_pivot: np.ndarray = field(
        default_factory=lambda: np.zeros(3, dtype=np.float32)
    )
    source: str = ""


def _node_local_matrix(node) -> np.ndarray:
    if node.matrix:
        return np.array(node.matrix, dtype=np.float64).reshape(4, 4, order="F")
    s = np.eye(4, dtype=np.float64)
    r = np.eye(4, dtype=np.float64)
    t = np.eye(4, dtype=np.float64)
    if node.scale:
        s[:3, :3] = np.diag(node.scale)
    if node.rotation:
        qx, qy, qz, qw = node.rotation
        r[:3, :3] = _quat_to_mat(qx, qy, qz, qw)
    if node.translation:
        t[:3, 3] = node.translation
    return t @ r @ s


def _quat_to_mat(x, y, z, w) -> np.ndarray:
    xx, yy, zz = x * x, y * y, z * z
    xy, xz, yz = x * y, x * z, y * z
    wx, wy, wz = w * x, w * y, w * z
    return np.array(
        [
            [1 - 2 * (yy + zz), 2 * (xy - wz), 2 * (xz + wy)],
            [2 * (xy + wz), 1 - 2 * (xx + zz), 2 * (yz - wx)],
            [2 * (xz - wy), 2 * (yz + wx), 1 - 2 * (xx + yy)],
        ],
        dtype=np.float64,
    )


def _read_accessor(gltf: GLTF2, accessor_index: int) -> np.ndarray:
    accessor = gltf.accessors[accessor_index]
    buffer_view = gltf.bufferViews[accessor.bufferView]
    buffer = gltf.buffers[buffer_view.buffer]
    blob = gltf.get_data_from_buffer_uri(buffer.uri)
    start = (buffer_view.byteOffset or 0) + (accessor.byteOffset or 0)
    dtype = {
        5120: np.int8,
        5121: np.uint8,
        5122: np.int16,
        5123: np.uint16,
        5125: np.uint32,
        5126: np.float32,
    }[accessor.componentType]
    count = accessor.count
    comps = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[accessor.type]
    arr = np.frombuffer(blob, dtype=dtype, count=count * comps, offset=start)
    if accessor.type != "SCALAR":
        arr = arr.reshape(count, comps)
    return arr


def _compute_normals(vertices: np.ndarray, indices: np.ndarray) -> np.ndarray:
    normals = np.zeros_like(vertices)
    for i0, i1, i2 in indices.reshape(-1, 3):
        v0, v1, v2 = vertices[i0], vertices[i1], vertices[i2]
        n = np.cross(v1 - v0, v2 - v0)
        ln = np.linalg.norm(n)
        if ln > 1e-8:
            n /= ln
        normals[i0] += n
        normals[i1] += n
        normals[i2] += n
    lens = np.linalg.norm(normals, axis=1, keepdims=True)
    lens[lens < 1e-8] = 1.0
    return (normals / lens).astype(np.float32)


def _should_skip_node(name: str) -> bool:
    if not name:
        return False
    if name in _SKIP_NAMES:
        return True
    return any(name.startswith(p) for p in _SKIP_NAME_PREFIX)


def load_articulated_glb(path: Path | str) -> ArticulatedModel:
    path = Path(path)
    gltf = GLTF2().load(str(path))

    nodes: list[str] = []
    parents: list[int] = []
    bind_local: list[np.ndarray] = []
    joint_node: list[int] = []
    parts: list[MeshPrimitive] = []
    index_map: dict[int, int] = {}

    def _ensure_node(gltf_index: int, parent_ui: int) -> int:
        if gltf_index in index_map:
            return index_map[gltf_index]
        gnode = gltf.nodes[gltf_index]
        name = gnode.name or f"node_{gltf_index}"
        ui = len(nodes)
        index_map[gltf_index] = ui
        nodes.append(name)
        parents.append(parent_ui)
        # 根节点 Base 通常带 scale=0.001 (mm→m)，勿再对平移做 MM_TO_M，否则会双重缩放
        bind_local.append(_node_local_matrix(gnode))
        j_idx = -1
        m = _LINK_RE.match(name)
        if m:
            j_idx = int(m.group(1)) - 1
        joint_node.append(j_idx)
        return ui

    def _walk(gltf_index: int, parent_ui: int) -> None:
        gnode = gltf.nodes[gltf_index]
        name = gnode.name or ""
        if name in _SKIP_NAMES or name == "Camera":
            return
        ui = _ensure_node(gltf_index, parent_ui)
        if gnode.mesh is not None and not _should_skip_node(name):
            _read_mesh_primitives(gltf, gnode.mesh, ui, parts)
        for child in gnode.children or []:
            _walk(child, ui)

    scene = gltf.scenes[gltf.scene or 0]
    for root in scene.nodes or []:
        rname = gltf.nodes[root].name or ""
        if rname == "Camera":
            continue
        _walk(root, -1)

    model = ArticulatedModel(
        nodes=nodes,
        parents=parents,
        bind_local=bind_local,
        joint_node=joint_node,
        parts=parts,
        source=str(path),
    )
    model.center, model.radius = _bounds(model)
    model.orbit_pivot = compute_orbit_pivot(model)
    return model


def find_base_node_index(model: ArticulatedModel) -> int:
    for i, name in enumerate(model.nodes):
        if name.lower() == "base":
            return i
    for i, parent in enumerate(model.parents):
        if parent < 0:
            nm = model.nodes[i].lower()
            if nm != "camera" and not nm.startswith("arrow"):
                return i
    return 0


def compute_orbit_pivot(
    model: ArticulatedModel,
    joint_rad: list[float] | None = None,
) -> np.ndarray:
    """轨道中心 = Base 网格几何中心（Z-up 模型下的基座中心）。"""
    worlds = compute_world_matrices_for_model(model, joint_rad or [0.0] * 6)
    base_idx = find_base_node_index(model)
    if base_idx >= 0:
        pts: list[np.ndarray] = []
        for part in model.parts:
            if part.node_index != base_idx:
                continue
            w = worlds[part.node_index].astype(np.float32)
            ones = np.ones((part.vertices.shape[0], 1), dtype=np.float32)
            pts.append((np.hstack([part.vertices, ones]) @ w.T)[:, :3])
        if pts:
            all_pts = np.vstack(pts)
            cmin = all_pts.min(axis=0)
            cmax = all_pts.max(axis=0)
            # 基座中心：XY 取包围盒中心，Z 取底座中部（更符合“基座中心”观感）
            return np.array(
                [
                    (cmin[0] + cmax[0]) * 0.5,
                    (cmin[1] + cmax[1]) * 0.5,
                    (cmin[2] + cmax[2]) * 0.5,
                ],
                dtype=np.float32,
            )
        return worlds[base_idx][:3, 3].astype(np.float32)
    for i, parent in enumerate(model.parents):
        if parent < 0:
            nm = model.nodes[i].lower()
            if nm != "camera" and not nm.startswith("arrow"):
                return worlds[i][:3, 3].astype(np.float32)
    return model.center.astype(np.float32)


def _read_mesh_primitives(
    gltf: GLTF2, mesh_index: int, node_index: int, out: list[MeshPrimitive]
) -> None:
    mesh = gltf.meshes[mesh_index]
    for prim in mesh.primitives:
        if prim.attributes.POSITION is None:
            continue
        pos = _read_accessor(gltf, prim.attributes.POSITION).astype(np.float32)
        if prim.indices is not None:
            indices = _read_accessor(gltf, prim.indices).astype(np.uint32).reshape(-1)
        else:
            indices = np.arange(pos.shape[0], dtype=np.uint32)
        if prim.attributes.NORMAL is not None:
            nrm = _read_accessor(gltf, prim.attributes.NORMAL).astype(np.float32)
            lens = np.linalg.norm(nrm, axis=1, keepdims=True)
            lens[lens < 1e-8] = 1.0
            normals = (nrm / lens).astype(np.float32)
        else:
            normals = _compute_normals(pos, indices)
        out.append(
            MeshPrimitive(
                vertices=pos,
                normals=normals,
                indices=indices,
                node_index=node_index,
            )
        )


def _bounds(model: ArticulatedModel) -> tuple[np.ndarray, float]:
    if not model.parts:
        return np.zeros(3, dtype=np.float32), 1.0
    worlds = compute_world_matrices_for_model(model, [0.0] * 6)
    pts = []
    for part in model.parts:
        w = worlds[part.node_index].astype(np.float32)
        ones = np.ones((part.vertices.shape[0], 1), dtype=np.float32)
        pw = (np.hstack([part.vertices, ones]) @ w.T)[:, :3]
        pts.append(pw)
    all_pts = np.vstack(pts)
    cmin = all_pts.min(axis=0)
    cmax = all_pts.max(axis=0)
    center = ((cmin + cmax) * 0.5).astype(np.float32)
    radius = float(np.linalg.norm(cmax - center))
    return center, max(radius, 1e-3)


def _axis_rotation(axis: str, angle: float) -> np.ndarray:
    c, s = float(np.cos(angle)), float(np.sin(angle))
    if axis == "x":
        r = np.array([[1, 0, 0], [0, c, -s], [0, s, c]], dtype=np.float64)
    elif axis == "y":
        r = np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]], dtype=np.float64)
    else:
        r = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]], dtype=np.float64)
    m = np.eye(4, dtype=np.float64)
    m[:3, :3] = r
    return m


def compute_world_matrices_for_model(
    model: ArticulatedModel,
    joint_rad: list[float],
    joint_axes: list[str] | None = None,
    joint_signs: list[float] | None = None,
) -> list[np.ndarray]:
    axes = joint_axes or ["z", "y", "y", "y", "z", "y"]
    signs = joint_signs or [1.0] * 6
    return _compute_worlds_impl(
        model.bind_local,
        model.parents,
        joint_rad,
        axes,
        signs,
        model.joint_node,
    )


def _compute_worlds_impl(
    bind_local,
    parents,
    joint_rad,
    axes,
    signs,
    joint_node,
) -> list[np.ndarray]:
    n = len(bind_local)
    if joint_node is None:
        joint_node = [-1] * n
    worlds: list[np.ndarray] = [np.eye(4, dtype=np.float64) for _ in range(n)]
    order = _topo_order(parents)
    for i in order:
        bind = bind_local[i]
        local = bind.copy()
        j = joint_node[i]
        if j >= 0 and j < len(joint_rad):
            axis = axes[j] if j < len(axes) else "z"
            sign = signs[j] if j < len(signs) else 1.0
            rj = _axis_rotation(axis, float(joint_rad[j]) * sign)
            # 与 GLB 节点一致：先平移（bind）再绕子坐标系转（保持连杆不断）
            local = bind @ rj
        p = parents[i]
        worlds[i] = local if p < 0 else worlds[p] @ local
    return worlds


def _topo_order(parents: list[int]) -> list[int]:
    n = len(parents)
    order: list[int] = []
    seen = [False] * n

    def visit(i: int) -> None:
        if seen[i]:
            return
        p = parents[i]
        if p >= 0:
            visit(p)
        seen[i] = True
        order.append(i)

    for i in range(n):
        visit(i)
    return order


# 兼容旧接口
LoadedMesh = MeshPrimitive
LoadedModel = ArticulatedModel


def load_glb(path: Path | str) -> ArticulatedModel:
    return load_articulated_glb(path)
