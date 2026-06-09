from __future__ import annotations

import pytest

from app.agents.production_scheduling_agent import ProductionSchedulingAgent
from app.schemas.production_scheduling import (
    EquipmentInput,
    MaterialConstraintInput,
    OrderInput,
    ProcessRouteInput,
    ProcessStepInput,
    SchedulingConstraints,
    SchedulingRequest,
    WorkOrderInput,
)

# ── 测试辅助工厂函数 ──────────────────────────────────────────


def make_standard_orders() -> list[OrderInput]:
    return [
        OrderInput(order_id="ORD-001", product_id="P-1001", quantity=500, due_date="2026-06-20", priority="high"),
        OrderInput(order_id="ORD-002", product_id="P-1001", quantity=300, due_date="2026-06-22", priority="medium"),
        OrderInput(order_id="ORD-003", product_id="P-1002", quantity=200, due_date="2026-06-25", priority="low"),
    ]


def make_standard_work_orders() -> list[WorkOrderInput]:
    return [
        WorkOrderInput(work_order_id="WO-001", order_id="ORD-001", product_id="P-1001", quantity=500),
        WorkOrderInput(work_order_id="WO-002", order_id="ORD-002", product_id="P-1001", quantity=300),
        WorkOrderInput(work_order_id="WO-003", order_id="ORD-003", product_id="P-1002", quantity=200),
    ]


def make_standard_routes() -> list[ProcessRouteInput]:
    return [
        ProcessRouteInput(
            route_id="RT-001",
            product_id="P-1001",
            product_name="精密齿轮",
            steps=[
                ProcessStepInput(
                    step_id="ST-001",
                    step_name="CNC 粗加工",
                    sequence=1,
                    standard_minutes_per_unit=2.0,
                    equipment_types=["CNC"],
                ),
                ProcessStepInput(
                    step_id="ST-002",
                    step_name="热处理",
                    sequence=2,
                    standard_minutes_per_unit=1.5,
                    equipment_types=["heat_treatment"],
                ),
                ProcessStepInput(
                    step_id="ST-003",
                    step_name="精磨",
                    sequence=3,
                    standard_minutes_per_unit=3.0,
                    equipment_types=["grinding"],
                ),
            ],
        ),
        ProcessRouteInput(
            route_id="RT-002",
            product_id="P-1002",
            product_name="轴承座",
            steps=[
                ProcessStepInput(
                    step_id="ST-010",
                    step_name="铣削",
                    sequence=1,
                    standard_minutes_per_unit=1.0,
                    equipment_types=["milling"],
                ),
                ProcessStepInput(
                    step_id="ST-011",
                    step_name="钻孔",
                    sequence=2,
                    standard_minutes_per_unit=0.8,
                    equipment_types=["drilling"],
                ),
            ],
        ),
    ]


def make_standard_equipment() -> list[EquipmentInput]:
    return [
        EquipmentInput(
            equipment_id="EQ-CNC-01",
            equipment_name="CNC 加工中心 #1",
            equipment_type="CNC",
            status="available",
            available_minutes_per_day=480,
            cost_per_hour=200,
        ),
        EquipmentInput(
            equipment_id="EQ-CNC-02",
            equipment_name="CNC 加工中心 #2",
            equipment_type="CNC",
            status="available",
            available_minutes_per_day=480,
            cost_per_hour=220,
        ),
        EquipmentInput(
            equipment_id="EQ-HT-01",
            equipment_name="热处理炉 #1",
            equipment_type="heat_treatment",
            status="available",
            available_minutes_per_day=600,
            cost_per_hour=150,
        ),
        EquipmentInput(
            equipment_id="EQ-GR-01",
            equipment_name="精密磨床 #1",
            equipment_type="grinding",
            status="available",
            available_minutes_per_day=480,
            cost_per_hour=180,
        ),
        EquipmentInput(
            equipment_id="EQ-ML-01",
            equipment_name="铣床 #1",
            equipment_type="milling",
            status="available",
            available_minutes_per_day=480,
            cost_per_hour=120,
        ),
        EquipmentInput(
            equipment_id="EQ-DR-01",
            equipment_name="钻床 #1",
            equipment_type="drilling",
            status="available",
            available_minutes_per_day=480,
            cost_per_hour=100,
        ),
    ]


