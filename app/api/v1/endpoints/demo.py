from __future__ import annotations

from fastapi import APIRouter

from app.agents.registry import get_registry
from app.core.config import get_settings
from app.db.session import initialize_database
from app.services.deepseek_client import DeepSeekClient
from app.services.neo4j_health_service import Neo4jHealthService

router = APIRouter(prefix="/demo", tags=["demo"])

DEMO_SCENARIOS = [
    {
        "id": "production-bottleneck",
        "title": "生产排程瓶颈",
        "agent_name": "production_scheduling",
        "expected_mode": "single",
        "request_text": "本周3个工单面临交期风险，CNC设备产能利用率达到92%，请分析瓶颈并给出排产优化建议。",
    },
    {
        "id": "quality-defect-root-cause",
        "title": "质量缺陷根因",
        "agent_name": "quality_inspection",
        "expected_mode": "single",
        "request_text": "最近批次缺陷率上升至8%，主要缺陷为尺寸偏差和表面粗糙度，请分析根因并给出改进建议。",
    },
    {
        "id": "maintenance-vibration",
        "title": "设备振动预警",
        "agent_name": "predictive_maintenance",
        "expected_mode": "single",
        "request_text": "CNC-001主轴振动传感器读数达到12mm/s，温度65摄氏度，请预测故障风险并生成维护建议。",
    },
    {
        "id": "supply-shortage",
        "title": "供应链缺料",
        "agent_name": "supply_chain_management",
        "expected_mode": "single",
        "request_text": "生产计划需要钢材2000kg，当前库存300kg，安全库存1000kg，请分析缺料风险并生成采购建议。",
    },
    {
        "id": "collaborative-quality-equipment-process",
        "title": "质量设备工艺协同",
        "agent_name": None,
        "expected_mode": "collaborative",
        "request_text": "质量缺陷率上升，设备振动异常需要维护处理，同时需要优化工艺参数改善良品率。",
    },
]

ACCEPTANCE_FLOW = [
    "进入仪表盘查看 MySQL、DeepSeek、Neo4j 健康状态。",
    "选择一个演示场景进入智能体工作台。",
    "执行分析并查看 summary、decision、evidence、next_actions。",
    "检查 node_feedback 是否展示完整节点链路。",
    "进入业务闭环中心查看预警、工单、报告和行动项。",
]


@router.get("/mvp")
async def read_mvp_manifest() -> dict[str, object]:
    settings = get_settings()
    registry = get_registry()
    health = {
        "database_ready": initialize_database(),
        "model_ready": DeepSeekClient().is_configured,
        "graph_ready": Neo4jHealthService(settings).check_ready(),
    }
    agents = [
        {
            "name": meta.name,
            "display_name": meta.display_name,
            "scenario_hint": meta.scenario_hint,
        }
        for meta in registry.all_meta()
    ]
    return {
        "name": "smart-manufacturing-mvp",
        "status": "ready" if health["database_ready"] else "degraded",
        "health": health,
        "agents": agents,
        "scenarios": DEMO_SCENARIOS,
        "acceptance_flow": ACCEPTANCE_FLOW,
    }
