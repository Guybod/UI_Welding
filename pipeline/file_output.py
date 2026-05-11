"""焊接点位 TXT + JSON 文件输出"""

import json
import os
from datetime import datetime
from core.types import WeldPointSegment, Pose


def _pose_to_str(pose: Pose) -> str:
    p = pose.position
    o = pose.orientation_euler_deg
    return f"{p.x:.3f},{p.y:.3f},{p.z:.3f},{o.rx:.3f},{o.ry:.3f},{o.rz:.3f}"


def _pose_to_dict(pose: Pose) -> dict:
    return {
        "x": round(pose.position.x, 3),
        "y": round(pose.position.y, 3),
        "z": round(pose.position.z, 3),
        "rx": round(pose.orientation_euler_deg.rx, 3),
        "ry": round(pose.orientation_euler_deg.ry, 3),
        "rz": round(pose.orientation_euler_deg.rz, 3),
    }


def write_weld_txt(
    segments: list[WeldPointSegment],
    output_path: str,
    metadata: dict | None = None,
):
    """写入焊接点位 TXT 文件。

    Format:
        SEGMENT id=... source=... role=... closed=...
        phase,index,x,y,z,rx,ry,rz,tag
        ...
        END_SEGMENT
    """
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("# Robot Text/Shape Weld Point File\n")
        f.write("# version: 1.0\n")
        f.write("# units: position=mm, orientation=deg\n")
        if metadata:
            for k, v in metadata.items():
                f.write(f"# {k}: {v}\n")
        f.write("\n")

        for seg in segments:
            src = seg.metadata.get("source", "")
            role = seg.metadata.get("role", seg.metadata.get("glyph", ""))
            glyph = seg.metadata.get("glyph", "")
            source_info = f"source={glyph}" if glyph else f"source={src}"
            f.write(f"SEGMENT id={seg.id} {source_info} role={role} "
                    f"closed={str(seg.closed).lower()}\n")
            f.write("# phase,index,x,y,z,rx,ry,rz,tag\n")

            phases = [
                ("approach", seg.approach_path),
                ("arc_start", seg.arc_start_path),
                ("lead_in", seg.lead_in_path),
                ("main", seg.main_weld_path),
                ("overlap", seg.overlap_path),
                ("lead_out", seg.lead_out_path),
                ("arc_end", seg.arc_end_path),
                ("retreat", seg.retreat_path),
            ]

            for phase_name, poses in phases:
                for idx, pose in enumerate(poses):
                    f.write(f"{phase_name},{idx},{_pose_to_str(pose)},{phase_name}\n")

            f.write("END_SEGMENT\n\n")


def write_weld_json(
    segments: list[WeldPointSegment],
    output_path: str,
    metadata: dict | None = None,
):
    """写入焊接点位 JSON 文件。"""
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    data = {
        "version": "1.0",
        "units": "position=mm, orientation=deg",
        "metadata": metadata or {},
        "segments": [],
    }

    phase_names = [
        "approach", "arc_start", "lead_in", "main",
        "overlap", "lead_out", "arc_end", "retreat",
    ]

    for seg in segments:
        seg_data = {
            "id": seg.id,
            "closed": seg.closed,
            "overlap_length_mm": seg.overlap_length_mm,
            "metadata": seg.metadata,
            "phases": {},
        }
        phase_list = [
            seg.approach_path, seg.arc_start_path, seg.lead_in_path,
            seg.main_weld_path, seg.overlap_path, seg.lead_out_path,
            seg.arc_end_path, seg.retreat_path,
        ]
        for name, poses in zip(phase_names, phase_list):
            seg_data["phases"][name] = [_pose_to_dict(p) for p in poses]

        data["segments"].append(seg_data)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def make_output_paths(text: str, output_dir: str = "examples/output") -> tuple[str, str]:
    """生成带时间戳的输出文件路径。"""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_text = "".join(c if c.isalnum() else "_" for c in text)[:20]
    base = os.path.join(output_dir, f"weld_{safe_text}_{ts}")
    return f"{base}.txt", f"{base}.json"