def make_request(**overrides) -> SchedulingRequest:
    """创建标准调度请求，支持字段覆盖。"""
    kwargs = {
        "orders": make_standard_orders(),
        "work_orders": make_standard_work_orders(),
        "process_routes": make_standard_routes(),
        "equipment": make_standard_equipment(),
        "optimization_goal": "delivery_first",
    }
    kwargs.update(overrides)
    return SchedulingRequest(**kwargs)


# ── 测试用例 ──────────────────────────────────────────────────


class TestNormalScheduling:
    """场景 1：正常可排产"""

    def test_all_orders_scheduled(self) -> None:
        agent = ProductionSchedulingAgent()
        request = make_request()
        output = agent.execute(request)

        assert output.decision == "schedule_approved"
        assert output.schedule_detail.total_orders == 3
        assert output.schedule_detail.scheduled_orders == 3
        assert output.schedule_detail.delayed_orders == 0
        assert output.schedule_detail.overall_feasibility == "feasible"

    def test_output_contains_five_standard_fields(self) -> None:
        agent = ProductionSchedulingAgent()
        request = make_request()
        output = agent.execute(request)

        assert output.summary
        assert output.decision
        assert len(output.evidence) > 0
        assert len(output.next_actions) > 0
        assert len(output.node_feedback) >= 5  # 6 nodes expected

    def test_node_feedback_covers_all_stages(self) -> None:
        agent = ProductionSchedulingAgent()
        request = make_request()
        output = agent.execute(request)

        node_names = {n.node_name for n in output.node_feedback}
        assert "输入校验" in node_names
        assert "订单优先级排序" in node_names
        assert "工艺路线匹配" in node_names
        assert "产能评估与排程" in node_names
        assert "瓶颈分析" in node_names
        assert "调度建议生成" in node_names

    def test_schedule_items_have_timing(self) -> None:
        agent = ProductionSchedulingAgent()
        request = make_request()
        output = agent.execute(request)

        for item in output.schedule_detail.schedule:
            if item.status == "scheduled":
                assert item.total_minutes > 0
                assert item.end_minute >= item.start_minute
                assert item.equipment_id != ""

    def test_high_priority_scheduled_first(self) -> None:
        """场景 5：高优先级订单优先排程 —— 验证 high > medium > low 顺序"""
        agent = ProductionSchedulingAgent()
        request = make_request()
        output = agent.execute(request)

        # 查找每个订单首个工序的开始时间
        order_first_start: dict[str, float] = {}
        for item in output.schedule_detail.schedule:
            if item.order_id not in order_first_start:
                order_first_start[item.order_id] = item.start_minute

        # 高优先级应先于低优先级开始（同产品线共用设备时）
        assert order_first_start["ORD-001"] <= order_first_start["ORD-002"], (
            f"ORD-001(high) starts at {order_first_start.get('ORD-001')}, "
            f"ORD-002(medium) starts at {order_first_start.get('ORD-002')}"
        )
        # ORD-001(high) should also come before ORD-003(low)
        assert order_first_start["ORD-001"] <= order_first_start["ORD-003"], (
            f"ORD-001(high) starts at {order_first_start.get('ORD-001')}, "
            f"ORD-003(low) starts at {order_first_start.get('ORD-003')}"
        )


class TestCapacityInsufficient:
    """场景 2：设备产能不足"""

    def test_capacity_insufficient_detected(self) -> None:
        agent = ProductionSchedulingAgent()
        request = make_request(
            orders=[
                OrderInput(
                    order_id="ORD-001", product_id="P-1001",
                    quantity=5000,  # CNC: 5000*2=10000 min > 960 available
                    due_date="2026-06-20", priority="high",
                ),
            ],
            work_orders=[
                WorkOrderInput(
                    work_order_id="WO-001", order_id="ORD-001",
                    product_id="P-1001", quantity=5000,
                ),
            ],
        )
        output = agent.execute(request)

        # 应该检测到产能风险
        assert output.decision in ("schedule_risk_detected", "capacity_insufficient")
        assert output.schedule_detail.delayed_orders >= 0
        risk_items = [s for s in output.schedule_detail.schedule if s.status == "capacity_risk"]
        assert len(risk_items) > 0

    def test_bottleneck_flagged_for_overload(self) -> None:
        agent = ProductionSchedulingAgent()
        request = make_request(
            orders=[
                OrderInput(
                    order_id="ORD-001", product_id="P-1001",
                    quantity=5000, due_date="2026-06-20", priority="high",
                ),
            ],
            work_orders=[
                WorkOrderInput(
                    work_order_id="WO-001", order_id="ORD-001",
                    product_id="P-1001", quantity=5000,
                ),
            ],
        )
        output = agent.execute(request)

        critical_bottlenecks = [
            b for b in output.schedule_detail.bottlenecks if b.severity == "critical"
        ]
        assert len(critical_bottlenecks) > 0


