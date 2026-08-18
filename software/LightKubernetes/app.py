from typing import Dict, List, Any
from fastmcp import FastMCP
try:
    from session import LightKubernetesSession
except ImportError:
    from software.LightKubernetes.session import LightKubernetesSession
import logging
import colorlog

LOG_FORMAT = '%(log_color)s%(levelname)-8s%(reset)s %(message)s'
colorlog.basicConfig(level=logging.INFO, format=LOG_FORMAT)
logger = logging.getLogger(__name__)


mcp = FastMCP("LightKubernetes")

session_dict: Dict[str, LightKubernetesSession] = {}


def get_session(session_id: str):
	session = session_dict.get(session_id)
	if session is None:
		return None, {"status": "failed", "output": "session not found"}
	return session, None


@mcp.tool
async def login(os_cfg: Dict[str, str], seed: int | None = None):
	session = LightKubernetesSession(os_cfg=os_cfg, seed=seed)
	session_dict[session.session_id] = session
	logger.info(f"A new user logged in! [{session.session_id}]")
	return {
		"status": "ok",
		"session_id": session.session_id,
		"session_info": {
			"status": "ok",
			"output": {}
        }
    }


@mcp.tool
async def logout(session_id: str | None = None):
	session, err = get_session(session_id)
	if err:
		return err
	del session_dict[session_id]
	logger.info(f"A user logged out! [{session_id}]")
	return {
        "status": "ok",
        "output": session.kubernetes_session.get_session_dict(),
    }


@mcp.tool
async def list_namespaces(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.kubernetes_session.list_namespaces()


@mcp.tool
async def list_pods(namespace: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.kubernetes_session.list_pods(namespace)


@mcp.tool
async def get_pod(namespace: str, name: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.kubernetes_session.get_pod(namespace, name)


@mcp.tool
async def delete_pod(namespace: str, name: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.kubernetes_session.delete_pod(namespace, name)


@mcp.tool
async def list_deployments(namespace: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.kubernetes_session.list_deployments(namespace)


@mcp.tool
async def get_deployment(namespace: str, name: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.kubernetes_session.get_deployment(namespace, name)


@mcp.tool
async def scale_deployment(namespace: str, name: str, replicas: int, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.kubernetes_session.scale_deployment(namespace, name, replicas)


@mcp.tool
async def list_services(namespace: str, session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.kubernetes_session.list_services(namespace)


@mcp.tool
async def list_nodes(session_id: str):
	session, err = get_session(session_id)
	if err:
		return err
	return session.kubernetes_session.list_nodes()
