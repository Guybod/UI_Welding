# -*- coding: utf-8 -*-
"""机器人 Lua 工程 HTTP/WS SDK — 创建、覆盖、列表、槽位绑定。"""

from __future__ import annotations

import json
import logging
import random
import string
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
import websocket

logger = logging.getLogger(__name__)


class RobotProjectSDKError(Exception):
    pass


class RobotProjectSDK:
    UPDATE_TIME_JSON_PATH = "./webdata/webdb/cocontrol/updatetime.json"
    PROJECT_MAP_SIZE = 128

    def __init__(
        self,
        base_url: str,
        ws_url: Optional[str] = None,
        robot_type: str = "default",
        version: str = "2.3.3.43",
        timeout: int = 10,
        debug: bool = False,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.robot_type = robot_type
        self.version = version
        self.timeout = timeout
        self.debug = debug

        if ws_url:
            self.ws_url = ws_url
        else:
            self.ws_url = self._infer_ws_url_from_base_url(self.base_url)

        self.session = requests.Session()
        self.headers_json = {
            "Accept": "*/*",
            "Content-Type": "application/json",
            "Origin": self.base_url,
            "Referer": f"{self.base_url}/",
            "User-Agent": "Mozilla/5.0",
        }

    @classmethod
    def from_robot_ip(cls, robot_ip: str, **kwargs) -> "RobotProjectSDK":
        ip = robot_ip.strip()
        return cls(
            base_url=f"http://{ip}:9198",
            ws_url=f"ws://{ip}:9000/",
            **kwargs,
        )

    def _log(self, message: str) -> None:
        if self.debug:
            logger.debug(message)

    @staticmethod
    def _infer_ws_url_from_base_url(base_url: str) -> str:
        if base_url.startswith("https://"):
            host_part = base_url[len("https://") :]
            host = host_part.split(":")[0].split("/")[0]
            return f"wss://{host}:9000/"
        host_part = base_url.replace("http://", "")
        host = host_part.split(":")[0].split("/")[0]
        return f"ws://{host}:9000/"

    @staticmethod
    def _random_suffix(length: int = 14) -> str:
        chars = string.ascii_lowercase + string.digits
        return "".join(random.choice(chars) for _ in range(length))

    @classmethod
    def generate_project_id(cls) -> str:
        return "pr" + cls._random_suffix(14)

    @classmethod
    def generate_node_id(cls) -> str:
        return "tk" + cls._random_suffix(14)

    @staticmethod
    def _timestamp_ms() -> int:
        return int(time.time() * 1000)

    @staticmethod
    def _timestamp_str() -> str:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

    @staticmethod
    def _ensure_map_size(project_map: List[str], size: int = 128) -> List[str]:
        cleaned = [str(x) if x is not None else "" for x in project_map]
        if len(cleaned) < size:
            cleaned.extend([""] * (size - len(cleaned)))
        return cleaned[:size]

    def _request_json(
        self,
        method: str,
        url: str,
        *,
        params: Optional[dict] = None,
        json_body: Optional[Any] = None,
        step_name: str = "request",
    ) -> dict:
        resp = self.session.request(
            method=method,
            url=url,
            headers=self.headers_json,
            params=params,
            json=json_body,
            timeout=self.timeout,
        )
        self._log(f"[{step_name}] {method} {url} -> {resp.status_code}")
        resp.raise_for_status()
        try:
            result = resp.json()
        except Exception as e:
            raise RobotProjectSDKError(f"{step_name} 返回不是合法 JSON: {e}") from e
        if "code" in result and result["code"] != 909:
            raise RobotProjectSDKError(f"{step_name} 业务失败: {result}")
        return result

    def _request_text_like_json(
        self,
        method: str,
        url: str,
        text_body: str,
        *,
        step_name: str = "request_text",
    ) -> dict:
        resp = self.session.request(
            method=method,
            url=url,
            headers=self.headers_json,
            data=text_body.encode("utf-8"),
            timeout=self.timeout,
        )
        self._log(f"[{step_name}] {method} {url} -> {resp.status_code}")
        resp.raise_for_status()
        try:
            result = resp.json()
        except Exception as e:
            raise RobotProjectSDKError(f"{step_name} 返回不是合法 JSON: {e}") from e
        if "code" in result and result["code"] != 909:
            raise RobotProjectSDKError(f"{step_name} 业务失败: {result}")
        return result

    def _ws_send_and_recv_json(self, payload: dict) -> dict:
        ws = None
        try:
            ws = websocket.create_connection(
                self.ws_url,
                timeout=self.timeout,
                origin=self.base_url,
            )
            ws.send(json.dumps(payload, ensure_ascii=False))
            msg = ws.recv()
            try:
                return json.loads(msg)
            except Exception as e:
                raise RobotProjectSDKError(f"WebSocket 返回不是合法 JSON: {e}") from e
        except RobotProjectSDKError:
            raise
        except Exception as e:
            raise RobotProjectSDKError(f"WebSocket 通信失败: {e}") from e
        finally:
            if ws is not None:
                try:
                    ws.close()
                except Exception:
                    pass

    @staticmethod
    def make_var(value: Any, comment: str = "") -> dict:
        return {"value": value, "comment": comment}

    @staticmethod
    def build_vars_payload(variables: Dict[str, Any]) -> dict:
        payload: Dict[str, dict] = {}
        for var_name, item in variables.items():
            if isinstance(item, dict) and ("value" in item or "comment" in item):
                value = item.get("value", "0")
                comment = item.get("comment", "")
            else:
                value = item
                comment = ""
            payload[str(var_name)] = {"nm": str(comment), "val": str(value)}
        return payload

    @staticmethod
    def build_points_payload(points_list: List[dict]) -> dict:
        payload: Dict[str, dict] = {}
        for i, point in enumerate(points_list, start=1):
            key = f"p{i}"
            point_copy = dict(point)
            if "nm" not in point_copy or not point_copy["nm"]:
                point_copy["nm"] = key
            payload[key] = point_copy
        return payload

    def select_projectlist(self) -> dict:
        url = f"{self.base_url}/api/robotjson/projectlua/select/projectlist/"
        return self._request_json("GET", url, step_name="select_projectlist")

    def select_project(self, project_id: str) -> dict:
        url = f"{self.base_url}/api/robotjson/projectlua_{project_id}/select/project/"
        return self._request_json("GET", url, step_name="select_project")

    def update_projectlist(self, payload: dict) -> dict:
        url = f"{self.base_url}/api/robotjson/projectlua/update/projectlist/"
        return self._request_json("POST", url, json_body=payload, step_name="update_projectlist")

    def update_project(self, project_id: str, payload: dict) -> dict:
        url = f"{self.base_url}/api/robotjson/projectlua_{project_id}/update/project/"
        return self._request_json("POST", url, json_body=payload, step_name="update_project")

    def update_varsproject(self, project_id: str, payload: dict) -> dict:
        url = f"{self.base_url}/api/robotjson/projectlua_{project_id}/update/varsproject/"
        return self._request_json("POST", url, json_body=payload, step_name="update_varsproject")

    def update_varspoint(self, project_id: str, payload: dict) -> dict:
        url = f"{self.base_url}/api/robotjson/projectlua_{project_id}/update/varspoint/"
        return self._request_json("POST", url, json_body=payload, step_name="update_varspoint")

    def update_lua_code(self, project_id: str, node_id: str, lua_text: str) -> dict:
        url = f"{self.base_url}/api/robotcode/projectlua_{project_id}_lua/update/{node_id}/"
        return self._request_text_like_json("POST", url, lua_text, step_name="update_lua_code")

    def select_manage_json(self, path: str) -> dict:
        url = f"{self.base_url}/api/asaijson/manage/select/"
        return self._request_json("GET", url, params={"path": path}, step_name="select_manage_json")

    def update_manage_json(self, path: str, payload: dict) -> dict:
        url = f"{self.base_url}/api/asaijson/manage/update/"
        return self._request_json(
            "POST",
            url,
            params={"path": path},
            json_body=payload,
            step_name="update_manage_json",
        )

    def get_project_map(self, msg_id: int = 1) -> List[str]:
        payload = {"ty": "common/getProjectMap", "db": "", "id": msg_id}
        result = self._ws_send_and_recv_json(payload)
        if result.get("ty") != "common/getProjectMap":
            raise RobotProjectSDKError(f"get_project_map 返回 ty 不匹配: {result}")
        db = result.get("db")
        if not isinstance(db, list):
            raise RobotProjectSDKError(f"get_project_map 返回 db 不是数组: {result}")
        return self._ensure_map_size(db, self.PROJECT_MAP_SIZE)

    def set_project_map(self, project_map: List[str], msg_id: int = 1) -> dict:
        final_map = self._ensure_map_size(project_map, self.PROJECT_MAP_SIZE)
        payload = {"ty": "common/setProjectMap", "db": final_map, "id": msg_id}
        return self._ws_send_and_recv_json(payload)

    def bind_project_to_map_index(
        self,
        project_id: str,
        index: int,
        *,
        msg_id_get: int = 1,
        msg_id_set: int = 1,
    ) -> List[str]:
        if not (0 <= index < self.PROJECT_MAP_SIZE):
            raise RobotProjectSDKError(
                f"index 越界，必须在 0~{self.PROJECT_MAP_SIZE - 1} 之间，当前: {index}"
            )
        current_map = self.get_project_map(msg_id=msg_id_get)
        current_map[index] = project_id
        self.set_project_map(current_map, msg_id=msg_id_set)
        return current_map

    @staticmethod
    def _extract_content_object(result: dict) -> dict:
        data = result.get("data", [])
        if not data:
            return {}
        content = data[0].get("content", "{}")
        if isinstance(content, dict):
            return content
        if isinstance(content, str):
            try:
                return json.loads(content)
            except Exception:
                return {}
        return {}

    def get_projectlist_content(self) -> dict:
        return self._extract_content_object(self.select_projectlist())

    def find_project_id_by_name(self, display_name: str) -> Optional[str]:
        name = display_name.strip()
        if not name:
            return None
        for pid, meta in self.get_projectlist_content().items():
            if isinstance(meta, dict) and str(meta.get("nm", "")).strip() == name:
                return pid
        return None

    def list_projects(self) -> List[Dict[str, str]]:
        content = self.get_projectlist_content()
        items: List[Dict[str, str]] = []
        for pid, meta in content.items():
            if not isinstance(meta, dict):
                continue
            items.append({"id": str(pid), "name": str(meta.get("nm", pid))})
        items.sort(key=lambda x: x["name"].lower())
        return items

    @staticmethod
    def _find_main_node_id(project_payload: dict) -> str:
        for nid, node in project_payload.items():
            if isinstance(node, dict) and node.get("tk") == 1:
                return str(nid)
        if project_payload:
            return str(next(iter(project_payload.keys())))
        raise RobotProjectSDKError("项目无节点")

    def _read_lua_text(self, lua_file: str, include_lua_header: bool) -> str:
        lua_path = Path(lua_file)
        if not lua_path.exists():
            raise RobotProjectSDKError(f"Lua 文件不存在: {lua_file}")
        try:
            lua_text = lua_path.read_text(encoding="utf-8")
        except Exception as e:
            raise RobotProjectSDKError(f"读取 Lua 文件失败: {lua_file}, {e}") from e
        if include_lua_header and not lua_text.lstrip().startswith("--Lua"):
            lua_text = f"--Lua version 5.3 time:{self._timestamp_str()}\n{lua_text}"
        return lua_text

    def overwrite_project_lua(
        self,
        project_id: str,
        lua_file: str,
        *,
        project_name: Optional[str] = None,
        include_lua_header: bool = True,
    ) -> dict:
        project_payload = self._extract_content_object(self.select_project(project_id))
        node_id = self._find_main_node_id(project_payload)
        lua_text = self._read_lua_text(lua_file, include_lua_header)
        self.update_lua_code(project_id, node_id, lua_text)

        if project_name is not None:
            pl = dict(self.get_projectlist_content())
            if project_id in pl and isinstance(pl[project_id], dict):
                entry = dict(pl[project_id])
                entry["nm"] = project_name
                pl[project_id] = entry
                try:
                    self.select_manage_json(self.UPDATE_TIME_JSON_PATH)
                except Exception as e:
                    self._log(f"[warn] 读取 updatetime.json 失败: {e}")
                self.update_manage_json(
                    self.UPDATE_TIME_JSON_PATH, {"utprojectlist": self._timestamp_ms()}
                )
                self.update_projectlist(pl)

        return {"project_id": project_id, "node_id": node_id, "overwritten": True}

    def save_new_project(
        self,
        project_name: str,
        lua_file: str,
        points: List[dict],
        variables: Dict[str, Any],
        *,
        version: Optional[str] = None,
        robot_type: Optional[str] = None,
        include_lua_header: bool = True,
        map_index: Optional[int] = None,
        ws_msg_id_get: int = 1,
        ws_msg_id_set: int = 1,
    ) -> dict:
        project_id = self.generate_project_id()
        node_id = self.generate_node_id()
        final_version = version or self.version
        final_robot_type = robot_type or self.robot_type

        lua_text = self._read_lua_text(lua_file, include_lua_header)
        node_tail = node_id[-4:]
        project_payload = {node_id: {"nm": f"主程序-{node_tail}", "tk": 1}}
        vars_payload = self.build_vars_payload(variables)
        points_payload = self.build_points_payload(points)

        projectlist_content = dict(self.get_projectlist_content())
        projectlist_content[project_id] = {
            "nm": project_name,
            "tyrobot": final_robot_type,
            "ver": final_version,
            "varid": len(variables),
            "posid": len(points),
        }

        self.update_project(project_id, project_payload)
        self.update_varsproject(project_id, vars_payload)
        self.update_varspoint(project_id, points_payload)
        self.update_lua_code(project_id, node_id, lua_text)

        try:
            self.select_manage_json(self.UPDATE_TIME_JSON_PATH)
        except Exception as e:
            self._log(f"[warn] 读取 updatetime.json 失败: {e}")
        self.update_manage_json(
            self.UPDATE_TIME_JSON_PATH, {"utprojectlist": self._timestamp_ms()}
        )
        self.update_projectlist(projectlist_content)

        bound_map = None
        if map_index is not None:
            bound_map = self.bind_project_to_map_index(
                project_id=project_id,
                index=map_index,
                msg_id_get=ws_msg_id_get,
                msg_id_set=ws_msg_id_set,
            )

        return {
            "project_id": project_id,
            "node_id": node_id,
            "project_name": project_name,
            "var_count": len(variables),
            "point_count": len(points),
            "map_index": map_index,
            "project_map": bound_map,
        }