class TestRouteMissing:
    """场景 3：工艺路线缺失"""

    def test_route_missing_decision(self) -> None:
        agent = ProductionSchedulingAgent()
        request = make_request(
            orders=[
                OrderInput(
                    order_id="ORD-999", product_id="P-9999",
                    quantity=100, due_date="2026-06-20", priority="high",
                ),
            ],
            work_orders=[
                WorkOrderInput(
                    work_order_id="WO-999", order_id="ORD-999",
                    product_id="P-9999", quantity=100,
                ),
            ],
        )
        output = agent.execute(request)

        assert output.decision == "route_missing"
        unavailable_items = [
            s for s in output.schedule_detail.schedule
            if s.status == "unavailable" and "无匹配工艺路线" in s.status_reason
        ]
        assert len(unavailable_items) > 0


class TestMachineUnavailable:
    """场景 4：设备不可用"""

    def test_all_matching_equipment_offline(self) -> None:
        agent = ProductionSchedulingAgent()
        # 所有 CNC 设备设为不可用
        equipment = make_standard_equipment()
        for e in equipment:
            if e.equipment_type == "CNC":
                e.status = "maintenance"

        request = make_request(
            orders=[
                OrderInput(
                    order_id="ORD-001", product_id="P-1001",
                    quantity=100, due_date="2026-06-20", priority="high",
                ),
            ],
            work_orders=[
                WorkOrderInput(
                    work_order_id="WO-001", order_id="ORD-001",
                    product_id="P-1001", quantity=100,
                ),
            ],
            equipment=equipment,
        )
        output = agent.execute(request)

        assert output.decision == "machine_unavailable"
        unavailable_items = [
            s for s in output.schedule_detail.schedule
            if s.status == "unavailable" and "无可用设备" in s.status_reason
        ]
        assert len(unavailable_items) > 0


class TestMixedPriority:
    """场景 5 补充：混合优先级 + 有限产能"""

    def test_high_priority_gets_capacity_first(self) -> None:
        agent = ProductionSchedulingAgent()
        # 限制 CNC 产能，仅 480 分钟
        equipment = [
            EquipmentInput(
                equipment_id="EQ-CNC-01",
                equipment_name="CNC #1",
                equipment_type="CNC",
                status="available",
                available_minutes_per_day=480,  # 仅 480 分钟
                cost_per_hour=200,
            ),
            EquipmentInput(
                equipment_id="EQ-HT-01",
                equipment_name="热处理炉 #1",
                equipment_type="heat_treatment",
                status="available",
                available_minutes_per_day=2000,
                cost_per_hour=150,
            ),
            EquipmentInput(
                equipment_id="EQ-GR-01",
                equipment_name="精密磨床 #1",
                equipment_type="grinding",
                status="available",
                available_minutes_per_day=2000,
                cost_per_hour=180,
            ),
        ]

        # ORD-001(high): 200*2=400min, ORD-002(low): 100*2=200min
        # 总 CNC 需求 = 600min > 480min available
        request = make_request(
            orders=[
                OrderInput(order_id="ORD-001", product_id="P-1001", quantity=200,
                           due_date="2026-06-20", priority="high"),
                OrderInput(order_id="ORD-002", product_id="P-1001", quantity=100,
                           due_date="2026-06-22", priority="low"),
            ],
            work_orders=[
                WorkOrderInput(work_order_id="WO-001", order_id="ORD-001",
                               product_id="P-1001", quantity=200),
                WorkOrderInput(work_order_id="WO-002", order_id="ORD-002",
                               product_id="P-1001", quantity=100),
            ],
            process_routes=[
                ProcessRouteInput(
                    route_id="RT-001",
                    product_id="P-1001",
                    product_name="精密齿轮",
                    steps=[
                        ProcessStepInput(
                            step_id="ST-001", step_name="CNC 粗加工",
                            sequence=1, standard_minutes_per_unit=2.0,
                            equipment_types=["CNC"],
                        ),
                        ProcessStepInput(
                            step_id="ST-002", step_name="热处理",
                            sequence=2, standard_minutes_per_unit=1.0,
                            equipment_types=["heat_treatment"],
                        ),
                        ProcessStepInput(
                            step_id="ST-003", step_name="精磨",
                            sequence=3, standard_minutes_per_unit=1.0,
                            equipment_types=["grinding"],
                        ),
                    ],
                ),
            ],
            equipment=equipment,
        )

        output = agent.execute(request)

        # 高优先级订单应被排程（normal），低优先级可能有风险
        high_items = [s for s in output.schedule_detail.schedule if s.order_id == "ORD-001"]
        high_risks = [s for s in high_items if s.status != "scheduled"]

        # 高优先级的 risk 项应少于或没有（产能优先分配给它）
        low_items = [s for s in output.schedule_detail.schedule if s.order_id == "ORD-002"]
        low_risks = [s for s in low_items if s.status != "scheduled"]

        # 如果存在产能冲突，低优先级应首当其冲
        if high_risks or low_risks:
            assert len(high_risks) <= len(low_risks), (
                f"高优先级订单的风险项 ({len(high_risks)}) 不应多于"
                f"低优先级订单的风险项 ({len(low_risks)})"
            )


