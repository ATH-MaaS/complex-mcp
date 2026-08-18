import random
from typing import Dict, List, Any
from pathlib import Path
import yaml
import sys
from datetime import datetime

WORK_DIR = Path('.').__str__()
if WORK_DIR not in sys.path:
    sys.path.append(WORK_DIR)

from software.utils.core import OSConnector, DummyOSConnector
from software.utils.world_snapshot import restore_into, seed_mode, resolve_seed
from software.utils.time import TimeMachine

CORPUS_PATH = Path(__file__).resolve().parent / "corpus"


def _to_bool(v) -> bool:
    return str(v).strip().lower() == "true"


def _to_int(v) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def _labels(raw) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for pair in (raw or "").split(";"):
        pair = pair.strip()
        if not pair or "=" not in pair:
            continue
        k, v = pair.split("=", 1)
        out[k] = v
    return out


class KubernetesSession:
    """Deterministic sandbox for the Kubernetes mock, ported from the FastAPI service.

    State is loaded from the corpus at init; subsequent calls read and mutate the
    in-memory tables so repeated calls within a session stay consistent.
    """

    def __init__(self, os_cfg, seed=None):
        # Seedless: world loaded verbatim from a frozen snapshot next to
        # this module; `seed` is accepted for client compat and ignored.
        if seed_mode():
            # Seed architecture: world rolled from a seed (re-armed).
            self.rng = random.Random(resolve_seed(seed))
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()
            self.time_machine = TimeMachine(rng=self.rng)

            with open(CORPUS_PATH / "kubernetes.yaml") as f:
                info = yaml.safe_load(f)

            self.namespaces: List[Dict[str, Any]] = [
                {**n, "labels": _labels(n.get("labels"))} for n in info.get("namespaces", [])
            ]
            self.nodes: List[Dict[str, Any]] = list(info.get("nodes", []))
            self.pods: List[Dict[str, Any]] = [
                {
                    **p,
                    "restart_count": _to_int(p.get("restart_count")),
                    "ready": _to_bool(p.get("ready")),
                    "node": (p.get("node") or None),
                    "pod_ip": (p.get("pod_ip") or None),
                }
                for p in info.get("pods", [])
            ]
            self.deployments: List[Dict[str, Any]] = [
                {
                    **d,
                    "_pk": f"{d['namespace']}/{d['name']}",
                    "replicas": _to_int(d.get("replicas")),
                    "available_replicas": _to_int(d.get("available_replicas")),
                    "ready_replicas": _to_int(d.get("ready_replicas")),
                    "updated_replicas": _to_int(d.get("updated_replicas")),
                }
                for d in info.get("deployments", [])
            ]
            self.services: List[Dict[str, Any]] = [
                {
                    **s,
                    "_pk": f"{s['namespace']}/{s['name']}",
                    "port": _to_int(s.get("port")),
                    "target_port": _to_int(s.get("target_port")),
                    "external_ip": (s.get("external_ip") or None),
                }
                for s in info.get("services", [])
            ]
            from software.utils.world_data import hydrate as _hydrate_world_data
            _hydrate_world_data(self, 'LightKubernetes')
        else:
            # Seedless: world loaded verbatim from the frozen snapshot.
            restore_into(self, Path(__file__).resolve().parent / "world.pkl")
            self.os = OSConnector(session_id=os_cfg["session_id"], url=os_cfg["url"]) if os_cfg else DummyOSConnector()

    def get_session_dict(self):
        return {"pods": self.pods, "deployments": self.deployments}

    # --- helpers -----------------------------------------------------------
    def _now(self) -> str:
        return self.os.now()

    def uuid(self) -> str:
        alphabet = "0123456789abcdef"
        return ''.join(self.rng.choices(alphabet, k=16))

    def _ns_exists(self, ns: str) -> bool:
        return any(n["name"] == ns for n in self.namespaces)

    # --- serializers (k8s-style object metadata) ---------------------------
    def _ns_obj(self, ns):
        return {
            "kind": "Namespace",
            "apiVersion": "v1",
            "metadata": {
                "name": ns["name"],
                "labels": ns["labels"],
                "creationTimestamp": ns["created_time"],
            },
            "status": {"phase": ns["status"]},
        }

    def _pod_obj(self, p):
        return {
            "kind": "Pod",
            "apiVersion": "v1",
            "metadata": {
                "name": p["name"],
                "namespace": p["namespace"],
                "creationTimestamp": p["created_time"],
            },
            "spec": {
                "nodeName": p["node"],
                "containers": [{"name": p["container_name"], "image": p["image"]}],
            },
            "status": {
                "phase": p["phase"],
                "podIP": p["pod_ip"],
                "containerStatuses": [{
                    "name": p["container_name"],
                    "ready": p["ready"],
                    "restartCount": p["restart_count"],
                    "state": p["status"],
                }],
            },
        }

    def _deployment_obj(self, d):
        return {
            "kind": "Deployment",
            "apiVersion": "apps/v1",
            "metadata": {
                "name": d["name"],
                "namespace": d["namespace"],
                "creationTimestamp": d["created_time"],
            },
            "spec": {
                "replicas": d["replicas"],
                "strategy": {"type": d["strategy"]},
                "template": {
                    "spec": {"containers": [{"name": d["name"], "image": d["image"]}]},
                },
            },
            "status": {
                "replicas": d["replicas"],
                "availableReplicas": d["available_replicas"],
                "readyReplicas": d["ready_replicas"],
                "updatedReplicas": d["updated_replicas"],
            },
        }

    def _service_obj(self, s):
        return {
            "kind": "Service",
            "apiVersion": "v1",
            "metadata": {
                "name": s["name"],
                "namespace": s["namespace"],
                "creationTimestamp": s["created_time"],
            },
            "spec": {
                "type": s["type"],
                "clusterIP": s["cluster_ip"],
                "selector": _labels(s["selector"]),
                "ports": [{"port": s["port"], "targetPort": s["target_port"],
                           "protocol": s["protocol"]}],
            },
            "status": {
                "loadBalancer": (
                    {"ingress": [{"ip": s["external_ip"]}]} if s["external_ip"] else {}
                ),
            },
        }

    def _node_obj(self, n):
        return {
            "kind": "Node",
            "apiVersion": "v1",
            "metadata": {
                "name": n["name"],
                "labels": {"node-role.kubernetes.io/" + n["role"]: ""},
                "creationTimestamp": n["created_time"],
            },
            "status": {
                "capacity": {"cpu": n["cpu_capacity"], "memory": n["memory_capacity"]},
                "nodeInfo": {
                    "kubeletVersion": n["kubelet_version"],
                    "osImage": n["os_image"],
                },
                "addresses": [{"type": "InternalIP", "address": n["internal_ip"]}],
                "conditions": [{"type": "Ready",
                                "status": "True" if n["status"] == "Ready" else "False"}],
            },
        }

    def _list_envelope(self, kind, items):
        return {"kind": kind, "apiVersion": "v1", "items": items}

    # --- API methods -------------------------------------------------------
    def list_namespaces(self) -> Dict[str, Any]:
        return {"status": "ok", "output": self._list_envelope(
            "NamespaceList", [self._ns_obj(n) for n in self.namespaces])}

    def list_pods(self, namespace: str) -> Dict[str, Any]:
        if not self._ns_exists(namespace):
            return {"status": "failed", "output": f"namespace {namespace} not found"}
        pods = [self._pod_obj(p) for p in self.pods if p["namespace"] == namespace]
        return {"status": "ok", "output": self._list_envelope("PodList", pods)}

    def get_pod(self, namespace: str, name: str) -> Dict[str, Any]:
        for p in self.pods:
            if p["namespace"] == namespace and p["name"] == name:
                return {"status": "ok", "output": self._pod_obj(p)}
        return {"status": "failed", "output": f"pod {name} not found in namespace {namespace}"}

    def delete_pod(self, namespace: str, name: str) -> Dict[str, Any]:
        for i, p in enumerate(self.pods):
            if p["namespace"] == namespace and p["name"] == name:
                obj = self._pod_obj(p)
                self.pods.pop(i)
                obj["status"]["phase"] = "Terminating"
                return {"status": "ok", "output": obj}
        return {"status": "failed", "output": f"pod {name} not found in namespace {namespace}"}

    def list_deployments(self, namespace: str) -> Dict[str, Any]:
        if not self._ns_exists(namespace):
            return {"status": "failed", "output": f"namespace {namespace} not found"}
        deps = [self._deployment_obj(d) for d in self.deployments if d["namespace"] == namespace]
        return {"status": "ok", "output": self._list_envelope("DeploymentList", deps)}

    def get_deployment(self, namespace: str, name: str) -> Dict[str, Any]:
        for d in self.deployments:
            if d["namespace"] == namespace and d["name"] == name:
                return {"status": "ok", "output": self._deployment_obj(d)}
        return {"status": "failed", "output": f"deployment {name} not found in namespace {namespace}"}

    def scale_deployment(self, namespace: str, name: str, replicas: int) -> Dict[str, Any]:
        for i, d in enumerate(self.deployments):
            if d["namespace"] == namespace and d["name"] == name:
                replicas = max(0, int(replicas))
                self.deployments[i]["replicas"] = replicas
                self.deployments[i]["available_replicas"] = replicas
                self.deployments[i]["ready_replicas"] = replicas
                self.deployments[i]["updated_replicas"] = replicas
                return {"status": "ok", "output": {
                    "kind": "Scale",
                    "apiVersion": "autoscaling/v1",
                    "metadata": {"name": name, "namespace": namespace},
                    "spec": {"replicas": replicas},
                    "status": {"replicas": replicas},
                }}
        return {"status": "failed", "output": f"deployment {name} not found in namespace {namespace}"}

    def list_services(self, namespace: str) -> Dict[str, Any]:
        if not self._ns_exists(namespace):
            return {"status": "failed", "output": f"namespace {namespace} not found"}
        svcs = [self._service_obj(s) for s in self.services if s["namespace"] == namespace]
        return {"status": "ok", "output": self._list_envelope("ServiceList", svcs)}

    def list_nodes(self) -> Dict[str, Any]:
        return {"status": "ok", "output": self._list_envelope(
            "NodeList", [self._node_obj(n) for n in self.nodes])}


if __name__ == "__main__":
    s = KubernetesSession(seed=12)
    print(s.list_namespaces())
    print(s.list_pods("prod"))
    print(s.scale_deployment("prod", "api-gateway", 4))
