from __future__ import annotations

from app.schemas.production_scheduling import (
    BottleneckInfo,
    EquipmentInput,
    MaterialConstraintInput,
    OptimizationGoal,
    OrderInput,
    ProcessRouteInput,
    ProcessStepInput,
    ScheduleItem,
    SchedulingRequest,
    SchedulingResult,
    WorkOrderInput,
)

PRIORITY_ORDER: dict[str, int] = {"high": 0, "medium": 1, "low": 2}


class ProductionSchedulingService:
    """生产调度核心业务服务。

    负责工艺路线匹配、产能计算、工单排序、瓶颈分析和调度建议生成。
    """

    # ── RAG 预留接口 ──────────────────────────────────────────

    @staticmethod
    def match_process_route(
        product_id: str,
        process_routes: list[ProcessRouteInput],
    ) -> ProcessRouteInput | None:
        """根据 product_id 匹配工艺路线。

        **当前实现**：精确匹配 product_id。
        **RAG 扩展预留**：未来可替换为 embedding 语义检索，支持通过
        product_name / process_keywords 模糊匹配最合适的工艺路线，
        并返回匹配证据与置信度。
        """
        for route in process_routes:
            if route.product_id == product_id:
                return route
        return None

    # ── 排序 ──────────────────────────────────────────────────

    @staticmethod
    def sort_orders(
        orders: list[OrderInput],
        goal: OptimizationGoal = "delivery_first",
    ) -> list[OrderInput]:
        """按优先级 + 交期排序订单。

        delivery_first:
            1. 优先级 high > medium > low
            2. 同优先级按交期升序
        """
        if goal == "delivery_first":
            return sorted(orders, key=lambda o: (PRIORITY_ORDER.get(o.priority, 99), o.due_date))
        # cost_first / capacity_balance 在当前版本与 delivery_first 相同，
        # 差异体现在设备选择阶段。
        return sorted(orders, key=lambda o: (PRIORITY_ORDER.get(o.priority, 99), o.due_date))

    # ── 设备选择 ──────────────────────────────────────────────

    @staticmethod
    def select_equipment(
        step: ProcessStepInput,
        equipment_list: list[EquipmentInput],
        remaining_capacity: dict[str, float],
        goal: OptimizationGoal = "delivery_first",
    ) -> EquipmentInput | None:
        """为单个工序选择可用设备。

        规则：
        - 仅 status == "available" 的设备可选
        - 设备类型必须匹配步骤要求的 equipment_types
        - delivery_first: 在可承载当前工序的设备中，选剩余可用时间最多的
        - cost_first: 选成本最低的设备
        - capacity_balance: 选当前剩余容量占比最高的设备（均衡负载）
        - 剩余容量从 remaining_capacity 中读取（已扣除已分配的负载）
        """
        total_minutes = 0.0  # 调用方需在后续计算，此处只做设备筛选

        candidates = [
            e
            for e in equipment_list
            if e.status == "available" and e.equipment_type in step.equipment_types
        ]
        if not candidates:
            return None

        if goal == "cost_first":
            return min(candidates, key=lambda e: e.cost_per_hour)
        if goal == "capacity_balance":
            return max(
                candidates,
                key=lambda e: remaining_capacity.get(e.equipment_id, 0.0)
                / max(e.available_minutes_per_day, 1),
            )
        # delivery_first: 选剩余可用时间最多的（最不容易成为瓶颈）
        return max(candidates, key=lambda e: remaining_capacity.get(e.equipment_id, 0.0))

    # ── 产能计算 ──────────────────────────────────────────────

    @staticmethod
    def calculate_processing_minutes(quantity: int, standard_minutes_per_unit: float) -> float:
        """计算工序总加工时长（分钟）。"""
        return quantity * standard_minutes_per_unit

    # ── 物料校验 ──────────────────────────────────────────────

    @staticmethod
    def check_material_availability(
        product_id: str,
        quantity: int,
        constraints: list[MaterialConstraintInput],
    ) -> tuple[bool, str]:
        """校验物料是否充足。返回 (是否充足, 原因)。"""
        for constraint in constraints:
            if constraint.product_id == product_id:
                required = quantity * constraint.required_per_unit
                if constraint.available_quantity < required:
                    return False, (
                        f"物料 {constraint.material_id} 不足："
                        f"需要 {required:.0f}，可用 {constraint.available_quantity}"
                    )
        return True, ""

    # ── 瓶颈分析 ──────────────────────────────────────────────

    @staticmethod
    def identify_bottlenecks(
        equipment_load: dict[str, float],
        equipment_list: list[EquipmentInput],
        working_days: int = 1,
    ) -> list[BottleneckInfo]:
        """分析设备负载，识别瓶颈。

        - utilization > 90% → critical
        - utilization > 70% → warning
        - 其余 → normal
        """
        bottlenecks: list[BottleneckInfo] = []
        for equip in equipment_list:
            total_available = equip.available_minutes_per_day * working_days
            load = equipment_load.get(equip.equipment_id, 0.0)
            utilization = (load / total_available * 100) if total_available > 0 else 100.0

            if utilization > 90:
                severity = "critical"
            elif utilization > 70:
                severity = "warning"
            else:
                severity = "normal"

            bottlenecks.append(
                BottleneckInfo(
                    equipment_id=equip.equipment_id,
                    equipment_name=equip.equipment_name,
                    total_load_minutes=round(load, 1),
                    available_minutes=total_available,
                    utilization=round(utilization, 1),
                    severity=severity,
                )
            )

        bottlenecks.sort(key=lambda b: b.utilization, reverse=True)
        return bottlenecks

    # ── 调度主流程 ────────────────────────────────────────────

    def generate_schedule(self, request: SchedulingRequest) -> SchedulingResult:
        """执行生产调度，生成排程结果。"""
        orders = request.orders
        work_orders = request.work_orders
        process_routes = request.process_routes
        equipment_list = request.equipment
        goal = request.optimization_goal
        material_constraints = request.material_constraints or []

        # 计算工作天数：优先使用 constraints.working_days，为 0 时根据交期自动推算
        constraints = request.constraints
        if constraints.working_days > 0:
            working_days = constraints.working_days
        else:
            due_dates = [o.due_date for o in orders]
            working_days = max(5, (max(due_dates) - min(due_dates)).days)

        # 加班系数：allow_overtime 时扩展 20% 产能
        overtime_multiplier = 1.2 if constraints.allow_overtime else 1.0

        sorted_orders = self.sort_orders(orders, goal)

        # 设备剩余可用时间追踪（分钟），应用加班系数
        equipment_available: dict[str, float] = {
            e.equipment_id: float(e.available_minutes_per_day * working_days * overtime_multiplier)
            for e in equipment_list
        }
        # 设备累计负载追踪（原始值，用于瓶颈分析）
        equipment_load: dict[str, float] = {
            e.equipment_id: 0.0 for e in equipment_list
        }
        # 每台设备的下一个可用时间点（用于排程时序）
        equipment_next_time: dict[str, float] = {
            e.equipment_id: 0.0 for e in equipment_list
        }

        schedule: list[ScheduleItem] = []
        scheduled_order_ids: set[str] = set()
        delayed_order_ids: set[str] = set()

        for order in sorted_orders:
            order_work_orders = [wo for wo in work_orders if wo.order_id == order.order_id]
            if not order_work_orders:
                continue

            route = self.match_process_route(order.product_id, process_routes)
            if route is None:
                for wo in order_work_orders:
                    schedule.append(
                        ScheduleItem(
                            work_order_id=wo.work_order_id,
                            order_id=order.order_id,
                            product_id=order.product_id,
                            step_id="N/A",
                            step_name="工艺路线缺失",
                            sequence=0,
                            equipment_id="",
                            equipment_name="",
                            quantity=wo.quantity,
                            standard_minutes_per_unit=0,
                            total_minutes=0,
                            start_minute=0,
                            end_minute=0,
                            status="unavailable",
                            status_reason=f"产品 {order.product_id} 无匹配工艺路线",
                        )
                    )
                delayed_order_ids.add(order.order_id)
                continue

            # 物料校验
            material_ok, material_reason = self.check_material_availability(
                order.product_id, order.quantity, material_constraints
            )

            order_delayed = False
            previous_step_end: float = 0.0

            for wo in order_work_orders:
                for step in sorted(route.steps, key=lambda s: s.sequence):
                    total_minutes = self.calculate_processing_minutes(
                        wo.quantity, step.standard_minutes_per_unit
                    )

                    selected_equip = self.select_equipment(
                        step, equipment_list, equipment_available, goal
                    )

                    if selected_equip is None:
                        schedule.append(
                            ScheduleItem(
                                work_order_id=wo.work_order_id,
                                order_id=order.order_id,
                                product_id=order.product_id,
                                step_id=step.step_id,
                                step_name=step.step_name,
                                sequence=step.sequence,
                                equipment_id="",
                                equipment_name="",
                                quantity=wo.quantity,
                                standard_minutes_per_unit=step.standard_minutes_per_unit,
                                total_minutes=total_minutes,
                                start_minute=previous_step_end,
                                end_minute=previous_step_end + total_minutes,
                                status="unavailable",
                                status_reason=(
                                    f"工序 {step.step_name} 无可用设备"
                                    f"（需要类型: {', '.join(step.equipment_types)}）"
                                ),
                            )
                        )
                        order_delayed = True
                        previous_step_end += total_minutes
                        continue

                    equip_id = selected_equip.equipment_id
                    remaining = equipment_available[equip_id]

                    # 计算起止时间
                    start_minute = max(previous_step_end, equipment_next_time[equip_id])
                    end_minute = start_minute + total_minutes

                    if total_minutes > remaining:
                        status = "capacity_risk"
                        status_reason = (
                            f"设备 {selected_equip.equipment_name} 产能不足: "
                            f"需要 {total_minutes:.0f} 分钟，剩余 {remaining:.0f} 分钟"
                        )
                        order_delayed = True
                    else:
                        status = "scheduled"
                        status_reason = ""

                    equipment_available[equip_id] = remaining - total_minutes
                    equipment_load[equip_id] += total_minutes
                    equipment_next_time[equip_id] = end_minute
                    previous_step_end = end_minute

                    schedule.append(
                        ScheduleItem(
                            work_order_id=wo.work_order_id,
                            order_id=order.order_id,
                            product_id=order.product_id,
                            step_id=step.step_id,
                            step_name=step.step_name,
                            sequence=step.sequence,
                            equipment_id=equip_id,
                            equipment_name=selected_equip.equipment_name,
                            quantity=wo.quantity,
                            standard_minutes_per_unit=step.standard_minutes_per_unit,
                            total_minutes=total_minutes,
                            start_minute=start_minute,
                            end_minute=end_minute,
                            status=status,
                            status_reason=status_reason,
                        )
                    )

                if not material_ok:
                    order_delayed = True

            if order_delayed:
                delayed_order_ids.add(order.order_id)
            else:
                scheduled_order_ids.add(order.order_id)

        # 瓶颈分析
        bottlenecks = self.identify_bottlenecks(equipment_load, equipment_list, working_days)

        # 判定整体可行性
        total_orders = len(sorted_orders)
        scheduled_count = len(scheduled_order_ids)
        delayed_count = len(delayed_order_ids)

        if delayed_count == 0:
            feasibility = "feasible"
        elif scheduled_count == 0:
            feasibility = "infeasible"
        else:
            feasibility = "risk_detected"

        return SchedulingResult(
            schedule=schedule,
            bottlenecks=bottlenecks,
            total_orders=total_orders,
            scheduled_orders=scheduled_count,
            delayed_orders=delayed_count,
            overall_feasibility=feasibility,
        )