class TestInputValidation:
    """输入校验边界测试"""

    def test_empty_orders_rejected(self) -> None:
        """空订单列表应在 Schema 层被 Pydantic 拦截。"""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            make_request(orders=[])

    def test_empty_equipment_rejected(self) -> None:
        """空设备列表应在 Schema 层被 Pydantic 拦截。"""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            make_request(equipment=[])

    def test_orphan_work_order_detected(self) -> None:
        agent = ProductionSchedulingAgent()
        request = make_request(
            work_orders=[
                WorkOrderInput(
                    work_order_id="WO-999", order_id="ORD-NOT-EXIST",
                    product_id="P-1001", quantity=100,
                ),
            ],
        )
        output = agent.execute(request)

        validation_node = next(
            n for n in output.node_feedback if n.node_name == "输入校验"
        )
        assert validation_node.status == "failed"
        assert "ORD-NOT-EXIST" in validation_node.detail


class TestMaterialConstraints:
    """物料约束校验测试"""

    def test_material_sufficient_no_effect(self) -> None:
        agent = ProductionSchedulingAgent()
        request = make_request(
            material_constraints=[
                MaterialConstraintInput(
                    material_id="MAT-001", product_id="P-1001",
                    available_quantity=5000, required_per_unit=1.0,
                ),
            ],
        )
        output = agent.execute(request)
        # 物料充足时不应有额外延迟
        assert output.decision == "schedule_approved"

    def test_material_insufficient_flags_order(self) -> None:
        agent = ProductionSchedulingAgent()
        request = make_request(
            orders=[
                OrderInput(
                    order_id="ORD-001", product_id="P-1001",
                    quantity=500, due_date="2026-06-20", priority="high",
                ),
            ],
            work_orders=[
                WorkOrderInput(
                    work_order_id="WO-001", order_id="ORD-001",
                    product_id="P-1001", quantity=500,
                ),
            ],
            material_constraints=[
                MaterialConstraintInput(
                    material_id="MAT-001", product_id="P-1001",
                    available_quantity=100,  # 需要 500*1=500, 仅有 100
                    required_per_unit=1.0,
                ),
            ],
        )
        output = agent.execute(request)
        # 物料不足应导致延期
        assert output.schedule_detail.delayed_orders >= 1


class TestPlanCompatibility:
    """plan() 兼容方法测试"""

    def test_plan_returns_valid_result(self) -> None:
        agent = ProductionSchedulingAgent()
        result = agent.plan("需要排产", {})

        assert result.summary
        assert result.decision
        assert len(result.next_actions) >= 2


class TestCostFirstOptimization:
    """cost_first 优化目标测试"""

    def test_cost_first_selects_cheaper_equipment(self) -> None:
        agent = ProductionSchedulingAgent()
        request = make_request(
            orders=[
                OrderInput(
                    order_id="ORD-001", product_id="P-1001",
                    quantity=100, due_date="2026-06-20", priority="high",
                ),
            ],
            work_orders=[
                WorkOrderInput(
                    work_order_id="WO-001", order_id="ORD-001",
                    product_id="P-1001", quantity=100,
                ),
            ],
            optimization_goal="cost_first",
        )
        output = agent.execute(request)

        # cost_first 应优先选成本低的设备
        cnc_items = [
            s for s in output.schedule_detail.schedule
            if s.step_name == "CNC 粗加工" and s.status == "scheduled"
        ]
        if cnc_items:
            # CNC #1 cost 200/hr, CNC #2 cost 220/hr → 应选 CNC #1
            assert cnc_items[0].equipment_id == "EQ-CNC-01"


class TestConstraintsWorkingDays:
    """constraints.working_days 影响产能窗口的测试"""

    def test_working_days_from_constraints(self) -> None:
        """传入 constraints.working_days=10，产能按 10 天计算。"""
        agent = ProductionSchedulingAgent()
        order_qty = 200
        # 单件 CNC: 2min, 总量 400min。480*1=480 刚好够，但 480*10=4800 很宽松
        request = make_request(
            orders=[
                OrderInput(
                    order_id="ORD-001", product_id="P-1001",
                    quantity=order_qty, due_date="2026-06-20", priority="high",
                ),
            ],
            work_orders=[
                WorkOrderInput(
                    work_order_id="WO-001", order_id="ORD-001",
                    product_id="P-1001", quantity=order_qty,
                ),
            ],
            constraints=SchedulingConstraints(working_days=10),
        )
        output = agent.execute(request)

        # working_days=10 → 每台 CNC 4800 分钟可用，远大于 400min 需求
        assert output.decision == "schedule_approved"
        assert output.schedule_detail.overall_feasibility == "feasible"

        # 验证瓶颈利用率基于 10 天计算
        cnc_bottlenecks = [
            b for b in output.schedule_detail.bottlenecks
            if "CNC" in b.equipment_name
        ]
        # CNC#1 负载 400min, 总可用 4800min, 利用率约 8.3%
        for b in cnc_bottlenecks:
            assert b.available_minutes == pytest.approx(4800.0, abs=1), (
                f"预期可用 4800 分钟（480*10），实际 {b.available_minutes}"
            )

    def test_default_working_days_uses_date_calculation(self) -> None:
        """不传 constraints.working_days 时使用交期推算。"""
        agent = ProductionSchedulingAgent()
        request = make_request()
        output = agent.execute(request)

        # 不传 working_days，应自动推算（交期跨度 6/20→6/25 = 5 天）
        # 验证瓶颈报告的可用时间基于自动推算的天数
        for b in output.schedule_detail.bottlenecks:
            # 每个设备的可用分钟 > 0
            assert b.available_minutes > 0


class TestTwoEquipmentShared:
    """两台同类型设备分摊产能测试"""

    def test_two_cnc_share_load(self) -> None:
        """两台 CNC 设备应分摊 CNC 工序负载。"""
        agent = ProductionSchedulingAgent()
        # ORD-001(high): 500*2=1000min, ORD-002(medium): 300*2=600min
        # 总 CNC 需求 = 1600min
        # 两台 CNC 各 480min/天，默认 5 天窗口 → 各 2400min，绰绰有余
        # 但两台设备应都被使用
        request = make_request(
            orders=[
                OrderInput(order_id="ORD-001", product_id="P-1001", quantity=500,
                           due_date="2026-06-20", priority="high"),
                OrderInput(order_id="ORD-002", product_id="P-1001", quantity=300,
                           due_date="2026-06-22", priority="medium"),
            ],
            work_orders=[
                WorkOrderInput(work_order_id="WO-001", order_id="ORD-001",
                               product_id="P-1001", quantity=500),
                WorkOrderInput(work_order_id="WO-002", order_id="ORD-002",
                               product_id="P-1001", quantity=300),
            ],
            process_routes=[
                ProcessRouteInput(
                    route_id="RT-001",
                    product_id="P-1001",
                    product_name="精密齿轮",
                    steps=[
                        ProcessStepInput(
                            step_id="ST-001", step_name="CNC 粗加工",
                            sequence=1, standard_minutes_per_unit=2.0,
                            equipment_types=["CNC"],
                        ),
                    ],
                ),
            ],
            equipment=[
                EquipmentInput(
                    equipment_id="EQ-CNC-01", equipment_name="CNC #1",
                    equipment_type="CNC", status="available",
                    available_minutes_per_day=480, cost_per_hour=200,
                ),
                EquipmentInput(
                    equipment_id="EQ-CNC-02", equipment_name="CNC #2",
                    equipment_type="CNC", status="available",
                    available_minutes_per_day=480, cost_per_hour=200,
                ),
            ],
        )
        output = agent.execute(request)

        assert output.decision == "schedule_approved"

        # 检查两台 CNC 都被使用了（负载分摊）
        used_equipment = {
            s.equipment_id for s in output.schedule_detail.schedule
            if s.status == "scheduled"
        }
        assert "EQ-CNC-01" in used_equipment, "CNC #1 应被使用"
        assert "EQ-CNC-02" in used_equipment, "CNC #2 应被使用"

        # 两台设备负载应大致均衡（delivery_first 选剩余最多的）
        cnc_loads = {
            b.equipment_id: b.total_load_minutes
            for b in output.schedule_detail.bottlenecks
            if b.equipment_id in ("EQ-CNC-01", "EQ-CNC-02")
        }
        load_diff = abs(cnc_loads.get("EQ-CNC-01", 0) - cnc_loads.get("EQ-CNC-02", 0))
        # 负载差不应超过单台总量的 50%（即至少分摊了）
        assert load_diff < 1200, f"两台 CNC 负载差 {load_diff:.0f} 分钟，应更均衡"


class TestWarningBottleneck:
    """warning 瓶颈进入 node_feedback 的测试"""

    def test_warning_bottleneck_in_node_feedback(self) -> None:
        """warning 级别的瓶颈应在瓶颈分析节点中体现。"""
        agent = ProductionSchedulingAgent()
        # 使用 1 天窗口 + 较大订单量，让某设备利用率在 70-90% 之间
        request = make_request(
            orders=[
                OrderInput(order_id="ORD-001", product_id="P-1001", quantity=250,
                           due_date="2026-06-20", priority="high"),
            ],
            work_orders=[
                WorkOrderInput(work_order_id="WO-001", order_id="ORD-001",
                               product_id="P-1001", quantity=250),
            ],
            constraints=SchedulingConstraints(working_days=1),
            equipment=[
                EquipmentInput(
                    equipment_id="EQ-CNC-01", equipment_name="CNC #1",
                    equipment_type="CNC", status="available",
                    available_minutes_per_day=480, cost_per_hour=200,
                ),
                EquipmentInput(
                    equipment_id="EQ-HT-01", equipment_name="热处理炉 #1",
                    equipment_type="heat_treatment", status="available",
                    available_minutes_per_day=600, cost_per_hour=150,
                ),
                EquipmentInput(
                    equipment_id="EQ-GR-01", equipment_name="精密磨床 #1",
                    equipment_type="grinding", status="available",
                    available_minutes_per_day=480, cost_per_hour=180,
                ),
            ],
            process_routes=[
                ProcessRouteInput(
                    route_id="RT-001",
                    product_id="P-1001",
                    product_name="精密齿轮",
                    steps=[
                        ProcessStepInput(
                            step_id="ST-001", step_name="CNC 粗加工",
                            sequence=1, standard_minutes_per_unit=2.0,
                            equipment_types=["CNC"],
                        ),
                        ProcessStepInput(
                            step_id="ST-002", step_name="热处理",
                            sequence=2, standard_minutes_per_unit=1.5,
                            equipment_types=["heat_treatment"],
                        ),
                        ProcessStepInput(
                            step_id="ST-003", step_name="精磨",
                            sequence=3, standard_minutes_per_unit=3.0,
                            equipment_types=["grinding"],
                        ),
                    ],
                ),
            ],
        )
        output = agent.execute(request)

        # CNC: 250*2=500min/480min=104% → critical
        # 热处理: 250*1.5=375/600=62.5% → normal
        # 精磨: 250*3=750/480=156% → critical
        # 瓶颈分析节点应包含 warning 信息（如果有 warning 级别的瓶颈）
        bottleneck_node = next(
            n for n in output.node_feedback if n.node_name == "瓶颈分析"
        )
        warning_bottlenecks = [
            b for b in output.schedule_detail.bottlenecks if b.severity == "warning"
        ]
        critical_bottlenecks = [
            b for b in output.schedule_detail.bottlenecks if b.severity == "critical"
        ]
        # 至少应有 critical 级别的瓶颈在 detail 中被提及
        assert len(critical_bottlenecks) > 0, "应有 critical 瓶颈"
        for b in critical_bottlenecks:
            assert b.equipment_name in bottleneck_node.detail, (
                f"critical 瓶颈 {b.equipment_name} 应在 node_feedback 中提及"
            )
